# Stage1 Telegram Owner integration candidate
Status: CODE_COMMITTED_ONLY. Neither production webhook nor UK endpoint is deployed.

## Secret and identity configuration
- Domestic: use existing protected Telegram Bot token reference; never place bot token in Git or UK server.
- Domestic: verified Owner private chat id and distinct Telegram sender user id, bound by authenticated enrollment.
- Domestic and UK: shared owner-callback HMAC secret reference and short-lived scoped authentication token.
- UK: dedicated HTTPS endpoint with TLS, owner signature verification, replay ledger, fence and task-state checks.
- Existing R11 Telegram webhook must call accept_update after routing only authenticated Owner commands.
- Do not create competing getUpdates poller or replace existing customer webhook.

## Missing before deployment
Authenticated production R11 route integration; durable request lookup and delivery queue; secret provisioning; UK callback receiver; callback replay/fencing protection; real Owner identity enrollment; delivery acknowledgment and end-to-end Canary. Local transport has no server or listening port.

## Automated tests
Run Python 3 unittest test_telegram_owner_transport.py; this is not a real Telegram delivery test.
