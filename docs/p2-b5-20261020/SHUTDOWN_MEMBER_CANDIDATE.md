# B5 fixed shutdown member candidate — NOT EXECUTED

Continues6e3aa8f3 / PR17#6313765690. Owner supplied Dots manifest binding: dist/server-shutdown-6hlRrMSx.mjs,3884 bytes, SHA256 4fd5792f6c4dbd7dd3e257edd085866578eaf7ee0bafe3d9ab6cd77357a5df36. This is the direct import/call in the already verified server root and core, not a recursive dependency sweep. Manifest row and content must both match the fixed pin at execution. No archived module/parser/Node is executed.

## Complete frozen command

Candidate only: explicit confirmation of this specific UK action is still required. Source-fetch uses fixed Git blob, size, SHA,45-second total/30-second IO timeout and131072-byte response bound; no credentials.

```sh
sudo -n /usr/bin/python3 -I -B -S - <<'B5_SINGLE_SHUTDOWN_CANDIDATE'
import os,sys,json,signal,base64,hashlib
from urllib.request import build_opener,ProxyHandler
try:
    if os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or sys.version_info[:3]!=(3,6,8):
        raise RuntimeError('HOLD_FIXED_HOST_ROOT_PYTHON368')
    def deadline(signum,frame):raise RuntimeError('HOLD_SOURCE_FETCH_DEADLINE')
    signal.signal(signal.SIGALRM,deadline);signal.alarm(45)
    url='https://api.github.com/repos/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/git/blobs/4a879573d4cf98cb9de71524f1ef448a07278c95'
    with build_opener(ProxyHandler({})).open(url,timeout=30) as response:
        envelope=response.read(131073)
    if len(envelope)>131072:raise RuntimeError('HOLD_SOURCE_RESPONSE_BOUND')
    data=json.loads(envelope.decode('utf8'))
    if data.get('encoding')!='base64' or data.get('sha')!='4a879573d4cf98cb9de71524f1ef448a07278c95' or data.get('size')!=44109:
        raise RuntimeError('HOLD_SOURCE_GIT_BINDING')
    raw=base64.b64decode(''.join(data['content'].splitlines()),validate=True)
    if len(raw)!=44109 or hashlib.sha256(raw).hexdigest()!='81d18211d061532b23d3e6140ecb346e3c6a162800a8684f50325d6ace6224fc':
        raise RuntimeError('HOLD_SOURCE_SHA')
    signal.alarm(0)
except Exception as exc:
    print(json.dumps({'state':'HOLD_SOURCE_NOT_STARTED','error_type':type(exc).__name__,'error':str(exc)[:300],'http_status':getattr(exc,'code',None),'errno':getattr(exc,'errno',None),'sdk':'NOT_EXECUTED'}));raise SystemExit(2)
exec(compile(raw,'<sha256-verified-b5-retained-bootstrap>','exec'),{'__name__':'__main__'})
B5_SINGLE_SHUTDOWN_CANDIDATE
```

## Input, output and actual effects

Fixed host iZd7oeikknn1z21sq6ji6zZ, root via sudo -n; host Python3.6.8, no runtime upgrade. Only original retained source-tree.tar.pending / manifest.json beneath /var/lib/xuanjun-p2-isolated-test/b5-source-snapshot-20261020/uid1002 are opened with inherited protected path/FD checks. Full source tar559237632 B SHAe6d3a3cef96ee996eb4b130fb0bd9305438489326b85678a263998602413e485 and manifest5635704 B SHAcdd3c80360af8b4227d166d8ba643ed534055ea79a75b46dcd345c3e86fb52ba bindings, all-member verification and strict GNU/member safety unchanged. Full verification reads existing bytes; it is not a new snapshot.

Actual new writes: /home/admin/p2-b5-shutdown-candidate-v1-20261021 contains the5 hash-bound tool/support files and bootstrap-result.json; /home/admin/p2-b5-shutdown-member-v1-20261021 contains materials.tar,report.json,child-receipt.json,host-result.json. New directories0700 and files0600, owned admin. Bootstrap creates private tree with root then fchown; reader child drops groups/GID/UID to admin and uses inherited read-only input FDs. No old directory mode/owner is changed. No service, installation,SDK,Node,Docker,image or runtime action. B1–B4 unchanged.

Resource limits unchanged:768MiB address space,CPU180s,child wall240s,parent270s,FD128,core0,FSIZE20MiB. Inherited selection16MiB,report2MiB,tar18MiB boundaries are NOT increased; actual selection is exactly1member3884B (no recursion). Toolkit support bundle bounded262144B total and65536B per tool. Original command fetch bound unchanged.

## Stop and recovery

Either output directory already exists => exclusive mkdir fails,HOLD,no automatic alternate name/retry. Existing files cannot be overwritten: O_EXCL/O_NOFOLLOW. Full input/member validation failure,child timeout,changed input identity,output mismatch => preserve created directory and partial artifacts,HOLD. No delete/rename/chmod to clear failure. Source-fetch failure precedes new directories. Capture terminal JSON; success is MATERIALS_ONLY_NOT_CLOSURE with original_inputs UNCHANGED and SDK/CP11 NOT_EXECUTED, not exit0 alone. Transfer only new existing materials.tar/report.json plus terminal receipt; actual output digests are unknown until execution and must be verified on receipt. Do not rerun to recover a dropped SSH result; use a separately confirmed bounded read-only check of the fixed retained output.

After successful material receipt: verify entire new tar/report hashes and unique member against fixed pin, then statically trace native owner from real implementation. New unknown dependencies may only be named from actual bytes. Owner binding,dependency closure,real authenticated dispatch andB5 installation remain UNBOUND/UNKNOWN/NOT_EXECUTED. No installation permission is implied.

## Verification

New target-specific8tests cover fixed row/pin,one-member/no recursion,missing member,wrong size/hash before read,content corruption,embedded tools/command binding,full verifier failure with partial preservation,O_EXCL refusal and existing-directory retention. Test bytes are synthetic selection fixtures, not real SDK acceptance. Prior10native-drain/7static/20WS/9lifecycle and previous member-candidate tests remain inherited,not rerun. Hosted Python3.6.8 and3.12 required; local3.12 only initially.
