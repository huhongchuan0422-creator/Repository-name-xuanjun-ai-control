"""Prepared ONLY: three fixed-object reasons; no complete observation rerun.

No new credential, peer identity, endpoint or Docker mutation. Error text is
never relayed. The private probe intentionally keeps root/no private IP header.
"""
import errno
import json
import os
import signal
import sys
from scripts import community_preview_preupdate_observe as base

CODES={'EXACT_CONTAINER_STATE_REQUIRED','CONTAINER_SCOPE_CHANGED','CONTAINER_ISOLATION_CHANGED',
 'TMPFS_CHANGED','LOG_LIMIT_CHANGED','EXACT_EXISTING_MOUNTS_REQUIRED','EXPECTED_REFERENCE_TYPE',
 'DIRECTORY_REQUIRED','REGULAR_FILE_OR_DIRECTORY_REQUIRED','FIXED_ABSOLUTE_PATH_REQUIRED',
 'BODY_READ_OUT_OF_SCOPE','DUPLICATE_JSON_KEY','NONFINITE_JSON','COMMAND_TIMEOUT','COMMAND_OUTPUT_LIMIT','COMMAND_REJECTED','INSPECT_SHAPE_UNKNOWN',
 'CURRENT_INSPECT_SHAPE','CURRENT_RESOURCE_TYPE','CURRENT_RUNNING_UNKNOWN','CURRENT_ISOLATION_TYPE',
 'NO_NEW_PORT_DEVICE_CAPABILITY','CURRENT_IDS','CURRENT_SHAPE','IMAGE_BINDING','REPO_DIGEST_SHAPE',
 'REPO_DIGEST_TYPE','FILE_CHANGED','PATH_REPLACED','PARENT_OR_PATH_CHANGED','UNPROTECTED_PATH',
 'REFERENCE_HARDLINK_DENIED','BODY_FILE_BOUNDARY','FILE_CHANGED_OR_OVERSIZED','HEALTH_FRAME','HEALTH_OBJECT',
 'CURRENT_CONTAINER_CHANGED','FIXED_NAME_REBOUND','HEALTH_SIZE','HEALTH_RESPONSE'}
PRIVATE_DIAGNOSTIC=base.approved.PRIVATE_PROBE.replace("if r.status not in (200,503) or", "if not 100<=r.status<=599 or")


def reason(error):
    # Exact enums only. No arbitrary str(error), stderr, nested HTTP body or Env.
    value=error.args[0] if error.args else None
    if type(value) is str and value in CODES:return value
    if isinstance(error,FileNotFoundError):return 'FIXED_FILE_NOT_FOUND'
    if isinstance(error,PermissionError):return 'OS_PERMISSION_DENIED'
    if isinstance(error,OSError):return 'OS_ERROR'
    if isinstance(error,(ValueError,UnicodeError)):return 'STRUCTURE_OR_JSON_INVALID'
    return 'UNCLASSIFIED_UNKNOWN'


class ObservationFault(Exception):
    def __init__(self,stage,code):self.stage=stage;self.code=code


def one(stage,call):
    try:return dict(stage=stage,status='OBSERVED',value=call())
    except base.v.TotalDeadline:raise
    except ObservationFault as e:return dict(stage=e.stage,status='HOLD_UNKNOWN',reason=e.code)
    except Exception as e:return dict(stage=stage,status='HOLD_UNKNOWN',reason=reason(e))


def projected_current():
    original=base.v.capture
    def tracked(args,**kwargs):
        stage='CURRENT_FIXED_READ'
        if args[3:5]==['image','inspect']:stage='CURRENT_IMAGE_INSPECT'
        elif args[3:5]==['container','inspect']:
            stage='CURRENT_ISOLATION_INSPECT' if '.Mounts' in args[-2] else 'CURRENT_NAME_ID_LOOKUP'
        try:return original(args,**kwargs)
        except base.v.TotalDeadline:raise
        except Exception as error:raise ObservationFault(stage,reason(error)) from None
    base.v.capture=tracked
    try:return base.current_projection()
    finally:base.v.capture=original


def current_recheck():
    first=one('CURRENT_INITIAL_FIXED_BINDING',projected_current)
    if first['status']!='OBSERVED':return first
    second=one('CURRENT_SECOND_FIXED_BINDING',projected_current)
    if second['status']!='OBSERVED':return second
    a=first['value'];b=second['value']
    changed=[k for k in a if k!='observed_at' and a[k]!=b[k]]
    # Only bounded known field names, not private differing values.
    return dict(status='HOLD_CHANGED' if changed else 'OBSERVED',stage='CURRENT_COMPARE',
        changed_fields=changed,container_id=b['container_id'],image_id=b['image_id'],
        oci_revision=b['oci_revision'],snapshot_atomic=False)


def private_health():
    raw=base.v.capture(['/usr/bin/python3','-I','-B','-S','-c',PRIVATE_DIAGNOSTIC],timeout=10,budget=10000)
    f=base.v.exact_json(raw)
    if (type(f) is not dict or set(f)!={'http_status','body_hex'} or type(f['http_status']) is not int
        or not 100<=f['http_status']<=599 or type(f['body_hex']) is not str or len(f['body_hex'])>8192
        or base.re.fullmatch('[0-9a-f]*',f['body_hex']) is None):raise base.v.Hold('HEALTH_FRAME')
    body=base.v.exact_json(bytes.fromhex(f['body_hex']).decode('utf-8'))
    if type(body) is not dict:raise base.v.Hold('HEALTH_OBJECT')
    code=body.get('error')
    return dict(http_status=f['http_status'],request_peer='EXISTING_ROOT_NO_IMPERSONATION',
        private_origin_header_sent=False,error_enum=code if type(code) is str and code in ('PROXY_DENIED','ORIGIN_DENIED','NOT_FOUND') else 'UNKNOWN',
        backend_status=body.get('status') if type(body.get('status')) is str and body['status'] in ('READY','MAINTENANCE','UNAVAILABLE') else 'UNKNOWN',
        scope='RESPONSE_STATUS_ONLY_NOT_AUTHENTICATED_PRIVATE_HEALTH_ACCEPTANCE')


def main():
    if len(sys.argv)!=1 or os.getuid()!=0 or os.geteuid()!=0 or os.uname().nodename.split('.')[0]!=base.v.HOST:
        print('{"state":"HOLD_HOST_IDENTITY_ARGUMENTS"}');return 2
    r=dict(purpose='THREE_FIXED_OBJECT_REASON_ONLY_NOT_UPDATE_OR_FULL_REFRESH',site_executed_by_author=False,
        sections={},state='HOLD_NOT_ADMISSION',production_acceptance=False)
    def deadline(*a):raise base.v.TotalDeadline()
    previous=signal.signal(signal.SIGALRM,deadline);signal.alarm(70)
    try:
        r['sections']['current_recheck']=one('CURRENT_RECHECK',current_recheck)
        r['sections']['f131_loaded']=one('F131_EXACT_IMAGE_INSPECT',base.loaded_image)
        r['sections']['private_health']=one('FIXED_SOCKET_ROOT_HTTP',private_health)
    except base.v.TotalDeadline:r['state']='HOLD_TOTAL_TIMEOUT'
    finally:signal.alarm(0);signal.signal(signal.SIGALRM,previous)
    raw=json.dumps(r,sort_keys=True,allow_nan=False)
    print(raw if len(raw.encode())<=16384 else '{"state":"HOLD_OUTPUT_BOUND"}')
    return 2


if __name__=='__main__':raise SystemExit(main())
