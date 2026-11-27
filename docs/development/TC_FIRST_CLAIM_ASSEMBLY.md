# F4: scoped signed first-registration assembly

This is a callable project-local path through the original Ed25519 registration protocol and Supervisor/Fence, NOT a username/password SSO, Node delegation, browser session, OAuth scope or admin-role issuer. Existing HTTP/MCP identity behavior is unchanged.

## Exact inputs to be provided by lawful holders
Use the existing protected DevelopmentHost configuration selected by --mcp-development-config-file (same owned0600/bounded file checks; no new config schema):

- contract_file: existing JSON map keyed by original task id. Contract fields: task_id, spec_sha256, checkpoint_sha256, target_repository, target_base_sha, entry, developer={issuer,subject}, allowed_files, trusted_reviewers=[{issuer,subject,key_id,role}, ...]. Copy task/spec/checkpoint/entry from original canonical source, not a new task or the later SPEC draft. Two distinct QA/SECURITY reviewer identities/keys remain required. Never fill principal UNBOUND with an invented name.
- bindings: original validated DevelopmentHost rows, with task/spec/checkpoint/contract_sha256 pins and real tenant_id, project_id, principal_id, role_id/role_version, phase/review_kind, authority_identity, actions/candidate_root/executor_profile. Exactly one EXECUTOR identity maps the signed developer; reviewer mapping remains exact. This module issues no roles or model assignments. Native mode retains native_source_file/provider configuration; it does not fetch a candidate during registration.
- claim_registration.owner_public_key_file: an existing legitimately pinned Owner Ed25519 public key PEM. This public-key reference is a trust anchor, not proof that a new local key is authorized. Key selection must be supported by the original task Owner/custody facts. No private key is read/generated/copied by this module.
- claim_registration.custody_file: existing JSON map task_id -> {tenant_id,principal_id,project_id,custody}.
- custody exact fields: owner_grant, developer_credential, caller, lock_root, valid_until.
- owner_grant exact signed fields: issuer=owner-auth, subject=original canonical task.owner, developer=exact contract.developer, contract_sha256, valid_until, signature. Signature is Base64 Ed25519 over canonical signed fields excluding signature, exactly development_identity_adapter.verify_registration. An existing lawful signer supplies this original grant; do not generate a key or sign an example.
- developer_credential: original contract plus developer_identity equal to that signed developer. This is original first-registration evidence, not a general login credential.
- caller: existing trusted caller_id/run_id/session_id/gateway_id values, supplied by their original trusted host/custody source, not agent names, chat strings or generated ids. lock_root is the original canonical private lock directory; valid_until is the actual allowed writer period. This code rechecks protected custody consistency and signature validity, not the independent existence of a Node SDK run. If actual caller custody is unavailable, do not fabricate it.
- --authority-key-file: existing protected tenant context key used by the original GatewayKernel. It is neither a new key nor the Owner signing key.
- --db: existing legally FORMAL canonical authority for this SAME task. TEST_ONLY is rejected unchanged; no new DB/task or SQL profile promotion. Current deployed TEST_ONLY authority needs a separate lawful authority/data decision, not a flag passed to this script.

The named lawful signing-key holder is not identified by the delivered documents. owner-auth is a protocol label; canonical task.owner is a subject binding, not a proven human recipient. Installer must return the existing non-secret key/custody/owner-principal references from the original protected authority source; this module cannot name a person, grant authority or create missing facts.

## Actual command entry
Choose the existing Python environment with requirements-authority.lock cryptography==42.0.8. No service restart or new network listener is needed for this bounded action. Variables below are existing approved paths, never secret contents:

    PYTHONPATH="$RELEASE/scripts" "$PY" "$RELEASE/scripts/task_center_first_claim.py" --db "$CANONICAL_DB" --mcp-development-config-file "$PROTECTED_CONFIG" --authority-key-file "$PROTECTED_TENANT_KEY" --task-id tc-real-development-20261123-4d99c26f2b07 --action register

After successful canonical registration, use the exact same command with --action claim once. A lost/unknown response must be followed only by --action status; never blindly repeat claim. Status reports canonical attempt/lease/fence/epoch/state, not execution. Register duplicate handling is original canonical digest idempotency; a changed contract or non-READY task remains rejected.

## Actual authority boundary
FirstClaimAssembly.principal_mapper maps the result of the real signature verifier to exactly one existing host binding; it does not turn any JSON principal into an authenticated identity. Before registering, the signature subject is checked against the canonical task Owner, every digest against original task metadata and the host pins, and independent reviewer bindings are rechecked. Registration writes only that exact signed contract through the original Supervisor API. It does not give the signed Owner a general ModelControl admin context. The previous admin registration endpoint and its checks are retained.

Supervisor.register_development_contract now accepts an optional trusted in-process admission callback used here inside its existing BEGIN IMMEDIATE transaction before event admission. Claim re-verifies signed custody, role allowlist, dispatch preflight and start policy both before Fence and at the original storage-owner writer CAS. Caller/grant replacement cannot redirect an in-flight claim. No cross-runtime atomicity is claimed.

## Install and rollback
Runtime delta: scripts/task_center_first_claim.py (new), scripts/task_center_mcp_development.py (shared pinned content validator), scripts/task_supervisor.py (existing register transaction callback). Retain actual before manifest/hash backups and install only these necessary files after reviewing source/config dependencies. No service/unit/Gateway/profile/config/mini changes performed by developer. Roll back the files and stop using this entry; preserve any canonical contract/claim/events for reconciliation. Code rollback does not release a lease or undo data.

Tests use explicitly synthetic signed custody and isolated FORMAL fixture data. Their canonical RECEIVED is not this real task receiving work. Existing deployed runner12/12 and same-byte runtime tests are not rerun for F4. Production is blocked until real signed references, trusted caller and lawful FORMAL canonical authority are supplied; do not install TEST_ONLY evidence as identity.
