# Native controller candidate — active P2 review state

Current owner: CHATGPT_NATIVE. Dots is parallel on tasks 2/3. OpenClaw is mechanical-only / zero-model unless Owner changes policy.

Latest controller HIGH-finding repair: `3d7928b7c4c6c641d0799487c88df254ea08b0a2`.
The repair binds placement to the complete canonical execution identity, revalidates host bytes and container namespace after placement, and refuses to replay a receipt-less `LAUNCH_INTENT`.

Exact hosted zero-model regression on that source:
- P2 source regression run `38284448351` / job `114929338286`: PASS.
- 21 wiring + 11 SQLite ledger + 8 socket/parser Python tests: PASS.
- Node controller/host regression and syntax: PASS.
- Python 3.6 grammar compatibility: PASS.
- PR-level Control Plane, Entry Review/Continuation and native-entry receipt gates: PASS.
Hosted Python grammar is not UK Python 3.6.8 runtime acceptance.

UK verify-only evidence:
- Gateway process identity run `38284608109`: PASS.
- Python runtime observed on UK host: `3.6.8`.
- Gateway UID: 1002 (`xuanjun_dev`).
- Gateway cgroup: `/system.slice/xuanjun-uk-openclaw.service`.
- Gateway executable SHA256: `7fde7b8afa198da66257f42ee2001d874c7355631e6d1579a5fb5ef1f246df4c`.
- Initial host-facts run `38284608207` failed because the probe used ambiguous cmdline process scanning; source was corrected to bind systemd MainPID/ControlGroup and rerun is pending/active under the latest branch.
- OpenClaw dependency-hash and Gateway-unit verify-only runs remain pending at this snapshot.

Packaging:
- A same-source deterministic freeze workflow now reconstructs the old frozen archive, applies the reviewed patch/overlay, includes the native controller plugin, writes `P2_CANDIDATE_PROVENANCE.json` and `SHA256SUMS`, and uploads one candidate tarball.
- A frozen candidate is NOT a release approval.

Current gate: INSTALL HOLD until exact frozen candidate receives UK verify-only plus independent QA/Security/Release on the same artifact, followed by reviewed install/rollback and E2E. Unknown execution `f998...` is never replayed.
