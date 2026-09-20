from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import beacon
import moot_thin_proto as thin

JID = "0123456789abcdef"
PAIR = "aabbccddeeff0011"
PIN = "482917"


def _inv(**kw):
    now = kw.pop("now", 1_700_000_000)
    return beacon.make_invite(
        channel=kw.pop("channel", "#ops"),
        moot=kw.pop("moot", JID),
        pin=kw.pop("pin", PIN),
        pair=kw.pop("pair", PAIR),
        chair=kw.pop("chair", "cm-bob"),
        host=kw.pop("host", "irc.example.test"),
        now=now,
        **kw,
    )


def test_json_and_ini_roundtrip():
    inv = _inv()
    a = beacon.parse_invite(beacon.dumps_json(inv))
    b = beacon.parse_invite(beacon.dumps_ini(inv))
    assert a == b
    assert a.channel == "#ops"
    assert a.pin == PIN
    assert a.moot == JID
    assert a.pair == PAIR
    assert "psk" not in beacon.dumps_json(inv).lower()
    assert "connector.key" not in beacon.dumps_ini(inv).lower()


def test_expired_refused():
    inv = _inv(ttl_s=10, now=1_000)
    assert beacon.expired(inv, now=1_011)
    assert not beacon.expired(inv, now=1_009)
    with pytest.raises(ValueError, match="expired"):
        beacon.apply_invite(thin.ThinConfig(), inv, now=1_011)


def test_apply_fills_pairing_and_skips_prompt_fields():
    cfg = thin.ThinConfig(nick="walrus")
    beacon.apply_invite(cfg, _inv(), now=1_700_000_000)
    thin.self_heal(cfg, exe_dir="/tmp/airc", hostname="WALRUS")
    assert cfg.channel == "#ops"
    assert cfg.moot_id == JID
    assert cfg.pin == PIN
    assert cfg.pairing is True
    assert cfg.host == "irc.example.test"
    thin.validate_config(cfg)


def test_bad_kind_and_pin():
    with pytest.raises(ValueError, match="airc-invite"):
        beacon.parse_invite(json.dumps({"v": 1, "kind": "nope"}))
    inv = _inv().as_dict()
    inv["pin"] = "12"
    with pytest.raises(ValueError, match="pin"):
        beacon.parse_invite(json.dumps(inv))


def test_https_only_url():
    with pytest.raises(ValueError, match="https"):
        beacon.fetch_text("http://example.com/airc-invite.json")


def test_beacon_url_file(tmp_path: Path):
    f = tmp_path / "beacon.url"
    f.write_text("https://gist.githubusercontent.com/x/y/raw/airc-invite.json\n", encoding="utf-8")
    assert beacon.load_beacon_url_file(f).startswith("https://")
    f.write_text("http://insecure.example/\n", encoding="utf-8")
    with pytest.raises(ValueError, match="https"):
        beacon.load_beacon_url_file(f)


def test_write_pack(tmp_path: Path):
    paths = beacon.write_pack(_inv(), tmp_path)
    names = {p.name for p in paths}
    assert names == {"airc-invite.json", "airc-invite.ini"}
    got = beacon.resolve_invite(path=tmp_path / "airc-invite.json", now=1_700_000_000)
    assert got.pin == PIN


def test_double_click_story_local_file(tmp_path: Path):
    """USB / folder copy: agent writes invite beside the exe; thin loads it."""
    beacon.write_pack(_inv(ttl_s=600, now=int(time.time())), tmp_path)
    inv = beacon.resolve_invite(path=tmp_path / "airc-invite.ini")
    cfg = thin.merge_self_heal(None, None, exe_dir=str(tmp_path), hostname="WALRUS")
    beacon.apply_invite(cfg, inv)
    thin.validate_config(cfg)
    assert cfg.nick == "walrus"
    assert cfg.home == str(tmp_path)
    assert cfg.pin == PIN
