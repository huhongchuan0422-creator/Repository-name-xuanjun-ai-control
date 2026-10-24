"""Run actual RapidOCR inference on generated non-sensitive ASCII text; no mocks or document samples."""
import cv2
import numpy as np
from rapidocr import RapidOCR
from .ocr_core import _verified_model_paths, normalize_lines

def main():
    image = np.full((240, 1100, 3), 255, dtype=np.uint8)
    cv2.putText(image, "XUANJUN OCR SYNTHETIC TEST 1234567890", (28, 125),
                cv2.FONT_HERSHEY_SIMPLEX, 1.35, (0, 0, 0), 3, cv2.LINE_AA)
    models = _verified_model_paths()
    engine = RapidOCR(params={
        "Det.model_path": models["det"],
        "Cls.model_path": models["cls"],
        "Rec.model_path": models["rec"],
    })
    raw = engine(image)
    lines = normalize_lines(raw)
    text = " ".join(item["text"] for item in lines)
    print("INFERENCE_MODE=REAL_RAPIDOCR_ONNX")
    print("SYNTHETIC_IMAGE=GENERATED_IN_MEMORY")
    print("OCR_LINE_COUNT=" + str(len(lines)))
    print("OCR_OUTPUT=" + repr(text))
    print("CONFIDENCES=" + repr([round(item["confidence"], 4) for item in lines]))
    if not lines or not text.strip():
        raise SystemExit("REAL_INFERENCE_FAILED_EMPTY_RESULT")
    if "XUANJUN" not in text.upper() or "SYNTHETIC" not in text.upper():
        raise SystemExit("REAL_INFERENCE_FAILED_EXPECTED_TEXT_NOT_RECOGNIZED")
    print("REAL_SYNTHETIC_INFERENCE=PASS")

if __name__ == "__main__":
    main()
