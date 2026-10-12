import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {createHostBindings} from './host.mjs';
import {registerController} from './index.mjs';
import {protectedFile} from './ledger.mjs';
import {strictJson} from './strict-json.mjs';

export default {
  id:'xuanjun-p2-native-controller',
  name:'Xuanjun P2 native controller',
  register(api) {
    const spec=api.pluginConfig;
    if(!spec||Object.keys(spec).sort().join(',')!=='bindingFile,bindingSha256')throw new Error('HOLD_PLUGIN_CONFIG');
    protectedFile(spec.bindingFile,spec.bindingSha256);
    const settings=strictJson(readFileSync(spec.bindingFile,'utf8'),65536);
    const resolveContext=async params=>{
      // This is a reviewed immutable SDK dependency, never a worker import.
      for(const [file,entry] of Object.entries(settings.contextFiles||{})) {
        if(!entry||typeof entry!=='object'||!/^[0-9a-f]{64}$/.test(entry.sha256??'')
          ||!Number.isSafeInteger(entry.uid)||entry.uid<0)throw new Error('HOLD_CONTEXT_MANIFEST');
        protectedFile(file,entry.sha256,false,entry.uid);
      }
      if(!Object.hasOwn(settings.contextFiles||{},settings.contextPath))throw new Error('HOLD_CONTEXT_MANIFEST');
      const sdk=await import(pathToFileURL(settings.contextPath).href);
      if(typeof sdk.resolveSandboxContext!=='function')throw new Error('HOLD_CONTEXT_EXPORT');
      return sdk.resolveSandboxContext(params);
    };
    registerController(api,createHostBindings(api,settings,resolveContext));
  }
};
