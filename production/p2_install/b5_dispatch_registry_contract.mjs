/** Trusted composition-root contract, NOT an authentication implementation.
 * SDK callbacks are not proof of compiled provenance. No SDK import occurs here.
 * The actual WebSocket owner supplies its existing handler/context and clients;
 * this module never creates clients, grants/scopes, active registry or auth flags.
 */
import {createHash} from 'node:crypto';
import {inspectReadonlyLease,validateRegistry,PLUGIN} from './b5_loader_contract.mjs';
import {METHOD,validateMetadata} from './b5_combined_contract.mjs';
const hold=code=>{throw new Error(code);};
export const COMPILED_DISPATCH_BINDING=Object.freeze({state:'UNBOUND',registryModule:'dist/registry-CAoo0u-p.mjs',registrySha256:'6e370c7c50d3fc0c1502aec39a43bf84471210b6c8871e67a5019fa05236888f',dispatcherSha256:null,realAuthentication:'NOT_EXECUTED'});
function checkDescriptor(d,handler) {
 if(!d||d.name!==METHOD||d.handler!==handler||d.scope!=='operator.admin'||d.owner?.kind!=='plugin'||d.owner.pluginId!==PLUGIN||d.profileAccess!=='required'||d.sessionAccess!==undefined||d.controlPlaneWrite===true)hold('HOLD_METHOD_DESCRIPTOR');
}
export function inspectionMethodRegistry({registryApi,registry,expectedSource}) {
 validateRegistry(registry,expectedSource,'readonly');
 for(const key of ['createPluginGatewayMethodDescriptors','createGatewayMethodRegistry'])if(typeof registryApi?.[key]!=='function')hold('HOLD_REAL_REGISTRY_API_UNBOUND');
 // Use the real plugin descriptors; do not invent handler-only/admin fallback rows.
 const input=registryApi.createPluginGatewayMethodDescriptors(registry);
 if(!Array.isArray(input)||input.length!==1)hold('HOLD_METHOD_DESCRIPTOR_SET');
 const handler=registry.gatewayHandlers[METHOD];checkDescriptor(input[0],handler);
 const methods=registryApi.createGatewayMethodRegistry(input,registry);
 for(const key of ['getHandler','getScope','listMethods','requiresAuthenticatedProfile','descriptors','isControlPlaneWrite'])if(typeof methods?.[key]!=='function')hold('HOLD_METHOD_REGISTRY_API');
 if(methods.pluginRegistry!==registry||methods.getHandler(METHOD)!==handler||methods.getScope(METHOD)!=='operator.admin'||methods.requiresAuthenticatedProfile(METHOD)!==true||methods.isControlPlaneWrite(METHOD)!==false||JSON.stringify(methods.listMethods())!==JSON.stringify([METHOD]))hold('HOLD_METHOD_REGISTRY_BINDING');
 const normalized=methods.descriptors();if(!Array.isArray(normalized)||normalized.length!==1)hold('HOLD_METHOD_DESCRIPTOR_SET');checkDescriptor(normalized[0],handler);
 return methods;
}
export function inspectionDispatcherParams({params,methodRegistry}) {
 if(!params||Object.keys(params).sort().join(',')!=='handler,isWebchatConnect'||typeof params.isWebchatConnect!=='function'||!params.handler||typeof params.handler!=='object')hold('HOLD_WS_COMPOSITION_OWNER');
 // These are request/client facts, never composition-root configuration.
 for(const key of ['client','connect','scopes','authPolicy','authenticated','req','expectedProfileBinding'])if(Object.hasOwn(params.handler,key))hold('HOLD_REQUEST_FACTS_IN_OWNER_CONFIG');
 for(const key of ['buildRequestContext','send','close','isClosed'])if(typeof params.handler[key]!=='function')hold('HOLD_WS_COMPOSITION_OWNER');
 // All existing auth policy/context/client owner closures retain identity. Only this
 // per-request method-registry getter changes. No global setter/extra-handler trick.
 return {...params,handler:{...params.handler,getMethodRegistry:()=>methodRegistry}};
}
export function readonlyRequestFrame(frame) {
 if(!frame||frame.type!=='req'||frame.method!==METHOD||!frame.params||Object.keys(frame.params).join(',')!=='operation'||frame.params.operation!=='describe')hold('HOLD_B5_READONLY_REQUEST');
 for(const key of ['client','connect','scopes','authPolicy','authenticated'])if(Object.hasOwn(frame,key))hold('HOLD_REQUEST_AUTH_CLAIM');
 return frame; // Preserve id/profile binding/trace; actual protocol validation stays upstream.
}
export async function withInspectionDispatcherContract({acquire,registryApi,createAuthenticatedDispatcher,params,expectedSource,record,runAuthenticatedOwner}) {
 if(typeof acquire!=='function'||typeof createAuthenticatedDispatcher!=='function'||typeof runAuthenticatedOwner!=='function')hold('HOLD_AUTHENTICATED_OWNER_UNBOUND');
 let open=false,lease;
 const ownedAcquire=async options=>{lease=await acquire(options);return lease;};
 const result=await inspectReadonlyLease({acquire:ownedAcquire,expectedSource,record,whileAcquired:async()=>{
  const methodRegistry=inspectionMethodRegistry({registryApi,registry:lease.registry,expectedSource});
  const publications=new Map(),wrapped=new WeakSet();
  const observeSender=sender=>{
   if(wrapped.has(sender))return sender;
   const observed=(frame,...args)=>{
    const result=sender(frame,...args); // Preserve native transport result/policy behavior.
    const item=frame?.type==='res'?publications.get(frame.id):undefined;
    if(item) {
     item.count++;
     try {
      if(result?.kind!=='sent'||frame.ok!==true||frame.error!==undefined)hold('HOLD_NATIVE_PUBLICATION_REJECTED');
      validateMetadata(frame.payload);item.success=true;
     } catch(error) {item.error=error;item.nativeError=frame.error;}
    }
    return result;
   };
   wrapped.add(observed);return observed;
  };
  const configured=inspectionDispatcherParams({params,methodRegistry});
  const dispatcher=createAuthenticatedDispatcher({...configured,handler:{...configured.handler,send:observeSender(configured.handler.send)}});
  if(typeof dispatcher?.dispatch!=='function')hold('HOLD_REAL_DISPATCHER_UNBOUND');
  open=true;const pending=new Set(),dispatchErrors=[];let primary;
  try {
   const guarded=Object.freeze({dispatch:(frame,...ownerArgs)=>{
    if(!open)hold('HOLD_INSPECTION_LEASE_CLOSED');
    readonlyRequestFrame(frame);
    if(typeof frame.id!=='string'||!frame.id.length||frame.id.length>256||publications.has(frame.id))hold('HOLD_REQUEST_ID');
    publications.set(frame.id,{count:0,success:false});
    // Existing authenticated-owner arguments retain identity. A custom native
    // response sender, if present, is observed without changing its result.
    if(ownerArgs[3]!==undefined){if(typeof ownerArgs[3]!=='function')hold('HOLD_NATIVE_RESPONSE_OWNER');ownerArgs[3]=observeSender(ownerArgs[3]);}
    const promise=Promise.resolve(dispatcher.dispatch(frame,...ownerArgs));
    pending.add(promise);promise.then(()=>pending.delete(promise),error=>{dispatchErrors.push(error);pending.delete(promise);});
    return promise;
   }});
   await runAuthenticatedOwner(guarded); // Return value is NOT response evidence.
  } catch(error) {primary=new Error('HOLD_AUTHENTICATED_OWNER_FAILED');primary.cause=error;}
  finally {
   open=false; // Stop new admission; never abandon a dispatched owner request.
   await Promise.allSettled([...pending]);
  }
  if(primary)throw primary;
  if(dispatchErrors.length){const error=new Error('HOLD_NATIVE_DISPATCH_FAILED');error.cause=dispatchErrors[0];throw error;}
  if(!publications.size)hold('HOLD_NO_NATIVE_METADATA_PUBLICATION');
  for(const item of publications.values())if(item.count!==1||!item.success||item.error){const error=new Error('HOLD_NATIVE_METADATA_PUBLICATION');error.cause=item.error;error.nativeError=item.nativeError;throw error;}

 }});
 return {...result,scope:'CONTRACT_ONLY',compiledBinding:COMPILED_DISPATCH_BINDING.state,realLoader:'NOT_EXECUTED',authenticatedDispatch:'NOT_EXECUTED',cp11:'NOT_EXECUTED'};
}

