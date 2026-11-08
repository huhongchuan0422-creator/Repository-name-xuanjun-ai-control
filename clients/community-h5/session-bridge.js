'use strict';
module.exports=function bridge(port){
 const pages=new Set();let notifying=false;
 port.onRevoke(()=>{if(notifying)return;notifying=true;try{for(const p of [...pages])if(p.customerSessionRevoked){try{p.customerSessionRevoked('登录已失效，请重新登录',false)}catch(_){/* Continue revoking every page even if one cleanup hook fails. */}}}finally{notifying=false}});
 return {...port,attachPage(p){pages.add(p)},detachPage(p){pages.delete(p)},clear(){if(!notifying)port.clear()}};
};
