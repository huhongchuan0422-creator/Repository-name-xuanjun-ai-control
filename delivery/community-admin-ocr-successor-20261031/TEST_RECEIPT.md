# Developer affected-test receipt

Date: 2026-10-31

All container runs used the locally cached immutable e23e image
`sha256:2068eb13af3252332cb4716931ce01f1f5506f83ab615d772eeb9ba84a999261`
with `--pull=never`, no network, read-only rootfs, no capabilities and
`no-new-privileges`. The production container and COMMITTED attempt were not
used or changed.

## Results

- OCR composition plus explicit writeback route: 46 test executions PASS with
  2 skips caused by the inherited shared test class. Deduplicated result:
  **25 PASS / 1 SKIP**. The skipped test is the real local Chinese model journey
  and reports only `NotoSansCJK` missing.
- OCR host regression: **10/10 PASS**.
- Mini session regression (`node --test clients/community-mini/session.test.cjs`):
  **12/12 PASS**.
- Administrator authority/bootstrap/policy/preflight regression:
  **55/55 PASS**.
- Python syntax compile for the three changed production Python files and the
  four operational slices: PASS.
- `node --check clients/community-mini/session.js`: PASS.

## Runtime/model readback

- Python: `3.11.17`
- RapidOCR import: `/usr/local/lib/python3.11/site-packages/rapidocr/__init__.py`
- ONNX Runtime: `1.31.0`
- Pillow: `12.1.1`
- DET SHA256: `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f`
- CLS SHA256: `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c`
- REC SHA256: `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884`

These three hashes match the image's `OCR_MODEL_SHA256` environment binding.
The image contains no NotoSansCJK file, so this developer run does not claim a
fresh real Chinese inference PASS. Historical run `40008433722` remains prior
evidence, not a test of this successor tree.

## Reused unchanged independent evidence

- OCR reviewed delta: 25 PASS / 1 real-model SKIP, Host 10 PASS, session 12 PASS.
- First administrator maintenance exact source: 21/21 affected review PASS and
  21/21 sealed-envelope PASS.
- Admin-route reconcile exact source: 8/8 affected review PASS.
- Authenticated Runner route adapter: 10/10 affected review PASS.

The integrated successor still requires same-tree independent QA, security and
release review. This developer receipt is not an installation or acceptance
receipt.
