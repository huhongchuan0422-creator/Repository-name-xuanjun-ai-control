"""Offline byte binding only. Never import/evaluate the SDK or extract to disk."""
import hashlib,io,json,os,re,stat,sys,tarfile,types
from pathlib import Path
TAR_SHA='a79ef7c040f46a72a0d7286be9ee805350488c5411dee4f481b5192eb0440475'
HELPER_SHA='90684e11592552336663f1a3c53b70787af79e48ee3819c6e8a655d3f9936980'
LOADER='dist/loader-runtime-load-DpgEqnzx.mjs'
def require(ok,code):
    if not ok:raise ValueError(code)
def static_mapping(source):
    # Exact named mapping, never try alternate/default exports. This is source
    # declaration evidence only; a future real namespace must still contain t:function.
    exports=list(re.finditer(r'\bexport\s*\{([^{}]{0,16384})\}',source))
    require(exports,'HOLD_EXPORT_DECLARATION')
    pairs=[p.strip() for p in exports[-1].group(1).split(',') if p.strip()]
    matches=[p for p in pairs if re.match(r'^acquirePluginRegistryForInspection(?:\s|$)',p)]
    require(len(matches)==1 and re.fullmatch(r'acquirePluginRegistryForInspection\s+as\s+t',matches[0]),'HOLD_FIXED_T_EXPORT_MAPPING')
    return dict(canonical='acquirePluginRegistryForInspection',compiled='t',namespace_type='NOT_EXECUTED')
def direct_references(source):
    # Deliberately lexical, not a parser/closure claim. Dynamic expressions and
    # package resolution/resources/native dependencies remain separate HOLDs.
    refs=set(re.findall(r'(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s*)[\x22\x27]([^\x22\x27\r\n]{1,1024})[\x22\x27]',source))
    require(len(refs)<=1000,'HOLD_REFERENCE_BOUND')
    return sorted(refs)
def analyze(files):
    package=json.loads(files['package.json'].decode('utf8'))
    require(package.get('version')=='2026.9.9','HOLD_PACKAGE_VERSION')
    loader=files[LOADER].decode('utf8');context=files['dist/context-DyPstb2Q.mjs'].decode('utf8')
    refs={LOADER:direct_references(loader),'dist/context-DyPstb2Q.mjs':direct_references(context)}
    return dict(scope='OFFLINE_SOURCE_ONLY',mapping=static_mapping(loader),direct_lexical_references=refs,
        reference_analysis='LEXICAL_ONLY_NOT_AST_OR_TRANSITIVE_CLOSURE',dependency_closure='UNKNOWN',
        real_loader='NOT_EXECUTED',authenticated_dispatch='NOT_EXECUTED',cp11='NOT_EXECUTED')
def read_bound_archive(path):
    helper=Path(__file__).with_name('p2_b5_three_files.py')
    with helper.open('rb') as stream:raw=stream.read(65537)
    require(len(raw)<=65536,'HOLD_EXISTING_READER_BOUND')
    require(hashlib.sha256(raw).hexdigest()==HELPER_SHA,'HOLD_EXISTING_READER_SHA')
    m=types.ModuleType('b5_existing_bounded_reader');m.__file__=str(helper);exec(compile(raw,str(helper),'exec'),m.__dict__)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=m.identity(os.fstat(fd));require(stat.S_ISREG(os.fstat(fd).st_mode) and os.fstat(fd).st_nlink==1,'HOLD_ARCHIVE_TYPE');require(os.fstat(fd).st_size==430080,'HOLD_THREE_FILE_TAR_SIZE')
        require(m.hash_fd(fd,430080)==TAR_SHA,'HOLD_THREE_FILE_TAR_SHA')
        require(m.verify_small(fd,m.PINS)==419045,'HOLD_THREE_FILE_CONTENTS')
        os.lseek(fd,0,os.SEEK_SET);archive=os.read(fd,430081);require(len(archive)==430080,'HOLD_SHORT_READ')
        require(m.identity(os.fstat(fd))==before and hashlib.sha256(archive).hexdigest()==TAR_SHA,'HOLD_INPUT_CHANGED')
        # Only after strict existing USTAR verification and fixed whole-byte SHA.
        with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as tar:
            files={name:tar.extractfile(name).read() for name in m.PINS['targets']}
        for name,(size,pin) in m.PINS['targets'].items():require(len(files[name])==size and hashlib.sha256(files[name]).hexdigest()==pin,'HOLD_MEMBER_PIN')
        return files
    finally:os.close(fd)
def main():
    try:
        require(len(sys.argv)==2,'HOLD_ONE_EXISTING_ARCHIVE_REQUIRED')
        result=analyze(read_bound_archive(sys.argv[1]));result['source_archive_sha256']=TAR_SHA
        raw=json.dumps(result,sort_keys=True);require(len(raw.encode('utf8'))<=262144,'HOLD_OUTPUT_BOUND');print(raw);return 0
    except Exception as exc:
        code=str(exc) if type(exc) is ValueError and re.fullmatch('HOLD_[A-Z_]+',str(exc)) else 'HOLD_INPUT_OR_ANALYSIS_UNKNOWN'
        print(json.dumps(dict(state='HOLD',reason=code,real_loader='NOT_EXECUTED',cp11='NOT_EXECUTED')));return 2
if __name__=='__main__':sys.exit(main())
