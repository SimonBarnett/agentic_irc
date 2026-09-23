"""Offline tests for the Discworld guest client. No network."""
import socket
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import discworld_guest as dw


class StripTests(unittest.TestCase):
    def test_ansi_and_orphan_sgr(self):
        raw = "\x1b[32mbar\x1b[0m \x1b[1;31mHi\x1b[0m 0;10mdoor"
        self.assertEqual(dw.strip_ansi(raw), "bar Hi door")

    def test_keeps_plain_words(self):
        self.assertEqual(dw.strip_ansi("5p edition two"), "5p edition two")


class TelnetTests(unittest.TestCase):
    def test_will_and_do_and_iac_and_sb(self):
        data = bytes([
            dw.IAC, dw.WILL, 1,
            ord("A"),
            dw.IAC, dw.IAC,
            dw.IAC, dw.DO, 3,
            dw.IAC, dw.SB, 9, 1, dw.IAC, dw.SE,
            ord("B"),
        ])
        clean, replies, tail = dw.consume_telnet(data)
        self.assertEqual(clean, b"A" + bytes([dw.IAC]) + b"B")
        self.assertEqual(replies, bytes([dw.IAC, dw.DONT, 1, dw.IAC, dw.WONT, 3]))
        self.assertEqual(tail, b"")

    def test_split_option_is_tail(self):
        clean, replies, tail = dw.consume_telnet(bytes([dw.IAC, dw.WILL]))
        self.assertEqual(clean, b"")
        self.assertEqual(replies, b"")
        self.assertEqual(tail, bytes([dw.IAC, dw.WILL]))


def _peer(sock, steps, seen):
    buf = b""
    try:
        for expect, reply in steps:
            if expect is not None:
                while expect not in buf:
                    chunk = sock.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                    seen.append(chunk)
                buf = buf.split(expect, 1)[1]
            if reply:
                sock.sendall(reply)
    finally:
        try:
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass


class LoginTests(unittest.TestCase):
    def test_guest_reaches_room_then_quits(self):
        client, peer = socket.socketpair()
        menu = (
            b"R - Request a temporary password\n"
            b"Your choice: "
        )
        room = (
            b"You have never logged in before.\n>\nQueued command: look\n"
            b"There are four obvious exits: up, north, south and west.\n"
        )
        steps = [
            (None, menu),
            (b"G\n", b"Enter the name you wish to use: "),
            (b"Quilltest\n", b"How would you like your name capitalised? [Quilltest] "),
            (b"\n", b"Should your character be male or female? "),
            (b"male\n", b"Are you using a screenreader? [yes/no/help] "),
            (b"no\n", b"Please read the terms. We'll be back in 30 seconds\n"),
            (None, b"Enter 'yes' if you agree: [yes/no]\n"),
            (b"yes\n", room),
            (b"look\n", b"Read From 1 to 2 of 4 (50%) - return to continue, h for help.\n"),
            (b"\n", b"page two\n> "),
            (b"quit\n", b"But not saving for guests... sorry.\nDo come again!\n"),
        ]
        seen = []
        thread = threading.Thread(target=_peer, args=(peer, steps, seen), daemon=True)
        thread.start()
        conn = dw.Conn(client)
        try:
            dw.guest_login(
                conn, "Quilltest",
                menu_timeout=3, step_timeout=3, terms_timeout=3, room_timeout=3,
            )
            self.assertIn("obvious exits", conn.text)
            delta = conn.command("look", idle=0.2, cap=3)
            self.assertIn("page two", delta)
            wire = b"".join(seen)
            self.assertLess(wire.index(b"yes\n"), wire.index(b"look\n"))
            dw.quit_guest(conn, timeout=3)
            self.assertIn("Do come again!", conn.text)
        finally:
            conn.close()
            peer.close()
            thread.join(timeout=2)

    def test_password_prompt_sends_nothing(self):
        client, peer = socket.socketpair()
        steps = [
            (None, b"Your choice: "),
            (b"G\n", b"Enter the name you wish to use: "),
            (b"Someone\n", b"Password: "),
        ]
        seen = []
        thread = threading.Thread(target=_peer, args=(peer, steps, seen), daemon=True)
        thread.start()
        conn = dw.Conn(client)
        try:
            with self.assertRaises(dw.LoginError) as caught:
                dw.guest_login(conn, "Someone", menu_timeout=3, step_timeout=3, terms_timeout=3, room_timeout=3)
            self.assertIn("password", str(caught.exception))
            peer.settimeout(0.4)
            try:
                extra = peer.recv(100)
            except socket.timeout:
                extra = b""
            self.assertEqual(extra, b"")
        finally:
            conn.close()
            peer.close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
