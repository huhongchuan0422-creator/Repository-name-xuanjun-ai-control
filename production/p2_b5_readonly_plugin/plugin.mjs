/** Independent B5 metadata-only profile. Never co-load with the original same-id plugin.
 * The Gateway owns authentication. Client below MUST be the dispatcher-provided client,
 * never a request field. This source contains no execution-controller/runtime imports.
 */
import {createHash} from 'node:crypto';
import {openSync,fstatSync,readSync,closeSync,constants} from 'node:fs';
import {fileURLToPath} from 'node:url';
const ID='xuanjun-p2-native-controller';
const VERSION='0.1.1-b5-readonly.1';
const METHOD='xuanjun.capabilities.describe';
const CAPABILITIES=Object.freeze([Object.freeze({method:METHOD,operation:'describe',read_only:true,required_scope:'operator.admin'})]);
const sha=raw=>createHash('sha256').update(raw).digest('hex');
const DECLARATION=Object.freeze({plugin_id:ID,plugin_version:VERSION,declared_capabilities:CAPABILITIES});
function sourceDigest() {
  // The only filesystem read is this fixed module's own bytes, once at registration.
  // No caller path, plugin binding/config, credentials or application data are read.
  const fd=openSync(fileURLToPath(import.meta.url),constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
  try {
    const before=fstatSync(fd);
    if(!before.isFile()||before.nlink!==1||before.size>65536)throw new Error('HOLD_SELF_SOURCE');
    const buffer=Buffer.alloc(65537);let total=0;
    while(total<buffer.length){const n=readSync(fd,buffer,total,buffer.length-total,null);if(n===0)break;total+=n;}
    const raw=buffer.subarray(0,total),after=fstatSync(fd);
    if(raw.length!==before.size||['dev','ino','size','mtimeMs','ctimeMs','mode','uid','gid','nlink'].some(k=>before[k]!==after[k]))throw new Error('HOLD_SELF_SOURCE_CHANGED');
    return sha(raw);
  } finally {closeSync(fd);}
}
export default Object.freeze({
  id:ID,
  name:'Xuanjun P2 B5 read-only capabilities',
  register(api) {
    const config=api?.pluginConfig;
    if(config!==undefined&&(config===null||typeof config!=='object'||Array.isArray(config)||Object.keys(config).length!==0))throw new Error('HOLD_READONLY_CONFIG');
    if(typeof api?.registerGatewayMethod!=='function')throw new Error('HOLD_GATEWAY_API');
    const publicMetadata=Object.freeze({...DECLARATION,
      plugin_source_sha256:sourceDigest(),
      declaration_sha256:sha(JSON.stringify(DECLARATION))});
    api.registerGatewayMethod(METHOD,({params,respond,client})=>{
      // Same authenticated operator.admin client boundary as original index.mjs.
      if(!Array.isArray(client?.connect?.scopes)||!client.connect.scopes.includes('operator.admin')) {
        respond(false,undefined,{code:'UNAVAILABLE',message:'HOLD_ADMIN_REQUIRED'});return;
      }
      if(!params||typeof params!=='object'||Array.isArray(params)||Object.keys(params).length!==1||!Object.hasOwn(params,'operation')||params.operation!=='describe') {
        respond(false,undefined,{code:'INVALID_REQUEST',message:'HOLD_DESCRIBE_PARAMS'});return;
      }
      // No lazy runtime, host bindings, file reads, model/ledger/engine or lifecycle work.
      respond(true,publicMetadata);
    },{scope:'operator.admin'});
  }
});
