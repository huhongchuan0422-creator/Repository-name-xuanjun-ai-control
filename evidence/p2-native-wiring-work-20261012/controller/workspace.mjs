import { createHash } from 'node:crypto';
import { open, readdir, realpath, lstat, readFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { canonical, digest } from './canonical.mjs';
const execute = promisify(execFile);
const hash = (kind, raw) => createHash('sha1').update(Buffer.from(kind+' '+raw.length+'\0')).update(raw).digest();

/** Observe the actual Git-free snapshot, not a request's artifact labels. */
export async function verifySnapshot(source, requestedWorkdir) {
  if (!source || source.workdir !== requestedWorkdir || await realpath(requestedWorkdir) !== requestedWorkdir
      || !/^[0-9a-f]{40}$/.test(source.commit ?? '') || !/^[0-9a-f]{40}$/.test(source.tree ?? '')
      || !Array.isArray(source.files) || source.files.length < 1 || source.files.length > 4000)
    throw new Error('HOLD_SOURCE_MANIFEST_UNBOUND');
  const expected = new Map(); const entries=[]; let total=0;
  for (const entry of source.files) {
    if (!entry || typeof entry.path !== 'string' || entry.path.startsWith('/')
        || entry.path.split('/').some(p => !p || ['.','..','.git'].includes(p))
        || expected.has(entry.path) || !['100644','100755'].includes(entry.mode)
        || !/^[0-9a-f]{64}$/.test(entry.sha256 ?? '')) throw new Error('HOLD_SOURCE_MANIFEST_PATH');
    expected.set(entry.path,entry);
  }
  async function walk(directory,prefix='') {
    const rootInfo=await lstat(directory);
    if (!rootInfo.isDirectory() || await realpath(directory)!==directory) throw new Error('HOLD_SOURCE_SYMLINK');
    const tree=[];
    for (const item of await readdir(directory,{withFileTypes:true})) {
      const rel=prefix+item.name, absolute=path.join(directory,item.name);
      if (item.name === '.git' || item.isSymbolicLink()) throw new Error('HOLD_SOURCE_METADATA_OR_SYMLINK');
      if (item.isDirectory()) {
        const node=await walk(absolute,rel+'/'); tree.push({name:item.name,sort:item.name+'/',mode:'40000',sha:node});
      } else if (item.isFile()) {
        const declared=expected.get(rel);
        if (!declared) throw new Error('HOLD_SOURCE_EXTRA_FILE');
        const fd=await open(absolute,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
        let raw, info;
        try {
          info=await fd.stat();
          if (!info.isFile() || info.nlink!==1 || info.size>4*1024*1024) throw new Error('HOLD_SOURCE_FILE');
          raw=await fd.readFile(); const after=await fd.stat();
          if (info.size!==after.size || info.mtimeMs!==after.mtimeMs || raw.length!==info.size) throw new Error('HOLD_SOURCE_CHANGED');
        } finally { await fd.close(); }
        total+=raw.length;
        if (total>32*1024*1024 || createHash('sha256').update(raw).digest('hex')!==declared.sha256
            || (((info.mode & 0o111)!==0) !== (declared.mode==='100755'))) throw new Error('HOLD_SOURCE_BYTES');
        entries.push(rel); tree.push({name:item.name,sort:item.name,mode:declared.mode,sha:hash('blob',raw)});
      } else throw new Error('HOLD_SOURCE_SPECIAL_FILE');
    }
    tree.sort((a,b)=>Buffer.compare(Buffer.from(a.sort),Buffer.from(b.sort)));
    return hash('tree',Buffer.concat(tree.map(e=>Buffer.concat([Buffer.from(e.mode+' '+e.name+'\0'),e.sha]))));
  }
  const observedTree=(await walk(requestedWorkdir)).toString('hex');
  if (entries.length!==expected.size || observedTree!==source.tree) throw new Error('HOLD_SOURCE_TREE_MISMATCH');
  return {commit:source.commit,tree:observedTree,manifest_sha256:digest(source),workdir:requestedWorkdir};
}

/** Docker/Podman local unit evidence; no requested fields become OS proof. */
export class ContainerObserver {
  constructor({binary,backend,run=execute}) {
    if (!['docker','podman'].includes(backend) || !path.isAbsolute(binary)) throw new Error('HOLD_LOCAL_ENGINE_REQUIRED');
    this.binary=binary;this.backend=backend;this.run=run;
  }
  async command(args) {
    const info=await lstat(this.binary);
    if (!info.isFile() || info.uid!==0 || (info.mode&0o022) || !(info.mode&0o111)) throw new Error('HOLD_ENGINE_BINARY');
    const prefix=this.backend==='docker'?['--host=unix:///var/run/docker.sock']:['--remote=false'];
    try { return (await this.run(this.binary,[...prefix,...args],{
      env:{HOME:'/home/xuanjun_dev',PATH:'/usr/bin:/bin',LANG:'C.UTF-8'},
      timeout:20000,maxBuffer:65536,encoding:'utf8'})).stdout; }
    catch { throw new Error('HOLD_UNIT_OBSERVATION_UNAVAILABLE'); }
  }
  name(unit) {
    if (!unit || unit.backend!==this.backend || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(unit.name??'')) throw new Error('HOLD_UNIT_IDENTITY');
    if (unit.id!==undefined && !/^[0-9a-f]{64}$/.test(unit.id)) throw new Error('HOLD_UNIT_IMMUTABLE_ID');
    return unit.id || unit.name;
  }
  async bind(unit,workdir,readOnlyRoots=[],sandbox='workspace-write') {
    const name=this.name(unit);
    const id=(await this.command(['inspect','--format','{{.Id}}',name])).trim();
    if (!/^[0-9a-f]{64}$/.test(id)) throw new Error('HOLD_UNIT_IMMUTABLE_ID');
    const policyFormat='{"privileged":{{.HostConfig.Privileged}},"readOnly":{{.HostConfig.ReadonlyRootfs}},"pidMode":{{json .HostConfig.PidMode}},"ipcMode":{{json .HostConfig.IpcMode}},"capDrop":{{json .HostConfig.CapDrop}},"securityOpt":{{json .HostConfig.SecurityOpt}},"network":{{json .HostConfig.NetworkMode}},"user":{{json .Config.User}}}';
    const policy=JSON.parse(await this.command(['inspect','--format',policyFormat,id]));
    if (policy.privileged!==false || policy.readOnly!==true || policy.pidMode==='host'
        || policy.ipcMode==='host' || policy.network!=='none'
        || !Array.isArray(policy.capDrop) || !policy.capDrop.some(x=>x.toUpperCase()==='ALL')
        || !Array.isArray(policy.securityOpt) || !policy.securityOpt.some(x=>x.startsWith('no-new-privileges'))
        || !/^[1-9][0-9]*(?::[0-9]+)?$/.test(policy.user??'')) throw new Error('HOLD_UNIT_CONFINEMENT');
    const mounts=JSON.parse(await this.command(['inspect','--format','{{json .Mounts}}',id]));
    const workspaceMount=Array.isArray(mounts)?mounts.find(m=>m.Type==='bind' && m.Source===workdir
      && m.RW===(sandbox==='workspace-write')):undefined;
    if (!workspaceMount || typeof workspaceMount.Destination!=='string'
        || !workspaceMount.Destination.startsWith('/')
        || workspaceMount.Destination.split('/').includes('..')
        || mounts.some(m=>m.Type!=='bind' || (m.Source!==workdir && (m.RW!==false
          || !readOnlyRoots.some(r=>m.Source===r || m.Source.startsWith(r+'/'))))))
      throw new Error('HOLD_UNIT_MOUNTS');
    const data=JSON.parse(await this.command(['inspect','--format','{{json .State}}',id]));
    if (data.Running!==true || !Number.isSafeInteger(data.Pid) || data.Pid<=0) throw new Error('HOLD_UNIT_NOT_ACTIVE');
    const rows=(await readFile('/proc/'+data.Pid+'/cgroup','utf8')).trim().split('\n').map(s=>s.split(':'));
    const row=rows.find(r=>r[0]==='0' && r[1]==='') || rows.find(r=>r[1].split(',').includes('pids'));
    if (!row || !row[2].startsWith('/') || row[2]==='/' || row[2].split('/').includes('..')) throw new Error('HOLD_UNIT_CGROUP');
    const cgroup=(row[0]==='0'?'/sys/fs/cgroup':'/sys/fs/cgroup/pids')+row[2];
    if (await realpath(cgroup)!==cgroup) throw new Error('HOLD_UNIT_CGROUP');
    return {...unit,id,cgroup,container_pid:data.Pid,workspace_source:workdir,
      workspace_destination:workspaceMount.Destination};
  }
  async attestSnapshot(unit,source) {
    if(!unit||!Number.isSafeInteger(unit.container_pid)||unit.container_pid<=0
      ||unit.workspace_source!==source?.workdir
      ||typeof unit.workspace_destination!=='string'||!unit.workspace_destination.startsWith('/')
      ||!Array.isArray(source?.files))throw new Error('HOLD_NAMESPACE_ATTESTATION');
    const namespaceRoot=path.join('/proc',String(unit.container_pid),'root');
    const chunks=[];let total=0;
    for(const entry of source.files) {
      if(!entry||typeof entry.path!=='string'||entry.path.startsWith('/')
        ||entry.path.split('/').some(p=>!p||p==='.'||p==='..'))throw new Error('HOLD_NAMESPACE_PATH');
      const absolute=path.join(namespaceRoot,unit.workspace_destination,entry.path);
      const fd=await open(absolute,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
      try {
        const info=await fd.stat();
        if(!info.isFile()||info.size>4*1024*1024)throw new Error('HOLD_NAMESPACE_FILE');
        const raw=await fd.readFile();
        total+=raw.length;
        if(total>32*1024*1024||raw.length!==info.size
          ||createHash('sha256').update(raw).digest('hex')!==entry.sha256
          ||(((info.mode&0o111)!==0)!==(entry.mode==='100755')))throw new Error('HOLD_NAMESPACE_BYTES');
        chunks.push(Buffer.from(entry.mode+' '+entry.path+' '+entry.sha256+'\n'));
      } finally {await fd.close();}
    }
    return {container_pid:unit.container_pid,workspace_destination:unit.workspace_destination,
      file_count:source.files.length,total_bytes:total,
      namespace_sha256:createHash('sha256').update(Buffer.concat(chunks)).digest('hex')};
  }
  async emptyCgroup(unit) {
    const root=unit.cgroup;
    if (!root || !root.startsWith('/sys/fs/cgroup/') || root.split('/').includes('..')) throw new Error('HOLD_UNIT_CGROUP');
    let count=0;
    async function empty(dir) {
      if (++count>1024) throw new Error('HOLD_CGROUP_LIMIT');
      try {
        if (await realpath(dir)!==dir) throw new Error('HOLD_CGROUP_SYMLINK');
        if ((await readFile(path.join(dir,'cgroup.procs'),'utf8')).trim()) return false;
        for (const item of await readdir(dir,{withFileTypes:true})) {
          if (item.isSymbolicLink()) throw new Error('HOLD_CGROUP_SYMLINK');
          if (item.isDirectory() && !await empty(path.join(dir,item.name)))return false;
        }
        return true;
      } catch(e) {if(e.code==='ENOENT')return true;throw e;}
    }
    return empty(root);
  }
  async inspect(unit) {
    const name=this.name(unit);
    const data=JSON.parse(await this.command(['inspect','--format','{{json .State}}',name]));
    if (typeof data.Running!=='boolean' || !Number.isInteger(data.Pid) || data.Pid<0) throw new Error('HOLD_UNIT_STATE');
    // Never equate a missing inspect response with an empty cgroup.
    return {active:data.Running,process_alive:data.Running || data.Pid!==0,
      descendants_exited:!data.Running && data.Pid===0 && await this.emptyCgroup(unit),unit_id:this.backend+':'+name};
  }
  async stop(unit) {
    const name=this.name(unit);
    await this.command(['stop','--time','15',name]);
    const observed=await this.inspect(unit);
    if (observed.active || observed.process_alive || !observed.descendants_exited) throw new Error('HOLD_STOP_UNCONFIRMED');
    return observed;
  }
}
