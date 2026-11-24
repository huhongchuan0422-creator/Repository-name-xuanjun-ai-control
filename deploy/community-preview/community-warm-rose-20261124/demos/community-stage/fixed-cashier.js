'use strict';
(()=>{
'use strict';

// Existing checkout view bindings (beforeAd/afterAd/afterAdVerified).
// Rendering must use textContent, never HTML, and no creative affects payment.
const pattern = /^data:image\/(?:png|jpeg|webp);base64,[A-Za-z0-9+/]+={0,2}$/;
const same = (a,b,keys) => !!a && !!b && keys.every(k=>typeof a[k]==='string' && a[k]!=='' && a[k]===b[k]);
const scope = ['tenant_id','merchant_id','store_id'];
function creative(c) {
  if (!c || typeof c.title!=='string' || !c.title.trim() || c.title.length>160) return {title:'',image:''};
  return {title:c.title, image:typeof c.image_data==='string' && c.image_data.length<=750000 && pattern.test(c.image_data)?c.image_data:''};
}
function amountSurface(view, current) {
  const a=creative(same(view,current,scope) && view.amount_mode==='OWN' ? view.amount_ad : null);
  return {beforeAd:a.title,beforeAdImage:a.image};
}
function resultSurface(view,current) {
  // "verified" is an authenticated server projection, not an SDK callback/URL parameter.
  const verified=same(view,current,[...scope,'reference']) &&
    view.payment_success_verified===true && view.provider_state==='SUCCESS' &&
    typeof view.transaction_id==='string' && /^[A-Za-z0-9_-]{1,64}$/.test(view.transaction_id);
  const a=creative(verified && view.result_mode==='OWN' ? view.creative : null);
  return {paymentSuccessVerified:verified,afterAd:a.title,afterAdImage:a.image,afterAdVerified:!!a.title};
}
function qrDownload(view,current,approvedLink) {
  if (!same(view,current,scope) || view.fixed_url!==approvedLink || typeof approvedLink!=='string' ||
      !/^https:\/\/[^\s]+$/.test(approvedLink) || view.download_state!=='READY' ||
      typeof view.png_data!=='string' || view.png_data.length>550000 || !/^data:image\/png;base64,iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(view.png_data)) return null;
  try {const u=new URL(approvedLink);if(u.username||u.password||u.hash)return null;} catch (_) { return null; }
  // The protected server issuer—not this helper—must bind/decode the PNG to fixed_url.
  return {filename:'门店收款码.png',href:view.png_data};
}
function payDirect(intent,current,invokeWechat) {
  // Only the actual checkout button should call this with authenticated server data.
  // No second QR, redirect URL, app jump, or SDK return interpreted as payment proof.
  if (!same(intent,current,[...scope,'reference']) || intent.flow!=='WECHAT_IN_PAGE_JSAPI' ||
      typeof invokeWechat!=='function' || !intent.jsapi) throw Error('DIRECT_PAYMENT_UNAVAILABLE');
  const keys=['appId','timeStamp','nonceStr','package','signType','paySign'];
  if (!keys.every(k=>typeof intent.jsapi[k]==='string' && intent.jsapi[k].length>0) ||
      !/^prepay_id=[A-Za-z0-9_-]+$/.test(intent.jsapi.package)) throw Error('DIRECT_PAYMENT_UNAVAILABLE');
  return invokeWechat(Object.fromEntries(keys.map(k=>[k,intent.jsapi[k]])));
}

'use strict';

// Original host supplies authorized API closure and current private identity.
// Never put authenticated scope, secrets, payer identifiers or order reference
// in DOM/links/logs. No route, provider URL, or public bootstrap is defined here.
function createPage({api,current,invokeWechat,view}) {
  let generation=0, pending=false;
  let reference='';
  function bound() {return {...current,reference};}
  async function entry() {
    const g=++generation;
    const r=await api.amount();
    if (g!==generation) return;
    view.amount({name:r.store_name,...amountSurface(r,current)});
  }
  function reset() {generation++; reference=''; pending=false;}
  async function check(g=generation) {
    if (!reference || g!==generation) return;
    const r=await api.result(reference);
    if (g!==generation) return;
    const projection=resultSurface(r,bound());
    view.result({...projection, state:projection.paymentSuccessVerified?'SUCCESS':
      r.reference===reference&&['tenant_id','merchant_id','store_id'].every(k=>r[k]===current[k])&&r.provider_state==='CLOSED'?'CLOSED':'UNCONFIRMED'});
  }
  async function pay(yuan) {
    if (pending||reference) return;
    pending=true;
    const g=generation;
    try {
      const r=await api.reserve(yuan);
      if (g!==generation) return;
      if (!r||typeof r.reference!=='string'||!/^[A-Za-z0-9_-]{1,64}$/.test(r.reference))
        throw Error('ORIGINAL_ORDER_UNCONFIRMED');
      reference=r.reference;
      const intent=await api.prepare(reference);
      if (g!==generation) return;
      try { await payDirect(intent,bound(),invokeWechat); }
      finally { await check(g); }
    } finally {
      if (g===generation) pending=false;
    }
  }
  return Object.freeze({entry,pay,check,reset});
}

// Original private session remains in memory; never in links, DOM, or storage.
const $ = id => document.getElementById(id);
let auth = null, epoch = 0, page = null;
const current = {};
const merchant = document.body.dataset.surface === 'merchant';
const locator = /^\/community-preview\/go\/(fx[0-9a-f]{24})$/.exec(location.pathname)?.[1];
const status = text => { $('status').textContent = text; };
async function call(op, params = {}) {
  const ticket = epoch, config = auth;
  const response = await fetch('/community-preview/community/fixed-cashier', {method:'POST',
    credentials:'same-origin', cache:'no-store', redirect:'error',
    headers:{'Content-Type':'application/json', ...(config ? {'X-CSRF-Token':config.csrf} : {})},
    body:JSON.stringify({op, ...params})});
  const value = await response.json();
  if (ticket !== epoch) throw Error('身份已变化');
  if (!response.ok) throw Error('操作未确认，请查询原单；不要重复付款。');
  return value;
}
function renderAd(prefix, title, image) {
  $(prefix).textContent = title;
  $(prefix+'Box').hidden = !title;
  $(prefix+'Image').hidden = !image;
  if (image) $(prefix+'Image').src = image;
  else $(prefix+'Image').removeAttribute('src');
}
async function loadCode() {
  const ticket = epoch;
  $('codeSection').hidden = true;
  $('qr').removeAttribute('src'); $('download').removeAttribute('href'); $('fixedLink').removeAttribute('href');
  if (!auth) return;
  const value = await call('qr_view', {workspace:auth.workspace});
  if (ticket !== epoch) return;
  const approved = value.locator && /^fx[0-9a-f]{24}$/.test(value.locator)
    ? location.origin + '/community-preview/go/' + value.locator : '';
  const download = qrDownload(value, value, approved);
  if (!download) { status('当前固定码暂不可生成，请重新读取。'); return; }
  $('storeName').textContent = value.store_name || '当前门店';
  $('qr').src = download.href; $('download').href = download.href;
  $('fixedLink').href = approved; $('codeSection').hidden = false;
  $('qualification').textContent = value.official_code_available === true
    ? '支付资格已由原受保护配置核实' : '展示预览：支付资格待现场核实，暂不可付款';
  status('长期固定金额页二维码 · 本门店');
}
function invokeWechat(jsapi) {
  return new Promise((resolve, reject) => {
    if (!window.WeixinJSBridge || typeof window.WeixinJSBridge.invoke !== 'function')
      return reject(Error('请在微信内打开，并等待原付款人授权完成。'));
    window.WeixinJSBridge.invoke('getBrandWCPayRequest', jsapi, resolve);
    // SDK success/cancel/failure is never a payment verification result.
  });
}
function setupPayer() {
  let reservedReference = '';
  page = createPage({current, invokeWechat, api:{
    amount:async () => {
      const value = await call('amount',{locator});
      for (const key of ['tenant_id','merchant_id','store_id']) current[key] = value[key];
      current.payable = value.payable === true;
      return value;
    },
    reserve:async yuan => {
      if (!auth || !current.payable) throw Error('付款人授权或支付资格尚未就绪。');
      reservedReference ||= 'fc_' + crypto.randomUUID().replaceAll('-','');
      return call('reserve',{locator,reference:reservedReference,yuan});
    },
    prepare:reference => call('prepare',{locator,reference}),
    result:reference => call('result',{locator,reference})
  }, view:{
    amount:value => {
      $('storeName').textContent = value.name;
      renderAd('beforeAd',value.beforeAd,value.beforeAdImage);
      $('pay').disabled = !auth || !current.payable;
      status(!current.payable ? '金额页可浏览；支付资格待现场核实，暂不可付款。'
        : !auth ? '金额页可浏览；等待原网页付款人授权。' : '请确认门店与金额。');
    },
    result:value => {
      $('resultSection').hidden = false;
      $('resultState').textContent = value.state === 'SUCCESS' ? '支付成功 · 已验签核实'
        : value.state === 'CLOSED' ? '订单已关闭' : '支付结果待核验';
      renderAd('afterAd',value.afterAd,value.afterAdImage);
      if (value.state === 'SUCCESS' || value.state === 'CLOSED') $('amountSection').hidden = true;
    }
  }});
  $('payForm').onsubmit = async event => {
    event.preventDefault(); if ($('pay').disabled) return;
    $('pay').disabled = true; $('yuan').disabled = true;
    try { await page.pay($('yuan').value); }
    catch (error) { status(error.message); }
    finally { $('check').hidden = false; }
    // Never re-enable a payment after an ambiguous reserve/prepay/SDK result.
  };
  $('check').onclick = () => page.check().catch(error => status(error.message));
  page.entry().catch(error => status(error.message));
}
window.configureCommunityFixedCashier = value => {
  epoch++; page?.reset(); auth = null;
  if (value && typeof value.csrf === 'string' && value.csrf &&
      (!merchant || /^[A-Za-z0-9_-]{1,64}$/.test(value.workspace)))
    auth = {csrf:value.csrf,workspace:value.workspace};
  if (merchant) {
    $('reload').disabled = !auth;
    loadCode().catch(error => status(error.message));
  } else {
    renderAd('afterAd','',''); $('resultSection').hidden = true;
    $('amountSection').hidden = false; $('check').hidden = true; $('yuan').disabled = false;
    setupPayer();
  }
};
if (merchant) $('reload').onclick = () => loadCode().catch(error => status(error.message));
else setupPayer();

})();
