// Add-only candidate for original SaaS console. No fetch, login or write endpoint.
export function presentEcosystem(snapshot) {
  if (snapshot?.schema !== 'ecosystem-read-model-v1' || !Array.isArray(snapshot.rows) || snapshot.publish_allowed !== false || snapshot.http_wired !== false) throw Error('UNVERIFIED_ECOSYSTEM_SNAPSHOT');
  return snapshot.rows.map(row => {
    if (!['UNPACKAGED','BLOCKED','LOCAL_REVIEW_ONLY'].includes(row.listing_state) || row.published !== false || !Array.isArray(row.dependencies)) throw Error('INVALID_LISTING_STATE');
    return {module:row.module_id,title:row.title,version:row.package_version ?? 'UNKNOWN',
      dependencies:row.dependencies.join(', ') || 'none',
      state:row.listing_state,evidence:row.evidence?.qualification?.local_qualification ?? 'UNKNOWN',
      warning:'仅合成集成；现网租户/权限/Writer未验，不可上架',canPublish:false};
  });
}
export function renderEcosystem(container,snapshot,doc=container.ownerDocument) {
  const rows=presentEcosystem(snapshot); const fragment=doc.createDocumentFragment();
  for(const row of rows){const el=doc.createElement('article');
    for(const key of ['module','title','version','dependencies','state','evidence','warning']){
      const line=doc.createElement('p');line.textContent=String(row[key]);el.appendChild(line);
    }fragment.appendChild(el);
  }container.replaceChildren(fragment);
}

