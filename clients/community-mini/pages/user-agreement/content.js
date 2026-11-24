'use strict';
// Private staging, not approved for publication. Leave disabled until the
// real terms are approved and the same AppID's native guideline is published.
const release = Object.freeze({
  privacyContractPublished: false,
  version: '2026-11-23',
  operator: '重庆拾陆数字传媒有限公司',
  privacyContact: '客服电话 13508319735',
  retentionAndDisposal: '作为当前联系方式保存至你修改、清空并保存，或我们根据你的删除请求完成处理。修改或清空并保存会更新当前资料',
});
const confirmed = v => typeof v === 'string' && !!v.trim() &&
  !/[【】［］<>]/.test(v) && !/(待确认|待填写|占位|示例|草稿|未核实|TODO|TBD|FIXME|DRAFT|PLACEHOLDER|EXAMPLE)/i.test(v);
const agreementPath = '/pages/user-agreement/index';
function active() {
  return [release.operator, release.privacyContact, release.retentionAndDisposal].every(confirmed) &&
    /^\d{4}-\d{2}-\d{2}(?:-[A-Za-z0-9]+)?$/.test(release.version);
}
function policy() {
  if (!active()) return null;
  return Object.freeze({version:release.version,agreementPage:agreementPath,privacyContractPublished:release.privacyContractPublished});
}
function agreement() {
  if (!active()) return null;
  return {version:release.version, sections:[
    '本小程序由'+release.operator+'运营。你可以浏览社区服务与推荐内容；在满足相应功能的登录或使用条件时，可以查看自己的订单、通知，或使用商家服务。',
    '在「我的 → 个人资料」中，手机号为选填，仅用于保存和管理你本人在该页面填写的联系方式。你可以先阅读本协议和《隐私政策》，再决定是否同意。不同意时不会在该页面读取、预填或保存你的手机号，也不会因此影响订单、通知、商家服务等与手机号无关的功能。',
    '请仅填写你有权提供的联系方式，并点击「保存资料」提交修改。手机号保存期限和到期处理：'+release.retentionAndDisposal+'。',
    '你可选择「停止在本页使用手机号」，页面会清除显示的资料并停止后续读取或编辑，但不会自动删除此前保存的信息。需要查询、更正、删除资料或反映问题，可通过'+release.privacyContact+'联系我们。',
  ]};
}
module.exports = {policy,agreement};
