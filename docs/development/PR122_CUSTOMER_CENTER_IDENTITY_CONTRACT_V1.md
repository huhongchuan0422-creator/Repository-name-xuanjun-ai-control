# PR122 identity authorization and explicit linkage V1

Owner scope: PR122 #6315079509. Shared contract registration: #6315137611.
Base: 58b1dbbc51dbd7c70bf31e2f4f2afd021d41fbe8, tree
b04cf9b0f9dc81757bcc66f7a1343ae8c6dea270. Window5 owns PR122 files;
Issue76 window4 owns community consumers and store authorization; the domestic
writer owns its existing CRM read wrapper. These are separate active paths.

This is mechanism source, not a deployed identity service or real linkage.
Existing Center.session/project, account database, project authority and audit
remain authoritative. There is no new IAM, automatic identity matching, remote
Center database proxy, credential provisioning, or round-trip fallback.
The brand review archive remains bound to caaac435 and is not rebuilt here.

## Shared request and browser boundary

Canonical bytes are UTF-8 JSON, sorted keys, no insignificant whitespace,
ensure_ascii=False, no duplicate keys or nonfinite numbers. Strict field sets
apply; caller-supplied store grants, email, phone, provider-verification flags,
roles, domestic IDs or extra fields are rejected.

POST /customer/center/api/authorization uses the original fixed same-origin
Host/Origin, __Host-xj_customer cookie and X-CSRF-Token. Request fields:

| Field | Contract |
|---|---|
| schema | PR122_IDENTITY_AUTHORIZATION_V1 |
| request_id | Unique per caller, persisted even after token expiry/consumption |
| caller / audience | Exact protected service identity and its configured audience |
| user_id | Must equal the original authenticated Center session user |
| tenant_id / project_id | Must equal the current authorized project subject |
| operation | community.access or crm.customer.read, explicitly enabled per caller |
| issued_unix / expires_unix | Strict integers; issued <= now < expires <= issued+30 |

Identifier fields use [A-Za-z0-9_.:-]{1,128}. This request declares desired scope;
it does not prove any identity. The actual session/project/policy/map checks do.
OFFICIAL_LOGIN_ONLY_V1 denies both new routes before DB access. FULL without
explicit identity service trust also denies them. Existing login scope is unchanged.

Successful issue response is the exact request scope plus authorization_token
(opaque 256-bit random token) and store_authorized=false. The browser session
never travels to the downstream service. Tokens are stored hashed; the original
session token retained for fresh validation is encrypted with the original data key.
Request IDs cannot be reused to mint a replacement authorization after an unknown
network outcome. The history bound is 100000 grants; reaching it holds issuance,
not silent deletion/reset of replay protection.

## Authenticated one-use consume

POST /customer/center/api/authorization/consume is a service MAC boundary,
not cookie authentication. No browser Origin is required for this exact route;
valid service MAC, exact scope, live session, current project and live mapping
are all mandatory. Method is POST only and service payload is bounded to 8192
bytes. It does not return login cookies or accept HTTP mapping imports.

Body = {payload, signature}. Payload = the ten scope fields above plus
authorization_token; do not echo store_authorized from the issue response.
Signature = lower-case hex HMAC-SHA256(service_key,
UTF8('/customer/center/api/authorization/consume') + LF + canonical(payload)).

Consumption holds the existing SQLite writer transaction, checks the exact
encrypted issued scope, reruns Center.session and Center.project with configured
role requirements, checks tenant, live mapping/version, authority revision and
unchanged role, marks used and appends the original audit before commit.
Audit failure rolls back consumption. A committed consume cannot be replayed,
including after process restart or a lost response. No business write occurs here.

Success body = {payload, signature}. Response payload = the original ten scope
fields plus domestic_customer_id, mapping_id, mapping_version, authority_revision,
project_role, store_authorized=false and decision=PROJECT_AUTHORIZED.
Response MAC domain is UTF8('PR122_IDENTITY_AUTHORIZATION_V1:response') + LF
+ canonical(response_payload), using the same purpose-scoped caller key.
No authorization_token or evidence body is returned in the consume response.

Consumer obligations: verify MAC with the configured peer key, exact expected
request/caller/audience/user/tenant/project/operation/time, and strict response
types before use; persist its own request/reference replay handling. An expired,
unknown, mismatched or unavailable result does not authorize new work. A result
is a project authorization snapshot at consumption, not continuous distributed
locking or a store/payment grant. Community must check its current store/employee
rules before its own operation; OWNER does not mean all-store administrator.
For later privileged operations obtain fresh authorization; never replay a write
whose outcome is UNKNOWN. This component adds no network or business retry.

## Mapping and original protected operator boundary

New command: original pr122_customer_ops.py import-identity-mapping --input
<existing root-private mapping document>. It retains the original fixed host,
root admission, FULL-only scope and drop to the original runtime account.
There is no user-facing mapping import route.

Mapping envelope = {payload, signature}; HMAC domain PR122_IDENTITY_MAPPING_V1
+ LF + canonical(payload), using the existing protected authority_verify_key.
Its confirmer assertion is trusted only through the protected exporter/operator
and explicit identity_mapping_confirmers allowlist; a self-reported Owner name
or browser role cannot establish this trust. No production allowlist is supplied.

