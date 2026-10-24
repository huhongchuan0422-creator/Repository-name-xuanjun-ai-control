"""Offline import and shared-library closure gate; never starts the OCR service."""
import importlib.metadata
import subprocess
import sys
from pathlib import Path

def verify_shared_libraries(candidates, runner=subprocess.run):
    checked=set()
    for shared in candidates:
        result=runner(["ldd",str(shared)],text=True,capture_output=True)
        output=result.stdout+"\n"+result.stderr
        if result.returncode != 0:
            raise RuntimeError("LDD_FAILED:"+Path(shared).name+":"+output)
        if "not found" in output:
            raise RuntimeError("SHARED_LIBRARY_NOT_FOUND:"+Path(shared).name+":"+output)
        if "not a dynamic executable" in output.lower() or "statically linked" in output.lower():
            raise RuntimeError("LDD_NOT_DYNAMIC_ELF:"+Path(shared).name+":"+output)
        checked.add(Path(shared).name)
    return checked

def main():
    import cv2
    import fastapi, uvicorn, onnxruntime, rapidocr, numpy, cryptography
    names={d.metadata.get("Name","").lower().replace("_","-") for d in importlib.metadata.distributions()}
    if "opencv-python" not in names or "opencv-python-headless" in names:
        raise SystemExit("OPENCV_DISTRIBUTION_COLLISION_OR_MISSING")
    package_root=Path(cv2.__file__).parent
    candidates=sorted({p for p in package_root.rglob("*.so") if p.is_file() and not p.is_symlink()} |
                      {p for p in package_root.rglob("*.so.*") if p.is_file() and not p.is_symlink()})
    if not candidates: raise SystemExit("CV2_SHARED_OBJECT_NOT_FOUND")
    try:
        checked=verify_shared_libraries(candidates)
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    subprocess.run(["dpkg-query","-W","-f="+ "${Package}=${Version}" + chr(10),
                    "libgl1","libglib2.0-0","libsm6","libxext6","libxrender1","libxcb1"],check=True,text=True)
    subprocess.run([sys.executable,"-m","pip","check"],check=True)
    print("OPENCV_DISTRIBUTION=opencv-python=="+importlib.metadata.version("opencv-python"))
    print("CV2_IMPORT=PASS:"+str(cv2.__version__))
    print("LDD_SHARED_LIBRARIES=PASS:"+",".join(sorted(checked)))
    print("OFFLINE_IMPORT_CHECK=PASS")

if __name__=="__main__": main()
