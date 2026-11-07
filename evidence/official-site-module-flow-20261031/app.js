(function(){
  'use strict';
  var selectedModules=['智能客服'];
  var selectedMode='BYO_ACCOUNT';
  var modeLabels={BYO_ACCOUNT:'使用我的上游账号',XUANJUN_API_SERVICE:'购买玄钧AI新 API 服务'};
  var modeDescriptions={BYO_ACCOUNT:'客户管理上游账号与付款；平台仅在已验证的安全通道上为项目启用。',XUANJUN_API_SERVICE:'由玄钧AI新提供项目权益；无需准备上游 Key，按合同与订单开通。'};
  function byId(id){return document.getElementById(id);}
  function paint(){
    byId('selectionCount').textContent=selectedModules.length+' 个模块';
    byId('summaryModules').textContent=selectedModules.join('、')||'尚未选择';
    byId('summaryMode').textContent=modeLabels[selectedMode];
    byId('summaryProject').textContent=byId('project').value;
    byId('modeBoundary').innerHTML='<strong>'+modeLabels[selectedMode]+'</strong><span>'+modeDescriptions[selectedMode]+'</span>';
  }
  document.querySelectorAll('[data-module]').forEach(function(button){button.addEventListener('click',function(){var name=button.dataset.module,index=selectedModules.indexOf(name);if(index>=0&&selectedModules.length>1)selectedModules.splice(index,1);else if(index<0)selectedModules.push(name);button.classList.toggle('selected',selectedModules.indexOf(name)>=0);button.setAttribute('aria-pressed',String(selectedModules.indexOf(name)>=0));button.querySelector('b').textContent=selectedModules.indexOf(name)>=0?'已选择':'选择';paint();});});
  document.querySelectorAll('[data-mode]').forEach(function(button){button.addEventListener('click',function(){selectedMode=button.dataset.mode;document.querySelectorAll('[data-mode]').forEach(function(item){var active=item.dataset.mode===selectedMode;item.classList.toggle('selected',active);item.setAttribute('aria-pressed',String(active));item.querySelector('.radio').textContent=active?'✓':'';});paint();});});
  byId('project').addEventListener('change',paint);
  byId('continueButton').addEventListener('click',function(){byId('feedback').textContent='候选提示：需 Owner 确认后，才由官网责任方接入真实购买与配置流程。';});
  paint();
}());
