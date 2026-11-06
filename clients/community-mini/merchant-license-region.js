'use strict';
// Pure, offline lookup against the unchanged original payment-provider directory.
// Read only the retained first-step license address, never unconfirmed OCR rows.
const areas = require('./merchant-official-areas-data');
const LICENSE_ADDRESS_PATH = 'subject_info.business_license_info.license_address';
const BIZ_ADDRESS_CODE_PATH = 'business_info.sales_info.biz_store_info.biz_address_code';
const DIRECTORY = Object.freeze({ source_url: areas.source_url, observed_at_utc: areas.observed_at_utc,
  xlsx_sha256: areas.xlsx_sha256, row_count: areas.rows.length, effective_version: null });
const root = { next: new Map(), rows: [] };
const byCode = new Map();
const provinces = new Set(), cities = new Set(), districts = new Set();
const districtsByCity = new Map();
function normalize(value) {
  // Formatting only. Do not truncate, transliterate, infer aliases, or modify source data.
  return value.replace(/[\s\u3000,，、]/g, '').replace(/（/g, '(').replace(/）/g, ')');
}
function addPath(names, row) {
  let node = root;
  for (const char of normalize(names.join(''))) {
    if (!node.next.has(char)) node.next.set(char, { next: new Map(), rows: [] });
    node = node.next.get(char);
  }
  if (!node.rows.some(item => item[0] === row[0])) node.rows.push(row);
}
for (const source of areas.rows) {
  const row = Object.freeze(source.slice());
  if (!/^[0-9]{6}$/.test(row[0]) || byCode.has(row[0])) throw Error('INVALID_OFFICIAL_REGION_DIRECTORY');
  byCode.set(row[0], row); provinces.add(row[1]); cities.add(row[2]); districts.add(row[3]);
  const cityKey = row[1] + '|' + row[2];
  if (!districtsByCity.has(cityKey)) districtsByCity.set(cityKey, []);
  districtsByCity.get(cityKey).push(row[3]);
  addPath(row.slice(1), row);
  // Municipalities / province-administered units repeat the same name in the table.
  // A single explicit name is the same hierarchy, not a guessed missing level.
  if (row[1] === row[2]) addPath([row[1], row[3]], row);
  if (row[2] === row[3]) addPath([row[1], row[2]], row);
  // Licenses may omit the province. Accept two explicit, consecutive levels only
  // when the entire current directory gives one exact row; never a lone district.
  if (row[2] !== row[3]) addPath([row[2], row[3]], row);
}
function matchAt(text, start) {
  let node = root, match = null;
  for (let at = start; at < text.length; at++) {
    node = node.next.get(text[at]);
    if (!node) break;
    // Longest exact match protects annotated entries such as 珠海市香洲区(...).
    if (node.rows.length) match = { rows: node.rows, end: at + 1 };
  }
  return match;
}
function failure(reason, message) {
  return { ok: false, reason, code: null, row: null, correctionStep: 0, message };
}
function incomplete() {
  return failure('INCOMPLETE_ADDRESS', '营业执照地址信息不足以唯一确定地区，请返回第一步核对原地址；保持执照真实内容，暂不填写猜测编码。');
}
function mismatch() {
  return failure('DIRECTORY_MISMATCH', '营业执照地址与现有地区目录未匹配。请核对第一步原地址；地址正确时需核对或更新地区目录，不要改成旧地名。');
}
function resolveLicenseRegion(address) {
  if (typeof address !== 'string') return failure('INVALID_ADDRESS', '请返回第一步填写或核对营业执照地址。');
  let text = normalize(address);
  if (!text) return incomplete();
  // Optional literal document labels and country names, not arbitrary prefix skipping.
  text = text.replace(/^(?:营业执照注册地址|注册地址|经营场所|住所|地址)[:：]/, '')
    .replace(/^(?:中华人民共和国|中国)/, '');
  if (!text) return incomplete();
  const match = matchAt(text, 0);
  if (!match) {
    const province = [...provinces].find(name => text.startsWith(name));
    if (!province) {
      if ([...cities, ...districts].some(name => text.startsWith(name))) return incomplete();
      return failure('UNRECOGNIZED_ADDRESS', '未能识别营业执照地址的完整行政区信息，请返回第一步核对原地址；地址正确时需核对地区目录，不要填写猜测值。');
    }
    const rest = text.slice(province.length);
    if (!rest) return incomplete();
    const rows = areas.rows.filter(row => row[1] === province);
    const city = rows.map(row => row[2]).find(name => rest.startsWith(name));
    if (city && rest === city) return incomplete();
    if (!city && province !== rows[0][2] && rows.some(row => rest.startsWith(row[3]))) return incomplete();
    return mismatch();
  }
  if (match.rows.length !== 1) return failure('AMBIGUOUS_ADDRESS', '营业执照地址对应多个地区，请返回第一步核对，暂不填写地区编码。');
  const row = match.rows[0];
  // Also reject abbreviated alternatives such as 南山区或福田区. The second
  // district need not repeat its province/city for the address to be ambiguous.
  const tail = text.slice(match.end);
  const alternative = tail.replace(/^(?:或者|或|\/|;|；|\||至|及|与)+/, '');
  const names = alternative !== tail ? [...districts] : districtsByCity.get(row[1] + '|' + row[2]);
  if (names.some(name => name !== row[3] && alternative.startsWith(name))) {
    return failure('AMBIGUOUS_ADDRESS', '营业执照地址中出现不同地区，请返回第一步核对，暂不填写地区编码。');
  }
  // Multiple explicit administrative chains must not silently select the first one.
  for (let at = match.end; at < text.length; at++) {
    if (!root.next.has(text[at])) continue;
    const other = matchAt(text, at);
    if (other && other.rows.some(item => item[0] !== row[0])) {
      return failure('AMBIGUOUS_ADDRESS', '营业执照地址中出现不同地区，请返回第一步核对，暂不填写地区编码。');
    }
  }
  return { ok: true, reason: 'EXACT_DIRECTORY_MATCH', code: row[0], row: row.slice(),
    label: row.slice(1).filter((name, index, names) => !index || name !== names[index - 1]).join(' / '),
    correctionStep: null, message: '已依据第一步营业执照地址匹配地区。' };
}
function regionForExactCode(code) {
  const row = typeof code === 'string' ? byCode.get(code) : null;
  return row ? row.slice() : null;
}
module.exports = { resolveLicenseRegion, regionForExactCode, DIRECTORY, LICENSE_ADDRESS_PATH, BIZ_ADDRESS_CODE_PATH };
