"use strict";
(() => {
 const status=document.getElementById('demoSessionState');
 fetch('/_preview/community-api/session',{credentials:'same-origin',cache:'no-store',redirect:'error'}).then(async response=>{
  if(!response.ok)throw Error('PREVIEW_UNAVAILABLE');const data=await response.json();
  if(data.simulation_only!==true||data.provider_connected!==false)throw Error('INVALID_PREVIEW_SESSION');
  const field=document.getElementById('adminCapability');
  if(field){const platform=!!document.getElementById('approveCreative');field.value=platform?data.platform_demo_capability:data.merchant_demo_capability;}
  status.textContent='隔离模拟会话已就绪；不连接真实支付或生产客户数据。';
 }).catch(()=>{status.textContent='交互演示服务未开放；可浏览角色说明，不能创建模拟订单或提交操作。';document.querySelectorAll('button').forEach(button=>{button.disabled=true;});});
})();