/** Actual received bytes, static binding only. Never import/evaluate these modules. */
export const RECEIVED_DISPATCH_FILES=Object.freeze({
 'package.json':'214e9551a924a9ced04ecf38c7ed8f6bff8beeab33431db12ed6250eaa959e95',
 'dist/descriptor-C-QJ0nle.mjs':'ec5ff718c1b792fc7792a6afdf3da933d6d9e2ad4e32aede60bfe0e7c329b95c',
 'dist/registry-CAoo0u-p.mjs':'6e370c7c50d3fc0c1502aec39a43bf84471210b6c8871e67a5019fa05236888f',
 'dist/authenticated-request-dispatch.server-methods.runtime-C6C-oLg5.mjs':'d0c84817478302036b34ee42daf7c869be1a72b02de5f95d8d6ff0aaf8fd1c7a',
 'dist/authenticated-request-dispatch.server-methods.runtime.js':'b9f8dd4a708fc1c0b4eea8f9cb6d52550bb33fd4e2796c76a6a724087810e36e',
 'dist/server-methods-DJEQKCcV.mjs':'6a4db1ab8f440777eb96f7149dc00f12d311770d1400629092c990f6e92a3848',
 'dist/server-methods-DmuZ2oH_.mjs':'28e78f59498d06d42b4e8c639d48dc2f05c694d504413d44bc875509c5c6cc9c'
});
export function verifyReceivedDispatchBytes(files) {
 if(!files||Object.keys(files).sort().join(',')!==Object.keys(RECEIVED_DISPATCH_FILES).sort().join(','))hold('HOLD_DISPATCH_BYTE_SET');
 for(const [name,pin] of Object.entries(RECEIVED_DISPATCH_FILES))if(!Buffer.isBuffer(files[name])||createHash('sha256').update(files[name]).digest('hex')!==pin)hold('HOLD_DISPATCH_SOURCE_SHA');
 if(JSON.parse(files['package.json'].toString('utf8')).version!=='2026.9.9')hold('HOLD_DISPATCH_VERSION');
 const registry=files['dist/registry-CAoo0u-p.mjs'].toString('utf8');
 if(!/export\s*\{\s*createGatewayMethodRegistry as n, createPluginGatewayMethodDescriptors as r, createGatewayMethodDescriptorsFromHandlers as t\s*\}/.test(registry))hold('HOLD_REGISTRY_FIXED_EXPORTS');
 const bridge=files['dist/authenticated-request-dispatch.server-methods.runtime-C6C-oLg5.mjs'].toString('utf8');
 if(!bridge.includes('import { r as handleGatewayRequest } from "./server-methods-DJEQKCcV.mjs";')||!bridge.includes('export { handleGatewayRequest };'))hold('HOLD_DISPATCH_FIXED_BRIDGE');
 return {state:'RECEIVED_STATIC_BYTES_BOUND',realAuthentication:'NOT_EXECUTED',dependencyClosure:'UNKNOWN'};
}
export function bindReceivedRegistryNamespace(namespace,files) {
 verifyReceivedDispatchBytes(files);
 const result={};
 for(const [name,alias] of [['createGatewayMethodRegistry','n'],['createPluginGatewayMethodDescriptors','r']]) {
  const own=namespace&&Object.getOwnPropertyDescriptor(namespace,alias);
  if(!own||!Object.hasOwn(own,'value')||typeof own.value!=='function')hold('HOLD_REGISTRY_FIXED_NAMESPACE');
  result[name]=own.value;
 }
 // The trusted owner still must prove this namespace came from the same immutable
 // closure. A caller-injected namespace/fixture is never runtime/authentication proof.
 return Object.freeze(result);
}
