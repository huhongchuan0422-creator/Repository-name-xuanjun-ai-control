# Fixed saved-input completeness evidence

## Important: narrowed independent recomputation scope

To avoid exposing sensitive credential/profile/configuration digests, this version
withholds the complete retained delta, access rows, acceptance contract and full
resource views as opaque, keyed commitments. It does not provide independent
offline reconstruction of their original roots. The original reviewer must decide
whether this narrower evidence is sufficient; source review is not a claim that
every originally requested independent preimage check has been supplied.

This package implements the evidence method accepted for private review. It does
not issue a Schema 3 approval or authorize a host execution, preparation,
installation, recovery attempt, claim publication or service operation. The
command template remains unauthorized. A source review and a separate Owner
permission for one precisely scoped run are required before execution.

## Three evidence layers

1. The Owner runs the reviewed protected reader on the fixed UK host. It reports
   the identities and protected read/reread results for four exact saved files.
2. The authenticated, unchanged compiler reconstructs the private inputs and
   compares the exact proposed Plan and unsigned review body. Private inputs stay
   in host memory.
3. A reviewer, with the already received Plan and Packet, independently recomputes
   the exported safe derived objects and target structure. This is layered Owner evidence and
   offline recomputation, not remote attestation or independent access to hidden
   Seed bytes or the host.

No new or historical Seed is embedded in this public package. The public tests
use synthetic inputs and real public compiler bytes. Actual Seed contents have
not been obtained locally. The already received exact Plan and Packet were
checked separately; they are not public fixtures.

## Fixed identities and content reads

The private content input set is exactly four existing files in the fixed
complete-install candidate directory, in this order:

| Role | Filename | Bytes | SHA-256 |
|---|---|---:|---|
| New Seed | epoch7-lifecycle-resume-inputs-d7eabd4c0716bd23.private.json | 770702 | d7eabd4c0716bd23c35a210c0ace8493b8a9f23237d1df1eeef231fdda8d16f0 |
| Historical Seed | epoch7-resume-inputs-6de7d12246826388.private.json | 769086 | 6de7d12246826388949723e9238cd464686e6e86847187946837df927c97a550 |
| Plan | epoch7-lifecycle-approved-plan-5b3a34222dc634d9.private.json | 140648 | 5b3a34222dc634d95b4e070105de9afb3dc24b5c53f7b6497bc61d392887fb01 |
| Packet | epoch7-lifecycle-review-packet-2bf597ef911cba70.private.json | 29665 | 2bf597ef911cba70b5c94559ee36d8f90c2a339a3de1bfd2d8f58547900b8dec |

The directory is `/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520`.
The reader requires root:root, regular files, mode 0600, link count 1, no extended
ACL or capability attributes, no-follow descriptor traversal, exact size/hash,
path/descriptor identity stability, and final exact rereads of all four files.
It separately authenticates the fixed 0444 entry before executing it, and verifies
all 256 cached kit files before and after compilation. Existing ancestor and
loader authority checks are retained. Any failure stops without proof payload.
Reported metadata and final-reread equality remain Owner-terminal claims; an
offline JSON object is not a cryptographic host-attestation mechanism.

The original Seed has 12 fields; the successor Seed has those same fields plus
`claim_successor`. The tool requires canonical equality of all original private
values and exact equality of the new claim to the existing Packet. Hydration
adds five authenticated public fields, resulting in 18 compiler inputs; the
factory derives 19 more, resulting in 37 final top-level fields. These counts
refer to different stages, not competing schemas.

## Compiler and approval boundaries

