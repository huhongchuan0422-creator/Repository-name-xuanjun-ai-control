"""Pinned formal runtime preflight; legacy migration fixtures are not formal."""
import argparse
import json
import platform
import sqlite3
import sys
import cryptography

REQUIRED_PYTHON=(3,11,0)
REQUIRED_SQLITE=(3,40,0)
REQUIRED_CRYPTOGRAPHY='42.0.8'

def _version(value): return tuple(int(x) for x in value.split('.')[:3])

def preflight():
    facts={'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,
           'cryptography':cryptography.__version__}
    errors=[]
    if sys.version_info[:3] < REQUIRED_PYTHON: errors.append('PYTHON_3_11_REQUIRED')
    if _version(sqlite3.sqlite_version) < REQUIRED_SQLITE: errors.append('SQLITE_3_40_REQUIRED')
    if cryptography.__version__ != REQUIRED_CRYPTOGRAPHY: errors.append('CRYPTOGRAPHY_PIN_MISMATCH')
    return {'ok':not errors,'facts':facts,'errors':errors,
            'requirements':{'python':'3.11+','sqlite':'3.40+','cryptography':REQUIRED_CRYPTOGRAPHY}}

def main(argv=None):
    parser=argparse.ArgumentParser(); parser.parse_args(argv)
    result=preflight(); print(json.dumps(result,sort_keys=True))
    return 0 if result['ok'] else 69

if __name__=='__main__': raise SystemExit(main())
