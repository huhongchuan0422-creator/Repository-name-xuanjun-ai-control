"""Build-only rebind of the exact previously approved fixed-channel source.
Never imports/executes candidate Python or writes domestic protected paths.
Generated channel code still exposes only inspect/plan/apply/rollback.
Owner installation and rollback are a separate reviewed transaction.
"""
import ast
import io
import json
from pathlib import Path
import tarfile
from scripts.pr122_customer_core import canonical,digest,Denied

ORIGINAL_SHA='0804e33edac6ad07a711456c0c15708266b2ad8a75c4cb3bdc5964a9b79a96bd'

def bind(original,archive,wheel_folder=None):
    if digest(original)!=ORIGINAL_SHA:raise Denied('EXACT_ORIGINAL_CHANNEL_REQUIRED')
    if len(archive)>10000000:raise Denied('CANDIDATE_ARCHIVE_LIMIT')
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as t:
        ms=t.getmembers()
        if not 1<len(ms)<=100 or len({m.name for m in ms})!=len(ms) or any(not m.isfile() or not m.name.startswith('customer-center/') or '..' in Path(m.name).parts or m.size>8000000 for m in ms):raise Denied('CANDIDATE_MEMBERS')
        raw=t.extractfile('customer-center/CUSTOMER_MANIFEST.json').read();manifest=json.loads(raw)
        files=manifest['files']
        if len(files)!=len(ms)-1 or {m.name for m in ms}!={'customer-center/CUSTOMER_MANIFEST.json',*['customer-center/'+x['path'] for x in files]}:raise Denied('CANDIDATE_MANIFEST_SET')
        for item in files:
            if Path(item['path']).is_absolute() or '..' in Path(item['path']).parts:raise Denied('CANDIDATE_PATH')
            b=t.extractfile('customer-center/'+item['path']).read()
            if len(b)!=item['size'] or digest(b)!=item['sha256']:raise Denied('CANDIDATE_FILE_HASH')
    import re
    if not all(re.fullmatch('[0-9a-f]{40}',manifest[k]) for k in ('source_commit','source_tree')):raise Denied('CANDIDATE_GIT_IDENTITY')
    tree=ast.parse(original);replacements={'TAR_SHA':digest(archive),'MANIFEST_SHA':digest(raw),'SOURCE':manifest['source_commit']};seen=set();counts=[]
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in replacements:
            key=node.targets[0].id;seen.add(key);node.value=ast.Constant(replacements[key])
        if isinstance(node,ast.FunctionDef) and node.name=='files_from_tar':
            for sub in ast.walk(node):
                if isinstance(sub,ast.Constant) and type(sub.value) is int and sub.value in (33,34):
                    counts.append(sub.value);sub.value=len(ms) if sub.value==34 else len(files)
    if seen!=set(replacements) or counts.count(34)!=2 or counts.count(33)!=1:raise Denied('ORIGINAL_PIN_AST_CONTRACT')
    from scripts.pr122_customer_runtime import wheel_files
    vendors=wheel_files(wheel_folder)
    expected={p:digest(b) for p,b in sorted(vendors.items())}
    guard_source="""def verify_isolated_runtime():
    site=Path('/usr/local/lib/xuanjun-customer-runtime/venv/lib/python3.11/site-packages')
    secure(site,directory=True)
    expected=EXPECTED_VENDOR_FILES
    actual=set()
    for folder,dirs,names in os.walk(site,followlinks=False):
        secure(folder,directory=True)
        for name in dirs:secure(Path(folder)/name,directory=True)
        for name in names:
            path=Path(folder)/name
            for parent in path.parents:secure(parent,directory=True)
            st=path.lstat()
            need(st.st_uid==0 and stat.S_ISREG(st.st_mode) and st.st_nlink==1 and not st.st_mode & 0o022 and st.st_size<=20000000)
            relative=path.relative_to(site).as_posix()
            need(relative in expected and sha(path.read_bytes())==expected[relative])
            actual.add(relative)
    need(actual==set(expected))
    sys.path.insert(0,str(site))
"""
    guard=ast.parse(guard_source).body[0]
    expected_node=next(n for n in ast.walk(guard) if isinstance(n,ast.Name) and n.id=='EXPECTED_VENDOR_FILES')
    class Fill(ast.NodeTransformer):
        def visit_Name(self,node):return ast.parse(repr(expected),mode='eval').body if node is expected_node else node
    guard=Fill().visit(guard)
    dispatch=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='dispatch')
    import_call=next(i for i,n in enumerate(dispatch.body) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and n.value.func.attr=='insert')
    dispatch.body.insert(import_call,ast.Expr(ast.Call(ast.Name('verify_isolated_runtime',ast.Load()),[],[])))
    tree.body.insert(0,guard)
    code=(ast.unparse(ast.fix_missing_locations(tree))+'\n').encode();compile(code,'approved-channel-candidate','exec')
    return code,{'state':'REBIND_CANDIDATE_ONLY','original_channel_sha256':ORIGINAL_SHA,'channel_sha256':digest(code),'source_commit':manifest['source_commit'],'source_tree':manifest['source_tree'],'tar_sha256':digest(archive),'manifest_sha256':digest(raw),'archive_members':len(ms),'bound_files':len(files),'vendor_file_count':len(expected),'vendor_scope_sha256':digest(canonical(expected)),'runtime_site':'/usr/local/lib/xuanjun-customer-runtime/venv/lib/python3.11/site-packages','actions':['inspect','plan','apply','rollback'],'sudoers_changed':False,'root_execution':'NOT_RUN','owner_install':'NOT_AUTHORIZED','customer_install':'HOLD'}
