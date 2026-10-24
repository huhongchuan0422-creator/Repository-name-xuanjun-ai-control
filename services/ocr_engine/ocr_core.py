"""Xuanjun OCR local inference adapter. No network fallback and no authenticity claims."""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
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
SUPPORTED_TYPES = {"business_license", "id_front"}
def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ：:;；")
def normalize_lines(raw: Any) -> list[dict]:
    """Normalize RapidOCR 3.x result objects and compatible test fixtures."""
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
    if document_type not in SUPPORTED_TYPES:
        raise ValueError("UNSUPPORTED_DOCUMENT_TYPE")
    if not 0 <= threshold <= 1:
        raise ValueError("INVALID_CONFIDENCE_THRESHOLD")
    output = {}
    allowed = {
        "business_license": ["company_name", "credit_code", "legal_representative", "registered_address", "business_scope"],
        "id_front": ["id_name", "id_number", "registered_address"],
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
def _verified_model_paths() -> dict:
    """Require pre-staged absolute model files and SHA256 pins; never download at runtime."""
    keys = {"det": "OCR_DET_MODEL_PATH", "cls": "OCR_CLS_MODEL_PATH", "rec": "OCR_REC_MODEL_PATH"}
    expected_raw = os.environ.get("OCR_MODEL_SHA256", "")
    try:
        expected = json.loads(expected_raw)
    except (TypeError, ValueError):
        raise RuntimeError("OCR_MODEL_SHA256_REQUIRED")
    paths = {}
    for key, env_name in keys.items():
        raw_path = os.environ.get(env_name, "")
        digest = expected.get(key) if isinstance(expected, dict) else None
        if not raw_path or not Path(raw_path).is_absolute() or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError("OCR_MODEL_PATH_OR_SHA256_REQUIRED:" + key)
        path = Path(raw_path)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("OCR_MODEL_FILE_UNAVAILABLE:" + key)
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != digest:
            raise RuntimeError("OCR_MODEL_SHA256_MISMATCH:" + key)
        paths[key] = str(path)
    return paths
def run_local_ocr(image: bytes, document_type: str, max_bytes: int = 8 * 1024 * 1024, max_pixels: int = 20_000_000) -> dict:
    """CPU/local inference only. Requires approved model files already staged and hash-pinned."""
    if document_type not in SUPPORTED_TYPES:
        raise ValueError("UNSUPPORTED_DOCUMENT_TYPE")
    if not isinstance(image, bytes) or not image or len(image) > max_bytes:
        raise ValueError("INVALID_IMAGE_SIZE")
    if not (image.startswith(b"\xff\xd8\xff") or image.startswith(b"\x89PNG\r\n\x1a\n")):
        raise ValueError("UNSUPPORTED_IMAGE_MAGIC")
    models = _verified_model_paths()
    import cv2
    import numpy as np
    from rapidocr import RapidOCR
    decoded = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None or len(decoded.shape) != 3:
        raise ValueError("IMAGE_DECODE_FAILED")
    height, width = decoded.shape[:2]
    if width < 1 or height < 1 or width * height > max_pixels:
        raise ValueError("IMAGE_PIXEL_LIMIT")
    engine = RapidOCR(params={
        "Det.model_path": models["det"],
        "Cls.model_path": models["cls"],
        "Rec.model_path": models["rec"],
    })
    raw = engine(decoded)
    return extract_fields(normalize_lines(raw), document_type)
