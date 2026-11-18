/* Adapter for the existing authenticated UNIFIED_ADMIN_PROJECTION_V1.
 * No fixtures, credentials, persistence or writes. Integration into the
 * owner shell is intentionally separate from this source adapter. */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.AdminTaskRead = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';
  const fields = ['task_id','project_id','state','runtime_status','responsible_party','next_action','last_real_progress_at','blocker'];
  function text(v) { return v == null || v === '' ? 'UNKNOWN' : String(v); }
  function normalize(session, projection) {
    if (!session || !session.tenant_id || !projection || projection.projection !== 'UNIFIED_ADMIN_PROJECTION_V1' || projection.tenant_id !== session.tenant_id) throw new Error('INVALID_PROJECTION');
    const module = projection.modules && projection.modules['research-development'];
    if (!module || module.status !== 'CONNECTED_TEST_ONLY' || !Array.isArray(module.records)) throw new Error('SOURCE_UNAVAILABLE');
    const seen = new Set();
    return module.records.map(record => {
      if (!record || typeof record.task_id !== 'string' || !record.task_id || seen.has(record.task_id)) throw new Error('INVALID_TASK');
      seen.add(record.task_id);
      return Object.fromEntries(fields.map(k => [k, text(record[k])]));
    });
  }
  async function load(fetcher, base) {
    const prefix = base || '../api/';
    async function get(path) {
      const response = await fetcher(prefix + path, {credentials:'same-origin', cache:'no-store'});
      if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? 'ACCESS_DENIED' : 'SOURCE_UNAVAILABLE');
      return response.json();
    }
    const session = await get('session');
    return normalize(session, await get('admin/workbench'));
  }
  function list(records, options) {
    options = options || {};
    const keyword = String(options.keyword || '').trim().toLocaleLowerCase();
    const status = options.status || '';
    const filtered = records.filter(r => (!status || r.state === status) && (!keyword || fields.some(k => text(r[k]).toLocaleLowerCase().includes(keyword))));
    const size = Number.isInteger(options.pageSize) && options.pageSize > 0 ? options.pageSize : 20;
    const pages = Math.max(1, Math.ceil(filtered.length / size));
    const page = Math.min(pages, Math.max(1, Number.isInteger(options.page) ? options.page : 1));
    return {records: filtered.slice((page-1)*size,page*size), total: filtered.length, page, pages, state: records.length === 0 ? 'empty' : filtered.length === 0 ? 'no-results' : 'ready'};
  }
  function detail(records, id) { return records.find(r => r.task_id === id) || null; }
  return {normalize, load, list, detail};
});
