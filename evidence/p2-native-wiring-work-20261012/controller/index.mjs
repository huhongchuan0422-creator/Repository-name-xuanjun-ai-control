import { NativeController } from './controller.mjs';

/** Registration runs inside the installed Gateway plugin host only. */
export function registerController(api,hostBindings) {
  const controller=new NativeController(hostBindings);
  const methods={
    'xuanjun.execution.start':new Set(['admit','launch']),
    'xuanjun.execution.inspect':new Set(['preflight','inspect','report','stop'])
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
        if(params.operation==='preflight') {
          if(typeof hostBindings.preflight!=='function')throw new Error('HOLD_HOST_PREFLIGHT_MISSING');
          result=await hostBindings.preflight(runtime);
        } else if(params.operation==='admit') result=await controller.admit(params.request_json,params.idempotency_key,runtime);
        else result=await controller[params.operation](params.value,runtime);
        respond(true,result);
      } catch(error) {
        const reason=/^HOLD_[A-Z_]+$/.test(error?.message??'')?error.message:'HOLD_EFFECT_UNCONFIRMED';
        respond(false,undefined,{code:'UNAVAILABLE',message:reason});
      }
    },{scope:'operator.admin'});
  }
  if(typeof hostBindings.beforeToolCall==='function') {
    if(typeof api.on!=='function')throw new Error('HOLD_TOOL_HOOK_API');
    api.on('before_tool_call',hostBindings.beforeToolCall,{priority:1000});
  }
  return controller;
}
