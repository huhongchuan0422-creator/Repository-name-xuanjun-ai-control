// Component guard negatives only: no Gateway mock, registration or CP11 claim.
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,chmodSync,symlinkSync,rmSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {protectedFile,validateSdkParent} from '../../evidence/p2-epoch7-access-repair-20261014/runtime/plugins/p2-native-controller/ledger.mjs';
import plugin from '../../evidence/p2-epoch7-access-repair-20261014/runtime/plugins/p2-native-controller/plugin.mjs';
assert.equal(process.getuid(),0,'root-private disposable guard fixtures, never UK execution');
const root=mkdtempSync('/root/p2-b5-source-guard-');chmodSync(root,0o700);
try {
 const target=path.join(root,'binding.json');const raw=Buffer.from('{}');
 writeFileSync(target,raw,{mode:0o600});const pin=createHash('sha256').update(raw).digest('hex');
 protectedFile(target,pin);
 assert.throws(()=>protectedFile(target,'f'.repeat(64)),/HOLD_HOST_HASH/);
 assert.throws(()=>protectedFile(target,pin,false,1002),/HOLD_HOST_FILE/);
 const link=path.join(root,'link.json');symlinkSync(target,link);
 assert.throws(()=>protectedFile(link,pin),/HOLD_HOST_PATH/);
 assert.throws(()=>protectedFile(path.join(root,'missing.json'),pin),/ENOENT/);
 assert.throws(()=>plugin.register({pluginConfig:{}}),/HOLD_PLUGIN_CONFIG/);
 // Wrong binding must fail before any SDK or registration API is accessed.
 assert.throws(()=>plugin.register({pluginConfig:{bindingFile:target,bindingSha256:'f'.repeat(64)}}),/HOLD_HOST_HASH/);
 assert.throws(()=>validateSdkParent('/home/xuanjun_dev',1002,{uid:0,mode:0o700,isDirectory:()=>true}),/HOLD_SDK_HOME_IDENTITY/);
 assert.throws(()=>validateSdkParent('/home/xuanjun_dev/.openclaw/tools',1002,{uid:1002,mode:0o777,isDirectory:()=>true}),/HOLD_SDK_PARENT/);
 console.log(JSON.stringify({status:'COMPONENT_GUARD_NEGATIVES_PASS',assertions:8,node:process.version,
    real_openclaw_loader:'NOT_EXECUTED',registration:'NOT_EXECUTED',cp11:'NOT_EXECUTED',model_calls:0}));
} finally {rmSync(root,{recursive:true,force:true});}
