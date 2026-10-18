"""Emit exact Owner bootstrap bytes and SHA; no UK execution."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
out=Path(sys.argv[1]);out.mkdir()
head=subprocess.check_output(['git','-c','safe.directory=*','rev-parse','HEAD'],cwd=str(ROOT)).decode().strip()
source=(HERE/'prepare.py').read_bytes()
pin=hashlib.sha256(source).hexdigest()
url='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/'+head+'/delivery/p2-owner-6041/prepare.py'
command=("sudo -n /usr/bin/python3 -I -B -S - <<'P2_OWNER_DELIVERY'\n"
    "import hashlib,urllib.request\n"
    "u="+repr(url)+"\n"
    "p="+repr(pin)+"\n"
    "o=urllib.request.build_opener(urllib.request.ProxyHandler({}))\n"
    "with o.open(u,timeout=30) as r:\n"
    "    b=r.read(65537)\n"
    "if len(b)>65536 or hashlib.sha256(b).hexdigest()!=p:\n"
    "    raise SystemExit('DELIVERY_SCRIPT_SHA_MISMATCH')\n"
    "exec(compile(b,u,'exec'),{'__name__':'__main__','__file__':u})\n"
    "P2_OWNER_DELIVERY\n").encode('utf-8')
(out/'FULL_SCRIPT.sh').write_bytes(command)
(out/'prepare.py').write_bytes(source)
record={'delivery_commit':head,'runtime_commit':'6041c7458dce7c83c49c5a9eafa0e20cef52d1c0',
    'script_bytes':len(command),'script_sha256':hashlib.sha256(command).hexdigest(),
    'downloaded_python_bytes':len(source),'downloaded_python_sha256':pin,
    'state':'OWNER_PENDING_EXECUTION','scope':'PINNED_DELIVERY_PREPARATION_ONLY',
    'uk_execution':'NOT_EXECUTED'}
(out/'SCRIPT_MANIFEST.json').write_text(json.dumps(record,sort_keys=True,indent=2)+'\n')
print('SCRIPT_BINDING='+json.dumps(record,sort_keys=True))
print('FULL_SCRIPT_BEGIN\n'+command.decode()+'FULL_SCRIPT_END')
