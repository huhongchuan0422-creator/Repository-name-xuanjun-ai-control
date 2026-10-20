/** Actual UK source bytes are data only: no SDK/parser import or eval. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {verifyReceivedDispatchBytes,bindReceivedRegistryNamespace,RECEIVED_DISPATCH_FILES} from '../../production/p2_install/b5_dispatch_registry_contract.mjs';
const raw=gunzipSync(readFileSync(new URL('../../evidence/p2-b5-dispatch-20261020/dispatch-byte-fixture.json.gz',import.meta.url)),{maxOutputLength:524288});
const files=Object.fromEntries(Object.entries(JSON.parse(raw)).map(([n,b])=>[n,Buffer.from(b,'base64')]));
assert.equal(Object.keys(files).length,7);assert.equal(verifyReceivedDispatchBytes(files).state,'RECEIVED_STATIC_BYTES_BOUND');
let invoked=0;const make=()=>{invoked++;},descriptors=()=>{invoked++;};
const api=bindReceivedRegistryNamespace({n:make,r:descriptors},files);assert.equal(api.createGatewayMethodRegistry,make);assert.equal(api.createPluginGatewayMethodDescriptors,descriptors);assert.equal(invoked,0);
for(const n of Object.keys(RECEIVED_DISPATCH_FILES)) {
 const bad={...files,[n]:Buffer.concat([files[n],Buffer.from('changed')])};assert.throws(()=>bindReceivedRegistryNamespace({n:make,r:descriptors},bad),/HOLD_DISPATCH_SOURCE_SHA/);
}
assert.throws(()=>bindReceivedRegistryNamespace({a:make,r:descriptors},files),/HOLD_REGISTRY_FIXED_NAMESPACE/);
const getter={r:descriptors};Object.defineProperty(getter,'n',{get(){invoked++;return make;}});assert.throws(()=>bindReceivedRegistryNamespace(getter,files),/HOLD_REGISTRY_FIXED_NAMESPACE/);assert.equal(invoked,0);
const server=files['dist/server-methods-DJEQKCcV.mjs'].toString('utf8');
for(const anchor of ['opts.methodRegistry?.getHandler(req.method)','authorizeGatewayRequestPreDispatch({','withPluginRuntimeRegistryScope(params.methodRegistry.pluginRegistry','authorizeAuthenticatedProfileForMethod({','withPluginRuntimeGatewayRequestScope({','readGatewayRequestMutationAuthority(opts)'])assert.ok(server.includes(anchor),anchor);
console.log(JSON.stringify({actual_seven_file_bytes:'PASS',fixed_registry_exports:'n/r',namespace:'FIXTURE_ONLY_NEVER_INVOKED',sdk_evaluation:'NOT_EXECUTED',authentication:'NOT_EXECUTED'}));
