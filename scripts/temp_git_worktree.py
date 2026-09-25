"""FR #213: MRB/FR checkout helper that never mutates a live service tree HEAD.

Workers must use `git worktree add <tmp> <ref>` (or a separate clone under the
seat work dir), then remove the worktree. Never `git checkout`, `stash`, or
`reset` inside D:\\ai\\agentic_irc (or any path marked as the service tree).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path


class LiveTreeMutationError(RuntimeError):
    """Raised when a caller tries to mutate a protected live service tree."""


def _git(cwd: Path, *args: str, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def live_tree_fingerprint(path: Path) -> dict[str, str]:
    """Branch + status + HEAD — used to prove the live tree was unchanged."""
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(path, "rev-parse", "HEAD")
    status = _git(path, "status", "--porcelain")
    return {
        "branch": (branch.stdout or "").strip(),
        "head": (head.stdout or "").strip(),
        "status": status.stdout or "",
    }


def is_protected_live_tree(path: Path | str) -> bool:
    """True for known fleet service checkouts or AGENTIC_IRC_SERVICE_TREE."""
    p = Path(path).resolve()
    env = (os.environ.get("AGENTIC_IRC_SERVICE_TREE") or "").strip()
    if env and p == Path(env).expanduser().resolve():
        return True
    # Common live trees on fleet boxes (never mutate these in place).
    names = {p.name.lower()}
    parents = {x.lower() for x in p.parts}
    if "agentic_irc" in names or "agentic_build" in names:
        # D:\ai\... or C:\ai\... style
        if "ai" in parents or str(p).lower().startswith(r"d:\ai") or str(p).lower().startswith(r"c:\ai"):
            return True
    flag = p / ".agentic-irc-live-service"
    return flag.is_file()


def assert_not_live_mutation(path: Path | str, action: str) -> None:
    if is_protected_live_tree(path):
        raise LiveTreeMutationError(
            f"refusing {action} in live service tree {Path(path).resolve()} "
            f"(FR #213: use temp worktree)"
        )


@dataclass
class TempWorktree:
    """Isolated worktree for MRB/FR; remove() leaves the live tree untouched."""

    live_root: Path
    path: Path
    branch_or_ref: str
    before: dict[str, str]
    _removed: bool = False

    def fingerprint_live(self) -> dict[str, str]:
        return live_tree_fingerprint(self.live_root)

    def live_unchanged(self) -> bool:
        return self.fingerprint_live() == self.before

    def remove(self) -> None:
        if self._removed:
            return
        # Prefer git worktree remove; fall back to rmtree + prune.
        r = _git(self.live_root, "worktree", "remove", "--force", str(self.path))
        if r.returncode != 0 and self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
            _git(self.live_root, "worktree", "prune")
        self._removed = True


def add_temp_worktree(
    live_root: Path | str,
    ref: str,
    *,
    base_dir: Path | str | None = None,
    prefix: str = "mrb-fr-",
) -> TempWorktree:
    """Add a detached worktree under TEMP (or base_dir). Never checks out live_root."""
    root = Path(live_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"live_root missing: {root}")
    # Safety: if someone passes a path that *is* the destination of mutation,
    # we only *add* a sibling worktree — we still fingerprint and never checkout root.
    before = live_tree_fingerprint(root)
    parent = Path(base_dir) if base_dir else Path(tempfile.gettempdir())
    parent.mkdir(parents=True, exist_ok=True)
    dest = parent / f"{prefix}{os.getpid()}-{uuid.uuid4().hex[:8]}"
    if dest.exists():
        dest = parent / f"{prefix}{os.getpid()}-{time.time_ns()}"
    # Fetch is caller's job; we only attach to an existing ref.
    r = _git(root, "worktree", "add", "--detach", str(dest), ref)
    if r.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed: {(r.stderr or r.stdout or '').strip()}"
        )
    after = live_tree_fingerprint(root)
    if after != before:
        # Roll back the worktree if somehow live moved (should not happen).
        _git(root, "worktree", "remove", "--force", str(dest))
        raise LiveTreeMutationError(
            f"live tree changed during worktree add: before={before} after={after}"
        )
    return TempWorktree(live_root=root, path=dest, branch_or_ref=ref, before=before)


def run_mrb_checkout_flow(
    live_root: Path | str,
    ref: str,
    *,
    base_dir: Path | str | None = None,
    work_fn=None,
) -> dict[str, object]:
    """Canonical MRB path: worktree → optional work_fn(path) → remove; prove live unchanged."""
    tw = add_temp_worktree(live_root, ref, base_dir=base_dir)
    result: dict[str, object] = {
        "worktree": str(tw.path),
        "ref": ref,
        "before": dict(tw.before),
    }
    try:
        if work_fn is not None:
            result["work_result"] = work_fn(tw.path)
        result["worktree_head"] = (_git(tw.path, "rev-parse", "HEAD").stdout or "").strip()
    finally:
        tw.remove()
    after = live_tree_fingerprint(Path(live_root).resolve())
    result["after"] = after
    result["live_unchanged"] = after == tw.before
    if not result["live_unchanged"]:
        raise LiveTreeMutationError(
            f"MRB flow mutated live tree: before={tw.before} after={after}"
        )
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    p = argparse.ArgumentParser(description="FR #213 temp git worktree for MRB/FR")
    p.add_argument("--live-root", required=True)
    p.add_argument("--ref", required=True)
    p.add_argument("--base-dir", default="")
    p.add_argument("--keep", action="store_true", help="do not remove (debug)")
    args = p.parse_args(argv)
    tw = add_temp_worktree(args.live_root, args.ref, base_dir=args.base_dir or None)
    print(json.dumps({"worktree": str(tw.path), "before": tw.before}))
    if not args.keep:
        tw.remove()
        after = live_tree_fingerprint(Path(args.live_root).resolve())
        print(json.dumps({"after": after, "live_unchanged": after == tw.before}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
