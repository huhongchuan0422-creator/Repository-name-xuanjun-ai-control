# DOMESTIC_STAGING_READONLY local candidate

This helper is not an installation or execution permit. No cloud call has been
made. Its only production entry accepts no arguments and checks root UID and
the fixed domestic hostname iZvt5t8tlrm8oiZ before observing eight named files.

## Evidence and exact candidate scope

- Historical PR122 comment 6218584525 identifies
  `/root/pr122-unified-release-4ryrkhl9` as its evidence directory. The seven
  relative candidates beneath it are the seven exact members of distribution
  TAR SHA256 d6a73acb1037e55babbc882a82d6f98c23331a49faa1addfe9d9df5e82e5e125,
  preserving the archive's `pr122-unified-release/` packaging prefix. This is
  an explicitly bounded candidate layout, not proof that extraction used that
  layout or that any of these files still exists. No stripped-prefix alternate
  layout is searched. The Tokyo archive is excluded: the old controller required
  its filename relative to a supplied inputs argument but no historical absolute
  inputs argument is established. Missing this provenance remains a blocker.
- The original `pr122-unified-owner-stage.yml` establishes the sole candidate
  under `/home/githubrunner/pr122-unified-release-6218264390` as
  `approved-release.tar.gz`: 406102 bytes, SHA256
  d6a73acb1037e55babbc882a82d6f98c23331a49faa1addfe9d9df5e82e5e125.
  That workflow does not establish an extracted layout beneath this root.
- The code-derived old transaction bundle path is deliberately excluded from
  the reader. It remains a separately documented possible source, not new scope:
  `/var/lib/xuanjun-pr122-site-hub/transactions/pr122-public-mobile-20261016/bundle/candidate-manifest.json`.
- The historical input `R2_CANDIDATE_MANIFEST.json` has SHA092f2236..., not the
  current 1288-file baseline SHA17d580a7.... An OBSERVED digest must never be
  mistaken for current-baseline admission.

Evidence files inspected locally:
`/workspace/shared/pr122-static-controlled-v1/workflow-audit/pr122-unified-owner-stage.yml`,
`/workspace/shared/pr122-v4-r2-evidence/HISTORICAL_12053237878.zip`, and
`/workspace/shared/pr122-post-r2-plan-candidate/history/COMMENT_6218584525.json`.

## Read-only and trust boundaries

There is no listdir, glob, recursive scan, archive extraction, write, application
import, HTTP request, subprocess, or command execution. Each absolute component
is opened by directory descriptor with O_NOFOLLOW; named links and open descriptors
are compared before/after reading. Files must be ordinary single-link objects;
symlinks, hardlinks, directories, devices and FIFOs are refused. All errors are
constant diagnostic codes, never exception text or file content.

This is observation only. Root-directory ancestors and files must be UID 0 and
not group/other writable. The sole exception is the fixed `/home/githubrunner`
subtree on the runner-root route, which must be UID 1002 and not group/other
writable. `/` and `/home` still require UID 0. Files' ownership and mode are also
included in stability checks. The helper does not promote owner-stage files to
root-protected execution sources. Directory contents are not enumerated. An
ABSENT result requires the missing component still be absent after its opened
ancestry is rechecked. Disappearance between stat/open is HOLD. Any ABSENT is normal and
does not authorize copying, rebuilding, scanning, installing, or retrying an old
transaction. Unsafe objects, races and access failures produce HOLD and stop all
remaining file reads; remaining predefined labels are marked NOT_READ.
Each file is observed separately; the result is not a global atomic snapshot.
ABSENT does not prove loss, non-installation, never-executed state, or an empty
directory, and cannot trigger automatic discovery outside these fixed names.

Limits: eight named candidates; individual bounds are compiled into FILES;
1,500,000 bytes total; 65,536-byte read chunks; 20-second monotonic deadline plus
process alarm; 4096-byte maximum JSON output. Output contains only predefined
labels, observation states, file sizes, hashes and fixed diagnostics. No file
content, arbitrary path, credentials, permissions, or configurable command input
is returned. The SWAS wrapper should add its own existing invocation identity
binding; this helper does not create another ledger or dispatch mechanism.

Run fixtures locally with `python3 -B -m unittest discover -s . -p 'test_*.py' -v`.
Tests use isolated temporary directories, patch only in-process constants and
host identity, and do not execute main against production paths.
