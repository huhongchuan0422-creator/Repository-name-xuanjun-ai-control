'use strict';
let epoch=0;
function current(){return epoch;}
function active(snapshot){return snapshot===epoch;}
function revokePages(pages,status='登录已退出，请重新登录'){
  epoch++;
  const snapshot=[...(Array.isArray(pages)?pages:[])];
  for(const page of snapshot){
    if(page&&typeof page.customerSessionRevoked==='function')page.customerSessionRevoked(status);
  }
  return epoch;
}
module.exports={current,active,revokePages};
