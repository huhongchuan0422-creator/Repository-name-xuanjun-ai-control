# B5 retained archive three-file tool — candidate, NOT_EXECUTED in UK

Task PR17 #6289056886; baseline931893e44b33762c27e16f29a30e4adcfabf9f4e. Only new tool/tests/candidate. Original source capture, readonly plugin, B1–B4 and applicable CI are inherited. No reinstall, new source capture, live SDK traversal, Node/SDK execution, network operation or input permission change.

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

Complete self-contained command: `THREE_FILES_CANDIDATE.sh` in this directory. Source is embedded; it does not download a script or invoke any network tool. SHA256 `7d695fdec27f07201286c9ccad5948a4550db4182733d5ab9a8f807226a6fdbe`.

Tool `scripts/p2_b5_three_files.py` SHA256 `3407caaeb9e2ee37e00dcb863ad24251c6ee14b56ae7daf47c23fcbbe2687c58`.

This is a candidate for separate on-site confirmation, not an instruction to execute now. No placeholders, runtime installation, package download or source re-collection are hidden inside it.

1. `sudo -n /usr/bin/python3 -I -B -S -` on fixed UK hostname iZd7oeikknn1z21sq6ji6zZ; root and exact host Python3.6.8 guard. Resolve local admin identity/home with pwd; admin must be a nonroot identity separate from1002. These lookups do not read credentials or application config.
2. Open only the two fixed retained inputs, regular/single-link/protected owners0 or1002, readonly/nonblocking/NOFOLLOW; keep ancestor FDs and inode/metadata identities. No directory enumeration or runtime-tree traversal. Reads may update source atime; content/mode/owner are never written.
3. Open pwd's canonical protected home using NOFOLLOW directory FDs. Create exactly one new child `p2-b5-three-files-20261020`,0700; assign only that NEW directory to admin UID/GID. Existing output name causes immediate HOLD, no overwrite/cleanup/new automatic suffix. Existing home and source permissions remain unchanged.
4. Fork one short-lived reader; pass the already-open readonly input FDs and private output-directory FD, close input ancestor FDs in child, clear supplementary groups and drop to actual admin UID/GID. This grants the fixed child read access to those retained archive FDs, not a persistent permission change. No server/Node/SDK process is started. Parent remains root solely for final path-binding check and new summary.
5. Child completely hashes tar and manifest, checks canonical manifest and all20,000 members. Full tar SHA pass precedes parsing; every member's entire content SHA, byte size, numeric UID/GID/mode and unique path must match manifest. Therefore this tool verifies **all20,000 content digests**, not only headers/three targets. Only target bytes are retained in memory; no extraction to arbitrary filesystem paths and no extractall.
6. Build the three-member tar in bounded memory only after full input validation. Write new `three-files.tar` and `receipt.json`,0600/admin-owned, O_EXCL/fsync. Parent checks original path/FD identities again, checks child successful termination/receipt references, independently parses all3 output members and their fixed sizes/SHA, and hashes the resulting archive. Write one new admin-owned0600 `host-result.json`, fsync directory. No prior file is deleted/overwritten.
7. Print only output path, host summary and its SHA. No source content, base64, credentials or transfer/upload is printed/performed. Retrieving the private small archive is a later explicit action; this candidate does not change SSH/credentials or transfer it.

## Parsing/limits

- Input raw tar <=600MiB; actual exact559237632 bytes mandatory. Manifest <=8MiB, actual exact5635704 bytes mandatory. No gzip decompression of input.
- Exactly20,000 regular members, max40,000 tar headers including extensions, max128MiB/member,512MiB summed payload; paths <=4096 UTF8 bytes, PAX payload <=65536 bytes. JSON duplicate fields/paths rejected. Expected selected bytes/SHA are fixed in source, no user-supplied CLI configuration.
- Manual bounded USTAR/PAX parsing, checksum/numeric/magic/version checks. Reject absolute/traversal/empty/control/backslash paths, duplicate members, hard/symbolic links, device/FIFO/sparse/GNU/global extensions and nonzero trailing data. Accept only PAX local `path` records (one key, correct byte length/UTF8); reject size overrides, duplicate path, GNU.sparse and xattr keys. This matches the original Python snapshot maker's long/Unicode name records; it does not claim to accept all possible generic tar extensions.
- A fully matched retained prefix ending exactly at a complete-member boundary without tar end markers may be used, explicitly recorded as MEMBER_BOUNDARY_EOF; truncated header/payload/padding or dangling PAX is rejected. This does not turn a partial original SDK capture into a complete runtime. Normal zero end markers must have only zero padding afterward; concatenated archives rejected.
- Child CPU180s, wall alarm240s, AS384MiB, file-size2MiB, NOFILE128,CORE0. Parent270s watchdog kills/waits the child process group. Primary source I/O is one complete tar digest pass plus one all-member parse/content-hash pass, and bounded manifest passes; no unbounded scan or automatic fallback. Limits are enforced by the child/kernel under ordinary OS operation; missing final receipt remains UNKNOWN after abnormal termination.
- New archive <=1MiB; known selected content419045 bytes fits the bound (envelope tested). The later actual archive SHA is computed from real retained source bytes; no fabricated output hash is frozen before extraction. Source SHA/size and selected SHA/size remain in receipt. O_EXCL files are600 under umask077; no inherited executable/setuid file metadata.

## States and recovery

- Root `THREE_FILES_READY_OFFLINE_ONLY` plus exact archive/receipt hashes means the extraction and readback succeeded. It does **not** mean B5/SDK/production succeeded.
- Child `CHILD_VERIFIED_AWAIT_PARENT` alone is insufficient: root path/readback verification might not have completed. Missing host result =>UNKNOWN/HOLD; do not infer success from a detached process or child code0.
- Any source change, wrong SHA/member/identity, UID failure, budget/timeout/signal, incomplete receipt or output conflict =>HOLD. Preserve all existing inputs and new partial output. Do not rerun this command against an existing directory, remove evidence, re-collect SDK or silently choose another output name.
- Interruption during output may leave a short `three-files.tar` with no receipt; both signal-injection and actual child SIGKILL fixtures cover this retained state. The root may record failure if still alive. If parent itself dies, no final summary can be claimed. Recovery starts with bounded readback of the existing outputs under their original identities, not a new extraction.

## Development verification

23 synthetic archive/filesystem tests: correct3-file package; all-content hashing including non-target tamper; full20,000-member fixture; complete SHA failure; duplicate/link/device/FIFO/sparse rejection; long/Unicode PAX; malicious/duplicate PAX; source mutation and path replacement; input/output NOFOLLOW/mode and conflict checks; parent independent output digest validation; actual UID1002 FD-isolation in Hosted; actual SIGKILL partial-file retention; declared419045-byte envelope and parser/output limits. Fixtures are synthetic, never the real UK archive.

Local22 passed/1 UID-change skipped because local chown is unavailable. Hosted requires that UID case to run (B5_REQUIRE_UID=1; skip not accepted); results recorded in original PR17. Python3.6 grammar is checked, **actual Python3.6.8/UK execution NOT_EXECUTED**. No previous plugin/snapshot/loader tests are rerun or repackaged. New artifact contains only this tool, complete candidate, explanation and SHA list; no retained UK data. Source filesystem and tar safety tests do not demonstrate SDK exports, dependency closure or authentication.
