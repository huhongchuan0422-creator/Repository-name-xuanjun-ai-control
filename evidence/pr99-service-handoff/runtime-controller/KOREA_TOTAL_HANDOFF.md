# PR99 Tokyo–Korea continuation

Owner selected migration of the model RPC, OpenAI shim, Gateway and its
OpenClaw dependencies in the current conversation on 2026-10-20. This extends
the older Korea Binance-only scope. Trading/API activation remains deferred.

Entry: `korea_model_handoff.py` (Python 3.11+, Tokyo root). Dependencies:
`korea_project_controller.py`, `korea_current_sync.py`,
`portal_total_controller.py`. The latter supplies the existing durable
Checkpoint and kernel-fence reader; the domestic portal cutover is not replayed.

The controller reuses the accepted full-project archive and Korean extraction,
synchronizes the current private recovery point, refreshes model program bytes,
and stages the exact Node 24.16.0/OpenClaw 2026.9.3 installation. It copies only
the SSH identities actually resolved for the existing required tunnels, together
with the existing host trust files. Private keys, OAuth profiles, unit environment
values and mutable Gateway state remain in private host directories and SSH
transport; they are not uploaded to GitHub or printed.

Before source pause it checks target ports/capacity/protected service identities,
Node ABI, SSH authentication from Korea without changing forwarding, source
Gateway's unrelated tasks, external symlink gaps and fixed source hashes. It
then pauses the exact source services, proves their cgroups empty and captures
mutable state/workspace. Korea receives private mounted services, bounded by a
memory slice, with the existing ports and TLS identity. It verifies an actual
GPT-5.6 Sol model request with no fallback, shim health, the Korea local 19444
route and domestic reverse 19444 TLS health. Target services are enabled and
source services disabled only after these checks. Existing MoreLogin, Novel,
PostgreSQL, Redis, Tailscale and Runner units are not modified.

Each mutating phase has an exclusive source journal and a target install lock.
Existing attempts are query-only. Unknown effects are never replayed. Before
any target start was attempted, a failure may restore source services only after
proving all owned target services stopped. After a Gateway start was attempted,
OAuth/session state may have changed, so automatic rollback to stale Tokyo state
is refused; both sides remain available for exact reconciliation. No server is
shut down and no Binance order writer is enabled by this controller.

Validation: 91 local tests, 89 passed / 2 skipped. Tests cover real fixture tar
receive/readback, traversal and duplicate refusal, changed baseline refusal,
committed/uncommitted WAL, sealed closed-database reads, symlink boundaries,
unit namespace/dependency/mode generation and preserved uncertain intents.
Native immutable-kernel and Unix-socket tests are unavailable in this test
runtime. Target chown and external service/network inventories are replaced in
receiver fixtures. No Hosted or production execution is claimed. Native host
checks and actual model acceptance are gates inside the operator command.

Owner authorized termination of other Gateway tasks on 2026-10-20. The explicit
`--owner-drain-gateway-tasks` option drains only non-main/non-SSH Gateway
children with pidfd identity checks and a 45-second bound, both at initial
inspection and immediately before the handoff fence. It never suppresses
unknown migration results or broadens termination to other service groups.

The two live extension SDK symlinks (openclaw-lark and ws-ckpt) retain their
original /usr/local/lib/node_modules/openclaw target. This distinct installation
is included once in static capture and bound read-only in private service
namespaces; it is not redirected to the Gateway 2026.9.3 package.

Recovery for the observed legacy workspace setup error is implemented in
`korea_workspace_recovery.py`. It retains the original start UNKNOWN, requires
source fencing and completed transfer/install evidence, stops only the target
Gateway, backs up private state/workspace, and runs the existing Node/OpenClaw
`doctor --fix` in a cloned private namespace. No new global OpenClaw install or
source service resume occurs. Gateway/RPC/Shim health precedes the original real
model canary and route handoff. Every recovery mutation has its own intent and
result; existing recovery attempts are query-only. Four additional local
recovery tests pass (95 total: 93 passed, 2 skipped); native doctor execution
and real model acceptance remain server-side gates, not locally claimed PASS.
