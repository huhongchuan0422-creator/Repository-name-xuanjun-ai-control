# Concrete deployment dependencies — installation HOLD

The proposed controller uses the existing Gateway process and existing canonical ledger socket. It does not create a task database, queue, scheduler daemon or new model route.

The socket server authenticates the native Gateway UID separately from the Owner callback UID. Gateway requires access to the exact existing Unix socket, without joining the DB group or gaining database-file permissions. Release must bind the socket's ACL across recreation and verify the actual peer UID.

The active descriptor binary_sha256 must equal the reviewed native transport bytes. Existing Codex binary identity cannot attest a native controller. Switching that binding requires the existing activation cutover, stop proof and same-release freeze; current UK activation was not changed.

Observed installed SDK has runtime.config.current(), request-scoped subagent.run(), sandbox.resolveWorkspaceAuthority(), agent session metadata and before_tool_call. The tool run ID is carried on the hook event. Plugin controller source now checks it there and validates current canonical lease/unit before allowing tool use.

Remaining measured gaps: no explicit current UK worker sandbox configuration; exact effective OAuth store/route not attested by the assumed main auth-profiles path (it was missing); no installed immutable context dependency manifest, native plugin binding file, socket client config or updated dispatcher unit. Docker binary alone is not Docker access/image/read-only/isolation proof. SDK read-only QA workspace mapping still requires an actual verify-only test. These dependencies must be made concrete and reviewed before giving an install command.

Source regression is not installation, OAuth consumption, rollback, unknown-effect reconciliation or real E2E proof. Old unknown execution f998 is never replayed. No UK writer/lease/epoch/model/config/install mutation was performed.
