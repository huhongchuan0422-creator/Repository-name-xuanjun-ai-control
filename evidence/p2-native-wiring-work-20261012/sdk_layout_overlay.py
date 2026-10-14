"""Apply measured OpenClaw 2026.9.9 layout binding after owner/ACL overlays."""
import hashlib, json, pathlib, sys
root=pathlib.Path(sys.argv[1]); here=pathlib.Path(__file__).resolve().parent
plugin=root/'plugins/p2-native-controller'
manifest_path=root/'deploy/integration-manifest.json'
manifest=json.loads(manifest_path.read_text())
pins={'host.mjs':'4d6f44d292eae99dbc651c98a44bb5da975232a8a9924e4ed5354575780d77c6',
      'workspace.mjs':'c1ac70b325dd878f00c122f515719b182e62973e5b42c58ca6181d7cb242f3c4'}
texts={}
for name,pin in pins.items():
    raw=(plugin/name).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('SDK_LAYOUT_BASE_HASH_'+name)
    texts[name]=raw.decode()
def replace(name,old,new):
    if texts[name].count(old)!=1:raise ValueError('SDK_LAYOUT_ANCHOR_'+name)
    texts[name]=texts[name].replace(old,new)
replace('host.mjs',"import {digest} from './canonical.mjs';", "import {digest} from './canonical.mjs';\nimport {sandboxLayout} from './sdk-layout.mjs';")
replace('host.mjs',"""    if(context?.enabled!==true||context.sessionKey!==sessionKey||context.workspaceDir!==request.workdir
      ||context.backendId!==settings.engine.backend||typeof context.runtimeId!=='string'
      ||context.workspaceAccess!==(request.sandbox==='read-only'?'ro':'rw'))hold('SANDBOX_CONTEXT_BINDING');
    preparedSandboxes.set(sessionKey,{runtimeId:context.runtimeId,backendId:context.backendId,
      workspaceDir:context.workspaceDir,workspaceAccess:context.workspaceAccess});
    return {backend:context.backendId,name:context.runtimeId};""", """    const layout=sandboxLayout(context,request,sessionKey,settings.engine.backend);
    preparedSandboxes.set(sessionKey,layout);
    return {backend:context.backendId,name:context.runtimeId,sdk_layout:layout};""")
replace('host.mjs',"""      if(sandbox?.enabled!==true||sandbox.runtimeId!==saved.unit.name
        ||sandbox.backendId!==saved.unit.backend||sandbox.workspaceDir!==saved.request.workdir
        ||sandbox.workspaceAccess!==(saved.request.sandbox==='read-only'?'ro':'rw'))hold('TOOL_SANDBOX_BINDING');""", """      const layout=sandboxLayout(sandbox,saved.request,ctx.sessionKey,settings.engine.backend);
      if(layout.runtime_id!==saved.unit.name||layout.backend!==saved.unit.backend
        ||!saved.unit.sdk_layout||digest(layout)!==digest(saved.unit.sdk_layout))hold('TOOL_SANDBOX_BINDING');""")
replace('host.mjs',"""      if(!expected||expected.runtimeId!==unit.name||expected.backendId!==unit.backend
        ||expected.workspaceDir!==request.workdir||!store.guard(request))return null;""", """      if(!expected||expected.runtime_id!==unit.name||expected.backend!==unit.backend
        ||!unit.sdk_layout||digest(expected)!==digest(unit.sdk_layout)||!store.guard(request))return null;""")
replace('host.mjs',"""      if(current?.enabled!==true||current.runtimeId!==unit.name||current.backendId!==unit.backend
        ||current.workspaceDir!==request.workdir
        ||current.workspaceAccess!==(request.sandbox==='read-only'?'ro':'rw'))return null;""", """      const layout=sandboxLayout(current,request,sessionKey,settings.engine.backend);
      if(digest(layout)!==digest(expected))return null;""")
replace('workspace.mjs',"import { canonical, digest } from './canonical.mjs';", "import { canonical, digest } from './canonical.mjs';\nimport {verifySdkMounts} from './sdk-layout.mjs';")
replace('workspace.mjs',"""    const workspaceMount=Array.isArray(mounts)?mounts.find(m=>m.Type==='bind' && m.Source===workdir
      && m.RW===(sandbox==='workspace-write')):undefined;""", """    const workspaceMount=unit.sdk_layout
      ?verifySdkMounts(mounts,unit.sdk_layout,workdir,sandbox)
      :Array.isArray(mounts)?mounts.find(m=>m.Type==='bind' && m.Source===workdir
        && m.RW===(sandbox==='workspace-write')):undefined;
    if(unit.sdk_layout) {
      for(const extra of unit.sdk_layout.mounts.slice(1)) {
        const info=await lstat(extra.Source);
        if(!info.isDirectory()||info.uid!==1002||(info.mode&0o022)
          ||await realpath(extra.Source)!==extra.Source)throw new Error('HOLD_SDK_AUXILIARY_DIRECTORY');
      }
    }""")
replace('workspace.mjs',"""        || mounts.some(m=>m.Type!=='bind' || (m.Source!==workdir && (m.RW!==false
          || !readOnlyRoots.some(r=>m.Source===r || m.Source.startsWith(r+'/'))))))""", """        || (!unit.sdk_layout&&mounts.some(m=>m.Type!=='bind' || (m.Source!==workdir && (m.RW!==false
          || !readOnlyRoots.some(r=>m.Source===r || m.Source.startsWith(r+'/')))))))""")
if (plugin/'sdk-layout.mjs').exists():raise ValueError('SDK_LAYOUT_ALREADY_PRESENT')
texts['sdk-layout.mjs']=(here/'sdk-layout.mjs').read_text()
for name,text in texts.items():
    (plugin/name).write_text(text)
    rel='plugins/p2-native-controller/'+name
    manifest['files'][rel]=hashlib.sha256(text.encode()).hexdigest()
manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
print('SDK_LAYOUT_OVERLAY=PASS; MODEL_CALLS=0; INSTALL=NO')
