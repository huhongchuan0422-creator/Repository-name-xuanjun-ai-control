"""Source-only B5 preparation. Never imports a loader or claims CP11 success."""
import argparse,gzip,hashlib,io,json,os,stat,sys,tarfile
from pathlib import Path

SOURCE='ee183c19d1a3a05e99aedb98ecda71884d4d26b3'
PLUGIN_PATH='evidence/p2-epoch7-access-repair-20261014/runtime/plugins/p2-native-controller'
PINS={'canonical.mjs': 'f3a40e5f90b3abfcd81bc3c5c408011995c3ab32cda72f565f124576d3d0706a', 'controller.mjs': 'a0513740a5c8f1c99bf734494dab14baa8b5b2688c6f8ebdeea7e2c6cb2825b6', 'host.mjs': '3c9f5d2b4cce041ab6e7bc9a73707b467b30f5e884a450c4bd9b69a4b9c61a46', 'index.mjs': 'c1867c271bc48c6f38be92d29daf2fad5addd457db2468d01f1ef3ae14467286', 'ledger.mjs': 'cd5aed8ef78bcf0e95ee3b35102a7c228078d7425d53d5cee9eb91965bf0fa24', 'openclaw.plugin.json': '14916ef983942a57ffe6afe5e6bf1bdf8415d2243e2fd23dfed576b62b2d6fb5', 'package.json': '002645bf81d143cebeb08aab1b0be2d519b8ebc834f398441d8d2450310e2115', 'plugin.mjs': '1c0af2ce5723a5bfe8a025bb150e26a92e21be2e02b2da054e05456a2ac87bfc', 'sdk-layout.mjs': 'fa747f7bf664c5311ecbddc824387c10b3ac814a004bda0ee04364cb7938ed1e', 'strict-json.mjs': 'ce10a780c983a424f11cb0de37c748eda811efd3fa317b9445ab44bc1dac82fd', 'workspace.mjs': 'ca4b50aa4489087289b8726a10b3751c95f99314043eb5e8e7ddf66fbb1d8311'}
NODE='24.21.0'
OPENCLAW='2026.9.9'
UPSTREAM='bcfc88812a35243893585dbeca87ca41b48272ca'
SDK_ROOT='/home/xuanjun_dev/.openclaw/tools/node-v24.21.0/lib/node_modules/openclaw'


def need(ok,code):
    if not ok:raise ValueError(code)


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
def sha(raw):return hashlib.sha256(raw).hexdigest()


def read(path):
    path=Path(path);need(path.is_absolute() and '..' not in path.parts,'B5_ABSOLUTE_PATH')
    parent=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for name in path.parts[1:-1]:
            child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent)
            os.close(parent);parent=child
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
        with os.fdopen(fd,'rb') as stream:
            before=os.fstat(stream.fileno());need(stat.S_ISREG(before.st_mode) and before.st_size<=1048576,'B5_SOURCE_REGULAR_BOUND')
            raw=stream.read(1048577);after=os.fstat(stream.fileno())
            keys=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
            need(all(getattr(before,k)==getattr(after,k) for k in keys) and len(raw)==before.st_size,'B5_SOURCE_CHANGED')
            return raw
    finally:os.close(parent)


def plugin_files(root):
    root=Path(root);need(str(root.resolve())==str(root),'B5_SOURCE_CANONICAL')
    need({p.name for p in root.iterdir()}==set(PINS),'B5_SOURCE_EXACT_MEMBERS')
    files={}
    for name,pin in sorted(PINS.items()):
        raw=read(root/name);need(sha(raw)==pin,'B5_SOURCE_SHA:'+name);files[name]=raw
    need(json.loads(files['package.json'])['openclaw']['extensions']==['./plugin.mjs'],'B5_ORIGINAL_ENTRY')
    return files


def node_engine_compatible(version):
    try:parts=tuple(int(x) for x in version.lstrip('v').split('.'))
    except (ValueError,AttributeError):return False
    return len(parts)==3 and ((24,16,0)<=parts<(25,0,0) or parts>=(26,1,0))


