import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import plugin from '../plugins/tc-owner-read/index.mjs';

const root = resolve(import.meta.dirname,'..');
const env = {...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONPATH:join(root,'scripts')+':'+join(root,'tests')};
function setup(t) {
  const dir=mkdtempSync(join(tmpdir(),'tc-owner-read-'));t.after(()=>rmSync(dir,{recursive:true,force:true}));
  const fixture=action=>execFileSync('/usr/bin/python3',[join(root,'tests/owner_read_fixture.py'),dir,action],{env,encoding:'utf8'});
  const data=JSON.parse(fixture('prepare'));
  return {...data,dir,fixture};
}
function registration(config) {
  let method,handler,options;
  plugin.register({pluginConfig:config,registerGatewayMethod:(m,h,o)=>{method=m;handler=h;options=o;}});
  return {method,handler,options};
}
async function invoke(reg,data,change={}) {
  let releases=0,calls=0;const controller=new AbortController();
  const guard=()=>{calls++;if(change.abortAt===calls)controller.abort();if(change.revokeAt===calls)throw new Error('revoked fixture');};
  const authority={sandboxRequired:false,assertCurrent:guard,retain:()=>({signal:controller.signal,assertCurrent:()=>{
    if(controller.signal.aborted)throw new Error('ended fixture');
  },release:()=>{releases++;}})};
  let answer;
  await reg.handler({params:data.params,client:{authenticatedUserProfile:{profileId:'profile-fixture'}},
    sessionAccessAuthority:authority,respond:(ok,value,error)=>{answer={ok,value,error};},...change.options});
  return {...answer,releases,calls};
}

test('default-off has no registered surface',()=>{
  assert.equal(registration(undefined).handler,undefined); assert.equal(registration({}).handler,undefined);
  assert.equal(registration({enabled:false}).handler,undefined);
});
test('registered original handler -> private pipe -> Python canonical READ; repeat is safe and DB unchanged',async t=>{
  const data=setup(t),reg=registration(data.config);
  assert.equal(reg.method,'taskcenter.handoff.read');
  assert.deepEqual(reg.options,{scope:'operator.read',profileAccess:'required',sessionAccess:{mode:'read'}});
  const before=readFileSync(data.config.database);
  const a=await invoke(reg,data),b=await invoke(reg,data);
  assert.equal(a.ok,true,JSON.stringify(a));assert.equal(b.ok,true,JSON.stringify(b));
  assert.deepEqual(a.value,b.value);assert.equal(a.value.receipt.state,'HANDOFF_INCOMPLETE_ALERT_QUEUED');
  assert.equal(a.releases,1);assert.deepEqual(readFileSync(data.config.database),before);
});
test('request authority, wrong mapping, missing host handle and shared owner do not authorize',async t=>{
  const data=setup(t),reg=registration(data.config);
  for(const params of [{...data.params,principal_id:'alice'},{...data.params,task_id:'other'},
      {...data.params,action:'VERIFIED'}])assert.equal((await invoke(reg,{...data,params})).ok,false);
  for(const options of [{sessionAccessAuthority:null},{client:{authenticatedUserProfile:{profileId:'gateway-owner'}}},
      {client:{authenticatedUserProfile:{profileId:'other'}}},
      {client:{internal:{syntheticClient:true},authenticatedUserProfile:{profileId:'profile-fixture'}}}]) {
    assert.equal((await invoke(reg,data,{options})).ok,false);
  }
});
test('owner revocation denies before admission and after private read before disclosure',async t=>{
  const data=setup(t),reg=registration(data.config);
  const a=await invoke(reg,data,{revokeAt:1});assert.equal(a.ok,false);assert.equal(a.releases,0);
  const b=await invoke(reg,data,{revokeAt:3});assert.equal(b.ok,false);assert.equal(b.value,undefined);assert.equal(b.releases,1);
  assert.equal((await invoke(reg,data)).ok,true); // a new current invocation, not old authority revival
});
test('original TC grant and session revocation and TEST_ONLY profile remain enforced',async t=>{
  for(const action of ['revoke-grant','revoke-session','test-profile']) {
    const data=setup(t),reg=registration(data.config);data.fixture(action);
    const value=await invoke(reg,data);assert.equal(value.ok,false,action);assert.equal(value.releases,1);
    assert.equal(value.error.message,'TC_OWNER_READ_REJECTED');
  }
});
test('failed child read can retry same operation without new registration or data write',async t=>{
  const data=setup(t),reg=registration(data.config),before=readFileSync(data.config.database);
  const bad={...data,params:{...data.params,event_id:'missing'}};
  assert.equal((await invoke(reg,bad)).ok,false);
  assert.equal((await invoke(reg,data)).ok,true);
  assert.deepEqual(readFileSync(data.config.database),before);
});

test('sandbox-required source, expired mapping and native abort fail closed',async t=>{
  const data=setup(t),reg=registration(data.config);
  const authority={sandboxRequired:true,assertCurrent(){},retain(){throw new Error('must not retain');}};
  assert.equal((await invoke(reg,data,{options:{sessionAccessAuthority:authority}})).ok,false);
  const expired=structuredClone(data.config);expired.bindings[0].expires_at=1;
  assert.equal((await invoke(registration(expired),data)).ok,false);
  const aborted=await invoke(reg,data,{abortAt:2});assert.equal(aborted.ok,false);assert.equal(aborted.releases,1);
  assert.equal((await invoke(reg,data)).ok,true);
});

test('missing canonical database is not created or replaced',async t=>{
  const data=setup(t),config=structuredClone(data.config);
  config.database=join(data.dir,'must-not-create.sqlite');
  assert.equal((await invoke(registration(config),data)).ok,false);
  assert.equal(existsSync(config.database),false);
  assert.equal((await invoke(registration(data.config),data)).ok,true);
});
