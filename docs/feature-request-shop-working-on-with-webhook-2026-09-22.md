# Feature request: shop working_on at the same time as webhook

**Date:** 2026-09-22
**Repo:** https://github.com/SimonBarnett/agentic_irc
**Raised by:** Simon on #agentic_irc
**Related:** #100 shop channels

## LOCKED

1. When a worker posts the digest webhook with working_on, it must also
   announce on #{machine}: 
ick: This is what I'm working on: …
2. When a worker cc_send(working_on) on IRC, it must also POST the webhook.
3. Secrets-shaped working_on never leaves the box.

## Deliverable

- post_working_on.enqueue_shop_working_on after successful working_on POST
- irc_agent._cc_working_on POSTs webhook after shop PRIVMSG
