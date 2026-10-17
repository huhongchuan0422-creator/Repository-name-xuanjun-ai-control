# PR122 read-only permit gate repair — LOCAL / DEPLOYMENT HOLD

Scope: Task5 #6232366508 only. No GitHub writes, workflow activation, labels, host commands, trust enrollment, registry creation, credentials, or cloud APIs were performed. The existing registered actual-PR workflow remains outside this patch and unchanged/disabled. The patch targets only the original WORK branch offline-review files. It does not authorize use of a different host.

## Implementation delivered

The unchanged approved payload, readonly_probe.py, bundle.json and original 20 tests are retained byte-for-byte. The new fixed-purpose permit_gate.py is embedded into both generated workflow steps, so execution needs no checkout or external mutable code. Generated transport, deterministic packager and existing Hosted-review count change together.

ADMIT contains no Alibaba secret references. It checks the protected source before GitHub reads, then verifies exact official comment ID, full UTF-8 body SHA256, repository/PR provenance and historical fixed App/author provenance. Shared GitHub identity is NOT the independent authority. Independence is rooted in a separate Owner-root enrolled exact-body pin, distinct reviewer/source-writer principals and custody evidence. Source code contains no enrollment, signing, key generation, environment override for the trust path, or directory creation.

The comment's fixed schema binds final H/B/M, exact workflow ref, Git blob and SHA256, unchanged bundle/caller SHA, permit nonce, <=30-minute issuance/expiry (stricter than Task5's <=2h ceiling), exact role/region/instance/hostname, one STS session / one RUN / QUERY only for its recorded InvokeId. Current PR and head+merge workflow bytes are fetched and checked. These bindings are external after registration, avoiding a self-referential head/hash constant in the workflow. No static True or label is accepted as independent approval.

ADMIT durably reserves both the comment ID and nonce using O_EXCL/no-follow mode600 files in the SAME preexisting authorization registry, fsyncing file, directory and parent. Existing or partial markers consume the attempt. No registry creation, cleanup, reset, retry or second authority database is implemented. EXECUTE is conditioned on ADMIT's ready output; it separately reloads the protected exact pin, comment, final GitHub bindings and expiry, verifies ownership by the same run/attempt, and claims a one-use dispatch marker before reading cloud credentials. Pin SHA is carried across processes, so even anchor reserialization is detected. It repeats validation before STS and RUN. InvokeId is saved to the original runner evidence first, then bound durably; QUERY revalidates the same permit and same InvokeId, never dispatches. Expiry, revocation or drift halts query as well as RUN.

The existing literal false, ARMED=False and EXECUTION_ADMISSION=False remain kill switches. They are not authorization evidence. The old EXPIRES literal stays expired in source but is replaced in memory only by a machine-verified externally enrolled permit's expiry. There is no independent manual expiry override.

## Real source reuse, NOT a deployed integration claim

Read at exact commit 6051aa6cbdffbfa2b20f929dbb4ab0b4dc17f4b9:

1. deploy/pr122-r4-controlled-install/approval_gate.py, Git blob a15c524449bd18eb4f28d4d5fc88a19b673285b5. Reused contract: root-private exact comment body pin, fixed GitHub ID/App provenance plus separate Owner independent attestation; exclusive durable consumed markers under /var/lib/xuanjun-pr122-authorizations. Original root gate is explicitly bound to hostname iZ6wee8q9z4t03hvqumwfhZ, not GitHub Hosted and not this Shanghai target. Its original install/rollback permit is NOT reused for a new action.
https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6051aa6cbdffbfa2b20f929dbb4ab0b4dc17f4b9/deploy/pr122-r4-controlled-install/approval_gate.py

2. scripts/pr122_customer_review.py, Git blob 6ff7f846d9f83181254392dbe5b43c93517efc16. Confirms exact independent custody and distinct source-writer/reviewer requirements. Its separate Ed25519 install-specific verifier was inspected, not claimed reused cryptographically. This patch implements the existing R4 Owner-root registered-pin model, not a new key or signature system.
https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/blob/6051aa6cbdffbfa2b20f929dbb4ab0b4dc17f4b9/scripts/pr122_customer_review.py

## Exact unresolved deployment dependency

The executing runner has NO verified pre-cloud access to an existing independent pin and durable registry. The default ubuntu-24.04 hosted workflow therefore cannot pass this repaired gate. Source requires the original historical protected-executor hostname/root and does not change runs-on, add sudo, copy trust, create directories, or enroll a file. The hostname is an additional fail-closed restriction, not evidence that the R4 mechanism is installed or authorized for this operation.

/etc/xuanjun-pr122-release/readonly-admission.json is a proposed scope-specific enrollment in the EXISTING R4 contract, NOT an existing approved pin. No such file was created or found. /var/lib/xuanjun-pr122-authorizations existence, persistence and exclusive custody on an eligible executing environment are UNKNOWN. registry_persistent:true in a hypothetical protected pin is an operator attestation; the code cannot prove infrastructure durability or prevent a privileged administrator from deleting history. Tests never claim otherwise. The source author's arbitrary root process must not have permission to forge this trust; root ownership alone is inadequate if that author controls the executor.

There is currently no deployable activation patch. The required external decision is for the original protected-channel owner and Task5 to identify an already authorized, independently controlled pre-credential verification/consumption service or executor and provide evidence of its actual protected source, operator custody, persistence and use authorization. If none exists, establishing one is a NEW access/security integration requiring its own approval; do not silently move the workflow to self-hosted, transfer the R4 store, or reuse an install permit. A host-side gate reached only after SWAS RUN does not satisfy pre-credential admission.

Task5 may review this scoped verifier and negative tests now. It must not sign real execution until that genuine external dependency and final registered bytes are closed. Owner's prior approval for the fixed read-only operation does not fabricate a trust source. No further broad Owner approval is requested by this artifact.

## Verification and patch scope

53 offline tests pass, zero skipped: original 20 unchanged + 33 new tests. New tests exercise exact comment/hash/provenance, absent trust, same principal/custody failure, unknown execution source, revocation, H/B/M/ref/blob/content drift, expiry/future/overlong permit, wrong RUN/QUERY scope/target/payload, persisted nonce/comment reuse, cross-process pin drift, competing reservations, partial receipt, duplicate EXECUTE, unknown InvokeId, query revocation and no cloud access before denial. Both embedded scripts equal the generated transport; first step has no cloud secrets. All permits/hosts/registries are explicit mock fixtures. No live root probe occurred.

Existing Hosted-only review workflow is changed only from expected 20 to expected 53 tests. A new Hosted run has NOT been submitted or observed. Run39014153253 remains evidence for the old 20-test scope only.

READONLY_PROBE_RUNTIME_CONNECTION=HOLD
PERMISSION_TO_ARM=NO
PERMISSION_TO_LABEL=NO
ACCOUNT_CREATION=HOLD
