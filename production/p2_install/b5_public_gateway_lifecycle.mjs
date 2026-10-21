/** Public-handle lifecycle contract only. No SDK import or fake kernel/registry.
 * Inspection and Gateway runtime are distinct owners; never lend the inspection
 * registry or fabricate internal connectionWork to bridge the public boundary.
 */
import {inspectReadonlyLease} from './b5_loader_contract.mjs';
import {validateMetadata} from './b5_combined_contract.mjs';
export async function publicGatewayReadonlyLifecycle({acquire,expectedSource,record,startGateway,runAuthenticatedClient}) {
 if(typeof startGateway!=='function'||typeof runAuthenticatedClient!=='function')throw Error('HOLD_PUBLIC_GATEWAY_BINDING');
 // All inspection resources are released before another registry is acquired.
 await inspectReadonlyLease({acquire,expectedSource,record});
 let server,primary,closeError;
 try {
  server=await startGateway();
  if(!server||typeof server.close!=='function')throw Error('HOLD_PUBLIC_GATEWAY_HANDLE_UNKNOWN');
  // Caller must eventually bind original GatewayClient, not a constructed client
  // fact, mocked dispatcher or manually supplied authenticated principal.
  validateMetadata(await runAuthenticatedClient(server));
 }catch(e){primary=e;}
 finally {
  if(server&&typeof server.close==='function'){
   try {
    const closing=server.close({reason:'B5 readonly inspection completed'});
    if(!closing||typeof closing.then!=='function')throw Error('HOLD_PUBLIC_GATEWAY_CLOSE_PROMISE');
    if(await closing!==undefined)throw Error('HOLD_PUBLIC_GATEWAY_CLOSE_RESULT');
   }catch(e){closeError=e;}
  }
 }
 if(closeError){const e=Error('HOLD_PUBLIC_GATEWAY_CLOSE_UNKNOWN');e.cause=primary;e.closeCause=closeError;throw e;}
 if(primary)throw primary;
 return {scope:'PUBLIC_LIFECYCLE_CONTRACT_ONLY',inspectionOwner:'SEPARATE_RELEASED',runtimeOwner:'PUBLIC_SERVER_HANDLE_ONLY',runtimeBinding:'UNBOUND',authenticatedDispatch:'NOT_EXECUTED',cp11:'NOT_EXECUTED'};
}
