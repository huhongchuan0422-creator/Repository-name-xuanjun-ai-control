# Task Center Remote MCP v1

## Status

- Source and isolated HTTP fixture: implemented and tested.
- Hosted deployment: `NOT_EXECUTED`.
- ChatGPT account/plugin installation: `UNVERIFIED`.
- Real provider task call: `NOT_EXECUTED`; pricing/quota qualification remains a
  hard server-side gate.

This is a thin adapter over the existing task-center SQLite, Gateway, Writer
fence, `model_requests` queue, ModelScheduler, usage ledger, and result fields.
It does not introduce a second queue or task state.

## Endpoint and protocol

After the candidate is deployed with `--enable-mcp`, the intended endpoint is:

`https://uk.wenwenwenyiyiyi.work/task-center-test/mcp`

The endpoint implements stateless MCP Streamable HTTP JSON-RPC.  OAuth
authorization-code + PKCE (`S256`) is discovered through the protected-resource
and authorization-server metadata below the same base path.  DCR accepts only
the documented ChatGPT HTTPS callback paths.  Access tokens are stored only as
SHA-256 digests and are bound to tenant, principal, project, audience, scopes,
and expiry.

## Tools

1. `task_capabilities` — read current eligible connections/models and holds.
2. `task_submit` — persist one `TEXT_CLASSIFICATION` task and return `task_id`.
3. `task_get` — read canonical task and request status.
4. `task_query_result` — read persisted result, usage state, or exact failure.

No tool accepts a tenant, principal, secret, shell command, SQL statement, file
path, deployment action, or production-control request.

## ChatGPT installation (Owner action after deployment)

1. Confirm the account/workspace exposes **Plugins → Add custom MCP server**.
2. Enter the endpoint above and select OAuth/DCR authentication.
3. Complete the task-center Owner login in the first-party authorization page.
   The password is never entered in MCP arguments or ChatGPT messages.
4. Review the four discovered tools and install the plugin.
5. Start a new conversation, type `@`, select the plugin, then call
   `task_capabilities` before submitting a task.

Account/workspace policy can make the custom-MCP entry unavailable.  Source
support does not prove that the Owner account has this feature.

Official references:

- https://developers.openai.com/plugins/deploy/connect-chatgpt
- https://developers.openai.com/plugins/build/auth

## Runtime gates

`--enable-mcp` only exposes authenticated tools.  It does not enable model
calls.  `--allow-mcp-model-outbound` starts the durable worker, but every send
still requires all existing checks: active encrypted connection, exact selected
provider/model, successful model-call receipt, `KNOWN_FREE`, current attributable
quota `AVAILABLE`, `QUALIFIED` evaluation, current Writer lease/fence/epoch,
runtime/token limits, and enabled scheduler module.  Unknown pricing or quota is
`HOLD`; there is no paid fallback.

The currently deployed service has neither flag and therefore remains unchanged.
