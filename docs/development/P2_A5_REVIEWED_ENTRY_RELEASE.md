# P2 A5 reviewed entry registration

## 1 Design

Register only the independently reviewed A5 read-only metadata preflight entry from exact source `c8c23711f112558d35ceb8a6a1eea4088e35806a`. This is not the P2 business installation, runtime-policy installation, or release. The workflow requires explicit manual dispatch and a protected environment; a normal PR or push cannot execute a UK command. All six original source files are byte-identical to the accepted source. Source approval: PR58 #6232627191, limited to source/artifact. This new governance record itself requires a separate incremental review.

## 2 Development

The source is registered through a narrow PR forked from main rather than merging the diverged P2 development branch. GitHub Feature Compliance requires these new executable scripts and tests to have an explicit feature registry entry. The registry lists the four new Python paths and protected workflow; it does not grant credentials, production permission or a release status.

Acceptance prerequisites: the exact release PR's CI and original SHA parity; independent protection/reviewer/ref/actor verification, actual namespace non-replayable claims and custody verification; separately issued short-lived and attempt-bound permission; UK site script hash and ownership readback and global canonical writer evidence. The A5 source permit is **not** a live permit. No execution or merge is authorized here. The original PR17 remains the sole execution ledger.
