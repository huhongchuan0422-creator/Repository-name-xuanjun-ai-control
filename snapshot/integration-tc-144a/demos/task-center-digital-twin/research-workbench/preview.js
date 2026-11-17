'use strict';
// Explicit read-only workbench; the server retains session and admin authority.
var generation=0;
var workbench=window.XuanjunResearchWorkbench.mount(document.getElementById('app'),{onRefresh:refreshWorkbench,onReturn:function(){window.location.href=new URL('../task-center.html',document.baseURI).href;}});
function readProjection(path){
 return fetch(new URL('../api/'+path,document.baseURI).href,{credentials:'same-origin',cache:'no-store'}).then(function(response){
  if(!response.ok)throw new Error('unavailable');
  return response.json();
 });
}
function refreshWorkbench(){
 var current=++generation;
 // Clear previously authorized data immediately, including on session expiry.
 workbench.update(null,null,null);
 return Promise.all([
  readProjection('projection').catch(function(){return null;}),
  readProjection('admin/digital-twin').catch(function(){return null;}),
  readProjection('admin/delivery-ledger').catch(function(){return null;})
 ]).then(function(result){if(current===generation)workbench.update(result[0],result[1],result[2]);});
}
var publicSummary=window.XuanjunPublicProjection.mount(document.getElementById('publicSummary'),{endpoint:new URL('../api/public-projection',document.baseURI).href});
document.getElementById('reloadPublic').onclick=publicSummary.refresh;
refreshWorkbench();
