'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let auth = null, epoch = 0, busy = false, items = [], selected = null;
  const pending = new Set();
  const validID = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,64}$/.test(value);
  const notice = value => { $('reviewNotice').textContent = value; };
  function controls() {
    for (const button of document.querySelectorAll('button')) button.disabled = !auth || busy;
    const state = selected && selected.state;
    $('reviewBegin').hidden = state !== 'SUBMITTED';
    $('reviewChanges').hidden = $('reviewApprove').hidden = state !== 'IN_REVIEW';
    $('reviewReason').disabled = !auth || busy || state !== 'IN_REVIEW';
  }
  function clearDetail() {
    selected = null;
    $('reviewDetail').hidden = true;
    for (const id of ['reviewSelected', 'reviewInstructions', 'reviewVersions']) $(id).replaceChildren();
    $('reviewReason').value = '';
  }
  async function call(endpoint, operation, params, ticket) {
    if (!auth || ticket !== epoch) throw Error('身份或项目已变化');
    const context = auth, controller = new AbortController();
    pending.add(controller);
    try {
      const response = await fetch(endpoint, {
        method: 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
        signal: controller.signal, headers: {'Content-Type': 'application/json', 'X-CSRF-Token': context.csrf},
        body: JSON.stringify({workspace: context.workspace, operation, params})
      });
      if (ticket !== epoch) throw Error('身份或项目已变化');
      if (!response.ok) throw Error('请求未完成（HTTP ' + response.status + '）。请刷新核对当前权限与版本后再操作。');
      const data = await response.json();
      if (ticket !== epoch) throw Error('身份或项目已变化');
      if (!data || !Object.prototype.hasOwnProperty.call(data, 'result')) throw Error('服务返回格式无效，请刷新重试');
      return data.result;
    } finally { pending.delete(controller); }
  }
  async function action(task) {
    if (!auth || busy) return;
    const ticket = epoch; busy = true; controls(); notice('正在处理…');
    try { const message = await task(ticket); if (ticket === epoch) notice(message || '操作完成'); }
    catch (error) { if (ticket === epoch) notice(error.message || '操作未确认，请刷新核对结果'); }
    finally { if (ticket === epoch) { busy = false; controls(); } }
  }
  const addText = (parent, tag, text) => { const node = document.createElement(tag); node.textContent = text; parent.append(node); return node; };
  function button(parent, label, handler) {
    const node = addText(parent, 'button', label); node.type = 'button'; node.onclick = handler; return node;
  }
  async function download(objectID, ticket) {
    const file = await call('/community/project-materials', 'download', {object_id: objectID}, ticket);
    if (ticket !== epoch) return;
    const types = {'application/pdf': '.pdf', 'image/png': '.png', 'image/jpeg': '.jpg'};
    if (!file || !types[file.mime] || typeof file.content_base64 !== 'string' || file.content_base64.length > 6666668) throw Error('文件响应无效');
    const raw = atob(file.content_base64), bytes = Uint8Array.from(raw, character => character.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], {type: file.mime}));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = objectID + types[file.mime];
    document.body.append(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return '已下载材料。请核对内容后再审核。';
  }
  function show(item) {
    clearDetail(); selected = item; $('reviewDetail').hidden = false;
    $('reviewSelected').textContent = item.title + ' · ' + item.id + ' · 当前版本 ' + item.revision + ' · ' + item.state;
    $('reviewInstructions').textContent = (item.instructions || '') + (item.needs_reverification ? ' · 材料需重新核验' : '');
    const versions = Array.isArray(item.versions) ? item.versions : [];
    const saves = versions.filter(version => version.kind === 'SAVE');
    const currentSave = saves.length ? saves[saves.length - 1] : null;
    for (const version of versions) {
      const row = addText($('reviewVersions'), 'article', '版本 ' + version.seq + ' · ' + version.kind + (version === currentSave ? ' · 当前提交材料' : ''));
      const details = version.details || {};
      if (details.reason) addText(row, 'p', '审核意见：' + details.reason);
      if (details.reference) addText(row, 'p', '原中心引用：' + details.reference);
      if (version.kind === 'SAVE' && validID(details.object_id)) {
        const ticket = epoch;
        button(row, version === currentSave ? '下载当前材料' : '下载历史材料', () => {
          if (ticket === epoch) action(t => download(details.object_id, t));
        });
      }
    }
    controls();
  }
  async function reload(ticket, preferredID) {
    clearDetail(); items = []; $('reviewItems').replaceChildren();
    const result = await call('/community/project-materials', 'checklist', {}, ticket);
    if (ticket !== epoch) return;
    if (!result || result.project !== auth.workspace || !Array.isArray(result.items)) throw Error('项目清单不匹配');
    items = result.items;
    $('reviewProject').textContent = '项目 ' + result.project + ' · 整体状态 ' + result.overall + ' · 需求版本 ' + result.requirements_revision;
    for (const item of items) {
      const row = addText($('reviewItems'), 'article', item.title + ' · ' + item.state + ' · 版本 ' + item.revision + (item.required ? ' · 必需' : ' · 可选'));
      button(row, '查看材料与审核', () => { if (ticket === epoch && !busy) show(item); });
    }
    if (!items.length) addText($('reviewItems'), 'p', '当前项目没有材料要求');
    const matching = items.find(item => item.id === preferredID);
    if (matching) show(matching);
    return '清单已刷新，请核对当前版本';
  }
  function review(operation) {
    if (!selected || busy || !auth) return;
    const expectedState = operation === 'begin_review' ? 'SUBMITTED' : 'IN_REVIEW';
    if (selected.state !== expectedState) return;
    const item = selected.id, revision = selected.revision, reason = $('reviewReason').value.trim();
    if (operation !== 'begin_review' && !reason) { notice('请填写审核意见后再提交'); return; }
    action(async ticket => {
      // Once sent, discard actionable versions even on ambiguous network failure.
      clearDetail(); items = []; $('reviewItems').replaceChildren();
      const result = await call('/community/commerce', 'project_review', {item, revision, action: operation, reason}, ticket);
      if (ticket !== epoch) return;
      await reload(ticket, item);
      return '审核操作已记录：' + result.state + ' · 版本 ' + result.revision + '；清单已刷新';
    });
  }
  $('reviewReload').onclick = () => action(ticket => reload(ticket, selected && selected.id));
  $('reviewBegin').onclick = () => review('begin_review');
  $('reviewChanges').onclick = () => review('request_changes');
  $('reviewApprove').onclick = () => review('approve');
  $('reviewForm').onsubmit = event => event.preventDefault();
  window.configureCommunityProjectReview = value => {
    epoch++; for (const controller of pending) controller.abort(); pending.clear();
    auth = value && typeof value.csrf === 'string' && value.csrf && validID(value.workspace) ? {csrf: value.csrf, workspace: value.workspace} : null;
    busy = false; items = []; clearDetail(); $('reviewItems').replaceChildren(); $('reviewProject').replaceChildren(); controls();
    notice(auth ? '已连接原客户中心项目' : '请从客户中心打开已授权的项目');
    if (auth) action(ticket => reload(ticket));
  };
  window.configureCommunityProjectReview(null);
})();
