/** Glue for the original dedicated isolated Gateway owner, not its implementation.
 * Runtime provenance/root exposure is still UNBOUND. Never use on a shared Gateway.
 * isActiveHere must be the original SDK isAsyncWorkScopeActiveHere export.
 */
export function createNativeGatewayDrain({connectionWork:owner,isActiveHere}) {
 if(!owner||typeof owner.beginClose!=='function'||typeof owner.drain!=='function'||typeof isActiveHere!=='function')throw Error('HOLD_NATIVE_WORK_INTERFACE');
 return async ({connectionWork})=>{
  if(connectionWork!==owner)throw Error('HOLD_NATIVE_WORK_IDENTITY');
  const active=isActiveHere(owner);
  if(active!==false)throw Error('HOLD_NATIVE_WORK_SELF_JOIN_OR_UNKNOWN');
  // Original beginClose cancels admission; original drain closes registered
  // connections and joins dynamically admitted cleanup. No local tracker copy.
  if(owner.beginClose()!==undefined)throw Error('HOLD_NATIVE_BEGIN_CLOSE_RESULT');
  const pending=owner.drain();
  if(!pending||typeof pending.then!=='function')throw Error('HOLD_NATIVE_DRAIN_PROMISE');
  if(await pending!==undefined)throw Error('HOLD_NATIVE_DRAIN_RESULT');
  if(owner.hasPendingWork!==false||owner.isClosing!==true||owner.signal?.aborted!==true)throw Error('HOLD_NATIVE_DRAIN_STATE');
 };
}
