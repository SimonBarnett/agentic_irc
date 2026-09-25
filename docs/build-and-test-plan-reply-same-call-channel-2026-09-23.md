# Plan
1. Track `_last_call_channel` on channel PRIVMSG when `_joined_channel`.
2. Bare outbox drain uses that channel via new `say_to` / `say` update.
3. pytest for sticky + grok_talk.reply_target_for.
