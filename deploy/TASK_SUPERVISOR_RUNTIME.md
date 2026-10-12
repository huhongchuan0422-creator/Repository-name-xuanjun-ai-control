# Mechanical supervision runtime — preparation, not activation

This adds a timer-driven tick around the reviewed PR45 state machine. It is
independent of a Work/chat window and does not use a model. Every tick scans
the complete ledger inventory, persists due recovery events and publishes an
atomic private projection containing every task, owner, checkpoint, deadline,
next action and undelivered outbox item. Heartbeat is not task progress.
The earliest terminal deadline is also enforced for active attempts.

The runner requires an existing admitted canonical schema-v2 ledger, exact
device/inode identity, private owner directory and 0600 regular database. It
never creates a ledger or migrates an unrelated database. A different UK
canonical schema must be mapped by the existing controller after review;
creating a second task registry is prohibited. A process lock serializes
ticks; durable generation IDs prevent duplicate recovery events after crash.

The `.in` units are unexpanded preparation templates. The admitted package
must substitute verified canonical paths and ledger identity, bind the
reviewed code hashes and admission record, and independently verify systemd
hardening before enabling the timer. No paths, credentials or host settings
are inferred by this change. The entry script supports Python isolated mode.

The default result is SCAN_COMPLETED_PROVIDER_NOT_ADMITTED, not automatic
recovery success. The runner does not dispatch, claim execution authority,
send external messages, acknowledge delivery or close handoff. The existing
admitted controller/provider must authenticate lease/fence/epoch, reconcile
unknown effects, consume the same durable outbox idempotently and deliver
successor ACK. No arbitrary command or submitted plugin is loaded.

Remaining UK gates: current ledger schema/path/ownership mapping; real
provider and recipient binding; exact artifact QA/Security/Release; timer
activation and independent timer/process liveness; live 5/10/15 faults;
outbox delivery/unknown effects; reboot/power-loss and dashboard live bridge.
Local and hosted fake-ledger tests are source evidence only.
