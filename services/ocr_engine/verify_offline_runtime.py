"""Offline import and shared-library closure gate; never starts the OCR service."""
import importlib.metadata
import subprocess
import sys
from pathlib import Path

def main():
    import cv2
    import fastapi, uvicorn, onnxruntime, rapidocr, numpy, cryptography
    names={d.metadata.get("Name","").lower().replace("_","-") for d in importlib.metadata.distributions()}
    if "opencv-python" not in names or "opencv-python-headless" in names:
        raise SystemExit("OPENCV_DISTRIBUTION_COLLISION_OR_MISSING")
    candidates=list(Path(cv2.__file__).parent.glob("*.so"))
    candidates += list(Path(cv2.__file__).parent.glob("cv2*.so"))
    if not candidates: raise SystemExit("CV2_SHARED_OBJECT_NOT_FOUND")
    checked=set()
    for shared in candidates:
        result=subprocess.run(["ldd",str(shared)],text=True,capture_output=True)
        output=result.stdout+"\n"+result.stderr
        if result.returncode not in (0,1): raise SystemExit("LDD_FAILED:"+shared.name+":"+output)
        if "not found" in output: raise SystemExit("SHARED_LIBRARY_NOT_FOUND:"+shared.name+":"+output)
        checked.add(shared.name)
    subprocess.run([sys.executable,"-m","pip","check"],check=True)
    print("OPENCV_DISTRIBUTION=opencv-python=="+importlib.metadata.version("opencv-python"))
    print("CV2_IMPORT=PASS:"+str(cv2.__version__))
    print("LDD_SHARED_LIBRARIES=PASS:"+",".join(sorted(checked)))
    print("OFFLINE_IMPORT_CHECK=PASS")

if __name__=="__main__": main()
