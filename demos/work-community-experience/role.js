"use strict";
(()=>{
document.body.classList.toggle('preview-wide',['platform','website-admin'].includes(document.body.dataset.previewRole));
// This retains navigation context only; the reviewed role content stays Chinese.
const value=new URLSearchParams(location.search).get('lang');
const lang=value==='en'?'en':value==='zh-cn'?'zh-cn':'';
if(!lang)return;
const base='/visual/community-payment/mobile/';
const roles=new Set([base,base+'index.html',...['merchant','community','beneficiary','platform'].map(r=>base+r+'.html')]);
const hubs=new Set(['/visual/community-payment/','/marketplace/']);
document.querySelectorAll('a[href]').forEach(a=>{
  const raw=a.getAttribute('href');
  if(!raw||raw.startsWith('#'))return;
  let url;
  try{url=new URL(raw,location.href);}catch{return;}
  if(url.origin!==location.origin)return;
  if(roles.has(url.pathname))a.setAttribute('href',url.pathname+'?lang='+lang+url.hash);
  else if(hubs.has(url.pathname))a.setAttribute('href','/'+lang+url.pathname+url.hash);
});
})();

