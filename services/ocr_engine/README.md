# 玄钧AI新 OCR Engine — first isolated implementation

**State:** local adapter and governance-registered contract tests exist. HTTP gateway is specified but not implemented. No real-model inference has been verified; not deployed or connected to merchant onboarding.

## Engine / reproducibility
- RapidOCR 3.10.0 + ONNX Runtime CPU 1.31.0, pinned in requirements.txt.
- Upstream: https://github.com/RapidAI/RapidOCR
- Model files are not committed. Stage the approved three model files through an authorized offline supply path and independently record their source, license and SHA256.
- The adapter requires absolute paths OCR_DET_MODEL_PATH, OCR_CLS_MODEL_PATH, OCR_REC_MODEL_PATH, plus OCR_MODEL_SHA256 JSON such as {"det":"<64 lowercase hex>","cls":"<64 lowercase hex>","rec":"<64 lowercase hex>"}. Placeholder hashes are invalid. The code verifies each file before constructing RapidOCR and never intentionally downloads models at runtime.
- Python 3.11+ isolated environment only. Do not run package/model downloads on production hosts.

## Contract
OpenAPI contract: docs/development/XUANJUN_OCR_API_V1_20261024.yaml.
It defines POST /ocr/jobs, GET /ocr/jobs/{job_id}, and POST /ocr/jobs/{job_id}/confirm; these are contract definitions, not live HTTP endpoints. Authentication, tenant/attachment authorization, queue, persistent jobs, throttling, encrypted storage, retention, audit and confirmation persistence remain to be implemented before exposing an endpoint.

## Supported extractor scope
- Implemented heuristics: business_license, id_front.
- Explicitly unsupported until dedicated parser/tests exist: id_back, bank_card, food_business_license, other_permit, storefront_photo, interior_photo, cashier_photo. Unsupported types fail closed; storefront/interior/cashier photos are not OCR materials.
- All recognized values are suggestions with confidence and review flag. User confirmation is mandatory. authenticity_verified is always false.

## Tests / evidence
```bash
python3 -m unittest discover -s services/ocr_engine -p 'test_*.py'
python3 -m unittest tests.test_ocr_core
```
These tests exercise synthetic parser fixtures, output normalization, unsupported-type handling and fail-closed local-model configuration. They do not prove real image recognition. Actual offline inference remains BLOCKED until approved model files are staged with verified SHA256 and a non-sensitive synthetic image test is executed in an isolated environment.

No real identity or merchant documents, paid API, credentials, production server or onboarding source files are used.
