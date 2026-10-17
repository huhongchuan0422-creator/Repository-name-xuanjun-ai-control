"""Four-host read-only SWAS probe. No command input or automatic dispatch retry."""
import base64
import concurrent.futures
import datetime
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

UK = 'acs:ram::1107191612880779:role/xuanjun-ai-esc'
KR = 'acs:ram::1691189778575891:role/xuanjun-automation'
CN = 'acs:ram::1384884686754410:role/xuanjun-automation'
HOSTS = (
    ('uk', UK, 'eu-west-1', '40dfc6a47d5e4363b9da7d0d6ab01cb1', 'iZd7oeikknn1z21sq6ji6zZ'),
    ('korea', KR, 'ap-northeast-2', '09207081a09a466aa0079b07b5e3e7ca', 'iZmj7a5kwr75qc1tul4kf9Z'),
    ('domestic', CN, 'cn-shanghai', '3a22c458934142eea89ec6e3bf481a57', 'iZvt5t8tlrm8oiZ'),
    ('tokyo', CN, 'ap-northeast-1', '68985c531add4e90a131aef703a389e6', 'iZ6wee8q9z4t03hvqumwfhZ'),
)


class Hold(Exception):
    pass


def safe(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,180}', value) else 'DETAIL_WITHHELD'


def quote(value):
    return urllib.parse.quote(str(value), safe='~')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def rpc(endpoint, version, action, credentials, **params):
    # Endpoint and action are fixed by this program, never accepted from a task.
    if endpoint not in {'sts.aliyuncs.com'} | {'swas.' + h[2] + '.aliyuncs.com' for h in HOSTS}:
        raise Hold('ENDPOINT_REJECTED')
    key, secret, token = credentials
    values = dict(params, Action=action, Version=version, Format='JSON',
                  AccessKeyId=key, SignatureMethod='HMAC-SHA1', SignatureVersion='1.0',
                  SignatureNonce=uuid.uuid4().hex,
                  Timestamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
    if token:
        values['SecurityToken'] = token
    canonical = '&'.join(quote(k) + '=' + quote(v) for k, v in sorted(values.items()))
    signature = hmac.new((secret + '&').encode(), ('POST&%2F&' + quote(canonical)).encode(), hashlib.sha1).digest()
    values['Signature'] = base64.b64encode(signature).decode()
    request = urllib.request.Request('https://' + endpoint + '/',
        data=urllib.parse.urlencode(values).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'}, method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(262145)
    except urllib.error.HTTPError as error:
        try:
            data = json.loads(error.read(262145))
            code = safe(data.get('Code'))
        except Exception:
            code = 'HTTP_' + str(error.code)
        raise Hold(code) from None
    except Exception:
        # Never print a URL/body, key, temporary token, or raw exception.
        raise Hold('TRANSPORT_RESULT_UNKNOWN') from None
    if len(raw) > 262144:
        raise Hold('RESPONSE_TOO_LARGE')
    try:
        data = json.loads(raw)
    except Exception:
        raise Hold('INVALID_API_RESPONSE') from None
    if not isinstance(data, dict):
        raise Hold('INVALID_API_RESPONSE')
    if 'Code' in data:
        raise Hold(safe(data['Code']))
    return data


import shlex
import zlib
JOURNAL=Path("/root/pr99-s07-swas-transport-v1")
REMOTE_STAGE="/root/pr99-s07-swas-input-v1"
CN_CREDENTIALS=tuple(json.loads(os.environ["XJ_CN_STS_JSON"]))
FIXED_URL="https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/602b3c6e28ea2a9a77d2850d8fde18e5137c27c9/evidence/pr99-service-handoff/s07-source-closure/bridge_directory_fixed.py"
FIXED_SHA="ac6e64a2cf589b14b21bdab643060748862a7a711deb0bc29648632ccc6a7d9f"

def private_put(path,raw):
    with path.open("xb") as f: f.write(raw)
    path.chmod(0o400)

def remote(region,instance,expected,program,timeout=60):
    wrapped="import os"+chr(10)+"assert os.geteuid()==0 and os.uname().nodename=="+repr(expected)+chr(10)
    wrapped+="try:"+chr(10)+"".join(" "+x+chr(10) for x in program.splitlines())
    wrapped+="except Exception as e:"+chr(10)+" import re,json;d=str(e);print(json.dumps({'status':'HOLD','error_type':type(e).__name__,'code':d if re.fullmatch(r'[A-Z0-9_]{1,160}',d) else 'PRIVATE_DETAIL_WITHHELD'}));raise SystemExit(2)"+chr(10)
    command="/usr/bin/python3.11 -I -B -u -c "+shlex.quote(wrapped)
    if len(command.encode())>6000: raise Hold("COMMAND_LENGTH")
    endpoint="swas."+region+".aliyuncs.com"
    result=rpc(endpoint,"2020-06-01","RunCommand",CN_CREDENTIALS,
       RegionId=region,InstanceId=instance,Type="RunShellScript",Name="xuanjun-s07-bounded-private-continuation",
       Timeout=timeout,WorkingUser="root",WorkingDir="/root",CommandContent=command)
    invoke=result["InvokeId"]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,180}",invoke): raise Hold("INVOKE_ID")
    private_put(JOURNAL/(invoke+".json"),json.dumps({"region":region,"instance":instance,"invoke_id":invoke}).encode())
    deadline=time.monotonic()+timeout+90
    while time.monotonic()<deadline:
        r=rpc(endpoint,"2020-06-01","DescribeInvocationResult",CN_CREDENTIALS,RegionId=region,InstanceId=instance,InvokeId=invoke)["InvocationResult"]
        if r.get("InvocationStatus") in ("Pending","Running","Stopping"):
            time.sleep(2);continue
        if r.get("InstanceId")!=instance or r.get("InvokeId")!=invoke: raise Hold("RESULT_BINDING")
        output=r.get("Output","")
        if not isinstance(output,str):raise Hold("OUTPUT_TYPE")
        # This API currently sends base64 on these instances.
        try: json.loads(output.splitlines()[-1]); raw=output.encode()
        except Exception:
            try:raw=base64.b64decode(output,validate=True)
            except Exception:raise Hold("PRIVATE_OUTPUT_ENCODING")
        private_put(JOURNAL/(invoke+".output.private"),raw)
        if r.get("InvocationStatus")!="Success" or r.get("ExitCode")!=0:
            try:
                detail=json.loads(raw.splitlines()[-1]); error=detail.get("code")
            except Exception:error=None
            raise Hold(safe(error) if error else "REMOTE_FAILED_PRIVATE_LOG_PRESERVED")
        return raw
    raise Hold("REMOTE_RESULT_UNKNOWN_NO_RETRY")

def transfer_blob(host,payload,entry):
    # Exact new private staging tree on each peer; existing attempt is preserved.
    name,role,region,instance,expected=host
    init="from pathlib import Path;import os,json;os.umask(0o077);p=Path("+repr(REMOTE_STAGE)+");p.mkdir(mode=0o700);print(json.dumps({'status':'PRIVATE_STAGE_CREATED'}))"
    remote(region,instance,expected,init)
    wire=base64.b64encode(zlib.compress(payload,9)).decode()
    if len(wire)>1000000:raise Hold("WIRE_SIZE")
    chunks=[wire[i:i+3000] for i in range(0,len(wire),3000)]
    for index,chunk in enumerate(chunks):
        program="from pathlib import Path;import os,json;os.umask(0o077);p=Path("+repr(REMOTE_STAGE+"/"+str(index).zfill(4))+");f=p.open('xb');f.write("+repr(chunk.encode())+");f.close();print(json.dumps({'status':'CHUNK_STAGED'}))"
        remote(region,instance,expected,program)
    assembly="from pathlib import Path;import base64,zlib,hashlib,json;root=Path("+repr(REMOTE_STAGE)+");raw=zlib.decompress(base64.b64decode(b''.join((root/str(i).zfill(4)).read_bytes() for i in range("+str(len(chunks))+")),validate=True));assert len(raw)=="+str(len(payload))+" and hashlib.sha256(raw).hexdigest()=="+repr(hashlib.sha256(payload).hexdigest())+";h=json.loads(raw);n={'__name__':'swas_frozen_functions'};exec(base64.b64decode(h['self']),n);n["+repr(entry)+"](h)"
    return remote(region,instance,expected,assembly,timeout=150)

def main():
    if os.geteuid()!=0 or os.uname().nodename!="iZmj7a5kwr75qc1tul4kf9Z":raise Hold("KOREA_ROOT")
    os.umask(0o077)
    # A durable attempt guard precedes collection and all peer operations.
    JOURNAL.mkdir(mode=0o700)
    with urllib.request.urlopen(FIXED_URL,timeout=30) as f:raw=f.read(100001)
    if hashlib.sha256(raw).hexdigest()!=FIXED_SHA:raise Hold("FIXED_HELPER_HASH")
    private_put(JOURNAL/"helper.py",raw)
    n={"__name__":"swas_functions","__file__":str(JOURNAL/"helper.py")}
    exec(compile(raw,"fixed_bridge.py","exec"),n)
    if n["LOCAL"].exists() or n["BRIDGE_LOCAL"].exists():raise Hold("V4_STAGE_EXISTS_NO_RETRY")
    # Reuse the original preparation checks and bytes; only replace SSH transport.
    source=raw.decode()
    prepare=source[source.index("    tr=TRANSFER_PATH.read_bytes()"):source.index("    bridge=collect_bridge(")]
    exec("\n".join(line[4:] for line in prepare.splitlines()),n)
    combined=dict(n["files"],**n["extra"])
    paths=n["bridge_paths"](combined)
    if paths != [str(n["BRIDGE_ROOT"]/"domestic_bridge_cert.sha256"),str(n["BRIDGE_ROOT"]/"secrets"/"bridge_hmac.current")]:raise Hold("EXACT_TWO_BRIDGE_PATHS")
    h={"bridge_paths":paths,"source_hashes":{k:n["sha"](b) for k,b in combined.items()},
       "source_helper":base64.b64encode(n["sr"]).decode(),"self":base64.b64encode(raw).decode()}
    # Materials are fetched by Korea itself. They never traverse a GitHub runner.
    tokyo=next(h for h in HOSTS if h[0]=="tokyo")
    result=transfer_blob(tokyo,json.dumps(h).encode(),"bridge_pack")
    material=json.loads(result.splitlines()[-1])
    if material.get("host")!=tokyo[4] or material.get("current_source_hashes")!="PASS" or material.get("source_files")!=124:raise Hold("TOKYO_PROVENANCE")
    n["decode_bridge"](material["files"],paths)
    n["BRIDGE_LOCAL"].mkdir(mode=0o700)
    private_put(n["BRIDGE_LOCAL"]/"materials.private.json",result)
    private_put(n["BRIDGE_LOCAL"]/"receipt.json",json.dumps({"status":"AUTHENTIC_BRIDGE_MATERIALS_PRIVATE_RECEIVED","files":2,"service_actions":0,"transport":"SWAS_HOST_TO_HOST_NOT_CI"}).encode())
    h={"bridge":material["files"],"original":base64.b64encode(n["original"]).decode(),
       "transfer":base64.b64encode(n["tr"]).decode(),"source_helper":base64.b64encode(n["sr"]).decode(),
       "self":base64.b64encode(raw).decode(),
       "supplement":{k:base64.b64encode(b).decode() for k,b in n["extra"].items()},
       "commands":n["commands"],"sources":{k:{"bytes":len(b),"sha256":n["sha"](b)} for k,b in n["files"].items()},
       "tar_bytes":Path("/root/pr99-s07-private-materials-v2/materials.tar").stat().st_size}
    # Reduce wire size without changing the validated supplement source bytes:
    # domestic already holds all45 in its preserved v3 copied root. Fetch them
    # there using the exact source pins before calling unchanged run_domestic.
    h["supplement"]={}
    original_self=raw
    bootstrap=raw.decode().replace("def run_domestic(h):","def run_domestic(h):\n    if h.get('supplement')=={}:\n        for name,digest in SUPPLEMENT_PINS.items():\n            if name=='signal/__init__.py':continue\n            b=(Path('/var/lib/xuanjun-pr99-s07-isolated-start-v3/rootfs/opt/trading-system')/name).read_bytes()\n            need(sha(b)==digest,'V3_SUPPLEMENT_CHANGED')\n            h['supplement'][name]=base64.b64encode(b).decode()")
    # Child isolation still receives the exact helper actually used on domestic.
    h["self"]=base64.b64encode(bootstrap.encode()).decode()
    n["LOCAL"].mkdir(mode=0o700)
    private_put(n["LOCAL"]/"private-input.json",json.dumps(h).encode())
    domestic=next(h for h in HOSTS if h[0]=="domestic")
    output=transfer_blob(domestic,json.dumps(h).encode(),"run_domestic")
    receipt=json.loads(output.splitlines()[-1])
    if receipt.get("current_tokyo_source_hashes")!="PASS_124" or receipt.get("protected_state_unchanged") is not True:raise Hold("FINAL_RECEIPT_BINDING")
    private_put(n["LOCAL"]/"receipt.json",json.dumps(receipt).encode())
    print(json.dumps(receipt,sort_keys=True),flush=True)

if __name__=="__main__":
    try: main()
    except BaseException as e:
        print(json.dumps({"status":"S07_SWAS_CONTINUATION_HOLD","code":safe(str(e)) if isinstance(e,(Hold,RuntimeError)) else type(e).__name__,"private_logs_preserved":True,"retry_allowed":False}),flush=True)
        raise SystemExit(2)
