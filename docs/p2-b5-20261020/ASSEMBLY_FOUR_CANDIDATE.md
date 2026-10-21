# B5 four-member public assembly analysis candidate

Continues8da4cdcc / PR17#6314586145. Only preparation, UK NOT_EXECUTED. This is one finite analysis batch, not an installation dependency closure and not a promise of the last extraction. Inspection/Gateway public lifecycle5tests are reused, not rerun.

## Proven reference correction

4161-byte increment SHA49cabdbf25a529caea6123c88d1a715335b5fc3c8bd12f62a5ef72b617a1da8f matches. Recomputed canonical inventory82903B SHA63345c45bd7d5af61f93ded86543978465ed52f38765359ed78296031c62fb4e / Git blob9f858ce882fd89b0b645425f4c136b0fc97a476a; appending exactly one LF produces old82904B SHAaa601bc0632c08f693d63d5b1ef02ff08de1baf5b20706684c61c020c6cf0c57. This closes the explanation/current corrected reference, not retroactive PASS of the old byte claim. Old attachment/receipts remain unchanged. New evidence/source-reference-resolution.json retains both versions and original4-row evidence. No original manifest re-request.

## Exact finite selection

| Member | Bytes | SHA256 |
|---|---:|---|
| dist/server-startup-plugins-Cajv-q3y.mjs | 12979 | be588e2acbd30d55efb0c15a142354337dc220e107f2c00bda78067c07ec121f |
| dist/server-startup-config-Hx2M1x7s.mjs | 24633 | c6c846ead6ec7b1eaf081530966d7b41a6363e8f05e6590daf2469fbc329ee97 |
| dist/proxy-lifecycle-Dl57fEmL.mjs | 7794 | de283d5f397582801b5f35b43ffbe17cb4f49e70c14233a7d6bac2ac3fb794f6 |
| dist/url-protocol-OU3K-ySz.mjs | 823 | 8ad6637ea5831197a0ec03be4ef69c44f08ea616e06ab39b960f0f49b76f196e |

Exactly4 members /46229B. The2 startup modules are literal dynamic imports actually called by receivedcore atL5201/5202, for native config/auth and plugin bootstrap/live registry policy. The2 client modules are literal eager imports of received native GatewayClient and its bootstrap. Existing source callsites/provenance are in PUBLIC_ASSEMBLY_DECISION.md and the increment. Real bytes are needed before deciding whether the restricted original public startup/profile is feasible; metadata does not answer that question. No other384 boundary is selected. Selection is analyzed in two passes: all4 manifest rows must match before any selected content read; each actual member then matches fixedsize/SHA. No recursive dependency walk or SDK/parser import/evaluation.

## Inputs and actual onsite effects (not performed)

Fixed Britishhost iZd7oeikknn1z21sq6ji6zZ, sudo-n root, Python3.6.8 unchanged. Source tools downloaded through one fixed Git blob boundsize/SHA and45s deadline; no credentials. Root creates only new /home/admin/p2-b5-assembly-four-candidate-v1-20261021 tool tree and /home/admin/p2-b5-assembly-four-members-v1-20261021 output tree, admin owned0700/files0600; only new objects fchowned. No existing permissions changed.

Protected old read inputs: /var/lib/xuanjun-p2-isolated-test/b5-source-snapshot-20261020/uid1002/source-tree.tar.pending andmanifest.json; fixed tarSHAe6d3a3cef96ee996eb4b130fb0bd9305438489326b85678a263998602413e485,manifestSHAcdd3c80360af8b4227d166d8ba643ed534055ea79a75b46dcd345c3e86fb52ba. Reuse inherited protected parent/FD identity,strict GNU/all-member contents verification. Original inputs opened read-only, worker drops to admin; no new collection of running tree, no SDK/Node/Docker/model/service calls.

Unchanged AS768MiB,CPU180s,child wall240s,parent270s,FD128,core0,FSIZE20MiB; selection16MiB/report2MiB/tar18MiB ceilings not increased. Actualselected46229B fits without changinglimits; this alone is not why the4 were chosen.

