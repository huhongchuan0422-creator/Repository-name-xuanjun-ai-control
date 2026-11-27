# Original TC development-only bootstrap

task_center_handoff_launch.development_main is an in-process entry, not a CLI identity loader. Original main/HandoffHost remain unchanged. It removes development runner dependency on handoff enabled/config, backup evidence, candidate lifecycle and handoff ledger assembly, not authentication/HTTPS/CSRF/canonical scope/writer lease/execution evidence/review/release.

## Original trusted bootstrap integration
Call development_main(original_app_argv, issuer=registered_issuer, provenance_source=registered_source, principal_mapper=trusted_mapper, native_runner=trusted_isolated_runner, native_test_plan_sha256=approved_plan_digest, gateway_runtime=original_gateway_runtime). These must be existing authenticated objects, not strings/JSON/factories selected by model input. This call shape is not a runnable source producer. Runner and plan may both be absent for login/claim-only assembly; missing execution capability remains denied by existing DevelopmentHost.

original_app_argv retains original --db, --tenant, --enable-mcp, --mcp-development-config-file, --external-origin (HTTPS), --model-master-key-file and --test-authority-key-file protected reference plus existing loopback/port/base-path. The legacy authority-key selector is not a production login source/issuer. Do not pass handoff runtime config, test identities or legacy admin/actor tokens to this entry. No new service or config schema.

Existing load_host schema retains bindings, contract_file, review_keyring_file, writer_context_file and claim_registration(owner_public_key_file/custody_file) as appropriate. References locate existing protected material. This patch generates no contract, identity, key, signed custody, assignment or FORMAL profile. No source rejects before DB open/listener; TEST_ONLY still cannot login formally.

## Capability boundary
Source contract remains verify_login/current_provenance/assert_effect_current plus trusted mapper. Python final admission remains inside SessionStore.create. Node assertCurrent or JSON does not implement a cross-runtime authenticated source. Without a supported authenticated bridge, source registration is blocked exactly as before; separating HandoffHost cannot create that trust capability. Runner receipts must still be trusted, not arbitrary stdout PASSED.

## Installation and rollback
Dependencies unchanged: Python3.11+ and requirements-authority.lock cryptography==42.0.8, existing project venv. Only scripts/task_center_handoff_launch.py is a new runtime payload; tests/docs are source evidence. Installer binds actual before manifest, retains prior file and changes only necessary payload/invocation after real source availability is proved; no DB migration/config write by this patch. Rollback restores that file and prior trusted invocation, not database/external effects. No new port/service or author installation lock.

Deployability is conditional on actual registered source/mapper, original same-task contract/custody and approved trusted runner. Do not install fixtures as source or bypass controller. Source-free tests establish only rejection. This is not a standalone command that can start a formal host without its trusted bootstrap.