The installed compiler is fixed to source
[105996ed06a0bdb5d025914cf08ebd448425f739](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/commit/105996ed06a0bdb5d025914cf08ebd448425f739),
tree `343d315b3ead6266a626b5875dbdd6c2fa0309af`, manifest
`91252ba75c38b4a6d12f9b64eb06cb8793fabd97f03646bece97224178c28392`.
The entry is 56593 bytes, SHA-256
`21a982161bc4cb8ffd7e67e4b9a8e24bf23916df6d78c3dd43376af3cfb34890`.
The dependency publication is
[e2df38160e635af96dcfd63a1b75cf64671e4935](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/commit/e2df38160e635af96dcfd63a1b75cf64671e4935),
and final delivery is
[40a03182fe07ded1ff75fd3de3d16ecfbb396f73](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/commit/40a03182fe07ded1ff75fd3de3d16ecfbb396f73).
The selected archive is 1074448 bytes, SHA-256
`bd3708d5887c4dc2b866e9e0acb04da426e71ad88d89c23fe2576b5ed943a2c3`.
It contains 257 files; the original 107 runtime payloads and 16 business phases
are unchanged. This tool does not amend the kit or its approval parser.

The unsigned body in the actual Packet is 7968 canonical bytes, SHA-256
`35c6fd49a18845542c01c65b0f870cef1626b841e2daba138a687e4137d4a1f5`,
with proposed admission expiry `2026-10-16T18:00:00Z`. Its approval ID and approval
body-hash result fields are null. A candidate `decision` field is not a signed
approval. This evidence tool neither refreshes that expiry nor grants C admission.

The pure call chain is verified entry/cache loading, `_hydrate_seed`,
`prepare_host_inputs`, `compile_host_contract`, the existing proposal and timer
compilers, complete preimage construction and offline-equivalent validation.
The actual factory must report `COMPILED_NOT_ADMITTED`, unresolved `[]`, and
`install_admission: false`. The complete proposed Plan and body must match.
Both identity additions receive their existing compiled-object validation.
The original public renderer executes authenticated public installer code to
render bytes; no private Seed, JavaScript, configuration or source is executed.
No driver assembly, resume, claim, phase, approval publication or runtime
acceptance operation is called.

## Confidentiality and complete preimages

The authenticated on-host program first reconstructs and validates the complete
24 retained target deltas, both complete additions, access rows, acceptance
contract, saved timer baseline/contract, all 17 by 15 resource sections and
directory states. Strict original schemas and full bindings are checked before
privacy projection. Missing, extra, unsupported or malformed inputs cause HOLD.

The exported projection then has this exact independent-review boundary:

| Material | Offline check | Hidden original binding |
|---|---|---|
| 24 retained targets | Exact order, fixed target path/role, operation, object kinds, UID/GID/mode and closed safe structure | Original content and complete retained-delta root checked onsite only |
| Both complete identity additions | Full original object structure and additions root recomputed | Identity payload content remains private |
| Saved timer baseline and contract | Full original objects and bindings recomputed | No current timer observation or action |
| Directory states | Full original metadata objects and aggregate root recomputed | Owner report of original source/authority |
| Access rows | Whole opaque domain-separated HMAC only | Original security root checked onsite only |
| Acceptance contract | Whole opaque domain-separated HMAC only | Original acceptance root checked onsite only |
| All 17 by 15 resource views | Whole opaque domain-separated HMAC and finite count coverage only | Original section/checkpoint/full-view roots checked onsite only |
| Retained/full delta | Safe 24-target structure plus whole opaque HMAC only | Original delta/full-delta roots checked onsite only |

The complete original objects are never replaced and presented as their original
preimages. A privacy projection has its own explicit schema and verification
status. The offline result lists five affected derived roots as onsite-only, never as a
successful independent root recomputation. The full typed input root is a sixth,
separate onsite-only root, explicitly declared in hidden_inputs. No deduplicated hidden resource row
is retained elsewhere in the output. Whole affected segments are withheld,
rather than exposing almost every aggregate preimage together with a hidden
low-entropy leaf. This reduces newly disclosed guessing material; it does not
claim to eliminate every possible inference from previously public contracts.

Raw observations, six retained UTF-8 buffers, rendered configurations, identity
payloads, environment, arbitrary argv/ExecStart, source/configuration bodies and
customer data are not output. The entire acceptance_facts/service_facts objects
are not exported. Python identity, Node alias proof, NSS, activation and all other
nested resource forms use exact sub-schemas; arbitrary nested dictionaries are
not passed through. Existing JSON projection specs already contain field paths
and digests; this tool preserves those exact original specs rather than removing
values from a different object and claiming the same hash.

