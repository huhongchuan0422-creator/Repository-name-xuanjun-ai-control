/** Negative-policy candidate for the ORIGINAL browser executor. NOT an injector.
 * This file never resolves SecretRefs, launches a browser or accepts plaintext
 * credentials. A passing result is POLICY_ONLY, not proof of supported injection.
 * Inputs must be derived inside trusted original host, not model-supplied grants.
 */
import {NAMES} from './openclaw_store_adapter.mjs';
export function checkOriginalBrowserRefPolicy({refs,configuredStoreProvider,targetUrl,
  topLevelUrl,frameUrl,approvedOrigin,allowedHosts=[],ownerAuthorized=false,
  supportedConsumerVerified=false,observationBoundaryVerified=false}) {
  try {
    if (!ownerAuthorized) return {status:'FORBIDDEN'};
    if (typeof configuredStoreProvider!=='string' || !/^[a-z][a-z0-9_-]{0,63}$/.test(configuredStoreProvider) ||
        !Array.isArray(refs) || refs.length!==3 || !NAMES.every(name=>refs.filter(r=>
        r && Object.keys(r).length===3 && r.source==='store' &&
        r.provider===configuredStoreProvider && r.id===name).length===1))
      return {status:'REF_BINDING_REJECTED'};
    if (!Array.isArray(allowedHosts) || allowedHosts.length===0) return {status:'EGRESS_DENIED'};
    const approved=new URL(approvedOrigin);
    const urls=[targetUrl,topLevelUrl,frameUrl].map(u=>new URL(u));
    if (approved.protocol!=='https:' || approved.username || approved.password ||
        urls.some(u=>u.protocol!=='https:' || u.username || u.password ||
          u.origin!==approved.origin || !allowedHosts.includes(u.hostname)))
      return {status:'DESTINATION_REJECTED'};
    if (!supportedConsumerVerified) return {status:'BROWSER_SECRET_INJECTION_UNSUPPORTED'};
    if (!observationBoundaryVerified) return {status:'HOLD_OBSERVATION_BOUNDARY'};
    // Deliberately no URL/refs/values in output; cannot substitute for runtime proof.
    return {status:'POLICY_ONLY_NOT_INJECTED'};
  } catch {return {status:'DESTINATION_REJECTED'};}
}