def capabilities():
    return {'schema':1,'scope':'ISOLATED_TEST_ONLY','status':'PREPARED_WITH_UNAVAILABLE_CAPABILITIES',
      'source_commit':SOURCE,'plugin_id':'xuanjun-p2-native-controller','plugin_version':'0.1.0',
      'required_node':NODE,'required_openclaw':OPENCLAW,'upstream_commit':UPSTREAM,
      'node_engine_range':'>=24.16.0 <25 || >=26.1.0','node_binary_sha256':'UNKNOWN',
      'sdk_root':SDK_ROOT,'sdk_package_json_sha256':'214e9551a924a9ced04ecf38c7ed8f6bff8beeab33431db12ed6250eaa959e95',
      'npm_tar_sha256':'a46df5fc5e4d73837d5b3eeebc286e64a85dffc429c30f3a07f6398e2a9423f7',
      'historical_sdk_files':{
         SDK_ROOT+'/dist/loader-runtime-load-DpgEqnzx.mjs':'3c30c5d43fb3cd19525853bb6b756cf45cfd05f5da32a732dc129b85cb309787',
         SDK_ROOT+'/dist/context-DyPstb2Q.mjs':'db7fc7539455da0c564d4ded0d04da1c764a46903d1632489b8bd04641098320'},
      'evidence_scope':'HISTORICAL_SOURCE_AND_METADATA_NOT_CURRENT_UK_MEASUREMENT',
      'real_loader':{'state':'UNAVAILABLE','reason':'FULL_COMPILED_LOADER_DEPENDENCIES_AND_EXACT_EXPORT_NOT_AVAILABLE_IN_DELIVERY',
        'upstream_facade':'src/plugins/loader.ts:loadPluginRegistryHandle',
        'options':{'activate':False,'runtimeSideEffects':False},'packaged_export':'UNKNOWN'},
      'safe_function':{'state':'UNAVAILABLE','reason':'NO_ORIGINAL_POSITIVE_GATEWAY_METHOD_WITHOUT_LEDGER_OR_OWNER_EFFECTS',
        'methods':{'xuanjun.execution.start':['admit','launch'],
                   'xuanjun.execution.inspect':['preflight','inspect','report','stop'],
                   'xuanjun.owner.delivery':['cycle']}},
      'forbidden_calls':['admit','launch','owner_delivery_cycle','model','canonical_ledger_write'],
      'cp11_acceptance':'NOT_EXECUTED','actual_registration':'NOT_EXECUTED',
      'authenticated_rpc':'NOT_EXECUTED','model_calls':0,'installation_executed':False}


def archive(files):
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as tar:
        for name,raw in sorted(files.items()):
            item=tarfile.TarInfo(name);item.size=len(raw);item.mode=0o444;item.mtime=0
            tar.addfile(item,io.BytesIO(raw))
    compressed=io.BytesIO()
    with gzip.GzipFile(fileobj=compressed,mode='wb',mtime=0,filename='') as stream:stream.write(buffer.getvalue())
    return compressed.getvalue()


def publish(path,raw):
    if os.path.lexists(str(path)):
        need(read(path)==raw,'B5_IMMUTABLE_INPUT_CONFLICT');return
    fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
    fd=os.open(str(path.parent),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def prepare(plugin,output):
    files=plugin_files(plugin);output=Path(output)
    if not os.path.lexists(str(output)):output.mkdir(mode=0o700)
    s=os.lstat(str(output));need(stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid()
        and stat.S_IMODE(s.st_mode)==0o700,'B5_OUTPUT_PRIVATE')
    data=archive(files);version=sha(encode(PINS))[:16]
    filename='p2-native-controller-0.1.0-'+version+'.tar.gz'
    manifest={'schema':1,'scope':'ISOLATED_TEST_ONLY','source_commit':SOURCE,'version_id':version,
      'package':filename,'sha256':sha(data),'bytes':len(data),
      'files':{name:{'sha256':sha(raw),'bytes':len(raw),'mode':0o444} for name,raw in files.items()},
      'status':'SOURCE_PACKAGE_ONLY_NOT_LOADED','cp11_acceptance':'NOT_EXECUTED'}
    publish(output/filename,data);publish(output/'MANIFEST.json',encode(manifest))
    publish(output/'CAPABILITIES.json',encode(capabilities()))
    return manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('report','prepare'))
    parser.add_argument('--output');args=parser.parse_args()
    if args.action=='report':print(json.dumps(capabilities(),sort_keys=True));return 0
    need(args.output is not None,'B5_OUTPUT_REQUIRED')
    repo=Path(__file__).resolve().parents[2]
    print(json.dumps(prepare(repo/PLUGIN_PATH,Path(args.output).absolute()),sort_keys=True));return 0


if __name__=='__main__':sys.exit(main())