For hidden inputs, a fresh random 32-byte HMAC key remains only in process memory.
A separate public 16-byte nonce, versioned structural domain, Seed identities and
field names are included in each commitment. The 37 original child fingerprint
hashes and secret scalar values are never exported. The key is not exported,
persisted or derived from the public nonce; no secure memory-erasure claim is made.
The offline reviewer can check the commitment structure, but cannot validate its
binding to the hidden Seed or recompute the secret input root. A well-formed
replacement commitment is not independently detectable. Only the on-host pure
compiler checks the complete original input root against the Plan.

The output still contains internal paths, identities, ACL metadata, credential
file names and file hashes. It is private operational evidence, not anonymized
or suitable for public GitHub. Compression is not encryption. A later Owner
permission must identify the private review recipient and purpose.

## Inherited OS reads and execution limits

The four-file restriction is the private content-input set, not an OS sandbox.
Authenticated kit/cache and interpreter modules are also read. The unchanged
pure compiler performs canonicalization metadata queries for
`/var/lib/xuanjun-development/generations/1/state.sqlite` and
`/run/xuanjun-development/ledger.sock`, including ancestors and possible symlink
target metadata before alias rejection. It does not open database/socket
contents, connect to SQLite or the socket, or perform a live DB/TLS/process probe.

The reviewed cold UUID adapter blocks optional ctypes discovery while loading
the genuine standard-library UUID parser. Later unchanged compiler modules still
import ctypes. Interpreter/native-library initialization remains an inherited
trust boundary; this is not an OS-level zero-side-effect guarantee or sandbox.
At application level the tool creates no files, acquires no installation locks,
runs no subprocesses, calls no service or network API, and changes no permissions.
File access times may change. The only intended output write is stdout.

One-shot alarm plus monotonic terminal checks bound validation/encoding to 120
seconds and stdout emission to a separate 10 seconds. These are not hard-real-time
guarantees. Cleanup preserves a primary failure and reports unknown cleanup
rather than fabricating success. Output failure never retries the compiler or
starts a second host operation.

## Transport and offline verification

One complete proof object is validated before output. Its raw limit is 16 MiB;
a single in-memory gzip member is limited to 70000 bytes, and the exact JSON
Base64 envelope including LF is limited to 98304 bytes. The complete-public-
factory synthetic fixture measured 319879 uncompressed preimage bytes and 53973 compressed bytes for the full
proof before runtime fields, before the additional privacy projection. This is a
capacity example, not a measurement of the unavailable actual Seed. Actual
unsupported shape or excess size returns HOLD with no proof payload; there is
no automatic splitting, rereading, truncation or row deletion.

The offline verifier requires the previously received exact Plan and Packet as
separate local inputs. It authenticates this reviewed package's producer/schema
bytes against SOURCE_MANIFEST.json, loads the authenticated schema bytes directly,
and accepts one strict proof or one bounded single-member gzip envelope. It
rejects duplicate keys, nonfinite/nonnative number forms, excessive nesting,
noncanonical Base64, trailing gzip members/data, missing sections and wrong
length/hash. It outputs only bounded fixed checks and limitations, never rejected
private data or arbitrary exception text. This does not add network or host access.

## Tests and review status

The new suites cover strict nested schemas, complete onsite resource reconstruction,
whole-segment privacy projection and explicit onsite-only offline statuses,
protected fixed-file reading, HMAC privacy boundaries, whole-package bounds,
clean authenticated schema loading, actual public-factory synthetic composition,
error redaction and one-output/no-reentry behavior. Source-manifest rows bind the
exact files under review. New Hosted validation uses only official Python images
on Ubuntu-hosted runners and public synthetic fixtures. It executes only these
new suites; existing test modules may be imported solely as fixture definitions.
Exact final counts and source/Hosted results are recorded in the concentrated
review request after the bytes and corresponding runs are frozen. Local partial
results or inherited compiler CI are not proof of a successful actual Seed run.

SOURCE_MANIFEST.json records logical package basenames. The Hosted fixture maps
the three published tests/test_p2_private_completeness_*.py files back to those
logical sibling basenames; no private files are included in that package.
