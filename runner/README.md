# Runner topology

Required dedicated self-hosted runners:

- label: xuanjun-uk-dev
  purpose: UK REFERENCE/DEV/BUILD/TEST/STAGING only
  trading production write: forbidden

- label: xuanjun-korea-binance
  purpose: isolated Korea Binance migration target
  initial authority: preflight/install/test/read-only/shadow
  order-write: forbidden until migration canary gate

- label: xuanjun-tokyo-readonly
  purpose: inventory/export/hash/package source
  production mutation: forbidden during discovery/export

## Runner rules
- Use dedicated OS users.
- Runner work directory must not be the production application directory.
- Do not run GitHub runners as root.
- No raw secrets in GitHub logs/artifacts.
- Access production secrets through server-local SecretRef mechanisms only.
- Workflows must target explicit labels; never use a generic self-hosted selector alone.
- Tokyo workflow scripts enforce read-only operations.
