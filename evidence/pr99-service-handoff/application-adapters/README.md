# PR99 exact application adapters

These are two integration components, not a running migration or a production
startup hook. They use the unchanged original `ingress_gate.py` and create no
Writer, controller, journal, seal fd, epoch or installation state.

## Observed source bindings

Tokyo receipt: run39179101395/job117827887578, Invoke t-jpn70gjz1rzfgu8,
2026-10-19T00:04:32.910243Z. Eleven exact source definitions were observed with
all requested classes present. All business literals were removed. In particular:

- `database/repositories/credential_repository.py` uses the initialized
  `session_factory or SessionLocal`, source SHA256
  `8e133d4b07b0d6698befb2f0c9c98963a2d1156f58fa9e2c2a0fe4879bbf9104`.
- `WeComCustomerServiceIngress.accept_callback` calls `jobs.put_nowait` followed
  by an audit write. Its worker consumes `jobs.get` unless a nonempty job is
  supplied, performs original API/bridge/state work, and has no `task_done` call.
  Source SHA256 `aa50fff75f53646bac75a30adbeccb98104e25d58bf099929bfea93e5810a402`.
- Contact callback audit, Telegram state writes, portal session/secret stores,
  and Douyin/TikTok stores are additional origins. The WeCom adapter does not
  cover those other origins or prove a complete data catalogue.

The historical failed attempts remain: t-jpn70gjapyv2j28 FileNotFoundError;
t-jpn70gjrmi0248w STORAGE_SEMANTICS_WIRE_BOUND. The former was queried without
issuing a host command. The label/HEAD race run39178799366 rejected before
credentials or host dispatch. No consumed label was removed/re-added.

## Configuration capture

`capture_repository_database` must run in the original admitted application
process on the actual repository instance. It takes its already attached engine
binding, never a newly constructed SessionLocal or environment/default guess.
It rejects remote, URI-option, memory and multiple-engine cases, source-binding
withdrawal and identity changes. It opens no database. The original verifier
must bind the concrete instance, process, source and original controller context.
Returned records are private technical input and do not grant catalogue authority.

## Queue integration

`WeComQueueBinding` must be installed during verified exclusive original startup,
before a listener or worker starts. An existing nonempty queue, unfinished work,
or existing gate tickets are preserved and rejected. No live queue is copied.
The caller supplies the original gate and original request/job identifiers.
The original callback runs under a synchronous gate ticket, including the audit
after enqueue. The original worker receives the accepted job explicitly; the gate
acknowledges it only after return and source verification. Exceptions remain
UNKNOWN and require original outcome reconciliation; they are never replayed.

The instance's original API signature remains `worker_once(job=None)` but direct
job bypasses are rejected. Retained old workers attempting `jobs.get` are held.
The full caller/activator coverage must still be proved before production use.

## Validation and remaining native work

25 ordinary tests use real queues, threads and held temporary fds, with business
API objects, original source admission and session/engine shapes as fixtures.
They are not live application acceptance, M99 or production migration evidence.
The original 113-test runtime sources and accepted 21-test startup helper are
unchanged. Only these two components and their affected tests are new.

No deployment hook is installed, actual process configuration exported, source
ingress sealed, queue drained, original material guard instantiated, final data
captured, canonical Writer assigned, production service started or route changed
by this package. Restricted original M99/40-file release is not retried. Owner's
removal of separate reviewer/permit waits remains effective.

## Credential key selection increment, 2026-10-19

Owner terminal results on the Tokyo preparation snapshot showed that the
project configuration key decrypts records 1 and 2, while the portal key
decrypts record 3. All carry key version `v1`; selecting solely by that version
would be incorrect. Both original configuration files were preserved privately
on Tokyo. No key, credential identifier, ciphertext or configuration-file hash
is included in this public package.

`credential_key_binding.py` implements an explicitly bound, read-only native
credential reader. Private per-credential bindings include a fingerprint of
the identity/AAD and encrypted fields and an opaque key reference. It uses
exactly one supplied key, delegates to the original supplied store factory,
rechecks repository data before returning, and holds for unbound/changed
records, missing inputs or native failures. It does not rotate, guess or fall
back among keys, write databases, or install a live hook. Eight fixture tests
cover selection, no fallback, error redaction, binding mutation and concurrent
record changes; the complete adapter suite is now 33 tests.

Still required: construct private bindings from an exact accepted snapshot,
verify the supplied native factory and real repository, integrate reads and
new-credential writes into the original application lifecycle, and perform
target-host acceptance. This read-only increment is not a complete production
credential adapter, production migration, or M99 acceptance.

## Private snapshot acceptance batch

`accept_private_credential_bindings.py` is a Tokyo-only, root-only acceptance
program for the exact Owner preparation snapshot and preserved configuration
copies. It pins both the original pure crypto source and the reader adapter.
It imports no original business modules and opens only the immutable private
copy. Explicit record/key assignments are verified using the original pure
methods with the installed cryptography dependency. Bindings stay private and
contain references and fingerprints, never master-key values or plaintext.
The batch records intent before verification, never overwrites prior outcomes,
and reuses exact successful checkpoints. Incomplete/failed attempts require
reconciliation; no automatic retry or key fallback is provided.

Six additional tests use real AES-GCM and synthetic records/source, and real
private filesystem operations. The complete suite is 39 tests. These are not
proof of a running application instance, target deployment, a live Writer
Fence or M99 acceptance. The program does not install a service hook or
integrate new credential writes. It must never be used as a production start
command. Neither existing production configuration is changed.
