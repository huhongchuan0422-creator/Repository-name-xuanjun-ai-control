import assert from 'node:assert/strict';
import {NAMES} from '../openclaw_store_adapter.mjs';
import {checkOriginalBrowserRefPolicy as policy} from '../browser_ref_policy.mjs';
const base={refs:NAMES.map(id=>({source:'store',provider:'default',id})),configuredStoreProvider:'default',
 targetUrl:'https://community.example.invalid/login',topLevelUrl:'https://community.example.invalid/login',
 frameUrl:'https://community.example.invalid/login',approvedOrigin:'https://community.example.invalid',
 allowedHosts:[],ownerAuthorized:true};
let checks=0;const check=(overrides,expected)=>{assert.equal(policy({...base,...overrides}).status,expected);checks++;};
check({},'EGRESS_DENIED');check({ownerAuthorized:false},'FORBIDDEN');
check({refs:[{source:'store',provider:'default',id:'OTHER'}]},'REF_BINDING_REJECTED');
const hosts={allowedHosts:['community.example.invalid']};
check(hosts,'BROWSER_SECRET_INJECTION_UNSUPPORTED');
check({...hosts,targetUrl:'http://community.example.invalid/login'},'DESTINATION_REJECTED');
check({...hosts,topLevelUrl:'https://attacker.invalid/redirect'},'DESTINATION_REJECTED');
check({...hosts,frameUrl:'https://community.example.invalid.attacker.invalid'},'DESTINATION_REJECTED');
check({...hosts,targetUrl:'https://user:synthetic@community.example.invalid'},'DESTINATION_REJECTED');
check({...hosts,targetUrl:'https://community.example.invalid:8443/login'},'DESTINATION_REJECTED');
check({...hosts,allowedHosts:['*.example.invalid']},'DESTINATION_REJECTED');
check({...hosts,supportedConsumerVerified:true},'HOLD_OBSERVATION_BOUNDARY');
check({...hosts,supportedConsumerVerified:true,observationBoundaryVerified:true},'POLICY_ONLY_NOT_INJECTED');
console.log(JSON.stringify({stage:'BROWSER_REF_NEGATIVE_POLICY_ONLY',checks,pass:true,injection:false,browser:false,production:false}));
