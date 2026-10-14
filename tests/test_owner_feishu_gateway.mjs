import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const root=process.env.P2_FEISHU_INTEGRATION_ROOT;
if(!root)throw new Error('INTEGRATION_ROOT_REQUIRED_NO_SKIP');
const {registerController}=await import(pathToFileURL(root+'/plugins/p2-native-controller/index.mjs'));
const methods=new Map();let cycles=0,modelCalls=0;
const api={registerGatewayMethod:(name,handler,options)=>methods.set(name,{handler,options}),
  runtime:{subagent:{run(){modelCalls++;throw new Error('MODEL_MUST_NOT_RUN');}}}};
const host={ownerDelivery:()=>{cycles++;return {state:'ACKED',receiver_ack:true,model_calls:0};}};
for(const name of ['prepare','eligibility','collectResult','verifyLease','commitGuard','verifyWorkerPlacement','releaseWorkerPlacement','selectAgent'])host[name]=()=>{throw new Error('UNRELATED_MODEL_PATH_CALLED');};
registerController(api,host);
const entry=methods.get('xuanjun.owner.delivery');assert.equal(entry.options.scope,'operator.admin');
async function call(params,scopes=['operator.admin']){
  let response;await entry.handler({params,client:{connect:{scopes}},respond:(...args)=>{response=args;}});return response;
}
assert.equal((await call({operation:'cycle'}))[0],true);
assert.equal(cycles,1);assert.equal(modelCalls,0);
for(const params of [{operation:'cycle',claim:{}},{operation:'cycle',chat_id:'oc_other'},
  {operation:'send'},{operation:'sql'},null])assert.equal((await call(params))[0],false);
assert.equal((await call({operation:'cycle'},[]))[0],false);assert.equal(cycles,1);
host.ownerDelivery=()=>({state:'ACKED',receiver_ack:false,model_calls:0});
assert.equal((await call({operation:'cycle'}))[0],false);
assert.equal(modelCalls,0);
console.log('OWNER_GATEWAY_ADMIN_PARAM_RECEIPT_GATE=PASS MODEL_CALLS=0');
