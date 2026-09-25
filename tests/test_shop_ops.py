from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import shop_ops  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_bob_kicks_on_own_shop_only():
    assert shop_ops.raw_op_line("KICK #marchhare w-mh-41124 :leak", "bob-marchhare") == (
        "KICK #marchhare w-mh-41124 :leak"
    )
    assert shop_ops.raw_op_line("KICK #flamingo w-fl-1 :x", "bob-marchhare") is None
    assert shop_ops.raw_op_line("KICK #bobiverse w-mh-1 :x", "bob-marchhare") is None


def test_non_bob_nicks_get_no_raw_ops():
    for nick in ("marchhare-34992", "w-mh-41124", "simon", "Jeeves"):
        assert shop_ops.raw_op_line("KICK #marchhare w-mh-41124", nick) is None


def test_never_kick_self_jeeves_or_bobs():
    for victim in ("bob-marchhare", "Jeeves", "bob-ionos"):
        assert shop_ops.raw_op_line(f"KICK #marchhare {victim}", "bob-marchhare") is None


def test_kick_default_reason_and_mode_names():
    k = shop_ops.raw_op_line("KICK #marchhare w-mh-9", "bob-marchhare")
    assert k and k.startswith("KICK #marchhare w-mh-9 :invalid worker")
    assert shop_ops.raw_op_line("MODE #marchhare +o bob-marchhare", "bob-marchhare") == (
        "MODE #marchhare +o bob-marchhare"
    )
    assert shop_ops.raw_op_line("MODE #marchhare +b *!*@*", "bob-marchhare") is None
    assert shop_ops.raw_op_line("NAMES #marchhare", "bob-marchhare") == "NAMES #marchhare"
    assert shop_ops.raw_op_line("hello MODE #marchhare +o x", "bob-marchhare") is None


def test_invalid_workers_dead_pid_local_only():
    members = ["Jeeves", "simon", "@bob-marchhare", "marchhare-34992", "w-mh-41124", "w-fl-5", "flamingo-7"]
    live = {34992}
    bad = shop_ops.invalid_shop_workers(members, "marchhare", alive=lambda p: p in live)
    assert bad == ["w-mh-41124"]


def test_members_from_log_replay():
    lines = [
        ":irc 353 bob-marchhare = #marchhare :Jeeves simon @bob-marchhare",
        ":marchhare-34992!~u@h JOIN #marchhare",
        ":w-mh-41124!~u@h JOIN #marchhare",
        ":w-mh-6288!~u@h JOIN #marchhare",
        ":w-mh-6288!~u@h QUIT :bye",
        ":simon!~u@h PART #marchhare :x",
        ":simon!~u@h JOIN :#marchhare",
        ":x!~u@h JOIN #bobiverse",
    ]
    mem = shop_ops.members_from_log(lines, "#marchhare")
    assert mem == {"Jeeves", "simon", "bob-marchhare", "marchhare-34992", "w-mh-41124"}


def test_irc_agent_sends_shop_ops_raw_and_logs_482():
    src = (ROOT / "scripts" / "irc_agent.py").read_text(encoding="utf-8")
    assert "shop_ops.raw_op_line(line, self.original_nick)" in src
    assert 'cmd == "482"' in src and "INFO shop-op 482" in src


def test_cli_dry_run(tmp_path: Path, capsys):
    (tmp_path / "irc.log").write_text(
        ":irc 353 bob-marchhare = #marchhare :Jeeves bob-marchhare w-mh-1\n", encoding="utf-8"
    )
    rc = shop_ops.main(["kick-invalid", "--home", str(tmp_path), "--nick", "bob-marchhare", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "invalid: w-mh-1" in out and "DRY KICK #marchhare w-mh-1" in out
    assert not (tmp_path / "outbox.txt").exists()

def test_mrb_reason_sanitized_and_mode_v():
    k = shop_ops.raw_op_line("KICK #marchhare w-mh-1 :bad\r\nline", "bob-marchhare")
    assert k and "\r" not in k and "\n" not in k
    assert shop_ops.raw_op_line("MODE #marchhare +v w-mh-1", "bob-marchhare") == "MODE #marchhare +v w-mh-1"
    assert shop_ops.raw_op_line("MODE #marchhare -o simon", "bob-marchhare") == "MODE #marchhare -o simon"
    assert shop_ops.raw_op_line("MODE #bobiverse +o bob-marchhare", "bob-marchhare") is None


def test_mrb_dead_talk_seat_is_invalid():
    members = ["@bob-marchhare", "marchhare-34992", "w-mh-41124", "simon"]
    bad = shop_ops.invalid_shop_workers(members, "marchhare", alive=lambda p: False)
    assert set(bad) == {"marchhare-34992", "w-mh-41124"}


def test_mrb_members_kick_and_nick_change():
    lines = [
        ":irc 353 bob-marchhare = #marchhare :@bob-marchhare w-mh-1 w-mh-2",
        ":bob-marchhare!b@h KICK #marchhare w-mh-1 :gone",
        ":w-mh-2!~u@h NICK :w-mh-9",
    ]
    mem = shop_ops.members_from_log(lines, "#marchhare")
    assert "w-mh-1" not in mem
    assert "w-mh-9" in mem and "w-mh-2" not in mem


def test_mrb_bob_l_suffix_and_cli_non_bob(tmp_path, capsys):
    assert shop_ops.own_shop("bob-marchhare_l") == "#marchhare"
    rc = shop_ops.main(["names", "--home", str(tmp_path), "--nick", "simon", "--dry-run"])
    assert rc == 2
    assert "bob-*" in capsys.readouterr().err
