/** Static provenance only: never imports or evaluates the archived SDK. */
import {createHash} from 'node:crypto';
export const SERVER_ROOT=Object.freeze({member:'dist/server-ChnNHwLm.mjs',bytes:4051,sha256:'26067e9a59a2addaeb05f39945dee9a42dc7ae9d22f6de530fc6f1d5ce25ae56'});
export function inspectServerRoot(bytes) {
 if(!Buffer.isBuffer(bytes)||bytes.length!==SERVER_ROOT.bytes||createHash('sha256').update(bytes).digest('hex')!==SERVER_ROOT.sha256)throw new Error('HOLD_SERVER_ROOT_BYTES');
 // This pin binds an inspected fixed version, not an arbitrary lexical parser.
 return Object.freeze({scope:'STATIC_BYTES_ONLY',member:SERVER_ROOT.member,
  publicEntry:'startGatewayServer',nextMember:'dist/server-start-Bz-KV48j.mjs',
  nextExport:'startGatewayServerCore',ownerBinding:'UNBOUND',
  executionReadiness:'HOLD_REAL_OWNER_UNBOUND',sdk:'NOT_EXECUTED',
  lifecycle:Object.freeze(['server.close','readOnlyWorkers.close','stopDatabaseAdmission','broker.close','ownedLock.release'])});
}
