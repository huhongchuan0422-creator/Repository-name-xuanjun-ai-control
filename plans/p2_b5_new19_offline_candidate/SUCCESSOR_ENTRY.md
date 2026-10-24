# B5 successor fixed entry (source candidate)

The new `successor_controller/pr17_b5_successor_entry.py` is a separate,
default-closed UK maintenance entry. The historical `review.main` still rejects
execution. It is not an installation receipt or an approval registrar.

## Fixed I/O contract

`FixedR2IO` implements the existing backend's `read`, `absent`, `mkdir`,
`newfile`, `parent`, `identity`, `state_directory`, `database_identity`,
`check_original_database`, `command`, `stable_unit`, and `resource_ready`.
Its paths come only from the exact successor spec: six original protected
files, two current links, the pinned queue DB and sidecars, one fixed job's
bounded journal/backups, and the 42 source paths plus manifest beneath the
two stage roots. New files use exclusive creation, no-follow directory FDs,
root ownership, fixed modes, and fsync. Service commands have an exact
`systemctl` unit/action/timeout allowlist; there is no shell or request path.
Readiness compares the fixed loopback OAuth resource metadata to the
protected activated config. A failed observation holds the stage.

## Entry actions

The fixed CLI accepts `execute --batch ... --attempt ... --approval-ref ...
--window-start ...`, followed by separate `intake`, `query`, `recover`, or
`close`. These are selectors, not proof of approval. `execute` rebuilds the
42-file pinned runtime bundle, inspects the two original protected witness
records and the separate release registration, and calls the original
Transaction. `intake` requires the exact durable window checkpoint, no
intent/SENT record, and the original Queue/OAuth attachment before the
existing persist-before-POST path. `query` only observes; `recover` never
resubmits a POST. `close` requires the protected B5 tool witness and an
independent close approval. All four later actions regenerate from the
protected reservation and original source bytes.

The fixed deployment root in this draft is
`/opt/xuanjun-cloud-connection/b5-successor-controller-staged-f0fe0d3978b7`.
The entry refuses a local checkout or an unbound deployment. No directory,
record, permission, grant, credential, or service is created by merely
reading this candidate. An actual site action requires separate exact
enrollment, source-root and recipient checks, the current protected
config/DB/lock facts, and a reviewed command with recovery checkpoints.

## Evidence boundary

Isolated tests verify the fixed scope, rejection and existing successor
algorithms. They do not prove the UK root, the real two-witness records,
current grant, queue or recipient, service readiness, original GitHub intake,
custody, or the B5 analyst's 19 authenticated cloud reads. The offline
`SOURCE_MANIFEST` and external binder must point to the final source commit;
an older commit with changed bytes is invalid. Python 3.6 AST parsing is a
compatibility check, not an actual Python 3.6.8 process result.
