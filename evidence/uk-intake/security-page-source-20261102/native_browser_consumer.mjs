/** PRIVATE original-executor candidate. Never register as a model plaintext tool.
 * Runtime adapter MUST establish original auth/run/document/observer/network
 * admission. No production adapter exists yet; absent adapter fails CLOSED.
 * SQLite is the existing shared state only. This module creates no schema/store.
 */
import {NAMES} from './openclaw_store_adapter.mjs';
const denial=code=>Object.freeze({status:code});
function validRefs(refs,provider){return Array.isArray(refs)&&refs.length===3&&NAMES.every(name=>refs.filter(r=>r&&Object.keys(r).length===3&&r.source==='store'&&r.provider===provider&&r.id===name).length===1);}
function origin(value){const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password)throw Error('REJECT');return u;}
export function createNativeAcceptanceConsumer({withReadSnapshot,database,authorize,acquirePrivateBoundary}){
 return Object.freeze({
  // PRIVATE trusted planner metadata; no value read and no model-facing RPC.
  async revisionMetadata(request){
   try{
    if(typeof authorize!=='function'||typeof withReadSnapshot!=='function'||!request||typeof request.targetId!=='string'||!request.targetId||Object.keys(request).some(k=>!['refs','targetId'].includes(k)))return denial('FORBIDDEN');
    const authority=await authorize(request.targetId);authority.assertCurrent();const p=authority.plan;
    if(!p||p.purpose!=='community-admin-acceptance'||p.version!=='community-acceptance-v1'||typeof p.storeProvider!=='string'||!p.storeProvider||!validRefs(request.refs,p.storeProvider))return denial('REF_BINDING_REJECTED');
    const rows=withReadSnapshot(({db})=>{authority.assertCurrent();return db.prepare("SELECT name,kind,revision_token FROM secret_store_entries WHERE scope_kind='team' AND scope_id='' AND deleted_at_ms IS NULL AND name IN (?,?,?)").all(...NAMES);},database);
    if(rows.length!==3||rows.some(r=>r.kind!=='secret'||typeof r.revision_token!=='string'||!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(r.revision_token)))return denial('VERSION_BINDING_REQUIRED');
    authority.assertCurrent();return {status:'REVISION_METADATA',versions:Object.fromEntries(rows.map(r=>[r.name,r.revision_token]))};
   }catch{return denial('REVISION_METADATA_UNAVAILABLE');}
  },
  async login(request){
   // request carries references and an existing target ID, NEVER values/grants.
   if(typeof authorize!=='function'||typeof withReadSnapshot!=='function'||typeof acquirePrivateBoundary!=='function')return denial('BROWSER_SECRET_INJECTION_UNSUPPORTED');
   let lease;
   try{
    if(!request||Object.keys(request).some(k=>!['refs','targetId'].includes(k))||typeof request.targetId!=='string'||!request.targetId)return denial('INVALID_REF_REQUEST');
    const authority=await authorize(request.targetId); // original server-owned scope/role/run authority
    if(!authority||typeof authority.assertCurrent!=='function')return denial('FORBIDDEN');
    authority.assertCurrent();
    const plan=authority.plan; // trusted, version-bound original acceptance plan, not body
    if(!plan||typeof plan.storeProvider!=='string'||!plan.storeProvider||plan.purpose!=='community-admin-acceptance'||plan.version!=='community-acceptance-v1'||!validRefs(request.refs,plan.storeProvider))return denial('REF_BINDING_REJECTED');
    const approved=origin(plan.approvedOrigin);
    if(approved.href!==approved.origin+'/')return denial('DESTINATION_REJECTED');
    if(!Array.isArray(plan.allowedHosts)||plan.allowedHosts.length!==1||plan.allowedHosts[0]!==approved.hostname)return denial('EGRESS_DENIED');
    if(!plan.secretVersions||!NAMES.every(n=>typeof plan.secretVersions[n]==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(plan.secretVersions[n])))return denial('VERSION_BINDING_REQUIRED');
    // Boundary is acquired BEFORE any store values are read. Its implementation
    // must pin document, drain preexisting actions, stop collectors/trace/video,
    // intercept ALL context request channels and keep output quarantined.
    lease=await acquirePrivateBoundary({targetId:request.targetId,authority,approvedOrigin:approved.origin});
    if(!lease||typeof lease.run!=='function'||typeof lease.finishQuarantined!=='function')return denial('HOLD_OBSERVATION_BOUNDARY');
    const result=await lease.run(async({page,assertCurrent,assertDestination,assertVersionCurrent,usernameLocator,passwordLocator,submitLocator,loginSuccess})=>{
     authority.assertCurrent();assertCurrent();
     await assertDestination(approved.origin); // exact original top/frame/document + SSRF checks
     // One original-DB statement gives values and policy from SAME row versions.
     const bundle=withReadSnapshot(({db})=>{
      authority.assertCurrent();assertCurrent();
      const rows=db.prepare("SELECT name,value,kind,allowed_hosts,revision_token FROM secret_store_entries WHERE scope_kind='team' AND scope_id='' AND deleted_at_ms IS NULL AND name IN (?,?,?)").all(...NAMES);
      if(rows.length!==3)throw Error('REF_UNAVAILABLE');
      const byName=new Map(rows.map(r=>[r.name,r]));
      for(const name of NAMES){const r=byName.get(name);let hosts;try{hosts=JSON.parse(r.allowed_hosts);}catch{throw Error('EGRESS_DENIED');}
       if(!r||r.kind!=='secret'||typeof r.value!=='string'||!r.value||!Array.isArray(hosts)||!hosts.includes(approved.hostname)||r.revision_token!==plan.secretVersions[name])throw Error('REF_POLICY_REJECTED');
      }
      return byName;
     },database);
     try{
      const url=origin(bundle.get(NAMES[0]).value);
      if(url.origin!==approved.origin)throw Error('DESTINATION_REJECTED');
      // Navigation occurs only within already-installed all-channel boundary.
      await assertVersionCurrent(plan.secretVersions);authority.assertCurrent();assertCurrent();
      await page.goto(url.href);await assertDestination(approved.origin);
      // Selectors/locators are original trusted page-plan artifacts, never body.
      const user=await usernameLocator(page),password=await passwordLocator(page),submit=await submitLocator(page);
      await assertVersionCurrent(plan.secretVersions);authority.assertCurrent();assertCurrent();
      await user.fill(bundle.get(NAMES[1]).value);
      await assertDestination(approved.origin);await assertVersionCurrent(plan.secretVersions);authority.assertCurrent();assertCurrent();
      await password.fill(bundle.get(NAMES[2]).value);
      await assertDestination(approved.origin);await assertVersionCurrent(plan.secretVersions);authority.assertCurrent();assertCurrent();
      await submit.click();await assertDestination(approved.origin);
      authority.assertCurrent();assertCurrent();
      // Never return DOM/text/screenshot/exception; a trusted exact success check.
      return (await loginSuccess(page))===true?denial('LOGIN_CONFIRMED_OBSERVATION_QUARANTINED'):denial('LOGIN_NOT_CONFIRMED');
     }finally{bundle.clear();} // JS strings cannot promise cryptographic zeroization.
    });
    await lease.finishQuarantined(); // does NOT reopen raw browser observation
    return result;
   }catch{
    if(lease)try{await lease.finishQuarantined();}catch{}
    return denial('PRIVATE_LOGIN_UNCONFIRMED'); // no cause/stack/value echo
   }
  }
 });
}
