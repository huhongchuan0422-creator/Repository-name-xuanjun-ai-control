# TC477 reviewed consumer delta on the installed a8a release

Runtime source: 1f163eff206a636a6ae0c618e58cd6995e7c31f7.
Only scripts/task_center_handoff_runtime.py is in this incremental payload.
The installed a8a base already contains the other 46 original payloads.
Do not replay the original 47-file ADD list against that installed release.

- Archive SHA256: 57249726d3ae2f495f4ad4fa5b50cbaf350c9a4924e1aba15d91f9485b965367
- RESULT-FILES SHA256: 4329ee7e6e0b5df687103f12220cfb859c035baa29a2bf230415de179c5b30ec
- Required installed manifest: 258113cd9e3891ae04675ddb14dd2ce9469382741f61a29981d8accee5fc0420
- Runtime before SHA256: 2f5060df69d113aec894a2ef02d47cf0f827f4c55e2f0997ba8a1bffa2ca1ca5
- Runtime result SHA256: eab6299401384de40c6b56f881a42a5f100f9458348da0d71b8e902c77332e69

A695 independently passed the six-line runtime delta and 3+1 isolated cases.
Package verification only binds the actual archive member to that reviewed Git
blob and preserves all before selectors/modes. No tests were repeated or claim
made that the installed runtime already contains this result. Source commit is
1f163eff; the later distribution commit changes no runtime code.

The original installer may stage exactly one MODIFY, zero ADD and zero DELETE
through its existing serial carrier/recovery procedure. Preserve every unlisted
installed path, unit, selector, configuration and existing rollback release.
The before manifest is the installed 258113cd, NOT the old 15ecfa38. The result
file/directory counts remain those of the installed base; regenerate its manifest
through the original installer, never overwrite it with RESULT-FILES.json.
This delivery does not install, restart or enable formal handoff.

Next original consumer entry: trusted host calls task_center_handoff_launch.main
with existing identity_backend and evidence objects and original service args,
including the protected --handoff-backup-inventory-file as applicable. The
runtime now exposes the exact live evidence.assess_backup consumer object for
that original v1/prepared loader. It does not copy grants, cache revoked evidence
or convert SOURCE-only readback into COMPLETE. No CLI provider loader is added.

Formal identity/action backend and independent receiver/supervisor permission
sources remain required; protected recover/reacquire is independently OPEN.
Do not use test authority or change unit/selector/access permissions to bypass
those requirements. Code rollback is not DB/external-effect rollback. This delta
is not present in the old 26c98cb9 or 5b0ce602 archives; preserve their receipts.
