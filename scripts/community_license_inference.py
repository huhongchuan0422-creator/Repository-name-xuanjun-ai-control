"""Explicit first-party infer callback for pinned api.create_app/compose.

No monkeypatch or dependency edit. One original-model inference per license.
No allocator changes, model downloads, image retention or automatic writeback.
"""
import hashlib
from pathlib import Path
from scripts.community_license_layout import normalize_layout, extract_license_fields

UPSTREAM_FILES = {
    'api.py':'0aa40ec64550b64c33bec4902d83155bcd19ab97cae7ea2b28874b28c222621c',
    'secure_store.py':'c0191b6766fc884fc4e5f32e9b6492daa5bf0d90527ab77ed2feb5bd03a05696',
    'ocr_core.py':'bbc99d7e5bc606fc0f069b5a26babc4b87a5f7b4e0726cd71acab231933bc308',
}


def run_license_layout_ocr(image, document_type, max_bytes=8*1024*1024, max_pixels=20_000_000):
    from services.ocr_engine import ocr_core
    root = Path(ocr_core.__file__).resolve().parent
    for name, digest in UPSTREAM_FILES.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
            raise PermissionError('LICENSE_OCR_UPSTREAM_PIN_MISMATCH')
    if document_type == 'id_front':
        return ocr_core.run_local_ocr(image, document_type, max_bytes=max_bytes, max_pixels=max_pixels)
    if document_type != 'business_license':
        raise ValueError('UNSUPPORTED_DOCUMENT_TYPE')
    # Identical input checks and model verification to the pinned entry point.
    if not isinstance(image, bytes) or not image or len(image)>max_bytes:
        raise ValueError('INVALID_IMAGE_SIZE')
    if not (image.startswith(b'\xff\xd8\xff') or image.startswith(b'\x89PNG\r\n\x1a\n')):
        raise ValueError('UNSUPPORTED_IMAGE_MAGIC')
    models = ocr_core._verified_model_paths()
    import cv2
    import numpy as np
    from rapidocr import RapidOCR
    decoded = cv2.imdecode(np.frombuffer(image,dtype=np.uint8),cv2.IMREAD_COLOR)
    if decoded is None or len(decoded.shape)!=3:
        raise ValueError('IMAGE_DECODE_FAILED')
    height,width=decoded.shape[:2]
    if width<1 or height<1 or width*height>max_pixels:
        raise ValueError('IMAGE_PIXEL_LIMIT')
    engine = RapidOCR(params={'Det.model_path':models['det'],'Cls.model_path':models['cls'],'Rec.model_path':models['rec']})
    raw = engine(decoded)
    rows = normalize_layout(raw)  # Detached Python scalars/coordinates only.
    # RapidOCROutput.img references the decoded image; release both that output
    # and all inference locals before geometry mapping allocates its candidates.
    # This is reference-lifetime control, not a promise that native allocators
    # immediately return every freed byte to the OS.
    del raw, engine, decoded
    return extract_license_fields(rows)
