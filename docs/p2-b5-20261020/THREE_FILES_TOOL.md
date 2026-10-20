# B5 retained archive three-file tool — candidate, NOT_EXECUTED in UK

GNU repair task PR17 #6289587537; baseline fa91394e3ebf57732c44b5dc43b8a6d610888b73. Original task #6289056886. Only new tool/tests/candidate. Original source capture, readonly plugin, B1–B4 and applicable CI are inherited. No reinstall, new source capture, live SDK traversal, Node/SDK execution, network operation or input permission change.

## Exact inputs and selected bytes

Only these existing paths are opened, component by component with directory FDs and NOFOLLOW:

`/var/lib/xuanjun-p2-isolated-test/b5-source-snapshot-20261020/uid1002/source-tree.tar.pending`

559237632 bytes / SHA256 `e6d3a3cef96ee996eb4b130fb0bd9305438489326b85678a263998602413e485`.

Same directory `manifest.json`:5635704 bytes / SHA256 `cdd3c80360af8b4227d166d8ba643ed534055ea79a75b46dcd345c3e86fb52ba`.

Tar-relative prefix: `home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw/`.

| Selected relative output member | Bytes | SHA256 |
|---|---:|---|
| package.json |145276|214e9551a924a9ced04ecf38c7ed8f6bff8beeab33431db12ed6250eaa959e95|
| dist/loader-runtime-load-DpgEqnzx.mjs |273593|3c30c5d43fb3cd19525853bb6b756cf45cfd05f5da32a732dc129b85cb309787|
| dist/context-DyPstb2Q.mjs |176|db7fc7539455da0c564d4ded0d04da1c764a46903d1632489b8bd04641098320|

Selected content total419045 bytes. New tar contains exactly these3 regular members,600 metadata, no source path prefix, no extra SDK data. Provenance remains in a separate receipt. The archive and sidecar are **offline analysis material only**, not a closed dependency tree, executable loader, B5 acceptance, production permission or a replacement of the original readonly plugin.

## Complete candidate and all actions

Complete self-contained command: `THREE_FILES_CANDIDATE.sh` in this directory. Source is embedded; it does not download a script or invoke any network tool. SHA256 `cc2b7a66d91e301e0f502069e1a8a61516afe24be5b996cb5e570ad51246f4e0`.

Tool `scripts/p2_b5_three_files.py` SHA256 `41385f49529471ab9144d01faac31d52b097a25e13cefccea06b900f1b0a1a5b`.

This is a candidate for separate on-site confirmation, not an instruction to execute now. No placeholders, runtime installation, package download or source re-collection are hidden inside it.

1. `sudo -n /usr/bin/python3 -I -B -S -` on fixed UK hostname iZd7oeikknn1z21sq6ji6zZ; root and exact host Python3.6.8 guard. Resolve local admin identity/home with pwd; admin must be a nonroot identity separate from1002. These lookups do not read credentials or application config.
2. Open only the two fixed retained inputs, regular/single-link/protected owners0 or1002, readonly/nonblocking/NOFOLLOW; keep ancestor FDs and inode/metadata identities. No directory enumeration or runtime-tree traversal. Reads may update source atime; content/mode/owner are never written.
3. Open pwd's canonical protected home using NOFOLLOW directory FDs. Before any new output, open the fixed old `p2-b5-three-files-20261020` directory read-only, require admin0700 and protected admin0600 regular single-link host-result/receipt <=65536 bytes. Require the reported host-result SHA e40abcd5304e4ab0e29c83a4865528272aca2b0ddb97e6d3df8d9941544c3bd6 and HOLD; print bounded receipt state/error and hashes. Missing or mismatched prior evidence stops before creating anything. Do not modify old files. Create exactly one independent new child `p2-b5-three-files-gnu-v2-20261020`,0700; assign only that NEW directory to admin UID/GID. Existing output name causes immediate HOLD, no overwrite/cleanup/new automatic suffix. Existing home and source permissions remain unchanged.
4. Fork one short-lived reader; pass the already-open readonly input FDs and private output-directory FD, close input ancestor FDs in child, clear supplementary groups and drop to actual admin UID/GID. This grants the fixed child read access to those retained archive FDs, not a persistent permission change. No server/Node/SDK process is started. Parent remains root solely for final path-binding check and new summary.
5. Child completely hashes tar and manifest, checks canonical manifest and all20,000 members. Full tar SHA pass precedes parsing; every member's entire content SHA, byte size, numeric UID/GID/mode and unique path must match manifest. Therefore this tool verifies **all20,000 content digests**, not only headers/three targets. Only target bytes are retained in memory; no extraction to arbitrary filesystem paths and no extractall.
6. Build the three-member tar in bounded memory only after full input validation. Write new `three-files.tar` and `receipt.json`,0600/admin-owned, O_EXCL/fsync. Parent checks original path/FD identities again, checks child successful termination/receipt references, independently parses all3 output members and their fixed sizes/SHA, and hashes the resulting archive. Write one new admin-owned0600 `host-result.json`, fsync directory. No prior file is deleted/overwritten.
7. Print only output path, host summary and its SHA. No source content, base64, credentials or transfer/upload is printed/performed. Retrieving the private small archive is a later explicit action; this candidate does not change SSH/credentials or transfer it.

## Parsing/limits

