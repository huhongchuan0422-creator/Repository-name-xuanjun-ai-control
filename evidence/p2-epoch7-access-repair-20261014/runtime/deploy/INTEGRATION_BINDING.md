# Integration artifact binding

The schema-2 manifest binds every installed byte by SHA-256 and records the
authorized parent plus contract digest. The outer frozen commit and tree are
supplied as immutable Release Gate inputs; the verifier reads `HEAD`,
`HEAD^{tree}` and `HEAD^` from the same source root and requires all three to
match. This avoids the impossible/self-referential claim that a checked-in file
can contain the hash of the commit that contains that file. The verifier fails
closed on missing, extra-path, symlink, commit/tree/parent or digest mismatches. The atomic
installer copies only manifested bytes into a new immutable version directory
using an atomic directory rename. The release-directory identity is the typed
value `integration-<manifest_sha256[0:16]>`; the artifact identity is the full
64-lowercase-hex manifest SHA-256. They cannot be substituted. The installer
renders both tokens deterministically, rejects unknown or unresolved identity
tokens, verifies the rendered bytes and argv/path bindings, and then performs
the atomic rename. Units bind the exact directory; no mutable `current` symlink
is used at runtime.

The final Git commit cannot contain its own commit hash. Therefore the
commit/tree and manifest SHA-256 are an external freeze receipt, while the
checked-in trust root is the authorized parent/contract plus complete per-file
manifest. Installer invocation requires all external identities together.

Schema migration is a separate backup-first staging gate. Neither manifest
verification nor installation activates systemd, nginx, a webhook, or a DB.
The required Owner-workbench renderer is itself a manifested immutable file;
its target, root ownership, `0555` mode and exact invocation are manifest-bound.
Rollback likewise uses a reviewed exact-directory/hash/unit/config map and
direct immutable backup paths, never a mutable release symlink.
