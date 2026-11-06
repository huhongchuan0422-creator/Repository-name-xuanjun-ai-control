'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { resolveLicenseRegion: resolve, regionForExactCode, DIRECTORY } = require('./merchant-license-region');
const original = require('./merchant-official-areas.json');
const runtime = require('./merchant-official-areas-data');
function exact(address, code) {
  const result = resolve(address);
  assert.equal(result.ok, true, JSON.stringify({ address, result }));
  assert.equal(result.code, code);
  assert.deepEqual(result.row, original.rows.find(row => row[0] === code));
  assert.equal(result.correctionStep, null);
  return result;
}
function unknown(address, reason) {
  const result = resolve(address);
  assert.equal(result.ok, false);
  assert.equal(result.code, null);
  assert.equal(result.row, null);
  assert.equal(result.correctionStep, 0);
  if (reason) assert.equal(result.reason, reason);
  return result;
}
test('runtime uses unchanged original 3240-row provider directory; observed date is not effective version', () => {
  assert.deepEqual(runtime, original);
  assert.equal(DIRECTORY.row_count, 3240);
  assert.equal(DIRECTORY.observed_at_utc, '2026-10-29T19:38:25Z');
  assert.equal(DIRECTORY.xlsx_sha256, 'c3e42f65b1dd2f4360972bdceccc3c522f987c015300fdae756c79682100511f');
  assert.equal(DIRECTORY.effective_version, null);
});
test('all 3240 complete canonical administrative paths return the exact existing code', () => {
  for (const row of original.rows) exact(row.slice(1).join('') + '合成测试路1号', row[0]);
});
test('all canonical paths with adjacent repeated levels collapsed still map exactly', () => {
  for (const row of original.rows) {
    const names = row.slice(1).filter((name, index, all) => !index || name !== all[index - 1]);
    exact(names.join('') + '合成测试路2号', row[0]);
  }
});
test('municipalities accept explicit once or the original repeated city level', () => {
  for (const [city, district, code] of [['北京市', '朝阳区', '110105'], ['天津市', '和平区', '120101'],
    ['上海市', '浦东新区', '310115'], ['重庆市', '渝中区', '500103']]) {
    exact(city + district + '合成路3号', code);
    exact(city + city + district + '合成路3号', code);
  }
});
test('province-administered units and autonomous regions use exact official labels', () => {
  exact('河南省济源市合成路4号', '419001');
  exact('河南省济源市济源市合成路4号', '419001');
  exact('广西壮族自治区南宁市青秀区合成路5号', '450103');
  exact('新疆维吾尔自治区乌鲁木齐市天山区合成路6号', '650102');
});
test('identically named districts use their full hierarchy, never a best guess', () => {
  exact('北京市朝阳区合成路7号', '110105');
  exact('吉林省长春市朝阳区合成路7号', '220104');
  unknown('朝阳区合成路7号', 'INCOMPLETE_ADDRESS');
  exact('长春市朝阳区合成路7号', '220104');
  unknown('吉林省朝阳区合成路7号', 'INCOMPLETE_ADDRESS');
});
test('explicit city plus district can uniquely resolve a license with no province text', () => {
  exact('深圳市南山区合成路8号', '440305');
  exact('长春市朝阳区合成路8号', '220104');
  for (const row of original.rows.filter(row => row[2] !== row[3])) exact(row.slice(2).join('') + '合成路8号', row[0]);
  unknown('南山区合成路8号', 'INCOMPLETE_ADDRESS');
  unknown('深圳市合成路8号', 'INCOMPLETE_ADDRESS');
});
test('a missing city/district or single explicit level cannot supply an exact chain', () => {
  for (const address of ['', '　\t\r\n', '广东省', '广东省深圳市', '广东省南山区合成路8号', '北京市', '北京市北京市']) {
    unknown(address, 'INCOMPLETE_ADDRESS');
  }
});
test('format-only whitespace, comma, fullwidth parentheses and fixed document labels', () => {
  exact('  广东省 ， 深圳市\n南山区\t合成路9号 ', '440305');
  exact('注册地址：中国广东省深圳市南山区合成路9号', '440305');
  exact('中华人民共和国北京市朝阳区合成路9号', '110105');
  exact('广东省珠海市香洲区（由澳门特别行政区实施管辖）合成路10号', '440499');
});
test('longest exact official district name keeps distinct annotated codes apart', () => {
  exact('广东省珠海市香洲区合成路10号', '440402');
  exact('广东省珠海市香洲区(由澳门特别行政区实施管辖)合成路10号', '440499');
});
test('literal old names can match the source; unsupported renamed places never become guessed old codes', () => {
  exact('河北省唐山市滦县合成路11号', '130223');
  const changed = unknown('河北省唐山市滦州市合成路11号', 'DIRECTORY_MISMATCH');
  assert.match(changed.message, /不要改成旧地名/);
  unknown('北京市崇文区合成路11号', 'DIRECTORY_MISMATCH');
  unknown('上海市南汇区合成路11号', 'DIRECTORY_MISMATCH');
});
test('known directory omissions stay explicit and preserve original address data', () => {
  for (const address of ['广东省东莞市合成路12号', '广东省中山市合成路12号', '海南省儋州市合成路12号']) {
    const profile = Object.freeze({ address });
    unknown(profile.address, 'DIRECTORY_MISMATCH');
    assert.equal(profile.address, address);
  }
});
test('inconsistent parents and unsupported abbreviations do not borrow a matching district', () => {
  unknown('广东省长春市朝阳区合成路13号', 'DIRECTORY_MISMATCH');
  unknown('北京朝阳区合成路13号', 'UNRECOGNIZED_ADDRESS');
  unknown('广东深圳南山合成路13号', 'UNRECOGNIZED_ADDRESS');
  unknown('未知省未知市未知区合成路13号', 'UNRECOGNIZED_ADDRESS');
});
test('multiple distinct complete addresses are ambiguous rather than first-match-wins', () => {
  for (const separator of ['；', '或', '\n', '（原地址：']) {
    unknown('北京市朝阳区合成路14号' + separator + '吉林省长春市朝阳区合成路15号', 'AMBIGUOUS_ADDRESS');
  }
});
test('abbreviated alternate districts do not silently select the first district', () => {
  for (const suffix of ['或福田区', '或者福田区', '/福田区', '、福田区', '；福田区', '至福田区']) {
    unknown('广东省深圳市南山区' + suffix + '合成路15号', 'AMBIGUOUS_ADDRESS');
  }
  exact('广东省深圳市南山区合成路15号', '440305');
});
test('no untrusted prefix scan and no arbitrary/default code', () => {
  for (const address of ['110105', '999999', '合成文本北京市朝阳区', '合成营业执照地址', '{}', '__proto__']) unknown(address);
  for (const value of [undefined, null, 110105, {}, [], true, { toString() { throw Error('must not coerce'); } }]) unknown(value, 'INVALID_ADDRESS');
});
test('overlong synthetic strings are processed without truncation or an added address limit', () => {
  const tail = '合成路'.repeat(100000);
  exact('广东省深圳市南山区' + tail, '440305');
  unknown(tail);
  unknown('广东省深圳市南山区' + tail + '吉林省长春市朝阳区合成路16号', 'AMBIGUOUS_ADDRESS');
  unknown(' '.repeat(100000), 'INCOMPLETE_ADDRESS');
});
test('results cannot mutate original dictionary and do not retain street details', () => {
  const result = exact('广东省深圳市南山区合成隐私详情17号', '440305');
  result.row[0] = '999999';
  const codeRow = regionForExactCode('440305'); codeRow[3] = '伪造区';
  exact('广东省深圳市南山区合成路18号', '440305');
  assert.equal(JSON.stringify(result).includes('合成隐私详情'), false);
  assert.equal(regionForExactCode(440305), null);
  assert.equal(regionForExactCode('999999'), null);
  assert.equal(regionForExactCode(' 440305'), null);
});
