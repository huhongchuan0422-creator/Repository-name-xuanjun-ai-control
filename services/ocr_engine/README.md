# 玄钧AI新 OCR Engine — initial implementation

Status: **isolated prototype; not deployed, not connected to merchant onboarding**.

## Choice
RapidOCR (Apache-2.0) with ONNX Runtime CPU. Source: https://github.com/RapidAI/RapidOCR . Models derive from PaddleOCR; vendor license/source attribution and SHA256 must be frozen before any production packaging.

## Local verification
```bash
python3 -m unittest discover -s services/ocr_engine -p 'test_*.py'
```
The unit tests only exercise normalization, extraction and input guards; **they do not run OCR inference**.

For later isolated inference evaluation: create dedicated Python 3.11+ environment, install pinned and independently verified `rapidocr` and `onnxruntime`, pre-stage signed/hashed offline model assets, then call `run_local_ocr(image_bytes, "business_license")`. Network/model downloading during execution is not approved.

## Integration blockers
- Current adapter accepts only JPEG/PNG magic; decoding validation, decompression-bomb protection, EXIF handling, resource limiting, tenancy, authorization, encrypted storage, throttling, idempotency, immutable confirmation record and HTTP API remain to be built.
- Current text extraction is heuristic, not official-license parser; ID validity and full credit-code checksum, date and OCR accuracy evaluation are pending.
- No OCR result validates identity or document authenticity.
- Preserve Issue #76's sole application-source Writer; this module changes no onboarding assets.
- Never send real document images or personal identity data to GitHub or third-party model endpoints.
