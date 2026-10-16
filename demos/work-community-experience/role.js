"use strict";
(()=>{const bar=document.querySelector('.device-role-tools');if(!bar)return;
const phone=bar.querySelector('[data-device=phone]'),desktop=bar.querySelector('[data-device=desktop]');
function mode(wide){document.body.classList.toggle('preview-wide',wide);phone.setAttribute('aria-pressed',String(!wide));desktop.setAttribute('aria-pressed',String(wide));}
phone.addEventListener('click',()=>mode(false));desktop.addEventListener('click',()=>mode(true));mode(document.body.dataset.previewRole==='platform');})();
