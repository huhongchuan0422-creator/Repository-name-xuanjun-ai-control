import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {inspectServerRoot} from '../../production/p2_install/b5_server_root_binding.mjs';
const evidence=JSON.parse(readFileSync(new URL('../../evidence/p2-b5-ws-20261021/server-root-bytes.json',import.meta.url)));
const raw=Buffer.from(evidence.base64,'base64');
let cases=0;
const result=inspectServerRoot(raw);assert.equal(result.nextMember,'dist/server-start-Bz-KV48j.mjs');assert.equal(result.nextExport,'startGatewayServerCore');cases++;
assert.equal(result.ownerBinding,'UNBOUND');assert.equal(result.executionReadiness,'HOLD_REAL_OWNER_UNBOUND');assert.equal(result.sdk,'NOT_EXECUTED');cases++;
for(const invalid of [raw.toString(),raw.subarray(0,-1),Buffer.concat([raw,Buffer.from(' ')]),Buffer.alloc(4051)]) {assert.throws(()=>inspectServerRoot(invalid),/HOLD_SERVER_ROOT_BYTES/);cases++;}
assert.ok(Object.isFrozen(result)&&Object.isFrozen(result.lifecycle));cases++;
console.log(JSON.stringify({affected_cases:cases,scope:'STATIC_BYTES_ONLY',archived_sdk:'NOT_EXECUTED',old_tests:'NOT_RERUN'}));
