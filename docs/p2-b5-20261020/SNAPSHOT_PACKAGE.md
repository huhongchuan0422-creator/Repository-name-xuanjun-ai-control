# B5 bounded operation package candidate — not approved or executed

Baseline db54bd818ade4a9ae51cd833193566c9acb72ae7. Existing B1–B4 and 17 loader-contract tests inherited unchanged. Original plugin archive version3dd9f8c4b8b0d4ff / SHA83eac1fca2bf811e8e0ee276cd40f577dc1d0fe77bd425499420fe9f58a9cd8b is reused, not rebuilt.

## Candidate A: one fixed bounded source acquisition

Complete candidate command is [SNAPSHOT_CANDIDATE.sh](SNAPSHOT_CANDIDATE.sh), SHA256 `1ef3e0660b0eab3b2aafc5261dc62dbe63a8f8981bc3634d89068c6dec7bb346`. This is a SOURCE capture, not plugin installation. Do not execute until the entire action list is confirmed. Do not run the earlier four-file inventory first.

Fixed source collector: commit `7c12b368b3586ba0b2d1f91498d8f9f4ed2d95b5`, `scripts/p2_b5_snapshot.py`, SHA256 `505fbcaca2edb0ce3d9cfc697008242dd2e270d71dd394beede82679b003bf85`. Candidate fetches only this exact source over HTTPS without proxy credentials, verifies bytes, compiles syntax, then invokes it through stdin. No runtime package download, Node invocation, SDK import or Docker action in A.

| Boundary | Frozen scope |
|---|---|
| Host | iZd7oeikknn1z21sq6ji6zZ only; root wrapper on /usr/bin/python3 exactly3.6.8 |
| Reader | Child UID/GID1002:1002 xuanjun_dev, supplementary groups cleared, no credentials/environment inherited |
| Node | /home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin/node, regular protected file; bytes/hash only, actual version UNKNOWN |
| SDK | Exact /home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw installation subtree only. No /home scan or other project roots. Historical package/loader/context pins from LOADER_BINDING.md checked before bulk capture. |
| ELF | Parse Node and captured .node modules statically, derive PT_INTERP/DT_NEEDED, capture unique canonical named library candidates only under /usr/lib64, /lib64, /usr/lib/x86_64-linux-gnu, /lib/x86_64-linux-gnu. Recursively parse copied libraries. No ldd, ELF execution, ldconfig or system-directory enumeration. Missing/ambiguous libraries and custom RUNPATH/RPATH HOLD. Observed candidates do not prove the actual linker's choice. |
| Exclusions | No auth/config/session/DB/ledger/customer roots, private keys, .env, credential JSON or user data. Package code such as dist/auth-code.mjs is vendor SOURCE, not user auth/config data. Metadata/data files in auth/config/secret-named directories are excluded. Non-source unknown formats, links and special files are not opened; exclusions force HOLD. Never follow an SDK symlink into another root. |
| Limits | 20,000 regular files,512MiB total source bytes,128MiB/file,40 directory depth,2,048 hold records,512 ELF modules;90s collection wall clock. Child RLIMIT_CPU100s,AS768MiB,FSIZE640MiB,NOFILE128,CORE0; wrapper150s timeout kills/waits the process group. Before creating output require at least1GiB available and64 free inodes; no disk cleanup or reservation performed. Directory listing memory is additionally bounded by RLIMIT_AS; entry count is checked after listdir (Python3.6 lacks fd-scandir). |
| Network | One fixed source GET by root wrapper. Collector has no network or subprocess code. This does not create an OS network namespace: it is a fixed non-executing source reader. No remote SDK resolution. |
| Output | New root-owned0700 /var/lib/xuanjun-p2-isolated-test/b5-source-snapshot-20261020; new uid1002 child0700. Parent base remains root0700. Child receives the already-open directory FD, so it need not traverse or change the private root parent. |

### All actual side effects proposed by A

1. HTTPS GET of the fixed collector source; source reads may update atime.
2. Create root0600 `.b5-source-snapshot.lock` under the existing isolated base, acquire nonblocking flock. Existing lock must already be protected; no chmod of it.
3. Create exactly the new B5 operation directory0700, root source.py0600, new uid1002 child0700; fchown **only this new child** to1002:1002. No recursive chmod/chown and no existing file permission changes.
4. Spawn one bounded short-lived UID1002 Python source reader, pass output FD and stdin source. No Node/SDK/plugin/business execution or long-running service.
5. Write new child0600 source-tree.tar.pending, manifest.json, result.json; root0600 stdout.log, stderr.log and host-result.json, O_EXCL/fsync. No database, .pending registry, new grant or installation ledger. No deletion or overwrite.
6. Parent captures exact manifest/archive/result hashes and child exit; intentional final exit2/HOLD. A source snapshot can be BOUNDED_SOURCE_CAPTURED while state remains HOLD. Exit0 never means closure, signature or CP11 success.

Files may not form an atomic point-in-time installation snapshot: leaf/parent checks reject detected races, but there is no filesystem freeze. The archived bytes plus manifest are a new candidate version; do not treat them as a proven immutable live installation. No archive is promoted to a runnable version or extracted by this command.

### Outputs and stopping/recovery points

