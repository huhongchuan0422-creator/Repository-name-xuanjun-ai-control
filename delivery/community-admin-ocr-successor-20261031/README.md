# Community admin + OCR successor (source only)

This directory binds the reviewed operational slices to the immutable community
source baseline `e23e1868b16f6c4c3f30f158418e6557037df28e`.

It is **not an installer** and has not changed the current production instance.
The already-COMMITTED e23e attempt must not be replayed.

## Included reviewed slices

- `admin_maintenance.py` and `original_manual_support.py`: exact reviewed first
  administrator maintenance bytes. Execution remains disabled until the current
  COMMITTED checkpoint, current host configuration SHA, mount identities and
  real Owner TTY confirmation are bound by the installer.
- `route_reconcile.py` / `OWNER_RECONCILE_COMMAND.txt`: exact reviewed
  reconciliation for the already-performed admin-route reload. It verifies the
  transformed HTTP wire asset and anonymous 403; it does not reload nginx.
- `community_runner_route_adapter.py`: exact reviewed adapter for the existing
  authenticated Runner boundary. It is not a credential or a self-admission
  path.
- `ocr-review-pins.json`: exact six-path review binding for the OCR source delta.

## Source delta in this successor

The repository source applies the reviewed six-path OCR patch on top of e23e:

- `scripts/community_wechat_applyment.py`
- `scripts/community_ocr_bridge.py`
- `scripts/community_ocr_host.py`
- `clients/community-mini/session.js`
- `tests/test_community_ocr_shared_composition.py`
- `tests/test_community_ocr_writeback_route.py`

The server now exposes explicit `apply_confirmed`, binds the persisted OCR job
to the requested application and subject, rechecks the attachment and both CAS
versions, and fills only empty fields. An ID-card write requires the original
profile to have selected `IDENTIFICATION_TYPE_IDCARD`; passport/other document
types are not rewritten. Manual fields remain authoritative.

The unchanged e23e administrator implementation exposes exactly 158
capabilities (153 business + 5 `/community/admin` management operations), and
the policy migration remains the required path from first-enable to configured
business scopes. `CORE_FIRST_ENABLE` is not claimed as full administrator
acceptance.

## Verified locally

- OCR writeback suite in the existing immutable e23e Python 3.11.17 image:
  25 deduplicated PASS / 1 real-model test SKIP (`NotoSansCJK` absent from the
  installed image; model/runtime imports and all three model SHA values match).
- Original OCR host regression: 10/10 PASS.
- Mini session regression: 12/12 PASS.
- Existing administrator authority/bootstrap/policy/preflight regression:
  55/55 PASS in the same immutable image.
- Changed Python sources compile and the changed JavaScript passes
  `node --check`.

The earlier independent reviews remain valid only for their exact unchanged
bytes. This integrated successor still requires same-tree independent
QA/security/release, a versioned image/carrier through the original release
mechanism, controlled installation, readback, and real browser/OCR acceptance.

## Remaining exact gates

1. Bind the administrator maintenance plan to the current COMMITTED checkpoint,
   current host configuration SHA and exact three mount identities; obtain the
   Owner's private TTY email/password confirmation at execution time.
2. Reconcile the existing admin-route reload with the exact reviewed command or
   authenticated Runner adapter; do not perform another reload.
3. Build a versioned successor image from this tree while reusing the existing
   OCR model layer. No hot source mount and no fourth production mount.
4. Obtain the formal OCR ZIP/TAR bytes (only their expected SHA values were in
   the received handoff):
   `d5142f25afdf6f48297545e504a201039b2d85608af6d16b3d9b5ddb3b6a81a9`
   and `5d4ac9dad0badefaab20853cc4ceff0be9caf4c4501cebb4e318599007d662f6`.
5. Complete real login/full-scope/revocation checks and real offline Chinese OCR
   confirmation/writeback/restart readback without customer documents.
