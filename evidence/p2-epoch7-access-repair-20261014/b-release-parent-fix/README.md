# Finite B release-parent correction

This candidate corrects one observed producer/consumer mismatch. The original
saved prerequisite producer enumerates only its original plan's directories;
the resource compiler incorrectly assumed a retained release-parent row also
existed. The actual B attempt stopped during compilation before creating any
private outputs. Its earlier source staging remains preserved.

## Evidence and compilation contract

The historical R7 observation, snapshot, retained evidence, probe results and
accepted topology body are unchanged. A new B-only `fresh_release_parent` field
contains descriptor-measured metadata for the fixed release parent and its
two ancestors. Every row must match the original policy's UID/GID/mode; the
parent additionally requires the existing root:root/0750 contract. No inferred
inode or ACL value is substituted for a missing historical row.

The wrapper performs actual no-follow, descriptor/path identity and xattr
checks, retains all three descriptors, and repeats the checks before and after
private publication. The field binds the original canonical observation and
policy hashes. Its compile-time state explicitly requires a final recheck.
Both prepare and independent factory recomputation validate the same field.

The original saved-evidence kit remains `epoch7-recovery-candidate-r7`.
The new compiler uses the distinct fixed sibling
`epoch7-recovery-candidate-r7-parentfix`; its eventual resume entry requires
that exact location and the unchanged complete-review/private-input gates.
All 107 runtime payloads must remain byte-identical. The new wrapper leaf is
`epoch7-preparation-candidate-r7-fresh-parent`. Compiler manifest and entry pins
are intentionally unbound in this source-stage candidate, so it refuses before
host reads. No install admission follows from this source or its tests.

## Focused test evidence

Python 3.12.14 local results: 23 new consumer/root-gate tests, 39 wrapper tests,
7 collector-to-three-output functional tests and 97 affected existing tests;
all 166 pass with zero skips/errors/failures. The new consumer also passes from
its actual packaged `tests/host_factory` location.

The offline artifact builder has a separate 24-case Python 3.12 suite over the
actual pinned original archive, including deterministic bytes, exact overlay
closure, unchanged runtime and authenticated discovery of the new test module.
It accepts caller-verified publication identities; it does not claim that a
well-formed commit string alone authenticates a Git publication.

The functional fixture exercises the unchanged prerequisite producer's actual
directory scope, the real fresh-directory producer, target seed hydration,
identity compilers, complete 107-runtime/17-resource-view factory, plan
compiler, seed serialization and exclusive output publication. It checks
collisions, partial writes, post-publication failure retention and the same
target's future seed rehydration reproducing the emitted plan. Historical host
facts, private byte pins and review receipt are synthetic; unavailable private
observation/v4 buffers are not claimed to be locally replayed.

Python 3.6.8 syntax compilation passes for the final 14 Python source/test
files. Runtime compatibility remains unresolved locally: final clean-cache
and pipeline processes crash natively in the existing uuid/ctypes import
chain. Earlier two seven-case successful runs do not override the final
failure. No replacement, skipped required test or preloading workaround is
used. The dedicated Hosted workflow must run a clean interpreter import and
all focused tests on Python 3.6 as well as a current Python before delivery.

## Immutable binding order

1. Review and publish this exact source/test/CI batch.
2. Build the new compiler deterministically from the pinned original archive
   and exact nine overlays, using the actual published source commit/tree.
   Verify the full archive and unchanged runtime closure.
3. Bind the wrapper and staging delivery to the actual new compiler
   manifest/entry/archive and the exact preparation-source publication.
   Any literal-only binding changes receive their own narrow review.
4. A separately authorized single B preparation attempt may then stage only
   the two new siblings and generate three protected private outputs. An
   existing or partial output is never overwritten. A failure stops the
   attempt and retains exact partial-output status.
5. C remains gated by a new exact complete recovery review and Owner execution
   authorization. The historical A receipt is not relabeled as approving the
   new compiler artifact or any production action.

The source-stage package is not an executable Owner command. No new host
collection, probe, installation, service change or production resume has been
performed during this local correction.
