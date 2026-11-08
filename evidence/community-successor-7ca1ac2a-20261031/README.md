# Community successor remote handoff (Issue #76)

This branch is a transport-only recovery for the local frozen successor `7ca1ac2a`.
It is not the source branch, not an installer, and must not be merged as business code.

The gzip file contains the exact binary Git diff from base
`e23e1868b16f6c4c3f30f158418e6557037df28e` to successor
`7ca1ac2a4e5a68704bb0cebe1c33049713070859`.

Before reconstruction, verify both compressed and uncompressed SHA-256 values
from `MANIFEST.json`. Reconstruction is valid only when the resulting commit/tree
match the manifest. Prior developer tests do not satisfy independent QA, security,
release, installation, or mini-program listing gates.

Canonical task: Issue #76. Final business result remains mini-program submission,
approval, listing, and online readback.
