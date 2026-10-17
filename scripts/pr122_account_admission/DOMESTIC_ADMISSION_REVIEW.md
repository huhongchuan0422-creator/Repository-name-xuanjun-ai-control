# Domestic fixed-channel read-only extension — review candidate

Status: LOCAL CANDIDATE / DEPLOYMENT HOLD. No installation, trust enrollment, GitHub write, workflow activation, or probe has been performed by this package's authors. Owner willingness to assist at an admin terminal is not approval of these yet-unreviewed final bytes.

## Why this route

The existing domestic channel has actual historical evidence: PR122 comment 6213830271, run 38889575618 / job 116935526733 executed the fixed `inspect` verb as githubrunner UID 1002 via sudo. That verb exposes only four customer-center metadata paths. It cannot install this extension or perform the new account preflight. Historical success is not current host/baseline proof.

The design extends only that domestic wrapper. The original `channel.py` (SHA256 `0804e33edac6ad07a711456c0c15708266b2ad8a75c4cb3bdc5964a9b79a96bd`) and its lock inode remain unchanged. Existing inspect/plan/apply/rollback semantics, grant state, archive, and account-creation receipt remain untouched. The new exact sudo verb is `inspect-account-once`; it accepts no extra parameter and executes only a fixed root-owned helper. No shell payload, checkout, cloud Secrets, STS, SWAS, new key, RAM grant, account creation, installation of system software, or service changes are part of execution.

## Source and trust reuse

- `scripts/pr122_domestic_customer_channel.py`: fixed domestic host, UID1002, wrapper, four old verbs and original canonical lock.
- `scripts/pr122_customer_channel_upgrade.py`: existing Owner-only deployment boundary, root-private exact public-comment body pin, independent source/reviewer custody statement, fail-closed baseline, exclusive transaction, durable evidence and restoration approach.
- `readonly_probe.py` and `approved_account_prepare.py`: exact already-reviewed bytes. Their hashes must remain respectively `118e3e972fd94a34647c1a289f449caf4eef40dbb444611d99f53d155cd148ba` and `885b850864465a554d99adbdfb4b4d4e33abf5dc52e7dcf84f27597c247c0818`.
- aa0869's permission-binding ideas only. Its Tokyo host, root-private files and registry are not copied as a deployment prerequisite. This is a local fixed action, so there is no RUN/QUERY cloud permission.

The new scope pin and transaction/receipt are explicitly NEW files within the existing domestic channel boundary, not claims that a protected source is already installed. Owner personally controls independent enrollment through the existing domestic admin/Root entrance. Original Task5 remains reviewer. Shared GitHub user/app identity is not proof of reviewer independence. The Owner's protected exact-comment/custody pin is the external root of trust; the helper verifies it and cannot write it. Source authors and the runner cannot register approval.

## Installation and use order

1. Review final source, generated helper and installer hashes, bounded file manifest, offline negative tests, and restoration bytes in original Task5. Current approval fields are UNKNOWN; no source/test PASS substitutes for install or execution permission.
2. After exact-byte review, obtain Owner's action-time confirmation for the specific temporary sudo/security-file changes. Owner runs the reviewed package's read-only plan through the existing admin entrance. It must establish live hostname, real/effective root, safe file ancestry, exact old code/wrapper/policy hashes and modes, GRANTED state, original lock identity and absence of conflicting transaction. Unknown baseline means HOLD, never normalization or overwrite.
3. Owner performs the separately approved bootstrap, which retains backups, publishes fixed helper/wrapper/policy and leaves durable transaction state. Installation never registers its own execution approval or runs the probe. Partial install is diagnosable; no forward retry. Use only reviewed recovery/restoration for a known partial state.
4. Task5 issues the final narrow one-use execution comment against final generated helper/wrapper/policy and scope/nonce/short expiry. Owner independently enrolls the exact comment ID/body hash/provenance/custody pin in the fixed root-private file. Owner must not paste an unverified source-author-generated approval as an independent attestation. No fabricated template is an approval.
5. Only after enrollment and final permission, invoke the exact fixed command once as the existing runner UID1002. A direct existing runner capability is required. Existing consumed metadata workflow permission is not reused. The actual PR122 workflow remains disabled unless its separately reviewed exact final bytes and one-shot trigger receive permission.
6. Helper verifies before observing, durably consumes before probe, and executes the unchanged probe under the original single lock. Failure, timeout, partial state or unknown outcome forbids retry. Redacted receipt survives. Unknown findings remain UNKNOWN; no account creation is authorized by a successful observation.
7. Owner restores original wrapper and sudoers bytes with reviewed rollback, preserving helper and transaction/receipt evidence. Verify restored hashes, modes and unchanged original lock inode. During the temporary extension, the existing customer-upgrade guard intentionally rejects changed wrapper/policy; do not relax that guard or run concurrent upgrades.

## Files and authority

