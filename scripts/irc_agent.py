#!/usr/bin/env python3
"""TLS IRC agent: reconnect, SASL from env, flood delay, AGPK TOFU, SEAL v2 inbox.

Stdout is INFO only (no raw IRC, no AGPK/SEAL bodies). Full lines go to irc.log if
AGENTIC_IRC_DEBUG=1. SASL: AGENTIC_IRC_SASL_USER + AGENTIC_IRC_SASL_PASSWORD (not argv).
"""
from __future__ import annotations

import argparse
import base64
import os
import random
import socket
import ssl
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bobreport  # noqa: E402
import bobstat  # noqa: E402
import bobtalk  # noqa: E402
import grok_talk  # noqa: E402
import filexfer  # noqa: E402
import moot  # noqa: E402
import protect  # noqa: E402
import seal  # noqa: E402
import talk_seat_pid  # noqa: E402
import wire  # noqa: E402

FLOOD_S = 0.8
REG_FAIL_CMDS = frozenset(
    {
        "ERROR",
        "464",
        "465",
        "471",
        "472",
        "473",
        "474",
        "475",
        "477",
        "478",
        "481",
        "482",
        "483",
        "484",
        "485",
        "486",
        "487",
        "488",
        "489",
        "490",
        "491",
        "492",
        "493",
        "494",
        "495",
        "496",
        "497",
        "498",
        "499",
    }
)


