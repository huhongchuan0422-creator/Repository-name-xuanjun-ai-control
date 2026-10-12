import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { lstat, readFile } from 'node:fs/promises';
import path from 'node:path';
import { promisify } from 'node:util';
import { strictJson } from './strict-json.mjs';

const execute = promisify(execFile);
export const JOB = 'a96b9a83-5e58-412c-ab66-ba3bf0add8b9';
export const TASK = 'XUANJUN_WORK_DOTS_OPENCLAW_FOUNDATION_DISCOVERY_V1';
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

/** Use the actual existing automation scratch CAS, never a new ledger. */
export class CanonicalScratchStore {
  constructor({ executable, executableSha256, ownerUid, taskPath, run = execute }) {
    if (!path.isAbsolute(executable) || !/^[0-9a-f]{64}$/.test(executableSha256)
        || !Number.isInteger(ownerUid) || ownerUid === 0 || !Array.isArray(taskPath)
        || taskPath.length < 1 || taskPath.length > 6
        || taskPath.some(k => typeof k !== 'string' || !/^[a-zA-Z][a-zA-Z0-9_]*$/.test(k)
          || ['__proto__','constructor','prototype'].includes(k))) throw new Error('HOLD_CANONICAL_CONFIG');
    this.executable = executable; this.sha256 = executableSha256;
    this.ownerUid = ownerUid; this.taskPath = taskPath; this.run = run;
  }
  async command(args) {
    const info = await lstat(this.executable);
    if (!info.isFile() || info.uid !== this.ownerUid || (info.mode & 0o022)
        || createHash('sha256').update(await readFile(this.executable)).digest('hex') !== this.sha256)
      throw new Error('HOLD_CANONICAL_CLI_CHANGED');
    try {
      const response = await this.run(this.executable, ['automations','scratch',JOB,...args], {
        env: { HOME:'/home/xuanjun_dev', PATH:'/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/bin:/usr/bin:/bin', LANG:'C.UTF-8' },
        timeout:20000, maxBuffer:2*1024*1024, encoding:'utf8'
      });
      return strictJson(response.stdout,2*1024*1024);
    } catch { throw new Error('HOLD_CANONICAL_IO_UNCONFIRMED'); }
  }
  async read() {
    const envelope = await this.command(['--json']);
    const content = envelope.scratch?.content;
    if (!Number.isSafeInteger(envelope.currentRevision) || envelope.currentRevision < 0
        || typeof content !== 'string' || Buffer.byteLength(content) > 1024*1024)
      throw new Error('HOLD_CANONICAL_SHAPE');
    const state = strictJson(content);
    canonical(state);
    if (state.task !== TASK) throw new Error('HOLD_CANONICAL_PARENT_TASK');
    let task = state;
    for (const key of this.taskPath) {
      if (!task || !Object.hasOwn(task,key)) throw new Error('HOLD_EXISTING_TASK_MAPPING_MISSING');
      task = task[key];
    }
    if (!task || typeof task !== 'object' || Array.isArray(task)) throw new Error('HOLD_EXISTING_TASK_MAPPING_MISSING');
    return { state, task, revision:envelope.currentRevision };
  }
  async replace(observed, task) {
    // Replace only execution details inside the existing mapped task record.
    const state = JSON.parse(canonical(observed.state));
    let cursor = state;
    for (const key of this.taskPath.slice(0,-1)) cursor = cursor[key];
    cursor[this.taskPath.at(-1)] = task;
    const raw = canonical(state);
    if (Buffer.byteLength(raw) > 1024*1024) throw new Error('HOLD_CANONICAL_LIMIT');
    await this.command(['--expected-revision',String(observed.revision),'--set',raw]);
    const current = await this.read();
    if (digest(current.task) !== digest(task) || current.revision <= observed.revision)
      throw new Error('HOLD_CANONICAL_CAS_UNCONFIRMED');
    return current;
  }
}