Outputs: tool/support files andbootstrap-result.json in firsttree; materials.tar,report.json,child-receipt.json,host-result.json in second. Tar/report bytes and SHA arise only from actual execution, not prefilled. On success transfer these2new original files plus terminal JSON; expected selection count4,total46229B,allfixedpins match. State MATERIALS_ONLY_NOT_CLOSURE/original_inputs UNCHANGED must accompany terminal/output bindings; exit0 alone insufficient.

## Failure and recovery boundary

Either fixed new directory alreadyexists =>HOLD,keep it; no rename,new suffix,delete,overwrite,chmod or automatic retry. O_EXCL/O_NOFOLLOW and unchanged reader protections remain. Validation/timeout/output-receipt failure preserves existing files/partial receipts. Source-fetch failure precedes output creation. SSH result lost =>do not rerun; inspect existing fixed outputs through separately agreed bounded read-only recovery. Old server/server-start/shutdown successes and failed directories are untouched.

## Complete frozen command — requires this specific onsite confirmation

```sh
sudo -n /usr/bin/python3 -I -B -S - <<'B5_FOUR_ASSEMBLY_CANDIDATE'
import os,sys,json,signal,base64,hashlib
from urllib.request import build_opener,ProxyHandler
try:
    if os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!='iZd7oeikknn1z21sq6ji6zZ' or sys.version_info[:3]!=(3,6,8):
        raise RuntimeError('HOLD_FIXED_HOST_ROOT_PYTHON368')
    def deadline(signum,frame):raise RuntimeError('HOLD_SOURCE_FETCH_DEADLINE')
    signal.signal(signal.SIGALRM,deadline);signal.alarm(45)
    url='https://api.github.com/repos/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/git/blobs/2c2ce62d1387bf9374fb6e77eead2bbba491df92'
    with build_opener(ProxyHandler({})).open(url,timeout=30) as response:
        envelope=response.read(131073)
    if len(envelope)>131072:raise RuntimeError('HOLD_SOURCE_RESPONSE_BOUND')
    data=json.loads(envelope.decode('utf8'))
    if data.get('encoding')!='base64' or data.get('sha')!='2c2ce62d1387bf9374fb6e77eead2bbba491df92' or data.get('size')!=44701:
        raise RuntimeError('HOLD_SOURCE_GIT_BINDING')
    raw=base64.b64decode(''.join(data['content'].splitlines()),validate=True)
    if len(raw)!=44701 or hashlib.sha256(raw).hexdigest()!='b554c695c685fb7418276876c25effad5842994be4b9582d1cfa6071cbdcc95c':
        raise RuntimeError('HOLD_SOURCE_SHA')
    signal.alarm(0)
except Exception as exc:
    print(json.dumps({'state':'HOLD_SOURCE_NOT_STARTED','error_type':type(exc).__name__,'error':str(exc)[:300],'http_status':getattr(exc,'code',None),'errno':getattr(exc,'errno',None),'sdk':'NOT_EXECUTED'}));raise SystemExit(2)
exec(compile(raw,'<sha256-verified-b5-retained-bootstrap>','exec'),{'__name__':'__main__'})
B5_FOUR_ASSEMBLY_CANDIDATE
```

Tool/command fingerprints are in assembly-four-candidate.json. New8 targeted tests verify all4manifest pins before content,missing row,exact count/total/no recursion,contenttamper,embeddedtools/command binding,original resource values,sourceLF correction andfailure partial/O_EXCL retention. Synthetic fixtures are not realSDK/load/auth proof. Local3.12 PASS; Hosted3.6.8/3.12 result inPR17. No British command is run here.

After actual receipt, verify real4bytes,then statically read startup auth/config/registry ownership and client dependencies together. Keep final installation selected_members empty until actual assembly and runtime closure are proved. This candidate's selected_members refers only to the4analysis files. No SDK/real authentication/B5 installation acceptance is claimed; B1–B4 unchanged.
