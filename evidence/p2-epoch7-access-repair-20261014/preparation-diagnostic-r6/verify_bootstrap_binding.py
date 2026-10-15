"""Local static pin-only verification. Never executes the Owner command."""
import argparse,hashlib,json,pathlib,re,sys
ROOT=pathlib.Path(__file__).resolve().parent

def expected(commit):
    if type(commit) is not str or not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('PUBLICATION_COMMIT')
    source=(ROOT/'diagnose_preparation.py').read_bytes();raw=(ROOT/'OWNER_DIAGNOSTIC_UNBOUND.txt').read_bytes()
    if not 0<len(source)<=65536 or len(raw)>16384:raise ValueError('SOURCE_BOUND')
    changes={b'DELIVERY_COMMIT=None':('DELIVERY_COMMIT='+repr(commit)).encode('ascii'),
        b'DELIVERY_SHA256=None':('DELIVERY_SHA256='+repr(hashlib.sha256(source).hexdigest())).encode('ascii'),
        b'DELIVERY_BYTES=None':('DELIVERY_BYTES='+str(len(source))).encode('ascii')}
    for before,after in changes.items():
        if raw.count(before)!=1:raise ValueError('EXACT_THREE_PIN_FIELDS')
        raw=raw.replace(before,after)
    return raw

def verify(commit,raw):
    if type(raw) is not bytes or len(raw)>16384 or raw!=expected(commit):raise ValueError('BOUND_BOOTSTRAP_EXACT_DELTA')
    return {'state':'PASS','commit':commit,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
        'delta':'EXACT_THREE_PUBLICATION_PINS','host_execution':'NOT_RUN'}

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--commit',required=True);parser.add_argument('--bound-file',required=True)
    args=parser.parse_args(argv)
    try:
        with open(args.bound_file,'rb') as stream:raw=stream.read(16385)
        value=verify(args.commit,raw)
    except Exception:value={'state':'FAIL','failure_code':'BOUND_BOOTSTRAP_VERIFICATION_FAILED','host_execution':'NOT_RUN'}
    print(json.dumps(value,sort_keys=True));return 0 if value['state']=='PASS' else 2

if __name__=='__main__':sys.exit(main())
