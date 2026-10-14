/** Parse data-only JSON while rejecting duplicate keys at every depth. */
export function strictJson(text,maxBytes=1024*1024) {
  if (typeof text!=='string' || Buffer.byteLength(text)>maxBytes) throw new Error('HOLD_JSON_LIMIT');
  let at=0;
  const space=()=>{while (/[\x20\x09\x0a\x0d]/.test(text[at]??'!'))at++;};
  function string() {
    const start=at++; let escaped=false;
    while(at<text.length) {
      const ch=text[at++];
      if (!escaped && ch==='"') return JSON.parse(text.slice(start,at));
      if (!escaped && ch==='\\')escaped=true;else escaped=false;
    }
    throw new Error('HOLD_JSON_STRING');
  }
  function value(depth) {
    if(depth>64)throw new Error('HOLD_JSON_DEPTH');space();
    const ch=text[at];
    if(ch==='"')return string();
    if(ch==='{') {
      at++;space();const object=Object.create(null),keys=new Set();
      if(text[at]==='}'){at++;return object;}
      while(true) {
        space();if(text[at]!=='"')throw new Error('HOLD_JSON_KEY');const key=string();
        if(keys.has(key) || ['__proto__','constructor','prototype'].includes(key))throw new Error('HOLD_JSON_DUPLICATE_OR_UNSAFE_KEY');
        keys.add(key);space();if(text[at++]!==':')throw new Error('HOLD_JSON_COLON');
        object[key]=value(depth+1);space();const next=text[at++];
        if(next==='}')return object;if(next!==',')throw new Error('HOLD_JSON_OBJECT');
      }
    }
    if(ch==='[') {
      at++;space();const array=[];if(text[at]===']'){at++;return array;}
      while(true) {array.push(value(depth+1));space();const next=text[at++];
        if(next===']')return array;if(next!==',')throw new Error('HOLD_JSON_ARRAY');}
    }
    for(const [token,result] of [['true',true],['false',false],['null',null]])
      if(text.slice(at,at+token.length)===token){at+=token.length;return result;}
    const token=/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(text.slice(at))?.[0];
    if(!token)throw new Error('HOLD_JSON_TOKEN');at+=token.length;const number=Number(token);
    if(!Number.isFinite(number) || (!/[.eE]/.test(token) && !Number.isSafeInteger(number)))throw new Error('HOLD_JSON_NUMBER');
    return number;
  }
  const result=value(0);space();if(at!==text.length)throw new Error('HOLD_JSON_TRAILING');return result;
}
