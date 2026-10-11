# UK Owner approval receiver core

New `stage1/uk_owner_callback_core.py` is a **fail-closed, transport-independent** approval receiver core. Its inputs match the existing `telegram_owner_transport.py` UK HMAC callback payload.

Deployment requires a separate, authenticated **HTTPS reverse proxy / transport** that forwards *unaltered raw bytes*, a UK-only trusted approval request issuer, a protected owner ID binding and signing/auth secrets. Never expose an unprotected Python endpoint or the Coordinator `decide` CLI.

`install_schema` only creates the two side tables for registered requests and replay protection. It DOES NOT register authorizations. A trusted UK Coordinator must create each request with matching task, live fence, owner and expiry. The handler must reject all callbacks otherwise.

Status: committed + unit test design; **no UK service deployed, no R11 webhook integration, no real approval callback completed**. Existing Telegram send was manually acknowledged by Owner from Tokyo. This does not prove reply routing.
