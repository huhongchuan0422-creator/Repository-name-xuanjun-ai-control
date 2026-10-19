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
