# I1 exact-action admission protocol — pending independent review

The prior source-only approval6205371670 and integrity review6205624143 do not
approve execution. No real action approval or Owner root admission pin is shipped.
The installer has no command to generate either. No production action runs in CI.

## Trust and registration

Developer receipt6205597052 and independent review6205624143 have the same GitHub
user332398908 and App1144995. GitHub identity alone cannot authenticate independent
reviewer context. The mandatory external trust anchor is an Owner/root-controlled
pin of an exact receipt **independently received from the original auditor**.
This is an explicit Owner trust decision, not a cryptographic reviewer signature
or a self-approval by this development window. A developer-made PASS, fabricated
receipt ID or old source-only receipt cannot create this root pin.

Only after the original independent audit window accepts this exact increment:

1. The auditor verifies the exact commit/tree, complete new artifact and all
   bound bytes, then separately issues a fresh one-attempt action receipt below.
   It must explicitly approve the four empty negative requests and one Portal
   restart. No real account operation is approved.
2. After posting, the auditor computes SHA256 of the **entire original GitHub
   comment body encoded UTF-8**, without newline normalization, and gives Owner
   its ID and full digest through that independent review window. Do not put the
   body digest inside its own body (circular). Approval lifetime is at most24h.
3. Owner/root registers that independently received pair in the fixed private
   anchor. Root0700 `/etc/xuanjun-pr122-release`, root0600 regular nlink1
   `install-admission.json`; no symlinks. No installer/Runner writes the anchor.
   The explicit `owner_attests_independent_review=true` records this handoff.
4. The standalone installer must itself be root0400 regular nlink1 and execute
   with isolated Python (`python3 -I`). No configurable approval path, ID, hash,
   allowed-action or env bypass is accepted by its CLI.

The existing non-root Runner sudo helper cannot register this new action/pin.
Standing Owner consent remains valid; it does not manufacture technical root
access or an independent exact-version approval. A trusted actual admin/root
handoff is still needed after audit. No new keys, sudoers or generic exec grants
are added by this increment.

## Machine-readable independent receipt

One block only, delimited by literal lines
`<!-- PR122_R4_ACTION_APPROVAL_V1` and `PR122_R4_ACTION_APPROVAL_V1 -->`.
Inside: strict JSON object, no duplicate/extra keys. All fields below mandatory.
This document intentionally contains no executable approval example or actual pin.

| Field | Required value |
| --- | --- |
| schema_version | integer1 |
| kind | PR122_R4_ACTION_APPROVAL |
| decision | APPROVED_EXACT_ONE_ATTEMPT, issued only by actual independent auditor |
| reviewer_role | INDEPENDENT_AUDITOR |
| repository | huhongchuan0422-creator/Repository-name-xuanjun-ai-control |
| pr_number | integer122 |
| host | iZ6wee8q9z4t03hvqumwfhZ |
| action | install |
| max_attempts | integer1 |
| source_commit / source_tree | full40hex exact reviewed code commit and Git tree |
| installer_sha256 | actual root executing controlled_install.py full64hex digest |
| binding_sha256 | exact REVIEW_BINDING.json full64hex digest |
| artifact_id | positive integer of exact reviewed GitHub Actions artifact |
| artifact_zip_sha256 / artifact_tar_sha256 | full64hex independently recomputed bytes |
| expected_source_sha256 | d5ab592a6a23dd5ebfa8689c95aaa453e371127aab9a39bc2fe7eba0febbbdf0 |
| result_source_sha256 | 57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1 |
| helper_sha256 | 0e61a4cab72a18e94ed8b97c81e035ee023dfe0969c871c50651cf75792cbcbe |
| allowed_effects | ordered array: backup_single_source, write_single_source, restart_portal_once, empty_negative_post_4 |
| negative_post_requests_max | integer4 |
| issued_at / expires_at | UTC Unix integers; issued within60s of GitHub created_at, not future, expires after issuance and within86400s |
| approval_nonce | unique32lowercasehex chosen by independent auditor |

Root pin has exactly these keys: `schema_version=1`, `action=install`,
`approval_comment_id` positive integer, `approval_body_sha256` full64hex,
`owner_attests_independent_review=true`, `owner_confirms_backend_outage=false`.
The pin is outside this repository/artifact, never bundled as an approval fixture.

## Validation, drift and replay

Before engine loading or any lock/state creation, validate root/host/private pin,
unused receipt ID, canonical PR122 comment/user/App and exact pinned body digest,
explicit action/effects/hash/time schema, actual root installer bytes, GitHub
commit/tree and committed installer bytes, committed binding bytes and installer
entry, exact nonexpired artifact ZIP digest and originating commit/repository.
Canonical API only: HTTPS verified, no redirects/proxy environment/credentials,
10s per request, bounded response/deadline, fail closed on errors/rate limits.
The runtime does not redownload private/authenticated archives or claim to rehash
TAR bytes; those are independently reviewed and covered by the Owner-pinned body.

Acquire existing nonblocking locks, then check exact live source/candidate and
service identity. Ticket max age30s. Recheck root pin, executing bytes, expiry and
canonical approval body before exclusive consumption; edited/revoked receipt
fails closed. Consume through O_EXCL/O_NOFOLLOW durable root0600 marker in fixed
root0700 `/var/lib/xuanjun-pr122-authorizations`, before creating R4 state or
changing source/service. Consumed/partial-failure markers are never deleted or
retried automatically. The checked proof replaces the former placeholder in
private grant.json. A crash after consumption requires a fresh independently
reviewed recovery action, never reuse of the approval. Existing source/new-PID,
once-only apply, health and four fixed403 request gates remain in force.

## Offline rollback is separately authorized

Never infer rollback authority from install. It needs a different exact receipt
with action `rollback-offline`, reversed source/result hashes, ordered effects
`stop_portal`, `restore_single_source_offline`, `keep_portal_stopped`, zero negative
POSTs, and distinct fixed `rollback-offline-admission.json` root pin with
`owner_confirms_backend_outage=true`. All other version/artifact/time/consumption
checks still apply. Owner explicitly accepts Portal dynamic-route outage.
Confirm PID0 and18080 refusal before restoring; preserve stopped backend, never
restart the vulnerable old version. No automatic rollback or Tokyo VM stop.

## Test scope

40 dedicated I1 tests use fake GitHub metadata and temporary root files, including
missing/forged/old/expired/consumed approvals, drift, wrong host/action, network
failure, edits before consumption, actual two-process exclusive consumption,
partial marker failure and pre-engine denial. Synthetic approval fixtures are
never written to production paths or posted as real GitHub approvals.
20 affected installation/rollback models inject synthetic admission separately;
they test integration mechanics, not independent-authority provenance. CI enforces
60 passed and zero skips. Original approved source18/HEAD44/static115/config83/
OAuth45 remain inherited and are not rerun.
