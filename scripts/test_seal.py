#!/usr/bin/env python3
"""Round-trip seal/open without touching ~/.agentic-irc."""
from pathlib import Path
import os
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import seal


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        os.environ["AGENTIC_IRC_HOME"] = td
        a = seal.genkey(Path(td) / "identity.json")
        # second identity in another dir
        os.environ["AGENTIC_IRC_HOME"] = td + "-b"
        Path(td + "-b").mkdir(exist_ok=True)
        b = seal.genkey(Path(td + "-b") / "identity.json")
        blob = seal.seal_bytes(b"MEDIA_WORKER_SECRET=test-only\n", b["pk"])
        os.environ["AGENTIC_IRC_HOME"] = td + "-b"
        pt = seal.open_bytes(blob, b)
        assert pt == b"MEDIA_WORKER_SECRET=test-only\n", pt
        lines = seal.irc_lines(blob, "grok-b")
        assert lines[0].startswith("SEAL v1 grok-b ")
        parsed = seal.parse_seal_line(lines[0])
        assert parsed is not None
        print("ok", len(lines), "line(s)", "agpk_len", len(a["pk"]))


if __name__ == "__main__":
    main()
