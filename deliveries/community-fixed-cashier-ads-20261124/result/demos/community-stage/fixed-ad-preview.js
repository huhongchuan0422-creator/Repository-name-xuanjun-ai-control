
'use strict';
(() => {
  const original=window.configureCommunityFixedCashier;
  let epoch=0;
  const image=/^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/;
  function render(prefix, creative, message) {
    document.getElementById(prefix+'Status').textContent=message;
    document.getElementById(prefix+'Title').textContent=creative && typeof creative.title==='string' ? creative.title : '';
    const img=document.getElementById(prefix+'Image');img.hidden=true;img.removeAttribute('src');
    if(creative && typeof creative.image_data==='string' && creative.image_data.length<=550000 && image.test(creative.image_data)) {img.src=creative.image_data;img.hidden=false;}
  }
  function clear(message) {render('amountPreview',null,message);render('successPreview',null,message);}
  window.configureCommunityFixedCashier = value => {
    original(value);const ticket=++epoch;clear('预览，非已付款；等待授权');
    if(!value || !value.csrf || !value.workspace)return;
    fetch('/community-preview/community/fixed-cashier',{method:'POST',credentials:'same-origin',redirect:'error',cache:'no-store',headers:{'Content-Type':'application/json','X-CSRF-Token':value.csrf},body:JSON.stringify({op:'ad_preview',workspace:value.workspace})})
      .then(async response=>{if(!response.ok)throw Error('预览读取未获授权');return response.json();})
      .then(result=>{
        if(ticket!==epoch)return;
        if(result.display_context!=='AD_PREVIEW_ONLY' || result.payment_success_verified!==false || result.payable!==false)throw Error('预览上下文不符');
        render('amountPreview',result.amount_ad,result.amount_ad?'金额页广告预览 · 非已付款':'本门店暂无已审核启用素材');
        render('successPreview',result.success_ad_preview,result.success_ad_preview?'完成页广告预览 · 非已付款':'本门店暂无已审核启用素材；非已付款');
      }).catch(()=>{if(ticket===epoch)clear('广告预览暂不可用，非已付款');});
  };
})();