- Input raw tar <=600MiB; actual exact559237632 bytes mandatory. Manifest <=8MiB, actual exact5635704 bytes mandatory. No gzip decompression of input.
- Exactly20,000 regular members, max40,000 tar headers including extensions, max128MiB/member,512MiB summed payload; paths <=4096 UTF8 bytes, PAX payload <=65536 bytes. JSON duplicate fields/paths rejected. Expected selected bytes/SHA are fixed in source, no user-supplied CLI configuration.
- Manual bounded USTAR/PAX/GNU parsing, checksum/numeric/magic/version checks. Reject absolute/traversal/empty/control/backslash paths, duplicate members, hard/symbolic links, device/FIFO/sparse/GNU longlink/global and all non-allowed extensions and nonzero trailing data. Accept only PAX local `path` records (one key, correct byte length/UTF8); reject size overrides, duplicate path, GNU.sparse and xattr keys. GNU support is restricted to CPython3.6.8 regular headers (`ustar  NUL`) and one local L longname (`././@LongLink`, zero metadata, 102..4097 bytes, single terminal NUL, safe UTF8 <=4096 bytes). Require zero old-GNU extension fields, zero padding, exact truncated fallback bytes, and same-format following regular member. Reject nested, mixed-format, dangling, K/sparse/other types and base256 numerics. POSIX prefix is never interpreted from GNU extension fields. Upstream reference: https://github.com/python/cpython/blob/v3.6.8/Lib/tarfile.py (`DEFAULT_FORMAT=GNU_FORMAT`, `create_gnu_header`, `_create_gnu_long_header`). Actual Python3.6.8 execution remains NOT_EXECUTED; explicit GNU writer fixtures reproduce that documented format. This is not arbitrary GNU support.
- A fully matched retained prefix ending exactly at a complete-member boundary without tar end markers may be used, explicitly recorded as MEMBER_BOUNDARY_EOF; truncated header/payload/padding or dangling PAX/GNU longname is rejected. This does not turn a partial original SDK capture into a complete runtime. Normal zero end markers must have only zero padding afterward; concatenated archives rejected.
- Child CPU180s, wall alarm240s, AS384MiB, file-size2MiB, NOFILE128,CORE0. Parent270s watchdog kills/waits the child process group. Primary source I/O is one complete tar digest pass plus one all-member parse/content-hash pass, and bounded manifest passes; no unbounded scan or automatic fallback. Limits are enforced by the child/kernel under ordinary OS operation; missing final receipt remains UNKNOWN after abnormal termination.
- New archive <=1MiB; known selected content419045 bytes fits the bound (envelope tested). The later actual archive SHA is computed from real retained source bytes; no fabricated output hash is frozen before extraction. Source SHA/size and selected SHA/size remain in receipt. O_EXCL files are600 under umask077; no inherited executable/setuid file metadata.

## States and recovery

- Root `THREE_FILES_READY_OFFLINE_ONLY` plus exact archive/receipt hashes means the extraction and readback succeeded. It does **not** mean B5/SDK/production succeeded.
- Child `CHILD_VERIFIED_AWAIT_PARENT` alone is insufficient: root path/readback verification might not have completed. Missing host result =>UNKNOWN/HOLD; do not infer success from a detached process or child code0.
- Any source change, wrong SHA/member/identity, UID failure, budget/timeout/signal, incomplete receipt or output conflict =>HOLD. Preserve all existing inputs and new partial output. Do not rerun this command against an existing directory, remove evidence, re-collect SDK or silently choose another output name.
- Interruption during output may leave a short `three-files.tar` with no receipt; both signal-injection and actual child SIGKILL fixtures cover this retained state. The root may record failure if still alive. If parent itself dies, no final summary can be claimed. Recovery starts with bounded readback of the existing outputs under their original identities, not a new extraction.

## Development verification

30 synthetic archive/filesystem tests: strict GNU regular/long UTF8 including byte100 split; malicious GNU fields/types/nested/mixed/dangling/payload/fallback; bound old-failure readback; correct3-file package; all-content hashing including non-target tamper; full20,000-member GNU longname fixture; complete SHA failure; duplicate/link/device/FIFO/sparse rejection; long/Unicode PAX; malicious/duplicate PAX; source mutation and path replacement; input/output NOFOLLOW/mode and conflict checks; parent independent output digest validation; actual UID1002 FD-isolation in Hosted; actual SIGKILL partial-file retention; declared419045-byte envelope and parser/output limits. Fixtures are synthetic, never the real UK archive.

Local29 passed/1 UID-change skipped because local chown is unavailable. Hosted requires that UID case to run (B5_REQUIRE_UID=1; skip not accepted); results recorded in original PR17. Python3.6 grammar is checked, **actual Python3.6.8/UK execution NOT_EXECUTED**. No previous plugin/snapshot/loader tests are rerun or repackaged. New artifact contains only this tool, complete candidate, explanation and SHA list; no retained UK data. Source filesystem and tar safety tests do not demonstrate SDK exports, dependency closure or authentication.

## Repair execution boundary

Owner reported old child exit2/HOLD; exact child error is still UNKNOWN until original receipt readback. GNU incompatibility is independently proven from source, not asserted as the onsite root cause. The new candidate performs that fixed readback before its independent output attempt; missing evidence stops without writes. Original archive, manifest, failure directory and permissions are retained. No automatic retry or cleanup. This candidate is NOT_EXECUTED in UK and requires separate onsite confirmation. No B5/closure/loader success is claimed.

Additional local provenance check: the unmodified official CPython v3.6.8 `Lib/tarfile.py` was loaded under Python3.12 and used with original `w|` / no format argument / TarInfo metadata rules. Its default GNU archive with five synthetic members including long UTF8 passed all-content verification. This verifies original writer-library bytes, not an actual Python3.6.8 interpreter run.
