import { NativeController } from './controller.mjs';

/** Registration runs inside the installed Gateway plugin host only. */
export function registerController(api,hostBindings) {
  const controller=new NativeController(hostBindings);
  const methods={
    'xuanjun.execution.start':new Set(['admit','launch']),
    'xuanjun.execution.inspect':new Set(['inspect','report','stop'])
  };
  for(const [method,allowed] of Object.entries(methods)) {
    api.registerGatewayMethod(method,async ({params,respond,client})=>{
      try {
        // Authorization comes from the authenticated Gateway client, not params.
        if(!client?.connect?.scopes?.includes('operator.admin'))throw new Error('HOLD_ADMIN_REQUIRED');
        if(!params || !allowed.has(params.operation))throw new Error('HOLD_OPERATION');
        const runtime=api.runtime;
        if(!runtime?.subagent?.run||!runtime.subagent.waitForRun)throw new Error('HOLD_REQUEST_SCOPED_SDK');
        let result;
        if(params.operation==='admit') result=await controller.admit(params.request_json,params.idempotency_key,runtime);
        else result=await controller[params.operation](params.value,runtime);
        respond(true,result);
      } catch(error) {
        const reason=/^HOLD_[A-Z_]+$/.test(error?.message??'')?error.message:'HOLD_EFFECT_UNCONFIRMED';
        respond(false,undefined,{code:'UNAVAILABLE',message:reason});
      }
    });
  }
  return controller;
}
