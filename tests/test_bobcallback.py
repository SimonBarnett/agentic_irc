from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobcallback
import bobreport


def setup_function() -> None:
    bobreport.reset_dedupe()


def test_post_merge_no_get_digest(tmp_path):
    secret = "test-secret"
    allow = {"127.0.0.1"}
    body = json.dumps(
        {"op": "merge", "machine": "ionos", "pid": 884, "working_on": "callback", "kind": "cursor"}
    ).encode()
    code, payload = bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        {"X-Bob-Secret": secret},
        body,
        "127.0.0.1",
        tmp_path,
        secret,
        allow,
    )
    assert code == 204 and payload == b""
    doc = bobreport.load_digest(tmp_path)
    assert doc["machines"]["ionos"]["workers"]["884"]["working_on"] == "callback"
    code2, payload2 = bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        {"X-Bob-Secret": secret},
        body,
        "127.0.0.1",
        tmp_path,
        secret,
        allow,
    )
    assert code2 == 200 and payload2 == b""
    assert bobreport.load_digest(tmp_path)["machines"]["ionos"]["workers"]["884"]["working_on"] == "callback"

    for method, path, expect in (
        ("GET", "/", 404),
    ):
        code, payload = bobcallback.handle_request(
            method, path, {"X-Bob-Secret": secret}, b"", "127.0.0.1", tmp_path, secret, allow
        )
        assert code == expect
        assert payload == b""

    for path in ("/bob/v1/digest", "/digest", "/bob/v1/report"):
        code, payload = bobcallback.handle_request(
            "GET", path, {}, b"", "127.0.0.1", tmp_path, secret, allow
        )
        assert code == 200
        assert b"ionos" in payload
        parsed = json.loads(payload.decode("utf-8"))
        assert parsed["machines"]["ionos"]["workers"]["884"]["working_on"] == "callback"
        code_h, payload_h = bobcallback.handle_request(
            "HEAD", path, {}, b"", "127.0.0.1", tmp_path, secret, allow
        )
        assert code_h == 200 and payload_h == b""


def test_callback_auth_and_allowlist(tmp_path):
    secret = "test-secret"
    allow = {"127.0.0.1"}
    body = b'{"op":"shop-down","machine":"ionos"}'
    code, _ = bobcallback.handle_request(
        "POST", "/bob/v1/report", {}, body, "127.0.0.1", tmp_path, secret, allow
    )
    assert code == 401
    code, _ = bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        {"X-Bob-Secret": "wrong"},
        body,
        "127.0.0.1",
        tmp_path,
        secret,
        allow,
    )
    assert code == 401
    code, _ = bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        {"X-Bob-Secret": secret},
        body,
        "203.0.113.9",
        tmp_path,
        secret,
        allow,
    )
    assert code == 403
    code, _ = bobcallback.handle_request(
        "POST",
        "/bob/v1/report",
        {"X-Bob-Secret": secret},
        b"{not-json",
        "127.0.0.1",
        tmp_path,
        secret,
        allow,
    )
    assert code == 400


def test_serve_factory_has_public_get_digest(tmp_path):
    handler_cls = bobcallback.make_handler(tmp_path, "s", {"127.0.0.1"})
    assert hasattr(handler_cls, "do_GET")
    assert hasattr(handler_cls, "do_POST")
    src = Path(bobcallback.__file__).read_text(encoding="utf-8")
    assert "DIGEST_PATH" in src
    assert "handle_digest_get" in src
    assert "do_GET" in src
