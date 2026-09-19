# Manual private-channel session (human, ~20 min)

Not run by CI. Do not open Libera from pytest.

1. Two homes, one private channel, human watching first AGPK pins.
2. Both `irc_agent.py --announce-key`. Confirm pins.
3. `moot.py open` / join / floor / SAY / YIELD / close. Transcripts match HexChat.
4. `filexfer.py offer --tier S` a 3-line snippet. Receiver hash-checks.
5. Optional: Server 2012 `airc-dumb` with PSK copied via RDP. CAPA visible.
6. `dumb_ctl.py ping` then put/exec/get. Jail refuse for a path outside `--allow-path`.
7. Ctrl+C connector; INFO reconnect.
8. Negative: third nick not on `--operators` sends DUMB ping; connector stays quiet.
