/** Fixed public WS seam; contract preparation only. No SDK import/authentication. */
import {createHash} from 'node:crypto';
import {inspectReadonlyLease} from './b5_loader_contract.mjs';
import {inspectionMethodRegistry,readonlyRequestFrame} from './b5_dispatch_registry_contract.mjs';
import {validateMetadata} from './b5_combined_contract.mjs';
const hold=code=>{throw new Error(code);};
export const WS_FILES=Object.freeze({
 'dist/run-BNH_gC9b.mjs':'55673f688f7e455cd1bfdaf6a0f26270ff5e6565881403c1b066a82530ab810f',
 'dist/message-handler-DKklmnFX.mjs':'ff332fdec514638bdd1655a510a7544f5b9a848eccf11c951851b97e192410f0',
 'dist/ws-connection-CsJ9cE0L.mjs':'b51e1190bd1ca47b2497311e798ee95c2d7acd1e1a410bc6f6c1b1aeb5862f53'
});
export function bindPublicWsNamespace(namespace,files,packageBytes) {
 if(!Buffer.isBuffer(packageBytes)||createHash('sha256').update(packageBytes).digest('hex')!=='214e9551a924a9ced04ecf38c7ed8f6bff8beeab33431db12ed6250eaa959e95'||JSON.parse(packageBytes).version!=='2026.9.9')hold('HOLD_WS_VERSION_BYTES');
 if(!files||Object.keys(files).sort().join()!==Object.keys(WS_FILES).sort().join())hold('HOLD_WS_BYTE_SET');
 for(const [name,pin] of Object.entries(WS_FILES))if(!Buffer.isBuffer(files[name])||createHash('sha256').update(files[name]).digest('hex')!==pin)hold('HOLD_WS_SOURCE_SHA');
 const text=files['dist/message-handler-DKklmnFX.mjs'].toString('utf8');
 if(!text.includes('export { attachGatewayWsMessageHandler };')||!text.includes('return onMessage;')||!text.includes('params.connectionWork.track('))hold('HOLD_WS_PUBLIC_EXPORT');
 const d=namespace&&Object.getOwnPropertyDescriptor(namespace,'attachGatewayWsMessageHandler');
 if(!d||!Object.hasOwn(d,'value')||typeof d.value!=='function')hold('HOLD_WS_NAMESPACE');
 return Object.freeze({attach:d.value,sourceState:'STATIC_BYTES_BOUND_ONLY',runtimeProvenance:'UNBOUND'});
}
/** Owner provides native quiesce+work/cleanup drain. This callback's actual compiled
 * implementation is still UNBOUND; a fixture or returned flag is never real proof.
 * No copies of the internal dispatcher, auth client, scopes or connectionWork.
 */
export async function withPublicWsContract({acquire,registryApi,attach,params,expectedSource,record,runTransportOwner,quiesceAndDrain}) {
 if(typeof attach!=='function'||typeof runTransportOwner!=='function'||typeof quiesceAndDrain!=='function')hold('HOLD_WS_OWNER_UNBOUND');
 for(const key of ['client','connect','scopes','authPolicy','authenticated','expectedProfileBinding'])if(Object.hasOwn(params??{},key))hold('HOLD_WS_OWNER_AUTH_FACTS');
 for(const k of ['getClient','buildRequestContext','send','close','isClosed'])if(typeof params?.[k]!=='function')hold('HOLD_WS_OWNER_PARAMS');
 if(!params.socket||typeof params.socket.on!=='function'||typeof params.socket.off!=='function'||typeof params.connectionWork?.track!=='function')hold('HOLD_WS_OWNER_PARAMS');
 let lease,drained=true;
 const result=await inspectReadonlyLease({expectedSource,record,acquire:async options=>{
  lease=await acquire(options);return {registry:lease.registry,release:async()=>{if(!drained)hold('HOLD_WS_WORK_NOT_DRAINED');await lease.release();}};
 },whileAcquired:async()=>{
  const methods=inspectionMethodRegistry({registryApi,registry:lease.registry,expectedSource});
  const publications=new Map(),errors=[];let native,guard,accepting=true,primary;
  const configured={...params,getMethodRegistry:()=>methods,send:(frame,...args)=>{
   const result=params.send(frame,...args),item=frame?.type==='res'?publications.get(frame.id):undefined;
   if(item){item.count++;try{if(result?.kind!=='sent'||frame.ok!==true||frame.error!==undefined)hold('HOLD_WS_PUBLICATION_DENIED');validateMetadata(frame.payload);item.ok=true;}catch(e){errors.push(e);}}
   return result;
  }};
  try {
   // Mark unknown before attach: a throwing attach may already own queued work.
   drained=false;native=attach(configured);
   if(typeof native!=='function')hold('HOLD_WS_ONMESSAGE_RETURN');
   params.socket.off('message',native);
   guard=data=>{
    if(!accepting)hold('HOLD_WS_INGRESS_CLOSED');
    try {
     if(!(Buffer.isBuffer(data)||typeof data==='string')||Buffer.byteLength(data)>65536)hold('HOLD_WS_FRAME_BOUND');
     const frame=JSON.parse(data.toString());
     if(frame?.type==='req'&&frame.method==='connect'&&!params.getClient())return native(data);
     readonlyRequestFrame(frame);
     if(typeof frame.id!=='string'||!frame.id.length||frame.id.length>256||publications.has(frame.id))hold('HOLD_WS_REQUEST_ID');
     publications.set(frame.id,{count:0,ok:false});return native(data); // void is NOT settled work.
    }catch(e){errors.push(e);params.close(1008,'B5 readonly ingress rejected');}
   };
   params.socket.on('message',guard);
   await runTransportOwner(); // Native socket/handshake owner, no fabricated client arguments.
  }catch(e){primary=e;}
  finally {
   accepting=false;
   // If attach threw before returning, owner must remove partial native listeners too.
   if(guard)params.socket.off('message',guard);
   try {const completed=await quiesceAndDrain({socket:params.socket,connectionWork:params.connectionWork});if(completed!==undefined)hold('HOLD_WS_DRAIN_RESULT_CONTRACT');drained=true;}
   catch(e){errors.push(e);}
  }
  if(!drained)hold('HOLD_WS_WORK_NOT_DRAINED');
  if(primary)throw primary;
  if(errors.length){const e=new Error('HOLD_WS_WORK_OR_RESPONSE');e.cause=errors[0];throw e;}
  if(!publications.size||[...publications.values()].some(x=>x.count!==1||!x.ok))hold('HOLD_WS_NO_CORRELATED_RESPONSE');
 }});
 return {...result,scope:'CONTRACT_ONLY',publicEntry:'attachGatewayWsMessageHandler',compiledEntry:'STATIC_BYTES_BOUND_ONLY',nativeWorkDrain:'UNBOUND_OWNER_CONTRACT',realLoader:'NOT_EXECUTED',authenticatedDispatch:'NOT_EXECUTED',dependencyClosure:'UNKNOWN',cp11:'NOT_EXECUTED'};
}
