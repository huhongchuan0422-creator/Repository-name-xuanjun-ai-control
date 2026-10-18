# R1-R4 exact-source integration candidate

Base: `86c5c36c982c4e0d047e7645b18415c32ffa6098`.
The earlier excerpt-based patch is not used.

R1/R2 archive identity is retained: source
`0bd83e6fb418ae04d4351b1de7eaf11a0325dd80`, tree
`5d790e58f9f644985fdf063dfc1466eb9b28e66f`, archive 1074452 bytes,
SHA256 `42d6d98f0fb1b1436f348a4ab70b2a9d91dd02e1ad085f49ecb2eb5c096d4465`.
All 257 archive files, 256 manifest pins and 107 runtime payloads are checked by
the original extractor and loader. Kit, helpers and sixteen business phases are
unchanged.

R3: `render_memory_launcher.py` renders a complete command that downloads and
hash-verifies the entire Delivery source into memory. It never places a launcher
in the strict one-file preparation directory or inside the kit. The renderer
requires an exact published Delivery commit and explicit UTC expiry, prints the
command bytes to stdout and their SHA256 to stderr, and performs no execution.
No expiry, admission, review identity or installation authorization is invented.

R4: the compiler lives under
`CAND/epoch7-v2-0bd83e6f/epoch7-recovery-candidate-r7-claim-lifecycle`.
The preparer lives under
`CAND/epoch7-preparation-candidate-r7-claim-lifecycle-v2-0bd83e6f`.
The original lifecycle/resourcebind directories are never overwritten. The new
preparer walks every descendant component of NEW_ROOT with descriptor-relative
O_NOFOLLOW opens and records each component for the original rechecks.
The version parent has strict inventory and mode/owner/ACL checks. Empty retained
parents, partial kits, links, extra files and altered content cause HOLD; no
partial attempt is repaired. An exactly verified complete kit may be reused.
Private publication retains O_EXCL and O_NOFOLLOW and never replaces outputs.

`run_r14_ci.py` creates a new local namespace under `/`, copies only public test
inputs and authenticates the old archive before loading its fixture definitions.
This avoids weakening protected-ancestry checks for hosted workspace permissions.
The integration suite uses real loopback HTTP downloads, the exact published
archive, the embedded extractor, real old/new Kit verification, full preparer
orchestration, new Kit imports, pure compilation, real three-output publication
and final rechecks. The `prepare` implementation is never mocked.
Fixed candidate paths and hostname are mapped to disposable local fixtures.
Unavailable original private inputs/host observations and four native byte pins
are explicitly synthetic; their real production validity is not claimed.
Fault cases inject system-call failures rather than replacing the orchestrator.

Historical fixed-version suites and assertions are unchanged. They describe their
own immutable versions, not this new candidate. Their previous source/binding
assertions must not be rewritten into new-version assertions.

The changed preparer is published at
`6e719dd8f43f2a43c41c6437d91ca29fa2b9cef8` and PUBLICATION_COMMIT is bound
to that exact commit. Its complete source bytes and length are pinned by SOURCES.
The local suite supplies a separate explicit loopback publication fixture.

P2_RELEASE=HOLD. No UK commands, old prepare, installation, approval signing,
production service, claim or rollback operation belongs to this change.
