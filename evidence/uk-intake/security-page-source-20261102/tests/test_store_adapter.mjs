// Adapter orchestration tests with synthetic callbacks, NOT Gateway integration.
import assert from 'node:assert/strict';
import {createProtectedBundleWriter,resolveAcceptanceBundle,NAMES} from '../openclaw_store_adapter.mjs';
let count=0; const check=x=>{assert.ok(x);count++;};
let writes=0,seen;
const writer=createProtectedBundleWriter({writeSecretStoreEntries:p=>{writes++;seen=p;return ['secret','secret','secret'];},
 listSecretStoreEntries:()=>NAMES.map(name=>({name,kind:'secret',allowedHosts:[],updatedAtMs:1,valuePreview:'OMIT_ME'})),
 resolveStoreProvider:()=> 'default',updatedBy:'synthetic-owner',database:{path:'NOT_OPENED'}});
const values=Object.fromEntries(NAMES.map(n=>[n,'non-sensitive-canary']));
check(writer.write(values).status==='STORED');
check(seen.entries.length===3 && seen.entries.every(e=>e.kind==='secret'&&e.allowedHosts.length===0));
check(!JSON.stringify(writer.metadata()).includes('OMIT_ME'));
check(writer.metadata().every(e=>e.secretRef.source==='store'));
let thrown=false;try{writer.write({...values,OTHER:'test'});}catch{thrown=true;}check(thrown&&writes===1);
const admitted={id:'request-1',questionId:'question-1',purpose:'community-admin-acceptance',version:'community-acceptance-v1',resolvedBy:'owner'};
let answers,managerWrites=0;
const manager={resolve(id,a,by,options){answers=a;options.commit();managerWrites++;}};
const params={authorizeOriginalQuestion:()=>admitted,manager,writer,requestId:'request-1',resolutionId:'resolution-1',values,reloadReferences:async()=>{}};
check((await resolveAcceptanceBundle(params)).status==='STORED');
check(JSON.stringify(answers)==='{"answers":{"question-1":["stored"]}}');
check((await resolveAcceptanceBundle({...params,authorizeOriginalQuestion:()=>({...admitted,id:'other'})})).status==='FORBIDDEN');
check((await resolveAcceptanceBundle({...params,authorizeOriginalQuestion:()=>null})).status==='FORBIDDEN');
check(managerWrites===1);
check((await resolveAcceptanceBundle({...params,reloadReferences:async()=>{throw Error('no secret output');}})).status==='STORED_REFRESH_PENDING');
check((await resolveAcceptanceBundle({...params,manager:{resolve(){throw Error('no secret output');}}})).status==='UNKNOWN_QUERY_ORIGINAL');
console.log(JSON.stringify({stage:'ADAPTER_SYNTHETIC_ORCHESTRATION',checks:count,pass:true,production:false}));