- `uid1002/source-tree.tar.pending`: path-preserving tar of actual selected regular SOURCE bytes and numeric UID/GID/modes. Never extract as root onto the live filesystem. Even a well-formed tar is not runtime-ready.
- `uid1002/manifest.json`: exact path/hash/size/uid/gid/mode/kind of captured files; schema scope ISOLATED_TEST_ONLY_SOURCE_SNAPSHOT.
- `uid1002/result.json`: capture/HOLD status, static ELF names/edges, exclusions and actual archive/manifest SHA. closure/export UNKNOWN, Node execution and CP11 NOT_EXECUTED.
- `host-result.json`: source binding, child code, capture and exact result/archive/manifest references. Timeout/signal/preexec failure is retained as HOLD, not hidden by a wrapper exit0.
- Before new directory creation failure: nothing installed, no retry of B1–B4. Existing operation directory causes STOP; never silently create another attempt or clean it.
- During capture: keep pending tar and logs. If killed before result/manifest, missing fields remain UNKNOWN; root summary records the missing result. Disk-full/parent-kill can prevent final fsync/receipt and must be reported UNKNOWN. No automatic retry.
- After capture: original inputs untouched; `.pending` source remains unusable for loading. Continue OFFLINE analysis from exact recorded bytes. If further materialization is needed, reconcile these records and freeze the next complete action; do not delete/re-run this command to simulate recovery.

## B: offline dependency closure and export observation (not ready to execute)

All required acquisition is requested together by A; no per-file Owner inventory requests. The offline reviewer/developer receives the whole retained source archive/manifest/result plus already available original plugin. Moving the private archive off host or to a test snapshot is a **future explicit action**; this package does not upload it anywhere. Hosted source artifacts below contain our NEW candidate code only, never UK SDK bytes or secrets.

1. Validate all artifact hashes and provenance; inspect exclusions/links/failures individually, not the top exit code. Match package version/source/pins. Unmaterialized links or changed historical hashes stay HOLD, not auto-accepted.
2. Build a real AST/package-resolution graph from the captured source, package exports/conditions, nested dependencies/versions and lock/integrity metadata. Enumerating the installation does NOT prove this graph. Runtime-selected/dynamic imports, native/ICU/assets or external edges remain unresolved until actual bounded resolution evidence covers them. No regex/hand-written VERIFIED flag can replace this work. The AST resolver and its exact parser/source binding are not yet delivered; they depend on the captured real module tree. If bytes are missing, the consolidated gap is the unresolved graph/target set, not another random file probe.
3. Bind ELF interpreter and library aliases/versions to actual isolated resolution; static unique host candidates are not link/runtime compatibility proof. Node must actually execute in the later isolated environment and satisfy >=24.16.0 <25 or >=26.1.0. Existing Python3.11 container alone is not proof of Node compatibility. No host Python upgrade or runtime installation proposed.
4. Only after a complete, reviewed fixed snapshot mapping exists, prepare an isolated no-network/read-only/cap-drop ALL/no-new-privileges UID1002 container. Preserve original absolute Node/SDK paths and original protected parent/UID assumptions, privately mount the frozen manifest and new probe output. No production, Docker socket, credentials, auth config or business data mounts. Pin the actual existing compatible image and interpreter/shared-library/mount bindings. Those actual bytes/image compatibility and complete mapping are currently UNKNOWN, so **there is no executable Docker command frozen for B**; inventing one would misrepresent readiness.
5. `scripts/p2_b5_export_probe.mjs` is provided for that future phase. It checks actual Node engine/path/UID, Docker marker, frozen manifest SHA, selected exact file hashes/metadata and historical loader SHA, then imports the REAL fixed compiled module and records namespace export types. It never calls acquire, a handler or plugin health API; never guesses aliases. An actual named function still leaves signature/provenance unproven. It always outputs HOLD/CP11 NOT_EXECUTED. Its execution is NOT part of A and NOT authorized by this source-only task. The env manifest hash is an exact byte reference, not an authority grant. A Docker marker alone is not proof of network/mount isolation; the future wrapper must enforce it.
6. Once real compiled mapping/signature and runtime closure are established, resume existing loader adapter lifecycle acquire→validate live registry→await release, with immutable version references. Missing compiled export stays HOLD. That lifecycle is not implemented/executed by this snapshot package.

Probe SHA `e02713bdfe72f0cff50d12c452b7469b2004dada510a293f6122b3e6df3a9aae`; it reuses unchanged loader contract SHA `54a2d972521d01dc3f6094020b52fd40e7673b87544534979a4492e2e22d7f0b` at db54bd81. Hosted bundle retains scripts/ and production/ relative paths to preserve that import.

## Delivery and verification boundary

New candidate code is versioned in the original branch and available in Hosted `P2 B5 bounded snapshot candidate` artifacts. Original plugin package remains CI39380788469; loader contract baseline17 tests remains CI39385318130. Neither is rebuilt/retested here. Fourteen new tests cover exclusions, special files, ELF parsing, bounds, partial output, output FD across process and no overwrite. Local13 passed/1 UID-change test skipped because local chown is unavailable; Hosted requires the actual UID1002 test with no skip. Python3.6 grammar is checked, not a claim of actual UK3.6 execution. Actual UK APIs/UID1002/source capture/ELF closure/export import/CP11: NOT_EXECUTED.

Current deliverable: bounded SOURCE acquisition candidate and offline follow-through boundaries. Full runtime test operation remains HOLD on real source/dependency/export/mount evidence. Safe no-effect positive function is still a separate unapproved feature decision; no new endpoint developed. No B6/B7/P3 or five-attempt quota.