def take_outbox_lines(path: Path, last: int) -> tuple[list[str], int]:
    """Complete newline-terminated outbox lines from byte offset `last`.

    A poll that lands mid-write must not send a truncated SEAL/FILE line
    (mode-2 flake: first OFFER seen, no DONE). Partial tail stays unconsumed.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return [], last
    if last > len(data):
        last = 0
    buf = data[last:]
    lines: list[str] = []
    consumed = 0
    while True:
        nl = buf.find(b"\n", consumed)
        if nl < 0:
            break
        raw = buf[consumed:nl].rstrip(b"\r")
        text = raw.decode("utf-8", "replace").strip()
        if text:
            lines.append(text)
        consumed = nl + 1
    return lines, last + consumed


def outbox_pos_path(outbox: Path) -> Path:
    return Path(str(outbox) + ".pos")


def load_outbox_pos(outbox: Path) -> int:
    """Byte offset of last successfully drained complete line. Missing → 0 (restart sends JOIN)."""
    p = outbox_pos_path(outbox)
    if not p.exists():
        return 0
    try:
        n = int(p.read_text(encoding="utf-8").strip() or "0")
    except (ValueError, OSError):
        return 0
    return n if n >= 0 else 0


def save_outbox_pos(outbox: Path, pos: int) -> None:
    outbox_pos_path(outbox).write_text(str(int(pos)) + "\n", encoding="utf-8")


def info(msg: str) -> None:
    print(msg, flush=True)


def reconnect_cap() -> int | None:
    """Max reconnect cycles after a failed session; None = unlimited."""
    raw = (os.environ.get("AGENTIC_IRC_RECONNECT_MAX") or "").strip()
    if not raw:
        return None
    try:
        n = int(raw)
    except ValueError:
        return None
    return n if n >= 0 else None


def debug_log(path: Path | None, line: str) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


class Client:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.original_nick = args.nick
        self.live_nick = args.nick
        if getattr(args, "chair", False):
            self.channels = [bobreport.FLEET_CHANNEL]
        else:
            self.channels = bobreport.channels_for_nick(args.nick, args.channel)
        if not self.channels:
            chan = args.channel if str(args.channel).startswith("#") else "#" + str(args.channel)
            if "|" in chan:
                raise ValueError("channel must not contain |")
            self.channels = [chan]
        self.chan = self.channels[0]
        self._pending_joins: set[str] = {c.lower() for c in self.channels}
        if args.home:
            os.environ["AGENTIC_IRC_HOME"] = str(Path(args.home).expanduser())
        self.home = seal.home()
        self.home.mkdir(parents=True, exist_ok=True)
        protect.protect_path(self.home)
        if getattr(args, "chair", False):
            bobreport.persist_chair_nick(self.home, args.nick)
        self.outbox = Path(args.outbox) if args.outbox else self.home / "outbox.txt"
        self.inbox = self.home / "inbox"
        self.inbox.mkdir(parents=True, exist_ok=True)
        protect.protect_path(self.inbox)
        self.debug = self.home / "irc.log" if os.environ.get("AGENTIC_IRC_DEBUG") else None
        self.ident = seal.load_ident() if seal.ident_path().exists() else None
        self.peers = seal.load_peers()
        self.fragments = seal.FragmentStore()
        self._moot: dict = {}
        self.file_bags = filexfer.FileBag()
        self.lock = threading.Lock()
        self.sock: ssl.SSLSocket | None = None
        self._outbox_gen = 0
        self.ready = threading.Event()
        self.joined = threading.Event()
        self.dead = threading.Event()
        self.stop = threading.Event()
        self.sasl_ack = threading.Event()
        self.sasl_plus = threading.Event()
        self.sasl_903 = threading.Event()
        self.sasl_fail = threading.Event()
        self._bobiverse_last_query: dict[str, float] = {}
        self._bobiverse_last_tray: dict[str, float] = {}
        self._report_gone_told: set[str] = set()
        self._pm_open: dict[str, float] = {}
        self._action_last: dict[tuple[str, str], float] = {}
        self._mention_last: dict[str, float] = {}
        self._grok_talk_dedup: dict[tuple[str, str], float] = {}

    def send(self, line: str) -> None:
        assert self.sock is not None
        with self.lock:
            self.sock.sendall((line + "\r\n").encode("utf-8"))

    def say(self, msg: str) -> None:
        self.send("PRIVMSG " + self.chan + " :" + msg)
        time.sleep(FLOOD_S)

    def _joined_channel(self, target: str) -> bool:
        t = bobreport.normalize_channel(target).lower()
        return t in {c.lower() for c in self.channels}

    def _shop_channel(self) -> str | None:
        worker = bobreport.parse_worker_nick(self.original_nick)
        if worker:
            return bobreport.shop_channel(worker[0])
        mid = bobreport.machine_from_nick(self.original_nick)
        if mid:
            return bobreport.shop_channel(mid)
        return None

    def whisper(self, nick: str, msg: str) -> None:
        target = (nick or "").strip()
        if not target or "|" in target:
            return
        self.send("PRIVMSG " + target + " :" + msg)
        time.sleep(FLOOD_S)

    def _mine_nicks(self) -> set[str]:
        return {self.original_nick.lower(), self.live_nick.lower()}

    def _fleet_moot_state(self) -> dict:
        disk = moot.load_state(self.home, bobtalk.FLEET_MOOT_ID)
        if disk.get("id") == bobtalk.FLEET_MOOT_ID:
            return disk
        if self._moot.get("id") == bobtalk.FLEET_MOOT_ID:
            return self._moot
        return disk or self._moot or {}

    def _online_bob_nicks(self) -> set[str]:
        doc = bobreport.load_digest(self.home)
        machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
        out: set[str] = set()
        for ent in machines.values():
            if isinstance(ent, dict) and ent.get("online"):
                nick = str(ent.get("nick") or "").strip()
                if nick.lower().startswith("bob-"):
                    out.add(nick.lower())
        return out

    def _is_briefer(self) -> bool:
        return bobtalk.is_briefer(self._fleet_moot_state(), self.live_nick, self._online_bob_nicks())

    def _is_digest_operator(self) -> bool:
        return bobtalk.is_digest_operator(
            self._fleet_moot_state(), self.live_nick, self._online_bob_nicks(), self.home
        )

    def _deliver_whispers(self, nick: str, lines: list[str]) -> None:
        for line in lines:
            if line:
                self.whisper(nick, line)

    def _fleet_joiner(self, nick: str) -> bool:
        return (nick or "").strip().lower().startswith("bob-")

    def _maybe_brief_joiner(self, nick: str) -> None:
        joiner = (nick or "").strip()
        if not joiner or joiner.lower() in self._mine_nicks():
            return
        if not self._fleet_joiner(joiner):
            return
        if not bobtalk.fleet_status_to_channel_enabled(self.home):
            return
        if not self._is_briefer():
            return
        lines = bobtalk.network_talk_lines(self.home)
        self._deliver_whispers(joiner, lines)
        info(f"INFO bobiverse brief to={joiner} lines={len(lines)}")

    def _handle_report(self, sender: str, _on_channel: bool, body: str) -> None:
        who = (sender or "").strip()
        if not who or not self._is_digest_operator():
            return
        if bobreport.looks_like_secret(body):
            return
        key = who.lower()
        if key in self._report_gone_told:
            return
        self._report_gone_told.add(key)
        self.whisper(who, bobreport.REPORT_GONE)

    def _fleet_action(self, event_class: str, key: str, text: str) -> None:
        if not bobtalk.fleet_status_to_channel_enabled(self.home):
            return
        if not self._is_digest_operator() or not text:
            return
        if bobreport.looks_like_secret(text):
            return
        now = time.time()
        stamp = (event_class, key)
        last = self._action_last.get(stamp, 0.0)
        if now - last < bobreport.ACTION_COOLDOWN_S:
            return
        self._action_last[stamp] = now
        self.send("PRIVMSG " + bobreport.FLEET_CHANNEL + " :\x01ACTION " + text + "\x01")
        time.sleep(FLOOD_S)

    def _emit_presence(self, outcome: bobreport.PresenceOutcome, event_class: str, key: str) -> None:
        if not bobtalk.fleet_status_to_channel_enabled(self.home):
            return
        for action in outcome.actions:
            self._fleet_action(event_class, key, action)

    def handle_join(self, nick: str, channel: str) -> None:
        who = (nick or "").strip()
        ch = bobreport.normalize_channel(channel)
        if who.lower() in self._mine_nicks():
            self._pending_joins.discard(ch.lower())
            if not self._pending_joins:
                self.joined.set()
        if who and who.lower() not in self._mine_nicks() and ch.lower() == bobreport.FLEET_CHANNEL:
            self._maybe_brief_joiner(who)
        if not self._is_digest_operator():
            return
        briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick
        out = bobreport.apply_join(self.home, who, ch, briefer)
        self._emit_presence(out, "join", f"{who}:{ch}")

    def handle_part(self, nick: str, channel: str) -> None:
        who = (nick or "").strip()
        ch = bobreport.normalize_channel(channel)
        self._maybe_local_shop_closed(who)
        if not self._is_digest_operator():
            return
        briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick
        out = bobreport.apply_part(self.home, who, ch, briefer)
        klass = "shop-down" if out.shop_closed else "drop"
        self._emit_presence(out, klass, f"{who}:{ch}")

    def handle_quit(self, nick: str) -> None:
        who = (nick or "").strip()
        self._maybe_local_shop_closed(who)
        if not self._is_digest_operator():
            return
        briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick
        out = bobreport.apply_quit(self.home, who, briefer)
        klass = "shop-down" if out.shop_closed else "drop"
        self._emit_presence(out, klass, who)

    def _maybe_local_shop_closed(self, departed: str) -> None:
        mid = bobreport.machine_from_nick(departed)
        mine = bobreport.parse_worker_nick(self.original_nick)
        if not mid or not mine or mine[0] != mid:
            return
        shop = bobreport.shop_channel(mid)
        for nick in list(self._pm_open):
            try:
                self.whisper(nick, "shop closed")
            except Exception:
                pass
        try:
            self.send("PART " + shop + " :shop closed")
            self.send("QUIT :shop closed")
        except Exception:
            pass
        self.stop.set()

    def _digest_home(self) -> Path:
        return bobreport.fleet_digest_home(self.home)

    def _cc_working_on(self, text: str) -> None:
        worker = bobreport.parse_worker_nick(self.original_nick)
        if not worker:
            return
        mid, pid = worker
        raw = (text or "").strip()
        if not raw:
            return
        out = bobreport.merge_worker_working_on(self._digest_home(), mid, pid, raw)
        if not out.ok or not out.actions:
            return
        shop = self._shop_channel()
        if not shop or shop.lower() == bobreport.FLEET_CHANNEL:
            return
        nick = self.live_nick or self.original_nick
        line = bobreport.working_on_shop_line(nick, raw)
        for piece in bobreport.split_irc_text(line):
            self.send("PRIVMSG " + shop + " :" + piece)
            time.sleep(FLOOD_S)

    def apply_digest_callback(self, payload: dict) -> None:
        if not self._is_digest_operator():
            return
        briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick
        out = bobreport.apply_callback(self.home, payload, briefer)
        if not out.ok or not out.actions:
            return
        actions = out.actions
        pid_raw = payload.get("pid")
        mid = bobreport.normalize_machine_id(str(payload.get("machine") or payload.get("id") or ""))
        key = f"{mid}:{pid_raw}" if mid and pid_raw is not None else str(mid or "merge")
        out = bobreport.PresenceOutcome(ok=True, actions=actions, machine_id=mid)
        self._emit_presence(out, "working_on", key)

    def cc_send(self, kind: str, text: str) -> None:
        k = (kind or "").strip().lower().replace("-", "_")
        if k == "working_on":
            self._cc_working_on(text)
            return
        pieces = bobreport.split_irc_text(text)
        dests = bobreport.route_cc(kind, bool(self._pm_open))
        shop = self._shop_channel()
        for piece in pieces:
            if bobreport.CC_SHOP in dests and shop and shop.lower() != bobreport.FLEET_CHANNEL:
                self.send("PRIVMSG " + shop + " :" + piece)
                time.sleep(FLOOD_S)
            if bobreport.CC_QUERY in dests:
                for nick in list(self._pm_open):
                    self.whisper(nick, piece)

    def _mark_pm_open(self, nick: str) -> None:
        n = (nick or "").strip()
        if not n or n.lower() in self._mine_nicks():
            return
        if n.lower().startswith("bob-") or bobreport.parse_worker_nick(n):
            return
        self._pm_open[n.lower()] = time.time()

    def _answer_bobiverse(self, asker: str, body: str) -> bool:
        who = (asker or "").strip()
        if not who or who.lower() in self._mine_nicks():
            return True
        if not self._is_digest_operator():
            return True
        parsed = bobreport.parse_bobiverse_query(body)
        if not parsed:
            return True
        form, machine_id = parsed
        now = time.time()
        key = who.lower()
        tray = bobtalk.is_tray_asker(who)
        cooldown = bobtalk.BOBIVERSE_AGENT_COOLDOWN_S if tray else bobtalk.BOBIVERSE_COOLDOWN_S
        last_map = self._bobiverse_last_tray if tray else self._bobiverse_last_query
        last = last_map.get(key, 0.0)
        if now - last < cooldown:
            return True
        last_map[key] = now
        briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick
        lines = bobreport.format_digest_whisper_lines(
            self.home, briefer, form=form, machine_id=machine_id, english=not tray
        )
        self._deliver_whispers(who, lines)
        info(f"INFO bobiverse digest to={who} form={form} lines={len(lines)}")
        return True

    def _maybe_mention_reply(self, src: str, target: str, body: str, to_channel: bool, to_me: bool) -> bool:
        """ACK when a human/worker addresses this bob-* nick. No grok.exe."""
        if getattr(self.args, "chair", False):
            return False
        if not bobtalk.is_fleet_bob_nick(self.original_nick):
            return False
        nicks = [self.live_nick, self.original_nick]
        mid = bobreport.machine_from_nick(self.original_nick) or self.original_nick
        line = bobtalk.mention_reply_line(self.home, mid, nicks, src, body, to_me=to_me)
        if not line:
            return False
        if bobreport.looks_like_secret(body) or bobreport.looks_like_secret(line):
            return False
        key = (src or "").strip().lower()
        now = time.time()
        last = self._mention_last.get(key, 0.0)
        if now - last < bobtalk.MENTION_COOLDOWN_S:
            return True
        self._mention_last[key] = now
        if to_channel:
            dest = bobreport.normalize_channel(target) or self.chan
            self.send("PRIVMSG " + dest + " :" + line)
            time.sleep(FLOOD_S)
        else:
            self.whisper(src, line)
        info(f"INFO mention-ack to={src} dest={'chan' if to_channel else 'pm'}")
        grok_talk.enqueue_mention(
            self.home,
            mid,
            self.live_nick,
            nicks,
            src,
            target,
            body,
            to_me=to_me,
            to_channel=to_channel,
            dedupe_last=self._grok_talk_dedup,
        )
        return True

    def connect(self) -> ssl.SSLSocket:
        ctx = ssl.create_default_context()
        raw = socket.create_connection((self.args.host, self.args.port), 20)
        raw.settimeout(None)
        sock = ctx.wrap_socket(raw, server_hostname=self.args.host)
        sock.settimeout(None)
        return sock

    def sasl_token(self) -> str | None:
        user = os.environ.get("AGENTIC_IRC_SASL_USER")
        pw = os.environ.get("AGENTIC_IRC_SASL_PASSWORD")
        if not user or not pw:
            return None
        return base64.b64encode(b"\0" + user.encode("utf-8") + b"\0" + pw.encode("utf-8")).decode("ascii")

    def sasl_on_line(self, cmd: str, args: list[str], trailing: str) -> list[str]:
        """Advance SASL. Returns lines to send. No network."""
        out: list[str] = []
        tokens = [a.lower() for a in args] + trailing.lower().split()
        if cmd == "CAP" and "ack" in tokens and "sasl" in tokens:
            self.sasl_ack.set()
            out.append("AUTHENTICATE PLAIN")
        if cmd == "AUTHENTICATE" and trailing.strip() == "+":
            self.sasl_plus.set()
            tok = self.sasl_token()
            if tok:
                out.append("AUTHENTICATE " + tok)
        if cmd == "903":
            self.sasl_903.set()
            out.append("CAP END")
        if cmd in ("902", "904", "905", "906", "907"):
            self.sasl_fail.set()
            out.append("CAP END")
        return out

    def sasl_plain(self) -> None:
        if not self.sasl_token():
            info("INFO no-sasl")
            self.send("CAP END")
            return
        self.sasl_ack.clear()
        self.sasl_plus.clear()
        self.sasl_903.clear()
        self.sasl_fail.clear()
        self.send("CAP REQ :sasl")
        if not self.sasl_ack.wait(10):
            info("INFO no-sasl")
            self.send("CAP END")
            return
        if not self.sasl_plus.wait(10):
            info("INFO no-sasl")
            self.send("CAP END")
            return
        if self.sasl_fail.wait(0.01):
            info("INFO no-sasl")
            return
        if not self.sasl_903.wait(10):
            info("INFO no-sasl")
            self.send("CAP END")
            return

    def handle_capa(self, src: str, body: str) -> None:
        p = wire.parse_capa_line(body)
        if p:
            info(f"INFO capa from={src}")

    def handle_moot(self, src: str, body: str) -> None:
        ml = wire.parse_moot_line(body)
        if not ml:
            return
        # IRC does not echo own PRIVMSG. Chair OPEN/FLOOR/CLOSE live on disk via CLI;
        # incoming JOIN/SAY/YIELD must load that snapshot or roster stays {chair}.
        disk = moot.load_state(self.home, ml.moot_id)
        if disk.get("id") == ml.moot_id:
            base = disk
        elif self._moot.get("id") == ml.moot_id:
            base = self._moot
        else:
            base = {}
        self._moot = moot.apply_moot(base, src, ml, self.home)
        if ml.verb == "OPEN":
            info(f"INFO moot OPEN id={ml.moot_id} chair={src}")
        elif ml.verb == "JOIN":
            info(f"INFO moot JOIN id={ml.moot_id} nick={src}")
            if ml.moot_id == bobtalk.FLEET_MOOT_ID:
                self._maybe_brief_joiner(src)
        elif ml.verb == "POINT" and (ml.text or "").startswith("BOB v1"):
            doc = bobstat.parse_bob_point(ml.text)
            if doc:
                bobstat.write_peer(self.home, doc)
                info(f"INFO bobstat id={doc['id']} from={src}")

    def handle_file(self, src: str, body: str) -> None:
        fl = wire.parse_file_line(body)
        if not fl:
            return
        if fl.verb == "OFFER":
            name = fl.fields[-1] if fl.fields else ""
            nbytes = fl.fields[3] if len(fl.fields) > 3 else ""
            sha = fl.fields[4] if len(fl.fields) > 4 else ""
            tier = fl.fields[5] if len(fl.fields) > 5 else ""
            if not fl.file_id:
                return
            if not self.file_bags.note_offer(src, fl.file_id, name, sha, nbytes, tier):
                info(f"INFO file OFFER id={fl.file_id} ignored (duplicate)")
                return
            info(f"INFO file OFFER id={fl.file_id} name={name} bytes={nbytes}")
            extra = 0
            try:
                extra = int(nbytes or 0)
            except (TypeError, ValueError):
                extra = 0
            if filexfer.would_exceed_cap(self.home, extra=extra):
                self._file_outbox(f"FILE v1 REFUSE {fl.file_id} :disk")
            else:
                self._file_outbox(f"FILE v1 ACCEPT {fl.file_id}")
        if fl.verb == "CHUNK" and fl.chunk_b64 and fl.i and fl.n and fl.file_id:
            data = self.file_bags.add_chunk(src, fl.file_id, fl.i, fl.n, fl.chunk_b64)
            if data is not None:
                pending = self.file_bags.take_pending_done(fl.file_id)
                if pending is not None:
                    self._finish_file(fl.file_id, pending, self.file_bags.take_assembled(fl.file_id) or data)
        if fl.verb == "ABORT" and fl.file_id:
            self.file_bags.abort(fl.file_id)
            info(f"INFO file ABORT id={fl.file_id}")
        if fl.verb == "DONE" and fl.file_id:
            sha = fl.fields[1] if len(fl.fields) > 1 else ""
            data = self.file_bags.peek_assembled(fl.file_id)
            if data is None:
                self.file_bags.note_done(fl.file_id, sha)
                info(f"INFO file DONE id={fl.file_id} wait (incomplete)")
                return
            self._finish_file(fl.file_id, sha, self.file_bags.take_assembled(fl.file_id))

    def _file_outbox(self, line: str) -> None:
        with self.outbox.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _finish_file(self, fid: str, sha: str, data: bytes | None) -> None:
        if data is None:
            info(f"INFO file DONE id={fid} fail (incomplete)")
            return
        offer = self.file_bags._offers.get(fid.lower(), {})
        name = offer.get("name") or "file.bin"
        expect = offer.get("sha") or sha
        if filexfer.complete_write(self.home, fid, name, data, expect):
            info(f"INFO file DONE id={fid} ok")
        else:
            info(f"INFO file DONE id={fid} fail")

    def handle_dumb(self, src: str, body: str) -> None:
        dl = wire.parse_dumb_line(body)
        if not dl:
            return
        if dl.from_nick and dl.from_nick.lower() != src.lower():
            info("INFO DUMB prefix != from_nick, drop")
            return
        info(f"INFO dumb job id={dl.msg_id} from={src}")

    def handle_privmsg(self, prefix: str, target: str, body: str) -> None:
        src = prefix.split("!", 1)[0].lstrip(":")
        tgt_l = target.lower()
        to_channel = self._joined_channel(target)
        to_me = tgt_l in self._mine_nicks()
        if not to_channel and not to_me:
            return
        if to_me:
            self._mark_pm_open(src)
        if bobtalk.parse_bobiverse_command(body):
            self._answer_bobiverse(src, body)
            return
        if bobreport.parse_report_command(body):
            self._handle_report(src, to_channel, body)
            return
        if not to_channel:
            self._maybe_mention_reply(src, target, body, to_channel=False, to_me=True)
            return
        if to_channel and self._is_briefer():
            ch = bobreport.normalize_channel(target)
            if ch.lower() != bobreport.FLEET_CHANNEL.lower():
                if bobreport.parse_working_on_shop_line(body):
                    briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick
                    out = bobreport.ingest_working_on_shop(self.home, src, body, briefer)
                    if out.ok and out.actions:
                        worker = bobreport.parse_worker_nick(src)
                        key = f"{worker[0]}:{worker[1]}" if worker else src
                        self._emit_presence(out, "working_on", key)
                    return
        if not to_channel:
            return
        pk = seal.parse_agpk_line(body)
        if pk is not None:
            result = seal.tofu_pin(self.peers, src, pk)
            if result == "pinned":
                seal.save_peers(self.peers)
                info(f"INFO peer {src} AGPK pinned")
            elif result == "mismatch":
                info(f"INFO peer {src} AGPK mismatch (ignored)")
            return
        parsed = seal.parse_seal_line(body)
        if parsed is None:
            self.handle_capa(src, body)
            self.handle_moot(src, body)
            self.handle_file(src, body)
            self.handle_dumb(src, body)
            self._maybe_mention_reply(src, target, body, to_channel=True, to_me=False)
            return
        if parsed.version == 2 and parsed.from_nick and parsed.from_nick.lower() != src.lower():
            info("INFO SEAL prefix != from_nick, drop")
            return
        mine = {self.original_nick.lower(), self.live_nick.lower()}
        if parsed.to_nick.lower() not in mine:
            return
        if parsed.version != 2:
            info(f"INFO SEAL {parsed.msg_id} v1 ignored")
            return
        payload = self.fragments.add(parsed)
        if payload is None:
            return
        if self.ident is None:
            info(f"INFO SEAL {parsed.msg_id} dropped (no identity)")
            return
        try:
            blob = seal.b64d(payload)
            if parsed.version == 2:
                from_nick = parsed.from_nick or src
                pin = self.peers.get(from_nick.lower(), {}).get("pk")
                if not pin:
                    info(f"INFO SEAL {parsed.msg_id} dropped (no AGPK pin for {from_nick})")
                    return
                pt = seal.open_bytes_v2(
                    blob, self.ident, self.chan, parsed.to_nick, from_nick, parsed.msg_id, pin
                )
            else:
                return
        except Exception as e:
            info(f"INFO SEAL {parsed.msg_id} decrypt failed {type(e).__name__}")
            return
        if self._take_airc_file(parsed.msg_id, pt):
            return
        dest = self.inbox / f"{parsed.msg_id}.bin"
        if dest.exists():
            info(f"INFO SEAL {parsed.msg_id} inbox id exists, skip write")
            return
        dest.write_bytes(pt)
        protect.protect_path(dest)
        info(f"INFO SEAL {parsed.msg_id} -> inbox ({len(pt)} bytes)")

    def _take_airc_file(self, msg_id: str, pt: bytes) -> bool:
        """Consume AIRC-FILE v1 plaintext into files/complete/. True = not an inbox SEAL."""
        if not pt.startswith(b"AIRC-FILE v1"):
            return False
        env = filexfer.decode_airc_file(pt)
        if env is None:
            info(f"INFO file DONE id={msg_id} fail")
            return True
        offer = self.file_bags._offers.get(msg_id.lower(), {})
        if offer:
            if offer.get("sha") and str(offer["sha"]).lower() != env["sha256"]:
                info(f"INFO file DONE id={msg_id} fail")
                return True
            try:
                offered_n = int(offer["bytes"]) if offer.get("bytes") is not None else None
            except (TypeError, ValueError):
                offered_n = None
            if offered_n is not None and offered_n != env["bytes"]:
                info(f"INFO file DONE id={msg_id} fail")
                return True
            if offer.get("name") and offer["name"] != env["name"]:
                info(f"INFO file DONE id={msg_id} fail")
                return True
        if filexfer.complete_write(
            self.home, msg_id, env["name"], env["data"], env["sha256"], expect_len=env["bytes"]
        ):
            info(f"INFO file DONE id={msg_id} ok")
        else:
            info(f"INFO file DONE id={msg_id} fail")
        return True

    def reader(self) -> None:
        assert self.sock is not None
        buf = b""
        try:
            while not self.stop.is_set():
                data = self.sock.recv(4096)
                if not data:
                    return
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    t = line.decode("utf-8", "replace").rstrip("\r")
                    debug_log(self.debug, t)
                    if t.startswith("PING "):
                        self.send("PONG " + t[5:])
                        continue
                    prefix = ""
                    rest = t
                    if t.startswith(":"):
                        prefix, _, rest = t[1:].partition(" ")
                    parts = rest.split(" ")
                    cmd = parts[0] if parts else ""
                    trailing = t.split(" :", 1)[1] if " :" in t else ""
                    if not self.ready.is_set() and cmd in REG_FAIL_CMDS:
                        detail = trailing.strip() or (parts[1] if len(parts) > 1 else "")
                        info(f"INFO reg {cmd} {detail}".strip()[:220])
                    if cmd == "001":
                        self.ready.set()
                    if cmd == "JOIN":
                        ch = parts[1].lstrip(":") if len(parts) > 1 else ""
                        if not ch and trailing:
                            ch = trailing
                        joiner = prefix.split("!", 1)[0].lstrip(":") if prefix else ""
                        if joiner:
                            self.handle_join(joiner, ch)
                    if cmd == "PART":
                        ch = parts[1].lstrip(":") if len(parts) > 1 else ""
                        if not ch and trailing:
                            ch = trailing
                        who = prefix.split("!", 1)[0].lstrip(":") if prefix else ""
                        if who:
                            self.handle_part(who, ch)
                    if cmd == "QUIT":
                        who = prefix.split("!", 1)[0].lstrip(":") if prefix else ""
                        if who:
                            self.handle_quit(who)
                    if cmd in ("433", "432"):
                        if self.live_nick == self.original_nick:
                            if bobreport.parse_worker_nick(self.original_nick):
                                self.live_nick = self.original_nick + "_"
                            else:
                                self.live_nick = self.original_nick + "_l"
                            self.send("NICK " + self.live_nick)
                            info(f"INFO nick -> {self.live_nick} (still accept {self.original_nick})")
                    for line in self.sasl_on_line(cmd, parts[1:], trailing):
                        self.send(line)
                    if cmd == "PRIVMSG" and " :" in t:
                        target = parts[1].lstrip(":") if len(parts) > 1 else ""
                        self.handle_privmsg(prefix, target, t.split(" :", 1)[1])
        except OSError:
            return
        finally:
            self.dead.set()

    def drain_outbox_once(self) -> list[str]:
        """Send complete unread outbox lines. Offset persisted; restart does not skip JOIN."""
        if not getattr(self.args, "chair", False):
            try:
                grok_talk.drain_completions_to_outbox(self.home, outbox=self.outbox)
            except OSError:
                pass
        path = self.outbox
        if not path.exists() or self.sock is None:
            return []
        last = load_outbox_pos(path)
        lines, new_last = take_outbox_lines(path, last)
        sent: list[str] = []
        gate_fleet = bobreport.chair_mode_active(self.home)
        for line in lines:
            if gate_fleet and bobreport.outbox_line_spam_for_fleet_channel(line, default_channel=self.chan):
                continue
            if line.startswith("PRIVMSG "):
                self.send(line)
                time.sleep(FLOOD_S)
            else:
                self.say(line)
            sent.append(line)
        if new_last != last:
            save_outbox_pos(path, new_last)
        return sent

    def outbox_loop(self, gen: int | None = None) -> None:
        while not self.stop.is_set() and not self.dead.is_set():
            if gen is not None and gen != self._outbox_gen:
                return
            if not self.joined.wait(timeout=1):
                continue
            if gen is not None and gen != self._outbox_gen:
                return
            try:
                self.drain_outbox_once()
            except OSError:
                return
            time.sleep(1)

    def _abort_gate(self, gate: str) -> None:
        info(f"INFO {gate}")
        raise TimeoutError(gate)

    def session(self) -> None:
        self.ready.clear()
        self.joined.clear()
        self.dead.clear()
        self.live_nick = self.original_nick
        self._pending_joins = {c.lower() for c in self.channels}
        self._outbox_gen += 1
        gen = self._outbox_gen
        info(
            f"INFO connecting {self.args.host}:{self.args.port} "
            f"nick={self.live_nick} home={self.home}"
        )
        self.sock = self.connect()
        threading.Thread(target=self.reader, daemon=True).start()
        threading.Thread(target=self.outbox_loop, args=(gen,), daemon=True).start()
        pw = (self.args.password or os.environ.get("AGENTIC_IRC_PASSWORD") or "").strip()
        if pw:
            self.send("PASS " + pw)
        self.send("CAP LS 302")
        self.send("NICK " + self.live_nick)
        self.send(f"USER {self.live_nick} 0 * :{self.args.realname}")
        self.sasl_plain()
        if not self.ready.wait(30):
            self._abort_gate("NO 001")
        time.sleep(1)
        self.send("JOIN " + ",".join(self.channels))
        if not self.joined.wait(30):
            self._abort_gate("NO JOIN")
        if self.args.hello:
            self.say(self.args.hello)
        if self.args.announce_key:
            if self.ident is None:
                info("INFO no identity; skip AGPK")
            else:
                self.say("AGPK v1 " + self.ident["pk"])
        info(f"INFO joined {self.chan} as {self.live_nick}")
        while not self.stop.is_set() and not self.dead.wait(timeout=1):
            pass

    def run_forever(self) -> None:
        backoff = 1.0
        attempt = 0
        cap = reconnect_cap()
        while not self.stop.is_set():
            try:
                self.session()
                backoff = 1.0
                attempt = 0
            except TimeoutError:
                pass
            except Exception as e:
                info(f"INFO session end {type(e).__name__}")
            try:
                if self.sock:
                    self.sock.close()
            except OSError:
                pass
            self.sock = None
            attempt += 1
            if cap is not None and attempt >= cap:
                info(f"INFO reconnect stopped (AGENTIC_IRC_RECONNECT_MAX={cap})")
                return
            delay = backoff + random.uniform(0, 1)
            info(f"INFO reconnect attempt={attempt} in {delay:.1f}s (backoff cap 60s)")
            time.sleep(delay)
            backoff = min(60.0, backoff * 2)


def main() -> None:
    import signal

    p = argparse.ArgumentParser(description="agentic TLS IRC")
    p.add_argument("--host", default="irc.ntsa.uk")
    p.add_argument("--port", type=int, default=6697)
    p.add_argument("--password", default="", help="IRC PASS (or env AGENTIC_IRC_PASSWORD)")
    p.add_argument("--nick", required=True)
    p.add_argument("--channel", required=True)
    p.add_argument("--home", default="", help="AGENTIC_IRC_HOME (required if two nicks on one box)")
    p.add_argument("--realname", default="agentic-irc")
    p.add_argument("--outbox", default="")
    p.add_argument("--hello", default="")
    p.add_argument("--announce-key", action="store_true")
    p.add_argument("--once", action="store_true", help="no reconnect (tests)")
    p.add_argument(
        "--chair",
        action="store_true",
        help="digest chair seat: JOIN #bobiverse only; !bobiverse + webhook digest",
    )
    p.add_argument(
        "--auto-nick",
        action="store_true",
        help="talk seat: set --nick suffix to this irc_agent PID",
    )
    args = p.parse_args()
    agent_pid = os.getpid()
    if args.auto_nick:
        args.nick = talk_seat_pid.auto_talk_seat_nick(args.nick, agent_pid)
    err = talk_seat_pid.check_nick_agent_pid(args.nick, agent_pid)
    if err:
        info(err)
        sys.exit(2)
    c = Client(args)

    def _stop(*_a: object) -> None:
        c.stop.set()

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)
    if args.once:
        try:
            c.session()
        except TimeoutError:
            sys.exit(1)
        return
    c.run_forever()


if __name__ == "__main__":
    main()