Only the fixed wrapper `/usr/local/libexec/xuanjun-customer-channel`, its sudoers policy `/etc/sudoers.d/xuanjun-customer-channel`, the fixed new helper `/var/lib/xuanjun-customer-channel/readonly-admission.py`, and scoped bootstrap/approval/one-use evidence under `/var/lib/xuanjun-customer-channel` are affected. Exact filenames and hashes are in the generated package manifest and source. The read-only observation itself writes only its scoped audit consumption/result evidence, so it must not be described as zero host writes.

The allowed principal is local UID1002 with one fixed action, not an independently attested GitHub job. A sudo environment variable or caller-supplied run ID cannot prove a GitHub run. If Task5 requires cryptographic job-specific authorization, this package remains HOLD until an existing verified mechanism supplies it; do not invent one.

## Required Owner confirmation, after hashes are final

Approve installation of the reviewed fixed helper and temporary exact `inspect-account-once` sudo entry/wrapper branch on the domestic host, with reviewed transaction backups and later restoration of original wrapper/sudoers. Owner personally enrolls original Task5's exact one-use approval and independent custody pin. The action observes only fixed system-account/path/tool/lock data and retains redacted audit receipts; it cannot create users, change services, or accept arbitrary Root commands. Installation, enrollment, execution, and restoration are separately identifiable actions within this same bounded reviewed procedure.

## Current external dependencies

- Actual current host baseline and original lock inode: UNKNOWN until Owner's reviewed plan.
- Final Task5 install/execution comment IDs, complete-body SHA256, nonce and expiry: UNKNOWN.
- Owner-enrolled protected pin and its custody evidence: NOT INSTALLED by this work.
- Exact authorized invocation route and corresponding final workflow bindings if used: UNKNOWN; actual workflow stays disabled.
- Owner's exact final-file action-time safety approval: PENDING.

The tools used for this work can author/test files and read repository evidence; they do not establish an authorized automatic route to install Root security files. The existing limited channel cannot bootstrap its own expanded sudo permission. This single Owner-admin installation closes that genuine bootstrap dependency without asking for a password, broad Root channel, new key, or generic approval service.

## Package and final command rendering

New candidate paths: `domestic_helper.py`, `domestic_bootstrap.py`, `build_domestic.py`, `build_owner_command.py`, four `tests/test_domestic_*.py` / `tests/test_owner_command.py` files, this note, and the four files in `domestic-install-package/`. Existing probe/payload files are unchanged, not patch replacements.

The deterministic builder embeds the exact approved bytes. The package manifest binds helper, original-wrapper-plus-fixed-branch, exact augmented sudoers and bootstrap bytes. After committing these generated files, render installation/verification/restoration commands with `build_owner_command.py --commit <verified full 40-hex commit> --package <local frozen package directory> --action install|verify|rollback --output <new review file>`. This renders text only. The final rendered text, source commit and SHA256 must go to Task5 and the Owner before use; do not substitute an unreviewed later commit or script.

Installation's single-copy command creates an exclusive root-private staging directory, downloads only the four fixed immutable URLs with curl configuration and proxies disabled, verifies each exact SHA256, and executes nothing downloaded until all four match. Verification/restoration commands reread the same hashes without downloading or modifying staging. A failed download or partial install is not automatically cleaned up or retried; report the observed state for narrow recovery. This deliberately avoids an unreviewed inline installer or curl-pipe-to-shell.

One additional bounded file may be necessary: if the original upgrade lock `/var/lib/xuanjun-customer-channel/.upgrade-lock` is absent, approved install creates it root0600 using exclusive creation and preserves it thereafter. Plan does not create it. Lock acquisition order matches the existing Owner upgrade: upgrade lock then original channel.py. `channel.py` is never replaced. Actual existence remains unknown until plan.

## Exact permission comment/pin contract

Task5's public approval body must be the literal prefix `XUANJUN_DOMESTIC_READONLY_ADMISSION` plus newline and one strict JSON object. No duplicate keys, extra keys or nonfinite values. Pin and comment share schema=1; source_writer_principal, reviewer_principal, owner_principal; custody_evidence_sha256; 64-hex nonce; UTC issued_at/expires_at (positive duration no more than 1800 seconds); review_source=`original-task5-pr122`; numeric github_author_id and github_app_id; and exact helper_sha256/wrapper_sha256/policy_sha256. The source writer must differ from reviewer and Owner. These labels are assertions enrolled by the independently acting Owner, not independent proof inferred from strings or GitHub identity.

The public comment additionally contains fixed scope=`domestic-runner-uid1002-fixed-inspect-account-once`, host=`iZvt5t8tlrm8oiZ`, runner_uid=1002, max_executions=1, channel_sha256, payload_sha256, probe_sha256 and creation_authorized=false. The root0600 pin contains shared fields plus exact positive comment_id and SHA256 of the entire UTF-8 comment body; it excludes those comment-only scope fields. Numeric author/app values must come from the actual approved comment metadata, not guesses. The helper checks exact GitHub repo, PR, URL, author/app and body. It rereads the comment immediately before consumption and before publishing success; edited/deleted/expired approval fails closed. It never writes the pin.

The final comment ID/body hash, actual authority metadata and independent custody evidence cannot yet be populated. They must be supplied through Owner's independent enrollment after the exact final review. A source-author-created example with placeholders is not a valid pin and no example pin is installed by this package.

