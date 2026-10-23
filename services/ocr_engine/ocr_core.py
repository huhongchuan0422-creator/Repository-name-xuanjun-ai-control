"""Xuanjun OCR: isolated, opt-in RapidOCR adapter and conservative structured extraction.
No image uploads, persistent records, external network calls or real-id fixtures here.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any

LICENSE_RE = re.compile(r"(?<![0-9A-Z])[0-9A-HJ-NP-RTUWXY]{2}[0-9]{6}[0-9A-HJ-NP-RTUWXY]{10}(?![0-9A-Z])")
ID_RE = re.compile(r"(?<![0-9])(?:[1-9][0-9]{16}[0-9Xx])(?![0-9])")
LABELS = {
    "company_name": ("名称", "企业名称", "个体工商户名称"),
    "credit_code": ("统一社会信用代码", "社会信用代码"),
    "legal_representative": ("法定代表人", "经营者", "负责人"),
    "registered_address": ("住所", "经营场所", "地址"),
    "business_scope": ("经营范围",),
    "id_name": ("姓名",),
    "id_number": ("公民身份号码", "身份证号码", "身份号码"),
}
def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ：:;；")
def normalize_lines(raw: Any) -> list[dict]:
    """RapidOCR OCRResult exposes txts/scores; tolerate documented object variants."""
    if hasattr(raw, "txts") and hasattr(raw, "scores"):
        return [{"text": str(t), "confidence": float(s)} for t, s in zip(raw.txts or [], raw.scores or [])]
    if isinstance(raw, dict) and "txts" in raw:
        return [{"text": str(t), "confidence": float(s)} for t, s in zip(raw.get("txts") or [], raw.get("scores") or [])]
    if isinstance(raw, (tuple, list)) and raw and isinstance(raw[0], (list, tuple)):
        first = raw[0]
        if first and isinstance(first[0], (list, tuple)) and len(first[0]) >= 3:
            return [{"text": str(row[1]), "confidence": float(row[2])} for row in first]
    raise ValueError("OCR_RESULT_UNSUPPORTED")
def extract_fields(lines: list[dict], document_type: str, threshold: float = 0.80) -> dict:
    if document_type not in {"business_license", "id_front", "id_back", "bank_card"}:
        raise ValueError("UNSUPPORTED_DOCUMENT_TYPE")
    if not 0 <= threshold <= 1:
        raise ValueError("INVALID_CONFIDENCE_THRESHOLD")
    output = {}
    allowed = {
        "business_license": ["company_name", "credit_code", "legal_representative", "registered_address", "business_scope"],
        "id_front": ["id_name", "id_number", "registered_address"],
        "id_back": [],
        "bank_card": [],
    }[document_type]
    for idx, line in enumerate(lines):
        content = _clean(str(line["text"]))
        confidence = max(0.0, min(1.0, float(line["confidence"])))
        for key in allowed:
            if key in output:
                continue
            for label in LABELS[key]:
                pos = content.find(label)
                if pos < 0:
                    continue
                candidate = _clean(content[pos + len(label):])
                candidate_score = confidence
                if not candidate and idx + 1 < len(lines):
                    candidate = _clean(str(lines[idx + 1]["text"]))
                    candidate_score = min(confidence, float(lines[idx + 1]["confidence"]))
                if not candidate:
                    continue
                if key == "credit_code":
                    match = LICENSE_RE.search(candidate.upper().replace(" ", ""))
                    if not match:
                        continue
                    candidate = match.group()
                if key == "id_number":
                    match = ID_RE.search(candidate.replace(" ", ""))
                    if not match:
                        continue
                    candidate = match.group().upper()
                output[key] = {"value": candidate, "confidence": round(candidate_score, 4), "requires_review": candidate_score < threshold, "source": "ocr"}
                break
    return {"document_type": document_type, "fields": output, "requires_human_confirmation": True, "authenticity_verified": False}
def run_local_ocr(image: bytes, document_type: str, max_bytes: int = 8 * 1024 * 1024) -> dict:
    """Lazy load third-party engine. Caller must enforce auth, tenancy and retention."""
    if not isinstance(image, bytes) or not image or len(image) > max_bytes:
        raise ValueError("INVALID_IMAGE_SIZE")
    if not (image.startswith(b"\xff\xd8\xff") or image.startswith(b"\x89PNG\r\n\x1a\n")):
        raise ValueError("UNSUPPORTED_IMAGE_MAGIC")
    import numpy as np
    from rapidocr import RapidOCR
    engine = RapidOCR()
    raw = engine(np.frombuffer(image, dtype=np.uint8))
    return extract_fields(normalize_lines(raw), document_type)
