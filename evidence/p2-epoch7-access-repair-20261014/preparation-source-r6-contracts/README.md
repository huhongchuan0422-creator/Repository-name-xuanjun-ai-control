# r6 preparation contract repair candidate

Local source/test candidate. The separately reported Owner diagnostic identifies
`COLLECT_INPUTS / EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY` as the actual first
failure. The manager/tool binding gap is an independently demonstrated downstream
contract issue; these tests do not claim that it caused the observed first HOLD.

## Production changes

Against frozen wrapper SHA-256
`83c218fc10d19094446494e10767be58593f09dbc92866cbc8779d9a0e776ebc`:

- Correct only the fixed native binding's expected authority and permitted owner
  to `(0,0,0644)` and `(0,0)`. This matches frozen r6
  `helpers/epoch7_snapshot.py` lines 239-242 and 562. Generic reader rules remain.
- Bind manager `binary_sha256` and typed integer `[dev,ino]` identity to the
  authenticated retained row. Bind each fixed systemd/systemctl policy path and
  SHA to that row, then pass the row to the existing `Gatherer.read(expected=...)`
  full typed stamp/hash equality. Its final reread checks remain active.
- Add only the three exact safe labels `EPOCH7_PREP_NATIVE_EXPECTED_AUTHORITY`,
  `EPOCH7_PREP_MANAGER_OBSERVATION_BINDING`, and
  `EPOCH7_PREP_TOOL_OBSERVATION_BINDING`. No prefix or string fallback is added.
- Change only the preparation destination leaf from
  `epoch7-preparation-candidate-r6` to `epoch7-preparation-candidate-r6-contracts`.
  `KIT_ROOT` remains the frozen r6 kit. The inherited exact suffix assertion is
  updated to this fresh leaf.

The frozen factory validates the manager's allowed path, UID/PID and writer
bindings, but does not cross-link its SHA/identity to retained files
(`helpers/epoch7_host_factory.py` lines 364-383). The frozen snapshot validates
executable pins against policy files, not retained rows
(`helpers/epoch7_snapshot.py` lines 301-305). New negative tests demonstrate those
observations passing existing validation before the added guards reject them.
Data/topology modules, kit and portable runner are unchanged.

## Real collection regression and public closure

`test_collect_native_integration.py` runs actual `collect_inputs`, `Gatherer.read`,
`Gatherer.runtime`, `Gatherer.recheck`, and the frozen entry's `DescriptorTree`.
The passing case reads all six retained buffers and exactly 222 temporary files,
including two 102-file historical packages, then rereads native and both tools.
No collector or native/tool read is mocked.

There are 31 integration cases: the original 9 native cases, 8 negatives for each
of systemd/systemctl (bytes, same-byte inode replacement, mode, during-read and
final-reread mutation, wrong policy path/digest, typed nlink), 2 native-only gap
reproductions, and 4 manager SHA/identity negatives. The native cases include the
frozen failure reproduction, valid collection, wrong GID/mode, mutation after
observation/during read/before recheck, hardlink and symlink rejection.

The portable suite has 88 cases: 87 inherited plus one exact safe-label regression
covering all three added labels, appended/private strings, multiple exception
arguments and wrong exception type. The inherited runner is unchanged.

Required public fixture layout relative to this candidate's parent:

- `r6-preparation-candidate/`: the already published frozen preparation sources
  and tests. Its wrapper is SHA-pinned before the baseline module is executed.
- `r6-integration-candidate/build-0c8a0f2a-python312-v2-a/epoch7-recovery-candidate-r6/`:
  the existing published full-kit archive fixture, including helpers, test
  subdirectories and `xuanjun-p2-package/stage1`.
- Local `test_fixtures/epoch7_prepare_native_only.py`: TEST_ONLY_NEVER_HOST_DELIVERED.
  This byte-identical intermediate wrapper is SHA-pinned to
  `e4b377b9b4913f72e79a940ce39890d5512db6792b68c6da81f4e8756e375510`
  before test-only execution. It is outside the three production files. No
  unpublished native-only sibling directory is required. Its two missing-tool-
  binding reproductions are retained unchanged.

### Explicit synthetic seams

1. Fixed logical roots map to disposable files. The descriptor tree's offline
   owner allowlist includes root and the local runner. Wrapper stat/fstat maps
   only UID/GID to root:root (wrong native GID maps that inode to 1002). Actual
   mode, kind, nlink, device/inode, size, timestamps, no-follow traversal,
   ACL/capability checks, FD reads and race checks execute.
2. Observation and retained bytes come exclusively from the existing public
   full-factory fixture. Real temporary file stamps replace invented stamps;
   authenticated fixture hashes and manager identity are rebuilt. Public native
   pins permit synthetic native bytes. Frozen observation, policy, acceptance
   and finite-probe validators execute without stubbing.
3. Original plan, historical kit/helpers and both 102-file packages are public
   synthetic placeholders. Only their test pins are replaced. Real manifest,
   file-count, path and per-file hash reads execute. `reproduce_v4` checks these
   synthetic inputs; `compile_bindings` returns the public fixture result.
4. Receipt authentication uses a public synthetic receipt hash check, followed
   by the actual private file read. The public finite-probe proof is rebuilt
   without running a probe. It is not a host receipt or provenance claim.
5. Socket drop-ins use the public topology fixture; that seam injects pre-final-
   reread mutation in negative cases. Both executable buffers are public
   synthetic ELF-marked bytes, read through the actual Gatherer.

No private observation buffers or private plans are used or included. Tests do
not perform host calls, probe execution, publication, installation or a production
resume. Local passes do not establish end-to-end Owner preparation success.

## Verified local runs

Python 3.12.14 and Python 3.6.8 each pass 31 integration and 88 portable tests,
with zero failures/errors/skips. Run the suites sequentially because the real
ancestor-stamp checks are intentionally sensitive to concurrent filesystem work.
From the workspace root, using each interpreter:

```
python -I -S -B p2-epoch7-repair/r6-preparation-contract-fix-candidate/test_collect_native_integration.py
python -I -S -B p2-epoch7-repair/r6-preparation-contract-fix-candidate/run_local_tests.py --portable
compatibility/python368/Python-3.6.8/python -I -S -B p2-epoch7-repair/r6-preparation-contract-fix-candidate/test_collect_native_integration.py
compatibility/python368/Python-3.6.8/python -I -S -B p2-epoch7-repair/r6-preparation-contract-fix-candidate/run_local_tests.py --portable
```

`LOCAL_STATUS.json` records the final source/test/document hashes and test logs.
Publication maps and delivery coordination are separate from this local freeze.
