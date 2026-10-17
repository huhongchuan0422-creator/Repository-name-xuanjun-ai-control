# P2 Work six-path transport handoff

Owner/dots delegation: PR58#6228357313 and exclusive stop confirmation
PR58#6228383533. Eight existing paths remain with the original writer.
Base commit: 8f1fb29ebec1fa65dd4c04d1ca606860eb162de3.

## Implemented offline scope

The six new paths implement an injectable UK-only transport library and strict
public receipt validator. This is not the original blocked diagnostic package,
and does not contain or encode it. The only command is a fixed stdlib identity
statement, no application imports or reads of private files. Its unique nonce
and exact script SHA are bound before submission. Accepted response cannot
contain extra fields/private evidence. Public results explicitly retain
p2_accepted=false. This does not replace actual private-completeness evidence.

Target is only eu-west-1 / 40dfc6a47d5e4363b9da7d0d6ab01cb1 /
iZd7oeikknn1z21sq6ji6zZ, role
acs:ram::1107191612880779:role/xuanjun-ai-esc. No other host tuple exists.
Reference transport is the existing fixed identity workflow at
4ee0216dc2ebfe3bedfc553783345ddc181d5606; it is unchanged and never replayed.

A caller-provided persistent protected directory is held by fd, must be 0700
and owned by its execution uid. Records are immutable O_EXCL/NOFOLLOW 0600,
fsync file and directory before continuing. dispatch-intent.json consumes the
attempt BEFORE RunCommand; invoke.json is saved after a valid InvokeId response.
Unknown response or failure before saving InvokeId leaves intent consumed and
requires separate investigation, never automatic RunCommand retry. Existing
InvokeId may only be queried; no code path in polling issues RunCommand.
Terminal accepted/rejected records prevent ordinary re-poll. Query limit or
transport uncertainty never becomes PASS. Failed receipt persistence also
keeps the exclusive attempt; it is not permission to dispatch again.

## Important external conditions

This library deliberately has no live CLI and no authenticated RPC adapter.
The workflow is offline test/build only: no Secrets references, STS requests,
SWAS invocation, workflow_dispatch, repository_dispatch or machine operation.
It is NOT a usable production entry or a substitute for explicit trigger tools.
Adding a remote adapter/trigger requires a separate reviewed caller with exact
one-use permission, source hashes, host binding and durable process ownership.
The directory must be unique per approved attempt, protected from substitution
by its parent custody, and on a proven durable filesystem. Reusing another path
must not be used to bypass the one-attempt intent. The library itself cannot
prove global unique writer or enforce a business approval from arbitrary Python
callers; those are mandatory caller and execution-gate checks.

poll_existing uses bounded query count; a future authenticated adapter must
set request timeouts and backoff/rate policy. This code does not claim wall-clock
termination for an arbitrary injected rpc function. Unknown outcomes retain
state and do not automatically re-dispatch. Full process kill/restart, filesystem
failure matrix, root provenance and live API response semantics remain target
acceptance items, not claims inferred from these unit tests.

## Privacy and production restrictions

Seed/history Seed/Plan/Packet remain in the original protected UK directories.
Do not publish originals, raw remote output, client exceptions, tokens, signed
URLs or private receipts into GitHub/logs/artifacts. No recipient/transfer
protocol is implemented; recipient authentication stays UNKNOWN and transfer
is prohibited until reviewed. TTY preview and dual SHA confirmations are not
emulated. The blocked original package is not republished by this writer.

Existing reviewed runtime, Schema3 and install controls inherit unchanged.
P2_RELEASE=HOLD; SCHEMA3_APPROVAL=NO; C_INSTALL_AUTHORIZATION=NO.

## Validation

20 local methods passed: 8 receipt methods and 12 transport methods. Adapter
responses and temporary ledgers are fixtures, not STS or Root proof. CI tests
exact revision and builds a 6-source-file manifest, plus log and manifest in an
8-member TAR. 3.6 AST syntax check does not prove Python3.6 runtime compatibility.
Future actual invocation must record InvokeId and terminal state in original
PR58/PR17 with only permitted redacted fields. Never call an identity transport
result private-completeness, installation or production acceptance.
