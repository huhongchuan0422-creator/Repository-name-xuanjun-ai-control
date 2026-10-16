# Stage A delivery evidence for review

These five files close the delivery-material gap identified in [Work review #6205641864](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/pull/58#issuecomment-6205641864). They are supplied for byte-level review. UK execution remains unapproved and has not run; Task5 approval has not been issued; Stage B/C remain unauthorized.

- [Exact reconstructed archive](stage-a-local-candidate.tar.gz): 1,274,167 bytes; SHA-256 `353a93b968551d8f9db161e9781b468bd339ebb5983cf5a4870c5fb449fb63c2`; 39 regular members.
- [External manifest](MANIFEST.json): 10,571 bytes; SHA-256 `5bda61fb6108e6f4091160004fdff1a661cfe552909511c8812929ea6de2074e`; pins the complete archive and every member, including its embedded inventory manifest.
- [Exact final bootstrap, review only](OWNER_COMMAND_UNAPPROVED.txt): 4,725 bytes; SHA-256 `36df056cc3cd9b345cf5cf51e831385fe112799eab1f6f952abff31934f85bd3`.
- [Delivery binding and scope](delivery-binding.json): immutable source, CI, test counts, review status and execution limits.

The archive is unchanged from the reconstructed source-stage handoff. Its UNBOUND / Hosted NOT_RUN fields are historical. Do not edit them or treat them as current delivery status. The separate bootstrap changes only its commit placeholder to `5dcf1c12d62671e44c443dfcbc773ccb0cc2b284`, preserving reporter SHA-256 `8ebd1ae2d572818677e5e404647f2d53ddae40f3aafa32320dcaf36d7384bde0` and the 93,912-byte limit. No source, archive or validation predicate changed.

[Exact source Hosted job](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38830407370/job/116747642358) passed 148 tests: 37 boundary contracts, 43 reporter, 66 mapper and 2 outer tests. Bootstrap tests passed 23 mocked cases on each local Python 3.6.8 and 3.12.14; these did not execute the UK command or download its source. Work's source review is PASS_WITH_SCOPE_LIMITS, with zero new confirmed source defects. That review explicitly had not obtained this archive and required final delivery-binding review; those two review items remain pending here. These results do not approve the current entire PR HEAD or authorize a merge.

## Privacy and evidence limits

The archive contains public source/tests, exact already-published dependencies and the previously privacy-validated public evidence subset, successful local test logs and reproducibility metadata. It includes fixed infrastructure hostname/paths, allowlisted public PATH/service/group/ExecStart fields, numeric metadata and a local test-file path warning. It excludes the full private observation, arbitrary private configuration bodies, secret environment values, credentials, private source buffers and raw private process output. Its contents are broader than the future Stage A reporter's bounded hash/count/enum output.

This check verified all 39 member sizes and hashes, the nine publication rows, eleven published dependencies and the exact bootstrap commit-only substitution. It performed no new live-host or private-observation inspection. Wall-clock and historical per-check FD/inode records remain explicitly unretained; access-time changes are possible with the existing read primitives. A complete reporter response still retains Stage A HOLD and exit status 2. The actual evidence decision belongs to the existing review gate.
