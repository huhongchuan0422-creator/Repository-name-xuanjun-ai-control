import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { isAbsolute } from 'node:path';

const CHILD = fileURLToPath(new URL('../../scripts/task_center_owner_read.py', import.meta.url));
const METHOD = 'taskcenter.handoff.read';
const atom = x => typeof x === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,100}$/.test(x);
const exact = (x, keys) => x && typeof x === 'object' && !Array.isArray(x) &&
  Object.keys(x).sort().join(',') === [...keys].sort().join(',');
const fail = () => { throw new Error('TC_OWNER_READ_REJECTED'); };

function configuration(value) {
  if (!value || value.enabled === undefined || value.enabled === false) return null;
  if (!exact(value, ['enabled','python','database','runtimeConfig','dispatchConfig','bindings']) || value.enabled !== true ||
      !['python','database','runtimeConfig','dispatchConfig'].every(k => typeof value[k] === 'string' && isAbsolute(value[k])) ||
      !Array.isArray(value.bindings) || value.bindings.length > 128) fail();
  const seen = new Set();
  for (const b of value.bindings) {
    if (!exact(b, ['gateway_profile_id','tenant_id','principal_id','session_hash','task_id','attempt_id','expires_at']) ||
        !['gateway_profile_id','tenant_id','principal_id','task_id','attempt_id'].every(k => atom(b[k])) ||
        !/^[a-f0-9]{64}$/.test(b.session_hash) || !Number.isFinite(b.expires_at)) fail();
    const key = JSON.stringify([b.gateway_profile_id,b.task_id,b.attempt_id]);
    if (seen.has(key)) fail(); seen.add(key);
  }
  return structuredClone(value);
}

function childRead(config, packet, borrow) {
  return new Promise((resolve, reject) => {
    // Fixed reviewed child; no shell, inherited environment secrets or daemon.
    const child = spawn(config.python, ['-I','-B',CHILD,'--db',config.database,
      '--runtime-config',config.runtimeConfig,'--dispatch-config',config.dispatchConfig], {
      stdio: ['ignore','pipe','pipe','pipe'], env: { PATH: '/usr/bin:/bin', LANG: 'C.UTF-8' },
    });
    let output = Buffer.alloc(0), settled = false;
    const done = (error, value) => {
      if (settled) return; settled = true;
      if (error) child.kill('SIGKILL'); clearTimeout(timer); borrow.signal.removeEventListener('abort', abort);
      error ? reject(error) : resolve(value);
    };
    const abort = () => { child.kill('SIGKILL'); done(new Error('TC_OWNER_READ_REJECTED')); };
    const timer = setTimeout(abort, 5000);
    borrow.signal.addEventListener('abort', abort, { once: true });
    if (borrow.signal.aborted) { abort(); return; }
    child.stdout.on('data', bytes => {
      output = Buffer.concat([output, bytes]);
      if (output.length > 65536) abort();
    });
    child.stderr.resume(); // Never forward child paths/rows/backend errors.
    child.on('error', () => done(new Error('TC_OWNER_READ_REJECTED')));
    child.stdio[3].on('error', () => done(new Error('TC_OWNER_READ_REJECTED')));
    child.on('close', code => {
      if (code !== 0) { done(new Error('TC_OWNER_READ_REJECTED')); return; }
      try {
        const value = JSON.parse(output.toString('utf8'));
        if (!exact(value,['operation_id','request_digest','receipt']) ||
            value.operation_id !== packet.operation_id || value.request_digest !== packet.request_digest ||
            value.receipt.task_id !== packet.request.task_id || value.receipt.attempt_id !== packet.request.attempt_id ||
            value.receipt.event_id !== packet.request.event_id) fail();
        done(null, value);
      } catch { done(new Error('TC_OWNER_READ_REJECTED')); }
    });
    child.stdio[3].end(JSON.stringify(packet));
  });
}

export function registerOwnerRead(api) {
  const config = configuration(api.pluginConfig);
  if (!config) return; // No registration, process or DB access when disabled.
  api.registerGatewayMethod(METHOD, async options => {
    let borrow;
    try {
      const { params, client, sessionAccessAuthority: authority } = options;
      if (!exact(params,['sessionKey','task_id','attempt_id','event_id','operation_id']) ||
          !['task_id','attempt_id','event_id','operation_id'].every(k => atom(params[k])) ||
          !authority || typeof authority.assertCurrent !== 'function' || typeof authority.retain !== 'function' ||
          authority.sandboxRequired === true || client?.internal?.syntheticClient || !client?.authenticatedUserProfile?.profileId ||
          client.authenticatedUserProfile.profileId === 'gateway-owner') fail();
      authority.assertCurrent();
      const b = config.bindings.find(b => b.gateway_profile_id === client.authenticatedUserProfile.profileId &&
        b.task_id === params.task_id && b.attempt_id === params.attempt_id);
      if (!b || b.expires_at <= Date.now()/1000) fail();
      borrow = authority.retain(); borrow.assertCurrent();
      const request = {task_id:params.task_id,attempt_id:params.attempt_id,event_id:params.event_id};
      const request_digest = createHash('sha256').update(JSON.stringify(request)).digest('hex');
      // Only host configuration supplies TC session/principal. Never request roles.
      const packet = {binding:b,request,operation_id:params.operation_id,request_digest};
      authority.assertCurrent(); borrow.assertCurrent();
      const result = await childRead(config,packet,borrow);
      // READ's externally observable effect is disclosure at respond, not the
      // private calculation. A revoked lifetime never releases buffered output.
      authority.assertCurrent(); borrow.assertCurrent();
      if (b.expires_at <= Date.now()/1000) fail();
      options.respond(true,result);
    } catch {
      options.respond(false,undefined,{code:'UNAVAILABLE',message:'TC_OWNER_READ_REJECTED'});
    } finally { borrow?.release(); }
  }, {scope:'operator.read',profileAccess:'required',sessionAccess:{mode:'read'}});
}

export default {
  id: 'tc-owner-read', name: 'TC owner-admitted receipt read',
  description: 'Default-off exact READ over the original canonical handoff consumer.',
  register: registerOwnerRead,
};
