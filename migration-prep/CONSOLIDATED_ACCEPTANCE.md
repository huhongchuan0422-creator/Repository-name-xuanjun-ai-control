# PR99 consolidated acceptance and migration gates

Consumed independent review: issuecomment-6165413654, reviewed HEAD 297a2b3698c0d80418b26c59772bda6d6cb8d99b.

## Scope of this candidate

Descriptor-relative O_NOFOLLOW traversal binds every parent and the final regular file to opened objects. Ownership/mode are checked via fstat; bytes are hashed from that same descriptor and metadata is checked after reading. Reopening sources catches persistent replacements. This does not defend against concurrent malicious root mutation or establish which source files sudo actually consumed. That limitation remains explicit.

The textual sudo grant checker is only a shape check. It is not a sudoers semantic engine. Output now independently reports source_closure and effective_policy_semantics NOT_VERIFIED. Never convert these to PASS from unit tests, source hashes or sudo -l text.

Tests cover descriptor reads, parent/file symlink rejection, writable parent/file rejection, wrong owner, malformed paths, command failure and timeout, plus the existing five parser cases. Hosted tests do not run root audit on either host.

## Single acceptance batch required before production

| Gate | Required evidence | Current status |
| --- | --- | --- |
| Root local source audit | Native sudo parser/plugin version; actual policy-source closure including external policy plugins; Defaults scope, aliases, rule precedence, Runas/tags, environment and command authorization reviewed privately | NOT_VERIFIED |
| Host execution | Reviewed immutable candidate provenance, trusted root-local invocation on both fixed hosts, private bounded receipts and exact runtime version; no new runner sudo grant | NOT_RUN |
| Runner admission | Administrative inventory of repository/group assignments, allowed workflows/ref restrictions, fork/PR exposure, and any other runners with production reach; verify controls apply globally | NOT_VERIFIED |
| Backup and restore | Consistent encrypted production snapshot and Korea Yibi backup in private storage; restore rehearsal and checksum receipts without public raw paths/data/secrets | NOT_RUN |
| Korea retirement | Stop only inventoried Yibi units/timers after backup; preserve novel and dependencies; tested reversible start procedure | NOT_RUN |
| Isolated deployment | Dedicated user/directories/secrets/ports and resource limits; exact verified artifact; novel/domestic-model tunnels inventoried and rerouted where needed | NOT_RUN |
| Trading validation | Read-only credentials, shadow run, restart recovery, position/order reconciliation; no duplicate orders | NOT_RUN |
| Exclusive writer | Proven Tokyo writer stop/fence and authoritative lease; Korea cannot write before acquisition; rollback fences Korea before Tokyo restarts | NOT_RUN |
| Cutover | Bounded canary, explicit health/reconciliation thresholds, timed rollback and observation receipts | HOLD |

This public repository's workflow-local conditions are not an admission boundary. Current connector capabilities do not expose runner administration; repository settings proof must come from authenticated administrative access, not an inferred workflow scan. Do not add production sudo privileges to the existing shared runners while this is unknown.

Retain PR99 Draft. No merge, Yibi stop, production deployment or order write is implied by this candidate. Tokyo to Korea remains the direction; novel retained; UK remains control/development only. Original Work17/P2 source and queues are not changed.