The Owner has now reported hostname `iZvt5t8tlrm8oiZ` in message Sentinel_ee200beb25188191989810812ac0a62b. This establishes the reported hostname only; real/effective Root, current file bytes/modes, grant state, locks and concurrent writers remain unverified. The helper reports global writer exclusion UNKNOWN rather than claiming this advisory lock excludes every possible administrator.

## Hosted-only CI integration

The 13th patch path is `.github/workflows/pr122-account-admission-review.yml`. It retains `ubuntu-latest`, contents-read only, no target transport or host credentials. Both deterministic builders run before the zero-diff check; discovery includes the existing 53 tests and 63 new package tests. The actual combined run returned **116 tests, OK, no skips**, not an assumed sum. CI asserts 116 and performs a second zero-diff check after tests. Its existing recursive artifact manifest/archive includes all admission source, both builders, Owner command renderer, tests and all four generated installation-package files, excluding Python cache files. It does not activate the actual Root workflow.

The command renderer does not execute plan/install itself. Its output may be delivered for use only after the exact source commit/package hashes and rendered command have passed the final review and Owner exact-file confirmation. Values supplied to the renderer are not machine proof of approval; never claim rendering a command grants permission.

## Owner-complete stage tool (increment after e38232a)

`domestic_owner.py` is a fourth root0400 staging file bound by the installation manifest. It is not a sudoers entry and is not installed as a general Root channel. Owner stages are explicit:

- `enroll`: takes the externally verified real Task5 comment ID, SHA256 of its complete body, and independently verified custody-evidence SHA256. It fetches the fixed PR122 comment, derives the strict pin from that real approved JSON, checks final installed hashes/provenance/scope/expiry, locks the original channel, then creates the root-private pin exclusively. It cannot create approval or overwrite an existing pin. No manual JSON editing is needed.
- `execute`: Owner-root delegates only the exact fixed sudo verb through the existing local githubrunner identity, which must actually be UID1002. This is a local identity-scoped execution, never represented as a GitHub job. A durable Owner dispatch-intent marker precedes the sole invocation. Any ambiguous outcome blocks retries even if the helper did not leave a final receipt.
- `export`: reads only the fixed scoped result and outputs allowlisted, sanitized metadata. It cannot read arbitrary paths or print raw account records, subprocess output, stderr, tokens, or environment data.

The renderer now accepts only an explicit, nonduplicated sequence of fixed stages: install/enroll/execute/export/verify/rollback. Default remains install only. Install must be first if selected, enrollment must precede execution when both are selected, rollback must be last. It verifies all four fixed staged file hashes before any downloaded code runs. For a separately approved end-to-end scope, a single copied command can list all approved stages and embed real final review parameters; otherwise render only the currently approved stage. A failed stage exits nonzero and stops the sequence. No automatic retry, automatic unknown-state rollback, or permission inferred from the stage name is provided.

Real Task5 approval and exact Owner confirmation must explicitly include the local UID1002 action and whichever stages are rendered. Installation/rollback authority remains Owner's independent exact-byte administrator approval, not something inferred from the execution permit. The generated command itself and all populated parameters still require final review. No current approval ID, body hash, custody proof, or nonce is invented by this increment.

The completed increment has **100 new-package tests and 153 integrated tests**, all passing with no skips; the earlier 63/116 counts describe the e38232a checkpoint only. Hosted CI is updated to assert 153. No mocked enrollment result is evidence that a real pin was registered.

Before changing wrapper/policy, bootstrap now verifies the actual fixed `/usr/bin/python3` interpreter: minimum Python 3.8 and required APIs, secure root-owned symlink chain, resolved executable identity, safe bounded binary metadata/hash. It saves that identity in the baseline. Unsupported/missing/changed interpreter causes HOLD rather than installing Python or guessing another path. Exact current domestic interpreter is still unobserved by this work.

Both direct fixed-helper entry and Owner enrollment/execution require the protected VERIFIED installation record, absence of rollback intent/completion, and the original installation's channel device/inode plus grant-file hash under its original lock. A same-byte replacement of channel.py is not accepted as the old lock. The Owner stage tool also validates its own root400 staged bytes and package manifest against the protected installed transaction manifest before loading the fixed approved helper. Fixed local execution checks that the githubrunner name resolves to UID1002, durably marks its one dispatch attempt, releases the channel lock before invoking the helper, and retains the existing upgrade lock. Unknown dispatch exits nonzero; following stages in the rendered sequence do not run automatically.

Final cross-module regression: actual bootstrap.plan()/install() output and its persisted baseline feed Owner enrollment and helper validation on one temporary filesystem transaction. The actual Owner baseline-check callback code is reused, not reimplemented; inode replacement, grant drift and interpreter identity drift are rejected against that same output. Only ownership/host/approval transport and interpreter observation are fixtures. Package **101 tests**, combined **154 tests**, no skips. Owner stages now reuse the manifest-verified staged bootstrap.baseline() under the existing lock, so its full interpreter identity is checked without a parallel implementation.
