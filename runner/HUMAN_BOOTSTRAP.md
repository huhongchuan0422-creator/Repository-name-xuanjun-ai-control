# One-time human bootstrap for self-hosted runners

This is the only manual bridge required before ChatGPT can execute server-side discovery/migration through GitHub Actions.

Repository: huhongchuan0422-creator/Repository-name-xuanjun-ai-control

For each server, open GitHub:
Settings -> Actions -> Runners -> New self-hosted runner
Choose Linux / x64 and run GitHub's generated commands on the target server.

Use a dedicated non-root runner OS user and the following custom label:

1. UK development server
   custom label: xuanjun-uk-dev

2. Korea server
   custom label: xuanjun-korea-binance

3. Tokyo server
   custom label: xuanjun-tokyo-readonly

Do not paste registration tokens into repository files or logs.
After registration, install/start the runner as a service using GitHub's displayed service command.

Expected queued jobs will automatically start when a matching runner comes online:
- UK Control Plane Preflight
- Korea Binance Target Preflight
- Tokyo Read-Only Discovery

Safety:
- UK runner has no trading production-write workflow.
- Korea preflight explicitly disables Binance order write.
- Tokyo discovery script performs read-only inventory only.
