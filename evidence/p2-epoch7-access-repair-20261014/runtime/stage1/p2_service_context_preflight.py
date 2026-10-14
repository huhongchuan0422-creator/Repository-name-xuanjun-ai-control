#!/usr/bin/python3
from __future__ import print_function
import argparse,json,os,pwd,sys
from development_service import load_config
from native_pipeline_runtime import load_reviewed_controller

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--native-controller',required=True)
    parser.add_argument('--native-controller-sha256',required=True)
    args=parser.parse_args(argv)
    expected=pwd.getpwnam('xuanjun-dispatcher').pw_uid
    if os.geteuid()!=expected: raise SystemExit('HOLD_DISPATCHER_UID')
    config=load_config(args.config)
    runtime=load_reviewed_controller(args.native_controller,args.native_controller_sha256,config)
    result=runtime.preflight(config)
    if not isinstance(result,dict) or result.get('ready') is not True:
        raise SystemExit('HOLD_PLUGIN_PREFLIGHT')
    print(json.dumps({'state':'P2_SERVICE_CONTEXT_PREFLIGHT_PASS','model_calls':0,
                      'launch_performed':False,'dispatcher_uid':expected},
                     sort_keys=True,separators=(',',':')))
    return 0
if __name__=='__main__': raise SystemExit(main())
