/* Adapter to the existing customer change ledger. No second comment store. */
export class FeedbackClient {
  constructor({fetcher=fetch, csrf=()=>sessionStorage.getItem('xj_csrf')||'', key=()=>crypto.randomUUID()}={}) {
    this.fetcher=fetcher;this.csrf=csrf;this.key=key;this.pending=new Map();this.busy=new Set();
  }
  async call(operation,body) {
    const r=await this.fetcher('/customer/center/api/'+operation,{credentials:'same-origin',cache:'no-store',
      method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-CSRF-Token':this.csrf()}:{},
      body:body?JSON.stringify(body):undefined});
    const d=await r.json();if(!r.ok){const e=Error(d.error||'请求未完成');e.status=r.status;throw e;}return d;
  }
  binding(b) {
    if(!b||typeof b.project!=='string'||!/^\/[A-Za-z0-9/_\-.]{1,300}$/.test(b.page)||b.page.includes('..')||!/^[a-f0-9]{64}$/.test(b.version))throw Error('页面版本尚未绑定');
    return {project:b.project,page:b.page,version:b.version};
  }
  async read(binding) {
    const b=this.binding(binding);await this.call('change_context',b);
    const data=await this.call('changes/'+encodeURIComponent(b.project));
    return data.cases.filter(c=>c.events[0]?.kind==='REQUEST'&&c.events[0].payload.page===b.page&&c.events[0].payload.page_sha256===b.version);
  }
  async submit(binding,text,intent='RECTIFICATION') {
    const b=this.binding(binding),scope=JSON.stringify(b);
    if(this.busy.has(scope))throw Error('本页意见正在核对');
    if(!text.trim())throw Error('请填写修改意见');
    this.busy.add(scope);
    try {
      let pending=this.pending.get(scope);
      // Once transport outcome is unknown, never issue another POST until the
      // original ledger supplies its receipt. Editing text cannot create a retry.
      if(pending){
        const rows=await this.read(b),found=rows.find(c=>c.events[0].payload.idempotency_key===pending.idempotency_key);
        if(found){this.pending.delete(scope);return {state:'SAVED',id:found.id,recovered:true};}
        return {state:'UNKNOWN'};
      }
      await this.call('change_context',b);
      pending={...b,text:text.trim(),intent,idempotency_key:this.key()};this.pending.set(scope,pending);
      let result;
      try {result=await this.call('change_submit_idempotent',pending);}
      catch(e){if(e.status){this.pending.delete(scope);throw e;}return {state:'UNKNOWN'};}
      this.pending.delete(scope);return {state:'SAVED',id:result.id};
    } finally {this.busy.delete(scope);}
  }
}
