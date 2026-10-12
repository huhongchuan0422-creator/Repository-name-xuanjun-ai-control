import { createHash } from 'node:crypto';
export function canonical(value, depth = 0) {
  if (depth > 64) throw new Error('HOLD_JSON_DEPTH');
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new Error('HOLD_NONFINITE_JSON');
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return '[' + value.map(v => canonical(v, depth + 1)).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => {
    if (['__proto__', 'constructor', 'prototype'].includes(k)) throw new Error('HOLD_UNSAFE_JSON_KEY');
    return JSON.stringify(k) + ':' + canonical(value[k], depth + 1);
  }).join(',') + '}';
  throw new Error('HOLD_JSON_TYPE');
}
export const digest = value => createHash('sha256').update(canonical(value)).digest('hex');