// Original-console UI: original account/project + original API; no publish authority.
// Only non-secret pending request metadata uses the existing sessionStorage. A key
// is saved before POST, restored on remount/reload and cleared only after a known
// rejection or a validated receipt. Storage errors fail closed, never overwrite.
export function mountPendingEcosystem(container,{api,project,keyFactory=()=>globalThis.crypto.randomUUID().replaceAll('-',''),storage=globalThis.sessionStorage},doc=container.ownerDocument){
  if(typeof project!=='string'||!/^[-\w]{1,128}$/.test(project))throw Error('INVALID_PROJECT');
  if(!storage||!['getItem','setItem','removeItem'].every(k=>typeof storage[k]==='function'))throw Error('PENDING_RECOVERY_STORAGE_REQUIRED');
  let disposed=false,generation=0,revision=null,owner=false,available=[],pending=null,busy=false,actor=null,storageKey=null;
  const el=(tag,text)=>{const n=doc.createElement(tag);if(text!==undefined)n.textContent=text;return n};
  const heading=el('h2','项目模块待审核登记'),status=el('p','尚未读取'),warning=el('p','PENDING_REVIEW 仅是本租户/项目的待审核登记，不是发布、授权复用、可销售或上线。'),select=el('select'),records=el('section'),keyInput=el('input'),register=el('button','登记为待审核'),refresh=el('button','刷新登记状态'),receipt=el('button','按原幂等键回读回执');
  status.setAttribute('role','status');select.setAttribute('aria-label','选择原目录模块版本');keyInput.setAttribute('aria-label','原登记幂等键');keyInput.autocomplete='off';for(const b of [register,refresh,receipt])b.type='button';
  container.replaceChildren(heading,warning,status,select,register,refresh,keyInput,receipt,records);
  const message=t=>{if(!disposed)status.textContent=t};
  const controls=()=>{register.disabled=disposed||busy||!owner||revision===null||!available.length||pending!==null;refresh.disabled=disposed||busy;receipt.disabled=disposed||busy||!owner;select.disabled=disposed||busy||pending!==null};
  function storedPending(){
    const raw=storage.getItem(storageKey);if(raw===null)return null;
    let p;try{p=JSON.parse(raw)}catch{throw Error('PENDING_RECOVERY_INVALID')}
    if(!p||Object.keys(p).sort().join(',')!=='actor,key,module,project,revision,schema,version'||p.schema!==1||p.actor!==actor||p.project!==project||typeof p.key!=='string'||!/^[A-Za-z0-9_-]{16,96}$/.test(p.key)||typeof p.module!=='string'||!/^[a-z][a-z0-9_.-]{0,95}$/.test(p.module)||typeof p.version!=='string'||!/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(p.version)||!Number.isSafeInteger(p.revision)||p.revision<0)throw Error('PENDING_RECOVERY_INVALID');
    return p;
  }
  function remember(p){if(storedPending())throw Error('PENDING_REQUEST_ALREADY_EXISTS');storage.setItem(storageKey,JSON.stringify(p));const read=storedPending();if(!read||read.key!==p.key)throw Error('PENDING_RECOVERY_WRITE_FAILED')}
  function clearPending(){const saved=storedPending();if((pending&&(!saved||saved.key!==pending.key))||(!pending&&saved))throw Error('PENDING_RECOVERY_BINDING_CHANGED');if(saved)storage.removeItem(storageKey);if(storage.getItem(storageKey)!==null)throw Error('PENDING_RECOVERY_CLEAR_FAILED');pending=null}
  function checkReceipt(r){if(!r||r.state!=='PENDING_REVIEW'||r.registration_scope!=='TENANT_PROJECT_PENDING_ONLY'||r.module_registered!==true||r.published!==false||r.approval_verified!==false||r.entitlement_granted!==false||typeof r.record_id!=='string')throw Error('INVALID_PENDING_RECEIPT');if(pending&&(r.module_id!==pending.module||r.version!==pending.version))throw Error('RECEIPT_PACKAGE_MISMATCH');return r}
  async function load(){
    if(disposed)return;const g=++generation;let authorized=false;busy=true;controls();
    try{
      const me=await api.me();if(disposed||g!==generation)return;
      const membership=me.projects?.find(p=>p.id===project);
      if(!membership||!['OWNER','EDITOR','VIEWER','REVIEWER'].includes(membership.role)||typeof me.user_id!=='string'||!/^[-\w]{1,128}$/.test(me.user_id))throw Error('PROJECT_MEMBERSHIP_REQUIRED');
      if(actor!==null&&actor!==me.user_id)throw Error('ACCOUNT_CHANGED_REMOUNT_REQUIRED');
      actor=me.user_id;storageKey='xj_ecosystem_pending_v1:'+actor+':'+project;const recovered=storedPending();if(pending&&(!recovered||recovered.key!==pending.key))throw Error('PENDING_RECOVERY_BINDING_CHANGED');pending=recovered;if(pending)keyInput.value=pending.key;owner=membership.role==='OWNER';authorized=true;
      const [catalog,list]=await Promise.all([api.ecosystemList(project),api.ecosystemPackages(project)]);if(disposed||g!==generation)return;
      if(list.scope!=='TENANT_PROJECT_PENDING_ONLY'||list.published!==false||!Number.isSafeInteger(list.catalog_revision)||list.catalog_revision<0||!Array.isArray(list.packages)||!Array.isArray(catalog.rows))throw Error('INVALID_PENDING_LIST');
      revision=list.catalog_revision;available=catalog.rows.filter(r=>typeof r.module_id==='string'&&/^[a-z][a-z0-9_.-]{0,95}$/.test(r.module_id)&&typeof r.package_version==='string'&&/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(r.package_version));
      select.replaceChildren(...available.map((r,i)=>{const o=el('option',r.module_id+' @ '+r.package_version);o.value=String(i);return o}));select.value=available.length?'0':'';
      records.replaceChildren(...list.packages.map(r=>{if(r.state!=='PENDING_REVIEW')throw Error('UNSUPPORTED_PACKAGE_STATE');return el('p',r.module_id+' @ '+r.version+' · 待审核 · '+r.record_id)}));
      message(pending?'上次提交结果 UNKNOWN；已恢复原幂等键，只能回读回执，禁止重复提交。':'已回读项目修订 '+revision+'；'+(owner?'OWNER 可登记待审核。':'当前角色仅查看，无登记授权。'));
    }catch(e){if(!disposed&&g===generation){revision=null;if(!authorized)owner=false;available=[];select.replaceChildren();records.replaceChildren();message('读取未完成：'+e.message)}}finally{if(g===generation){busy=false;controls()}}
  }
  register.addEventListener('click',async()=>{
    if(disposed||register.disabled||pending||busy)return;const item=available[Number(select.value)];if(!item)return;
    const key=keyFactory();if(typeof key!=='string'||!/^[A-Za-z0-9_-]{16,96}$/.test(key)){message('幂等键无效，未提交');return}
    const intent={schema:1,actor,project,key,module:item.module_id,version:item.package_version,revision};
    try{remember(intent);pending=intent;keyInput.value=key}catch(e){revision=null;message('恢复记录未保存，未提交：'+e.message);controls();return}
    busy=true;controls();message('提交待审核登记中；幂等键 '+key);
    try{
      const result=checkReceipt(await api.ecosystemRegisterPending(project,pending.module,pending.version,pending.revision,key));if(disposed)return;
      clearPending();message('已登记待审核；未发布。回执 '+result.record_id);await load();
    }catch(e){
      if(disposed)return;
      if(e.uncertain||['INVALID_PENDING_RECEIPT','RECEIPT_PACKAGE_MISMATCH'].includes(e.message)||e.message.startsWith('PENDING_RECOVERY_'))message('结果 UNKNOWN：保留原幂等键，只回读回执，不重试提交。');
      else{try{clearPending();revision=null;message('登记被拒绝：'+e.message+'；请刷新后重新确认。')}catch{revision=null;message('结果 UNKNOWN：原恢复记录未能确认清理，只回读原幂等键。')}}
    }finally{busy=false;controls()}
  });
  receipt.addEventListener('click',async()=>{
    if(disposed||receipt.disabled||busy)return;const key=keyInput.value;try{const recovered=storedPending();if(recovered)pending=recovered}catch(e){revision=null;message('回执恢复记录无效：'+e.message);controls();return}
    if(pending&&key!==pending.key){message('必须回读上次原幂等键，不能更换未知请求。');return}
    busy=true;controls();
    try{const result=checkReceipt(await api.ecosystemReceipt(project,key));if(disposed)return;clearPending();message('回执确认待审核；未发布。'+result.record_id);await load()}catch(e){message('回执仍未确认：'+e.message+'；不代表未提交，禁止自动重试。')}finally{busy=false;controls()}
  });
  refresh.addEventListener('click',load);controls();const ready=load();
  return {ready,refresh:load,hasPending:()=>busy||pending!==null,dispose(){disposed=true;generation++;controls();container.replaceChildren()}};
}
