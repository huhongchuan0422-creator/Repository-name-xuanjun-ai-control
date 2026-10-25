"""Foreground TEST_ONLY model scheduler loop; restart-safe, no daemon install."""
from __future__ import print_function

import argparse
import json
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from model_orchestration import ModelControl, ModelScheduler, load_master_key
from reusable_task_gateway import GatewayKernel, TestTenantAuthority
from task_supervisor import Supervisor


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',required=True)
    parser.add_argument('--test-authority-key',required=True)
    parser.add_argument('--model-master-key-file',required=True)
    parser.add_argument('--tenant',required=True)
    parser.add_argument('--principal',default='scheduler-runtime')
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--poll-seconds',type=float,default=1.0)
    args=parser.parse_args(argv)
    if not os.path.isfile(args.db):raise ValueError('CANONICAL_SQLITE_REQUIRED')
    supervisor=Supervisor(args.db)
    authority=TestTenantAuthority(args.test_authority_key.encode('utf-8'))
    gateway=GatewayKernel(supervisor,authority)
    context=authority.issue(args.tenant,args.principal)
    control=ModelControl(gateway,context,load_master_key(args.model_master_key_file))
    scheduler=ModelScheduler(control)
    stopping=[False]
    def stop(_signum,_frame):stopping[0]=True
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    print(json.dumps({'state':'STARTED','mode':'TEST_ONLY',
      'production_dispatch':'NOT_IMPLEMENTED'},sort_keys=True),flush=True)
    try:
        while not stopping[0]:
            result=scheduler.run_once();print(json.dumps(result,sort_keys=True),flush=True)
            if args.once:break
            # All outcomes are bounded by the configured poll interval.  In
            # particular QUEUED_LIMIT/CIRCUIT_OPEN must not busy-loop.
            time.sleep(max(.1,args.poll_seconds))
    finally:
        supervisor.close()
        print(json.dumps({'state':'STOPPED','mode':'TEST_ONLY'},sort_keys=True),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
