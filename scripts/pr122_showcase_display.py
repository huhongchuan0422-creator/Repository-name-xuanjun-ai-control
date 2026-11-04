"""Display metadata management within the original protected showcase namespace.

No HTTP writer, account store, task state writer, site build or release switch.
The catalog is a projection; state/history are private and stages stay upstream.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from urllib.parse import urlsplit
from scripts.pr122_showcase import ID, canonical, need

BASE = Path('/var/lib/xuanjun-showcase/delivery')
FIELDS = {'id','title','summary','preview_url','content_kind','public_consent_ref',
          'source_project_id','source_ref','listed','preview_access'}


def validate(record):
    need(type(record) is dict and FIELDS<=set(record)<=FIELDS|{'case_assets','case_snapshot_sha256'}, 'DISPLAY_FIELDS')
    need(type(record['id']) is str and ID.fullmatch(record['id']), 'DISPLAY_ID')
    for name in ('title','summary','source_ref','public_consent_ref'):
        need(type(record[name]) is str and record[name].strip(), 'DISPLAY_TEXT:'+name)
    need(type(record['listed']) is bool, 'DISPLAY_LISTED')
    need(record['content_kind'] in ('SAMPLE_DATA_PROTOTYPE','PUBLIC_PROJECT_PREVIEW'), 'DISPLAY_CONTENT_KIND')
    need(record['preview_access'] in ('UNVERIFIED','AVAILABLE','RESTRICTED'), 'DISPLAY_ACCESS_STATE')
    project=record['source_project_id']
    need(project is None or (type(project) is str and ID.fullmatch(project)), 'DISPLAY_SOURCE_PROJECT')
    url=record['preview_url']
    need(type(url) is str and not any(c.isspace() or ord(c)<32 for c in url) and '\\' not in url, 'DISPLAY_PREVIEW_URL')
    parsed=urlsplit(url)
    need(not parsed.username and not parsed.password, 'DISPLAY_URL_CREDENTIALS')
    need((parsed.scheme=='https' and bool(parsed.hostname)) or
         (url.startswith('/') and not url.startswith('//') and not parsed.scheme and not parsed.netloc), 'DISPLAY_PREVIEW_URL')
    assets=record.get('case_assets',[])
    if assets:
        import re
        need(type(record.get('case_snapshot_sha256')) is str and re.fullmatch('[a-f0-9]{64}',record['case_snapshot_sha256']), 'DISPLAY_CASE_SNAPSHOT')
    need(type(assets) is list, 'DISPLAY_CASE_ASSETS')
    for asset in assets:
        need(type(asset) is dict and set(asset)=={'kind','value','public_consent_ref'} and asset['kind'] in ('image','video','description','link'), 'DISPLAY_CASE_ASSET')
        need(type(asset['public_consent_ref']) is str and asset['public_consent_ref'].strip() and type(asset['value']) is str and asset['value'].strip(), 'DISPLAY_CASE_ASSET_CONSENT')
        if asset['kind']!='description':
            validate({**{key:record[key] for key in FIELDS},'preview_url':asset['value']})
    return record


def trusted(path, *, directory=False, public=False):
    info=path.lstat()
    need(not stat.S_ISLNK(info.st_mode) and info.st_uid==0 and (not info.st_mode&0o022 or (directory and bool(info.st_mode&stat.S_ISVTX))), 'DISPLAY_PATH_CUSTODY')
    need(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode), 'DISPLAY_PATH_TYPE')
    if not directory:
        need(info.st_nlink==1, 'DISPLAY_PATH_LINKS')
        need(stat.S_IMODE(info.st_mode)==(0o644 if public else 0o600), 'DISPLAY_PATH_MODE')
    return info


def load():
    path=BASE/'state.json'
    if not os.path.lexists(path):return {'schema':1,'revision':0,'records':{},'history':[]}
    trusted(path)
    with path.open() as stream:value=json.load(stream)
    need(type(value) is dict and set(value)=={'schema','revision','records','history'} and value['schema']==1
         and type(value['revision']) is int and value['revision']>=0 and type(value['records']) is dict
         and type(value['history']) is list, 'DISPLAY_STATE')
    for key,record in value['records'].items():need(validate(record)['id']==key, 'DISPLAY_STATE_KEY')
    replay={}
    need(len(value['history'])==value['revision'], 'DISPLAY_HISTORY_REVISION')
    for revision,row in enumerate(value['history'],1):
        need(type(row) is dict and set(row)=={'revision','action','id','record','operator_uid'} and row['revision']==revision and row['action'] in ('put','unlist') and row['id']==validate(row['record'])['id'] and row['operator_uid']==0, 'DISPLAY_HISTORY')
        replay[row['id']]=row['record']
    need(replay==value['records'], 'DISPLAY_HISTORY_BINDING')
    return value


def public_catalog(state):
    return {'schema':1,'revision':state['revision'],'source':'SHOWCASE_CONTROLLED_DISPLAY_METADATA',
            'stage_source':'/showcase/catalog.json','unlisted_project_ids':[r['source_project_id'] for r in state['records'].values() if not r['listed'] and r['source_project_id']], 'projects':[dict(record) for _,record in sorted(state['records'].items()) if record['listed']]}


def atomic(path, data, mode):
    if os.path.lexists(path):trusted(path, public=mode==0o644)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'-',dir=BASE)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        directory=os.open(BASE,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(name):os.unlink(name)


def manage(action, expected_revision=None, record=None, identifier=None):
    need(os.geteuid()==0, 'DISPLAY_PROTECTED_OPERATOR_REQUIRED')
    # Original showcase namespace only. Tests replace BASE with a private fixture.
    for parent in [BASE.parent,*BASE.parent.parents]:trusted(parent,directory=True)
    if action=='read':
        if not os.path.lexists(BASE):return {'schema':1,'revision':0,'records':{},'history':[],'projection_state':'ABSENT'}
        trusted(BASE,directory=True);state=load();catalog=BASE/'catalog.json'
        if os.path.lexists(catalog):trusted(catalog,public=True)
        return {**state,'projection_state':'CURRENT' if os.path.lexists(catalog) and catalog.read_bytes()==canonical(public_catalog(state)) else 'PENDING'}
    if not BASE.exists():BASE.mkdir(mode=0o755)
    trusted(BASE,directory=True)
    lock=BASE/'display.lock'
    fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        named=trusted(lock);opened=os.fstat(fd)
        need((named.st_dev,named.st_ino)==(opened.st_dev,opened.st_ino), 'DISPLAY_LOCK_REPLACED')
        state=load()
        base_identity=BASE.stat()
        def fence():
            current=trusted(lock);directory=trusted(BASE,directory=True)
            need((current.st_dev,current.st_ino)==(opened.st_dev,opened.st_ino) and (directory.st_dev,directory.st_ino)==(base_identity.st_dev,base_identity.st_ino), 'DISPLAY_LOCK_OR_DIRECTORY_REPLACED')
        catalog=BASE/'catalog.json'
        if os.path.lexists(catalog):
            trusted(catalog,public=True)
            actual=catalog.read_bytes()
            if actual!=canonical(public_catalog(state)) and action not in ('read','sync'):
                raise RuntimeError('DISPLAY_PROJECTION_DRIFT_QUERY_STATE_AND_SYNC')
            if actual!=canonical(public_catalog(state)):
                historical={'schema':1,'revision':0,'records':{},'history':[]}
                known={canonical(public_catalog(historical))}
                for row in state['history']:
                    historical['revision']=row['revision']
                    historical['records'][row['id']]=row['record']
                    known.add(canonical(public_catalog(historical)))
                need(actual in known, 'DISPLAY_UNKNOWN_EXISTING_CATALOG')
        if action=='read':return {**state,'projection_state':'CURRENT' if os.path.lexists(catalog) and catalog.read_bytes()==canonical(public_catalog(state)) else 'PENDING'}
        need(type(expected_revision) is int and expected_revision==state['revision'], 'DISPLAY_REVISION_CONFLICT')
        if action=='put':
            validate(record);state['records'][record['id']]=dict(record)
        elif action=='unlist':
            need(identifier in state['records'], 'DISPLAY_NOT_FOUND')
            state['records'][identifier]={**state['records'][identifier],'listed':False}
        else:need(action=='sync', 'DISPLAY_ACTION')
        if action!='sync':
            state['revision']+=1
            selected=record['id'] if action=='put' else identifier
            state['history'].append({'revision':state['revision'],'action':action,'id':selected,
                                     'record':dict(state['records'][selected]),'operator_uid':os.geteuid()})
            fence();atomic(BASE/'state.json',canonical(state),0o600)
        try:
            fence();atomic(BASE/'catalog.json',canonical(public_catalog(state)),0o644)
        except Exception as error:
            raise RuntimeError('DISPLAY_PROJECTION_PENDING_QUERY_STATE_AND_SYNC') from error
        return {'state':'DISPLAY_UPDATED','revision':state['revision'],'listed':len(public_catalog(state)['projects'])}
    finally:os.close(fd)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('read','put','unlist','sync'))
    parser.add_argument('--expected-revision',type=int);parser.add_argument('--record',type=Path);parser.add_argument('--id')
    args=parser.parse_args(argv)
    record=json.loads(args.record.read_bytes()) if args.record else None
    print(json.dumps(manage(args.action,args.expected_revision,record,args.id),ensure_ascii=False))

if __name__=='__main__':main()
