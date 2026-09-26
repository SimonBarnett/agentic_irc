"""FR #230: account map + irc_listen --from-account filter."""
from __future__ import annotations

from pathlib import Path

import account_map as am
import irc_listen as listen


def test_select_account_caps_degrades():
    assert am.select_account_caps("sasl account-notify") == ["account-notify"]
    assert am.select_account_caps("sasl") == []
    assert am.select_account_caps(
        "sasl account-notify extended-join account-tag"
    ) == ["account-notify", "extended-join", "account-tag"]


def test_account_map_nick_change_and_quit():
    m = am.AccountMap()
    m.set("simon", "simon")
    assert m.get("simon") == "simon"
    m.rename("simon", "simon_")
    assert m.get("simon") is None
    assert m.get("simon_") == "simon"
    m.clear_nick("simon_")
    assert m.get("simon_") is None


def test_parse_message_tags_account():
    tags, rest = am.parse_message_tags(
        "@account=simon;msgid=abc :spoof!u@h PRIVMSG #ce-priority-dev1 :!bored"
    )
    assert tags.get("account") == "simon"
    assert rest.startswith(":spoof!")
    assert am.account_from_tags(tags) == "simon"


def test_listen_from_account_drops_spoof(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "accounts.json").write_text('{"simon":"simon"}\n', encoding="utf-8")
    accounts = listen.load_accounts(home)
    # Spoofed nick, no account tag, not in map under that nick
    out = listen.format_talk_line(
        ":evil!u@h PRIVMSG #ce-priority-dev1 :do bad",
        from_accounts={"simon"},
        accounts=accounts,
    )
    assert out is None
    # Correct nick with mapped account
    out2 = listen.format_talk_line(
        ":simon!u@h PRIVMSG #ce-priority-dev1 :hello",
        from_accounts={"simon"},
        accounts=accounts,
    )
    assert out2 == "FROM simon #ce-priority-dev1 hello"
    # Account tag without map entry
    out3 = listen.format_talk_line(
        "@account=simon :other!u@h PRIVMSG #ce-priority-dev1 :hi",
        from_accounts={"simon"},
        accounts={},
    )
    assert out3 == "FROM other #ce-priority-dev1 hi"
    # Filter on, no caps/account -> drop
    out4 = listen.format_talk_line(
        ":simon!u@h PRIVMSG #ce-priority-dev1 :hi",
        from_accounts={"simon"},
        accounts={},
    )
    assert out4 is None


def test_listen_default_unchanged_without_filter():
    out = listen.format_talk_line(":bob!u@h PRIVMSG #marchhare :hi")
    assert out == "FROM bob #marchhare hi"


def test_include_account_opt_in():
    out = listen.format_talk_line(
        "@account=simon :simon!u@h PRIVMSG #c :x",
        include_account=True,
    )
    assert out == "FROM simon #c account=simon x"
