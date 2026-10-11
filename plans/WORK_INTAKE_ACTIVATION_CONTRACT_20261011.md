# Work to UK OpenClaw intake: candidate and platform admission

Status: CANDIDATE_CODE_REVIEW_PASS; PLATFORM_NOT_DEPLOYED_NOT_ACCEPTED.
This is a delivery transport for the existing task authority, not another task
registry, dispatcher, release approver or production database.

## Existing execution is preserved

Owner relayed UK A1/A2 STARTED at 18:16 Asia/Shanghai, bound to control commit
76c0cfe7f7a4dd9ed52a9dc719897c95c437ba8b and spec SHA256
deb334171fdbc10d9ab8abff046493526ca5c992428d514629a86cf32859fc6a.
Evidence: evidence/uk-intake/OWNER_RELAYED_REPAIR_START_20261011.json.
This is a relayed receipt, not an independent host process probe. B waits for
A2_CONTRACT_FREEZE; C waits for real release admission. Intake upgrades and
documentation commits must not restart these tasks, reset their failure budget,
discard checkpoints or revive the failed release candidate.

## Implemented candidate protocol

1. The existing host-guarded UK push workflow conditionally calls only the
   separately installed, root-owned and hash-matching intake module as githubrunner.
   Without that installation it explicitly reports WAITING_PLATFORM_INSTALL.
2. Publisher checks fixed repository/branch/checkout and the Actions control SHA.
   It obtains raw commit/tree/blob bytes with replace refs disabled and controlled
   Git environment, and verifies each object's SHA. It executes no source file
   from the request. Spec/design bytes are transported as bounded data.
3. Validate approved maintenance kind/authority, spec digest, permissions all
   false, exact two-model policy, OAuth route, preserved bounded budget and roles.
   Complete envelope limit is 98,304 bytes; duplicate JSON keys and malformed
   object types fail closed. No CODEX_EXEC is submitted to the old Coordinator.
4. Publication key = SHA256(control SHA + newline + spec digest). Publication is
   immutable per source and serialized. Different control SHAs never overwrite
   each other's envelope. Consumer ignores envelopes outside the current detached
   Runner checkout and rechecks source after auth, immediately before a wake.
   This local freshness check is not a distributed task lease or A2 epoch fence.
5. Execution receipt key = SHA256(parent task + newline + spec digest). Thus a
   documentation SHA change cannot repeat the same work. A changed design under
   the same spec requires a new explicitly approved spec. The already manually
   started spec is imported as STARTED_OWNER_RELAYED without any model request.
6. Consumer is xuanjun_dev, never root; it wakes main only using the existing
   OpenClaw CLI/OAuth route. There is no sudo/runuser, new GitHub credential,
   copied OAuth token, paid model API, channel delivery, DB write or release action.
   Current wake adapter uses the already verified 5.6 fallback and does not probe
   the known unavailable primary. Primary recovery policy remains a separate
   task-boundary model gate; this adapter does not prove that gate complete.
7. A flock and fsync journal record DISPATCHING before Gateway interaction.
   Crash/timeout/unbound response retains effect-unknown state with no automatic
   retry. Main's RECEIVED/STARTED/WAITING_HUMAN is separately reported; a receipt
   never proves independent role start or production PASS. A durable marker may
   conservatively hold even when a send never occurred; reconciliation is explicit.
8. Fixed expected transport profile is status=ok / result.meta.agentMeta with
   provider=openai and the requested 5.6 model. Free text/unrelated JSON cannot
   attest a model. Actual installed Gateway profile and OAuth route must still be
   verified before unattended activation; a schema change holds, never guesses.
9. Every fresh, replayed and Runner-readable receipt is schema checked and
   whitelist sanitized. Unknown fields/raw diagnostics are never printed;
   production_pass and independent_role_start_probe are always false. FIFO,
   symlink, hardlink, wrong owner/mode, unstable file and oversized output fail.
   CLI capture is bounded while reading, not after unlimited buffering.

## Installation boundary: still NOT_VERIFIED

Do not run a generic sudo/systemd grant or another root model command. Integrate
these reviewed transport files into the same controlled installation/manifest
mechanism after the A2 platform contract freezes. Root copies pinned verified
bytes; smoke tests/model calls run only as the intended unprivileged identities.
No standalone unreviewed root installer has been executed or supplied here.

Required dedicated boundaries (actual users/groups must be inspected):

| Path | Owner/group | Mode | Purpose |
|---|---|---|---|
| /opt/xuanjun-work-intake | root/root | 0755 | Immutable to service users |
| /opt/xuanjun-work-intake/uk-work-intake.py | root/root | 0644 | Hash-bound installed module |
| /etc/xuanjun-work-intake.json | root/root | 0644 | Exact two fixed delivery paths |
| /var/lib/xuanjun-work-intake | root/root | 0755 | Protected parent |
| requests | githubrunner/xuanjun_dev | 02750 | Publisher writes; consumer reads |
| receipts | xuanjun_dev/githubrunner | 02750 | Consumer writes; Runner reads |
| Published envelopes / receipts | respective directory owner/inherited group | 0640 | Explicit fchmod under UMask=0077 |
| Intake lock | respective writer | 0600 | Advisory local serialization |

Templates: deploy/uk-work-intake/{config.json,xuanjun-work-intake.service,
xuanjun-work-intake.timer}. Timer is proposed at 30 seconds; unit is oneshot,
unprivileged, NNP, PrivateTmp, with bounded CPU/memory/tasks. Template validation
is not evidence of systemd239 installation or runtime viability.

## Validation and remaining gates

Work local full regression: 242 PASS, including 20 intake tests. Negative cases
include concurrent duplicate wake, crash after durable marker, timeout/invalid
receipt, same spec/new SHA, changed design, forbidden model/API/permission/budget,
metadata spoofing, raw receipt secrets/false PASS, Git replace, auth-time source
change, malformed/duplicate JSON, true subprocess output bound, oversized envelope,
UMask/group-read preservation, symlink/hardlink/FIFO and root rejection.
Independent Work review initially FAIL; the reported blocking cases were fixed.
Final independent security rerun: 20/20 PASS, script SHA256
40d87f1deee7cd0a2183744ce385b80d278a34eeed136feb83683810a2b675e8.
This scope is Work intake, not the UK A1/A2 release artifact or production E2E.

Still required: controlled installed artifact/hash/owner/mode; real distinct-UID
read/write denial; real systemd239 timer/reboot; actual Gateway profile and OAuth
route; one approved new-source automatic receipt; replay/new-document-SHA no wake;
crash effect-unknown reconciliation and no customer/channel delivery. Production
loop, HTTPS dashboard, two tasks and migration retain their separate gates.
