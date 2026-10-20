/** Combined contract, not an SDK importer or authentication implementation.
 * Callbacks must eventually be supplied by the pinned real isolated transport.
 * Fixture callbacks NEVER establish CP11 or authenticated-dispatch success.
 */
import {bindFixedInspectionExport,inspectReadonlyLease,PLUGIN,READONLY_PROFILE,digest} from './b5_loader_contract.mjs';
export const METHOD='xuanjun.capabilities.describe';
const SOURCE='848b0b77df2ee65394c810de8aea40402abc0cf46e8d1eb66a014f2890eedba9';
const capabilities=[{method:METHOD,operation:'describe',read_only:true,required_scope:'operator.admin'}];
const declaration={plugin_id:PLUGIN,plugin_version:READONLY_PROFILE.version,declared_capabilities:capabilities};
export function validateMetadata(value) {
 const expected={...declaration,plugin_source_sha256:SOURCE,declaration_sha256:digest(declaration)};
 if(!value||Object.keys(value).sort().join(',')!==Object.keys(expected).sort().join(',')||
   Object.keys(expected).some(k=>JSON.stringify(value[k])!==JSON.stringify(expected[k])))
  throw new Error('HOLD_READONLY_METADATA');
 return expected;
}
export async function combinedContract({namespace,files,expectedSource,record,dispatch}) {
 // Byte gate precedes any callback. No arbitrary aliases or dynamic module paths.
 const acquire=bindFixedInspectionExport(namespace,files);
 if(typeof dispatch!=='function')throw new Error('HOLD_AUTHENTICATED_TRANSPORT_UNBOUND');
 const lifecycle=await inspectReadonlyLease({acquire,expectedSource,record,
  whileAcquired:async()=>validateMetadata(await dispatch(METHOD,{operation:'describe'}))});
 return {...lifecycle,scope:'CONTRACT_ONLY',realLoader:'NOT_EXECUTED',authenticatedDispatch:'NOT_EXECUTED',cp11:'NOT_EXECUTED'};
}
