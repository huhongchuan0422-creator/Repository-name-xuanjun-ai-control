const {createSession,parseScene}=require('../../session');
const H5_TEST_URL='https://uk.wenwenwenyiyiyi.work/community-h5-test';
const auth=require('../../customer-auth');
Page({
 data:{challenge:'',scene:'',contexts:[],contextIndex:-1,pending:false,description:null,status:''},
 onLoad(){this.dead=false;this.epoch=auth.current();this.setData({scene:''});},
 clearH5Session(){if(this.session)this.session.clear();this.session=null;this.request=null;this.epoch=auth.current();},
 onShow(){if(!auth.active(this.epoch))this.customerSessionRevoked();},
 onUnload(){this.dead=true;this.clearH5Session();},
 customerSessionRevoked(){this.clearH5Session();this.setData({description:null,contexts:[],scene:'',contextIndex:-1,pending:false,status:'微信登录已变化，请重新核对。'});},
 input(e){if(this.data.pending)return;const k=e.currentTarget.dataset.field;if(!['challenge','scene'].includes(k))return;this.request=null;this.setData({[k]:e.detail.value,description:null,status:''});},
 cancel(){this.request=null;this.setData({description:null,pending:false,status:'已取消本页确认。若刚才提交结果未知，请在本人 H5 页面取消请求。'});},
 chooseContext(e){if(this.data.pending)return;const i=Number(e.detail.value),c=this.data.contexts[i];if(!c)return;this.request=null;this.setData({scene:c.scene,contextIndex:i,description:null,status:'已选择本人原授权场景，请继续核对。'});},
 async describe(){
  if(!auth.active(this.epoch))this.customerSessionRevoked();
  if(this.data.pending)return;
  const challenge=this.data.challenge.trim();let scene=this.data.scene.trim();
  try{if(scene)parseScene({scene});if(!/^[A-Za-z0-9_-]{43,128}$/.test(challenge))throw Error();}catch(_){this.setData({status:'请输入本人 H5 页面交接码；授权场景将由原服务读取。'});return;}
  const req={challenge,scene};this.request=req;this.setData({pending:true,description:null,status:'正在使用原微信身份核对…'});
  try{req.session=this.session&&this.session.isAuthenticated()?this.session:createSession(wx,H5_TEST_URL);this.session=req.session;req.epoch=auth.current();if(!req.session.isAuthenticated())await req.session.login();if(this.dead||this.request!==req||this.session!==req.session||!auth.active(req.epoch))return;
   const contexts=[],seen=new Set();let cursor='';
   do{const r=await req.session.customer('contexts',cursor?{after_scene:cursor}:{});if(this.dead||this.request!==req||!auth.active(req.epoch))return;contexts.push(...r.contexts);if(!r.has_more)break;if(!r.next_cursor||seen.has(r.next_cursor))throw Error('INVALID_CURSOR');seen.add(r.next_cursor);cursor=r.next_cursor;}while(true);
   if(!contexts.length){this.setData({contexts:[],scene:'',status:'该独立测试环境尚无本人可用消费者场景；未添加任何授权。'});return;}
   const existing=contexts.findIndex(c=>c.scene===scene);
   if(existing<0&&contexts.length!==1){this.setData({contexts,scene:'',contextIndex:-1,status:'请选择原服务返回的本人授权场景，然后继续核对。'});return;}
   const chosen=existing<0?0:existing;scene=contexts[chosen].scene;req.scene=scene;this.setData({contexts,scene,contextIndex:chosen});
   const result=await req.session.h5Browser(scene,'DESCRIBE',challenge);if(this.dead||this.request!==req||!auth.active(req.epoch))return;this.setData({description:result,status:'逐字核对本人浏览器的网址和校验码，不确认他人发来的请求。'});}
  catch(_){if(!this.dead&&!auth.active(req.epoch)){if(this.request===req&&this.session===req.session)this.customerSessionRevoked();return;}if(!this.dead&&this.request===req)this.setData({status:'请求或原微信身份无法核实，未授予任何权限。'});}
  finally{if(!this.dead&&this.request===req)this.setData({pending:false});}
 },
 async confirm(){
  const req=this.request,d=this.data.description;if(!req||!d||this.data.pending||!auth.active(req.epoch))return;
  this.setData({pending:true});
  try{const yes=await new Promise(resolve=>wx.showModal({title:'确认本人 H5 登录',content:'网址：'+d.origin+'\n场景：'+d.scene+'\n校验码：'+d.verification+'\n仅继续本人原微信申请者身份，不授管理员。',confirmText:'本人确认',cancelText:'取消',success:r=>resolve(r.confirm===true),fail:()=>resolve(false)}));if(!yes||this.dead||this.request!==req||!auth.active(req.epoch))return;await req.session.h5Browser(req.scene,'CONFIRM_THIS_BROWSER',req.challenge,d);if(!auth.active(req.epoch)){if(!this.dead&&this.request===req&&this.session===req.session)this.customerSessionRevoked();return;}if(!this.dead&&this.request===req)this.setData({description:null,status:'已确认，请回到本人 H5 完成登录。'});}
  catch(_){if(!this.dead&&!auth.active(req.epoch)){if(this.request===req&&this.session===req.session)this.customerSessionRevoked();return;}if(!this.dead&&this.request===req)this.setData({description:null,status:'确认结果未知，不自动重试；请回本人 H5 查询或取消。'});}
  finally{if(!this.dead&&this.request===req)this.setData({pending:false});}
 }
});
