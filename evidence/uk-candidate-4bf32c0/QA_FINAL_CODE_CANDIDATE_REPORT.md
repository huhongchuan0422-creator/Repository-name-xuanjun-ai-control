# Final code candidate independent QA report

- Role: `TEST_QA_ENGINEER` (independent; no candidate-code edits/deployment)
- Declared source: `85ad1d7224485f3c57298e71a429eb576b8d943d`
- Reconstructed baseline: `b7f74de4c2283f204a3e7f77331e0ba1e07a47e2`
- Frozen candidate: `4bf32c009c433416ac1ef7ff7038fd4dcd29d7d2`
- Frozen/rebuilt tree: `fb8ee3bd3e2f175bcabc3eefe95aa182f3529b49`
- Patch SHA-256: `82e81c2bbca62ff28dddab409f66ee53106283a1ebb3a9271c5c89b38e11aac0`
- Manifest SHA-256: `7a721baadf570decf6fae72747394e84fdac29fe1432fcef4f44a4bd85bf9eaf`
- QA workspace: `/home/xuanjun_dev/xuanjun-uk-dev-20261011/qa-integration-final`

## Identity

The workspace was freshly reconstructed from the supplied baseline and patch.
The resulting tree exactly equals the frozen candidate tree. Patch/manifest
digests, diff whitespace, reverse-apply and all 33 manifest file hashes pass.
The superseded `93d5b04` candidate was not used as an acceptance base.

The original upstream SOURCE_COMMIT object remains unavailable locally. This
report therefore binds to the supplied reconstructed baseline rather than an
independently fetched upstream object.

## Results

1. Compileall: PASS.
2. Full repository suite: **232/232 PASS**.
3. Manifest external-anchor verification: `MANIFEST_OK`.
4. Same-descriptor manifest test: PASS. Replacing the manifest pathname during
   the read did not change the authenticated/parsed bytes.
5. Temporary release install: PASS for closure smoke and modes; helper `0755`,
   required runtime files `0444`.
6. Systemd 239 unit verification/property syntax: PASS.
7. Helper root/ledger/traversal/path-injection negatives: PASS.
8. Handoff orchestration test: PASS; main requests dispatcher→worker before
   execution and worker→dispatcher in `finally`.
9. Independent final suite: **4 PASS, 2 FAIL**.

## Code blockers

### FINAL-QA-001 — ordinary Git worktree is rejected before first handoff

An independent real repository and real `git worktree add` were used without
any undocumented preprocessing. Git produced its normal checkout permissions
(files/directories with group/other read/execute bits under the effective
umask). The helper's `_safe_tree()` runs before `_handoff_tree()` can normalize
permissions and requires every entry to have no group/other bits. It terminated
with:

`UNSAFE_WORKTREE_ENTRY`

The candidate's own real-worktree test manually changes all directories to
`0700` and files to `0600` before invoking `_safe_tree`; production
`CliBackend.prepare()` and the dispatcher service contain no equivalent step.
Therefore a normal first development task cannot reach the worker handoff.

### FINAL-QA-002 — worker-created files can prevent ownership return

The transient `systemd-run` unit does not set `UMask=0077`. A worker-created
file or directory will normally be created with system-manager default modes
such as `0644`/`0755`. In `finally`, `_handoff_tree()` first calls the same
strict `_safe_tree()` before it can normalize/chown entries back to the
dispatcher, so normal newly-created code can make the return handoff fail and
leave the worktree worker-owned.

The code boundary needs either a safe validation phase that permits ordinary
owner-controlled regular-file/directory modes before normalization, or an
explicit production preprocessing step, plus a transient `UMask=0077` (and a
test that creates a new file as the worker before return). Symlinks, devices,
cross-device entries and hardlinks must remain fail-closed.

## Separate conclusions

### Code QA

**FAIL.** The identity/manifest defects are fixed, but the real worktree cannot
complete the dispatcher→worker→dispatcher lifecycle under production-like file
modes.

### Platform/deployment

**HOLD / NOT TESTED.** Independently of the code failure, this host currently
lacks `/usr/bin/codex`, `/usr/bin/gh`, `xuanjun-dispatcher` and
`xj_codex_worker`. No real cross-UID chown, sudo helper invocation, live Codex
task, HTTPS/nginx activation, webhook change, database switch or deployment was
attempted. Those remain platform/Work acceptance items after code QA passes.
