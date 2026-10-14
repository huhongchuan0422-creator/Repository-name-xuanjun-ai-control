// Candidate only. Sites Dispatch supplies identity; UK controller owns task ACL.
// STATIC_FILES is embedded by build.mjs from the pinned original Site checkout.
const LABELS = {costs:'任务费用', usage:'运行用量', dependencies:'依赖证据',
  resume:'恢复前置', alert:'人工告警', handoff:'执行权交接', canary:'端到端验收'};
const ENDPOINT = 'https://uk.wenwenwenyiyiyi.work/api/work17/read';
const HEADERS = {'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
  'Referrer-Policy':'no-referrer', 'Content-Type':'application/json; charset=utf-8'};
const json = (status, data) => new Response(JSON.stringify(data), {status, headers:HEADERS});
const unavailable = () => json(503, {status:'HOLD', error:'OWNER_READ_UNAVAILABLE', execution_granted:false});
async function bounded(stream, limit) {
  if (!stream) throw new Error('MISSING_BODY');
  const reader = stream.getReader(); const parts=[]; let length=0;
  try {
    for (;;) {
      const {done,value} = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > limit) throw new Error('BODY_BOUND');
      parts.push(value);
    }
    const bytes=new Uint8Array(length); let offset=0;
    for (const p of parts) { bytes.set(p,offset); offset+=p.length; }
    return new TextDecoder('utf-8',{fatal:true}).decode(bytes);
  } finally { await reader.cancel().catch(()=>{}); reader.releaseLock(); }
}
function project(envelope, task) {
  if (!envelope || envelope.schema!=='WORK17_OWNER_HTTP_V1' || envelope.task_id!==task)
    throw new Error('TASK_RESPONSE_BINDING');
  const s=envelope.snapshot;
  if (!s || s.schema!=='WORK_FOUNDATION_INTEGRATION_V1' ||
      !['HOLD','VIEWS_READY_NOT_ADMITTED'].includes(s.status) ||
      !/^[a-f0-9]{64}$/.test(s.binding_sha256) ||
      ['execution_granted','resume_granted','release_granted','send_performed'].some(k=>s[k]!==false) ||
      !s.views || Object.keys(s.views).sort().join()!==Object.keys(LABELS).sort().join() ||
      typeof s.scan_complete!=='boolean' || !Number.isSafeInteger(s.task_count_observed) ||
      s.task_count_observed<0 || s.task_count_observed>1000)
    throw new Error('SNAPSHOT_CONTRACT');
  const summary=Object.entries(LABELS).map(([kind,label])=>{
    const status=s.views[kind]?.status;
    if (typeof status!=='string' || !/^[A-Z_]{1,48}$/.test(status)) throw new Error('VIEW_STATUS');
    return {kind,label,status,execution_granted:false};
  });
  const status = (!s.scan_complete || summary.some(v=>v.status==='HOLD')) ? 'HOLD' : s.status;
  // Raw receipts, identity, paths and arbitrary producer data never reach browser.
  return {schema:'WORK17_OWNER_SUMMARY_V1',task_id:task,status,summary,
    task_count_observed:s.task_count_observed,scan_complete:s.scan_complete,
    remaining_count:s.scan_complete ? 0 : null,execution_granted:false};
}
export default {
  async fetch(request, env) {
    const url=new URL(request.url);
    if (url.pathname==='/api/work17/read') {
      if (request.method!=='POST') return json(405,{error:'READ_POST_REQUIRED'});
      // Missing identity rejects service bypass callers too. Fixed principal is
      // configured only after a real protected Site session binding is obtained.
      const user=request.headers.get('oai-authenticated-user-id');
      if (!env.WORK17_OWNER_SITE_USER_ID || !user || user!==env.WORK17_OWNER_SITE_USER_ID)
        return json(403,{error:'OWNER_REQUIRED'});
      if (url.search || request.headers.get('Origin')!==url.origin ||
          request.headers.get('Content-Type')?.split(';')[0].trim().toLowerCase()!=='application/json')
        return json(400,{error:'INVALID_READ_REQUEST'});
      let task;
      try {
        const raw=await bounded(request.body,512);
        // One literal key: duplicate keys, dependency/identity injection and
        // deeply nested JSON are rejected before UK contact.
        const match=/^\s*\{\s*"task_id"\s*:\s*"([A-Za-z0-9][A-Za-z0-9_.:-]{0,199})"\s*\}\s*$/.exec(raw);
        if (!match) throw new Error('REQUEST_SHAPE');
        task=match[1];
      } catch { return json(400,{error:'INVALID_READ_REQUEST'}); }
      if (typeof env.WORK17_UK_READ_BEARER!=='string' ||
          !/^[A-Za-z0-9_-]{32,256}$/.test(env.WORK17_UK_READ_BEARER)) return unavailable();
      const controller=new AbortController();
      const timeout=setTimeout(()=>controller.abort(),5000);
      try {
        const response=await fetch(ENDPOINT,{method:'POST',redirect:'error',
          signal:controller.signal,headers:{'Content-Type':'application/json',
            'Authorization':'Bearer '+env.WORK17_UK_READ_BEARER},
          body:JSON.stringify({task_id:task})});
        if (response.status!==200 || response.headers.get('Content-Type')?.split(';')[0].trim()!=='application/json')
          throw new Error('UPSTREAM_REJECTED');
        return json(200,project(JSON.parse(await bounded(response.body,262144)),task));
      } catch { return unavailable(); } finally { clearTimeout(timeout); }
    }
    if (request.method!=='GET' && request.method!=='HEAD') return new Response('Method not allowed',{status:405});
    const paths=[url.pathname, url.pathname.replace(/\/$/,'')+'/index.html'];
    const entry=paths.map(p=>STATIC_FILES[p]).find(Boolean);
    if (!entry) return new Response('Not found',{status:404});
    return new Response(request.method==='HEAD'?null:Uint8Array.from(atob(entry.body),c=>c.charCodeAt(0)),
      {headers:{'Content-Type':entry.type,'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
  }
};
