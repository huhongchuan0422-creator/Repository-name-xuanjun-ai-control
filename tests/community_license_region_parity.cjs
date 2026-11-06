'use strict';
// Source-only cross-language verification. Not a runtime or Python test dependency.
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const { spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
// Repository layout after Writer integration, with standalone-delivery fallback.
const repositoryMini = path.join(root, 'clients/community-mini');
const mini = fs.existsSync(path.join(repositoryMini, 'merchant-license-region.js')) ? repositoryMini : root;
const { resolveLicenseRegion } = require(path.join(mini, 'merchant-license-region.js'));
const fixturePath = path.join(__dirname, 'fixtures/community_license_region.json');
const fixtures = require(fixturePath);
const areas = require(path.join(mini, 'merchant-official-areas.json'));
const cases = fixtures.map(item => ({ id: item.id, address: item.address, expected: item.expected }));
for (const row of areas.rows) {
  const variants = [row.slice(1), row.slice(1).filter((v, i, a) => !i || v !== a[i - 1])];
  if (row[2] !== row[3]) variants.push(row.slice(2));
  for (const names of variants) cases.push({ id: row[0], address: names.join('') + '合成路1号' });
}
for (const item of cases) {
  const result = resolveLicenseRegion(item.address);
  if (item.expected) assert.deepEqual(result, item.expected, item.id);
}
const python = spawnSync(process.env.PYTHON || 'python3', ['-c', `
import json, sys
sys.path.insert(0, sys.argv[1])
from community_license_region import resolve_license_region
print(json.dumps([resolve_license_region(case['address']) for case in json.load(sys.stdin)], ensure_ascii=False))
`, path.join(root, 'scripts')], { input: JSON.stringify(cases), encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 });
assert.equal(python.status, 0, python.stderr);
const actual = JSON.parse(python.stdout);
cases.forEach((item, index) => assert.deepEqual(actual[index], resolveLicenseRegion(item.address), item.id));
console.log(`Cross-language parity passed: ${cases.length} addresses; unchanged 3240-row directory.`);