Exact payload fields:

| Field | Required meaning |
|---|---|
| schema | PR122_IDENTITY_MAPPING_V1 |
| mapping_id / version | Explicit stable ID and strictly increasing positive integer |
| status | ACTIVE or REVOKED |
| user_id / tenant_id / project_id / domestic_customer_id | Explicit confirmed two-system subject; no name/email/phone matching |
| confirmed_by | Owner or explicitly designated original authority, in protected allowlist |
| issued_unix / expires_unix | Strict integers; issued no more than 300s old/nonfuture; now < expires <= issued+86400 |
| project_evidence / local_identity_evidence / domestic_identity_evidence | Each exactly {ref,sha256}, three distinct references |

ACTIVE imports require actual bounded evidence bytes read before privilege drop
from /etc/xuanjun-customer-center/identity-evidence/<ref>.json. This is an input
namespace, not a created directory or a deployed configuration. Descriptor-walked
root-owned non-writable ancestors, no symlinks, root-private regular single-link
files <=65536 bytes and unchanged file metadata are required. No arbitrary user
URL/file content is fetched. SHA256 is recomputed against signed proof descriptors.

Each evidence attestation has exactly schema=PR122_IDENTITY_EVIDENCE_V1,
kind=PROJECT_AUTHORITY / LOCAL_IDENTITY / DOMESTIC_IDENTITY respectively,
confirmed_by, verified=true (boolean), all four exact subject fields above and
expires_unix at least as late as the mapping. These are confirmations prepared by
the trusted evidence custodian after examining original project authority and
both identity ownership proofs. This code verifies trusted attestation bytes and
subject binding; it cannot decide that a real-world ownership assertion is true.
Evidence custody/provenance and the production confirmer designation remain
external requirements; users cannot upload an attestation to activate a mapping.

Import requires a verified existing account and currently authorized project,
matching tenant. The local project's existing customer field is not assumed to
be the domestic_customer_id. One mapping per user/tenant/project; mapping IDs
cannot change any subject or domestic ID. Conflicts fail; no automatic repair or
merge. History remains encrypted and append-only by ID/version, and current row
columns must agree with authenticated encrypted payload and its history record.

REVOKED is a new signed version for an existing immutable subject, with its
original proof descriptors, and remains possible after project expiry/removal.
It preserves history and invalidates outstanding grants. ACTIVE renewal requires
freshly validated evidence and invalidates older grants too. A project authority
revision change makes existing mappings stale until explicitly reconfirmed;
membership revoke immediately consumes outstanding grants so re-invitation does
not revive them. Session logout/reset/expiry and restore maintenance are checked
again at consume. No mechanism clears original restore maintenance or resets
authority revisions/replay records. A revocation is not a distributed rollback
of business work already completed elsewhere.

## Protected optional runtime trust and remaining boundaries

identity_authorization is absent by default. When explicitly configured in a
future separately admitted runtime, it maps caller to {key,audience,operations};
key is canonical Base64 32 bytes from existing protected custody, operations maps
each supported operation to an explicit allowed list of existing project roles.
There are no default audiences, callers, roles or keys. Caller keys must be distinct
and cannot reuse data, backup or project-authority key material. Operator config
and runtime projection must bind identically; LOGIN_ONLY rejects this extension.
No key was generated, requested, configured or deployed by this source task.

Services use the same request/reference and returned mapping/authority version
in their respective audits. PR122 audit changes are in its original transaction;
domestic AuditRepository.record opens its own session_scope, while add_to_session
can use a supplied session. Source session_scope commits after yield, rolls back
Exception and closes finally. This is not evidence of cross-call/cross-machine
atomicity. CustomerSource source_type/source_id and Customer source/phone_hash
source constraints do not establish actual live DB constraints or PR122 linkage.

Required negative tests cover missing/incorrect evidence or confirmer, conflicting
and stale mapping, revoked mapping/member/session, wrong user/tenant/project,
caller/audience/operation, short TTL, replay/reopen, lost response, role/authority
change, audit rollback, tampered mapping, root-input safety and actual HTTP gates.
All test identities are synthetic. Real mapping data, actual endpoint reachability,
TLS/service-caller custody and store authorization/consumer integration are not
accepted by these tests. Brand original byte review remains independently PENDING;
this work does not issue install or production permission.

## Exact customer candidate closure

The existing customer review package grows from 100 to 103 archive members only
because it adds the identity module, its test module and this contract. The fixed
channel build adapter accepts that shape only with those exact three paths plus
the complete 58b1dbbc baseline 99-file path set (canonical sorted-path SHA256
88200b5319005bc1e56a20c37f1ba822c8520a81dc2f3c64b4f26b5bfc225a6a)
and CUSTOMER_MANIFEST.json. Partial identity packages, arbitrary 101/102/103-file
sets, path substitutions, duplicate/unsafe/nonregular members are rejected.
Original per-file byte hashes, manifest coverage, archive limit and exact original
channel source/AST checks remain. This affects build-only customer review closure;
it does not expand actions, change frozen upgrade permission, or describe the
separate 1241-member static brand archive.
