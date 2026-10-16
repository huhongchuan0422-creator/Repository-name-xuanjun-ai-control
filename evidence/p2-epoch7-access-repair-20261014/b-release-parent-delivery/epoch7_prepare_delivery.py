#!/usr/bin/env python3
"""Observation-bound r7-fresh preparation delivery. No installation or approval operation."""
import argparse,ast,base64,zlib,contextlib,errno,hashlib,json,os,re,signal,socket,stat,sys,time,types,urllib.request

PINS_BOUND=True
PUBLICATION_COMMIT='2caa0bb45bcfcc26efc8d05f65d1473957e56d83'
RAW_PREFIX='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/'
PUBLIC_PREFIX='evidence/p2-epoch7-access-repair-20261014/b-release-parent-bound/'
CAND='/var/lib/xuanjun-p2-preparation/artifact-11796280855-p2pkg-38372304180-1/complete-install-candidate-38503014520'
PREP_ROOT=CAND+'/epoch7-preparation-candidate-r7-fresh-parent'
KIT_ROOT=CAND+'/epoch7-recovery-candidate-r7'
OBSERVATION_PATH=CAND+'/epoch7-observation-8df3b22b3762070f.private.json'
OBSERVATION_SHA256='a3f7042a1b3099c5699aaef547b22c8f744f0bdc514043a2a91a9847639f4f68'
HOST='iZd7oeikknn1z21sq6ji6zZ'
SOURCES={'epoch7_prepare.py': ('d32b55ab2164965b486dbe2d834281c5404d59fb454278e67ec32c306f34deb9', 55827), 'epoch7_prepare_data.py': ('71be3f9cb6a58c82083c029fad8f6ba2ba524451bc110443ed3423ef7c9364a1', 13888), 'epoch7_topology_projection.py': ('0e9817a1474dc4e54cf1779c0b4c243cf16e6204cab3a25210a12e41e03d00b6', 36482)}

COMPILER_ROOT=CAND+'/epoch7-recovery-candidate-r7-parentfix'
ARCHIVE_COMMIT='2caa0bb45bcfcc26efc8d05f65d1473957e56d83'
ARCHIVE_PATH='evidence/p2-epoch7-access-repair-20261014/artifacts/epoch7-kit-parentfix-dacd45a2.tar.gz'
ARCHIVE_SHA='6553938a56b882e17d13029fa9a06787131bb55a5c55bc1138e2b825277b7307'
ARCHIVE_SIZE=1045651
COMPILER_MANIFEST_SHA='b33b365ef1fd18458d85bcbbec44d883f3cc33bf859064cbdca6bfc3fad7d571'
COMPILER_ENTRY_SHA='33e4ad415c9496feb72a9e151603dcb808714e84d9af0d60b39542d92e967180'
COMPILER_SOURCE='dacd45a2f6888cae7b751cae5becacd3099c1ed2'
COMPILER_TREE='f31ae40b6f7c48f09846f6d70f5bb599f4980fe1'
COMPILER_CACHE_COUNT=253
EXTRACTOR_SHA='00177476be65c7adc3272aa50d2207fd0e9864c5c2fcdc2138da28862e20a78e'
EXTRACTOR_SIZE=10189
EXTRACTOR_Z='eNqtGu1y2kjyP0+h3as6SWehYG822cOrq8JYjrlg4ABnk+WoKVkajNZC0kkiNpvNu193z0gaAU6ydUeVsWamp6e7p7/FX757sc2zF3dh/ILHH7V0V6yT+IfW999/f+3l6/a9V/DA0u6SbRzgQ5y0k488e8zCgmv8qcg8vwiT+FyLOUxr4SZNsiLXHsJC85OA263WfB3msD8pcgBOtdzPwrR4EcYFz9KMw7e22eaFVqz5JufRRw7AXAvhtJTDV1xEO63IAIIHdmuSJcGWDtT6w4GW8f9swwx2ZIC+nTzGPNDSLCm4D9CaF/scztzZ2igBUB/p3gHN3N8iBht5bAmCNS+7T70s5+WYZ1mclIP738O0fF6DUKLwrhyGFdBveRKXz0lePmUVxrzwiup5VwEUXrYKI95qTcfjORv1blzN0XSeJv76dbskuu17cRAGcBXt7HUbCAWxrMInveWO5tMP9QZWbmAAAIynO7110xsNrtzZHKEqfHA97Y0XhysQkI2UI9x71h/fTKbubOZeAvQPZ9rftNPO2Uv5jyDc95Pe6JLWT1++PAJwNRgiB6ev9tfGly6bzXvz2xksf9Kn7tUtnMNuR3joGB71rqbPxrfTvsveDubszXR8O7r8ZTx9y0YgmcEINg+HrHd5M5jNBuORbrU0+Oi92/k1iGHQ780BXW8ymY7f9YbsDQ1ng9Gboct687l7M5njCeVprA98DC4Bik3df90OgG12BV/XFQr9c6vVCvgKNJsHxkcv2nKLdNrs0skhrCSFRgtdLfPCnGvvcOBmWZIZujsZ969fg8Tm015/znTtROyWWPO1Z2TeowlbebHN4lKzbFg4+/EVrdlr/hSE93BJRrnNj5KcMy+KjFWQW6Dt4cbLds4oiUu6Vh7oUwBCvvIiUGiaSjJtFYBRwVlw/znwA7slPH5AWbqgtTZhhzWzWuFPPk8L7cLLuUuPYDnd+ox5tuWlNMRkjRSmJHkaeACksF4j1CgnwPEFofWHcFfsqgdKdambh7vtgEchKbwfcS/epuyQsvIjboi2VfOSvq+hkTfmrTiLvQ038EtKj5Sj2KVyEjkFnwO+J9A62s9axGO58LOj/Xh6hgs1VRm3V9so2niFvzYyfdFr/+q1f++0/87sf7dfLE908Le0ubELLz8l3YMLNXQA0m36om/G0p3v+WvOmE4bCTK1wZnmj2GxNgwd/IKvW/gv0c2mVElVUkSMB9t5GoWFob8AMEA96c2v5S1InUUgKR2pp2QOoNS1XMSMKph9toFhr71afnr18jNwIODhuMvBG/BbemUwRRb6BUNvJQyHCMGV1Auz3ICAtFF1GuLCNirQ2XxuqdwhzfIU5JO2NRWTaEewUsgCFZJ0OxmSp2H/nI1H7K37QTfP5fICdyzhPEKtkEGSEjCq7JARO0q8IEd2QAXROxj6tli1f9KB/+TuN4hjjJhj6yR5cOjRat5X9aHwxfwkhkATF07kbe4CT9vGW7B2eR3kEICL0Xh0NRgNJBeoAkLCYZyneKSX+WswByTL0uSAgVuyNAor4rEMHzgqPQ9It5Kr8W0bm3qzZ1J4zag4d7sCgjyqDtoTzYI57UUsXC6dquY4TcL13rR/PXjnsuverNRhtAaK7fYb+LoCgzcwFIPcnTCxL/DMwZjQAdFwN46e3aFJkSJzb1MrzTZOPf+B/IVYsuErMBoB80Q7VdhDPspdFTMlLCqaW3IGoY5dYCiUVCOJ4PgDVAUt5zwmDcdHCBLyX82eTC/sBJKpY9xVNFQsdgWLUnrdhuls+OYOk7z4cLnBGZIFXGlnnZc/ATM37s2FO21wUX5qnypw2+TvDrEqq6VR4iENkxTHoEHiku0FwZ9ACgpTZ2AVq7bwgiDFQjjPGuZEQ7cIBNDUrD+euPqRM5BYiSv1ntga9AICMCmrnN6GAZ4uR/eN0aYIBW2dZggoPyWKkoUSSTmm4FCq/o0770HC09snk2BVhhd4hxWnZndpR+h8UwoEjb0Q4uW+MAeNNMzuAY2qpFHFiJvkdaejyiAPfxcL5Panbn8+nn54jmBy+6D+dMOHV8vByX2ZjDBHSzBMlYKatJeQ11LYRLkclTp+Omi0KvXShjH/BSbwH5t/mLhsfFzxiQmv8LTKUdmymiLaBGaz9iOUV1c+5KjVITpT0QIkqyRlNvjVPUIBOZMqcCGC1oH2evGuchOLktZktQJP012iAUCqNhhCos3mvSk45NEc0nFd8XWiSAGLpdNItlVR0phF7y0ooi1LYqaKHM27qGFLXAJcjS5AGyHCOyih1AAgYpXTyCz2ce5FpDqZCWALUV3P2/fgfHXCAEFVBVLoBhCCIGpxRFsXchsw8Yf2qTz+c3Pv/klpVQ0zTC82XJ5a5lkS8yHYEuWuVmSNY5QTsGjdAjNIqwK/eB7zEv19KWvVK9ap1yPkJ5yqkSbrNqViqg/Zy7jPy2RBYDCbulprBOkz0SwA6xCkXD5/SqlNwNCVUEmqf24QWulmTU+KcQBg93LjRozEzsUTJY1efM+NU4tyFtppQrrTOJY8GGCwf0tCCbPoEoKlqWieoNBp7kXlxiqJlBtLYjDAynU2s3QlZZCZ3oYXHlq7EcarRApcAtMUhDwW8I+WVg7COKkH6CvrEcSvegDhq8wmvW2xTrKw2EE9SYcD7Um2g8T2MYYQWFbRsBEkCrXnCpWtqj2JcQOn7BkbzIAzQz3exNBT4SSfr1XAU/dNE3ivgDJU0lXK8doEdVXhpOLR/kqR6+zMEm2H8XQwL0UtuwEVSTLlLrfHURg/4B2CPujXveklOMy3imU88J2o5vJdDlZgp0kePjHPj+DP53kO5drBCgjZg5pCP1LHg/E+eUWRoegB9UE5D1U1Fd+Q6FFBLKkVNTX1vogaerLd0RijsFWN5rPbiWnpvf6QTd2eGtko9qrFBgFhHlvHBKlnKBnQFD/y8lyblE27y1J+hih/lCqPgRKGBWOQXUYrK/WKtdXQpKajxvWGM8QJNZNDw6UFEBetxUm2wQex1XHoBLjoi9l4eAvppVL9CkcerWxBgEXPWfKYO3JisWxcSSPurgIHjqSEHGiw4HnMppfj0fDDH/RcGbEYjsZX4+Fw/Mte3lyeaHsp9kkNvGlssdRf5jM7Fu3TpdMEr9xBw2ax9VGKeA8ZdQm8jPJwlNPiFJLE2iFS6wemv3NgJIxzsTzMyUQj01kF54pMEO03C8UCe2OwWWA6zG+OikkAW3TQEUHRvsLbpM43iOX8UKwqesJjPpeMSuzAEbk+2tFgyFolUZQ8sny3Qf+RO2RUJignIbZ0CK8jNu3193M7ogrQrIIvNvJq+6cNovtHE+Y5tcsq4/PX3H8gyzObJeExhkV1JuXSbT3P+aFcFatS2OyN+pBOQCJ3hFVSNSQAjR1d8GGj8f8q8ovB6BJjrUJK1ZcVrulYU5YcH0hDcRXVk+ot6vbuApYWnSUJGR4powDgpSWxm4pj5PgyRXpGsysdLA5UmKfaeT5AjmHRPVtYcvA7SO7NQx2QgRxrkKondOh3pdwi7q2c0pcKV0COtO5FHHHycq/Eh+pYZFxtOtR+AfEf+oXSEZSj0cVw3H9bXikis9Vu9oEzvuMgX+40FFFELknTofaKLRjUscD62Wm2oSy9fj5a+JEoMN0JiC14CrYppj3Wfnsp8x6d/XZSjfxkrxT0VqADX2DkHNWZkzxJ9UmeTTk9o/tNzx9CVpuBDtY9RlDLbmVZMDBP8LvKeiw5oHJUPlNfg8V5Ofbl+Ii4lQOl6MEW1UlifG9O8Go2WoaO07w5S8fk5ZhLIXEIjwd+UPZvvceWIgOw0F238cJE2Iqs4al1mmyLdFtYah+yboM26lRxRY5hdKyOaZllO5XSdszanWOd2a/j3S9eBUGNrEhMfVteJLc7jnhQXkhUiETAV3ffQbyhCq7aXTWW1OTKfY+ve8a388ltmSc+71ckqv/JswDGzQO2rMgOqCH1rNeA877ihr6SnhxiBFRgi1BzdgH553M1Ynwhc1Qq0zzJClkatrF0xTS/NMinrvFk+8k2FtmY9WQe6culFrPwchwqZjOMhCHmBLTlvBIPgjTFI2hfpMvDvEYuUf1dSYww/FmJPXNI1USg1lktBjKVsn/wZ5k97IoFR4j/ZVoT3wfPMReP7vv+cI+FTvLqm6SFRLOjN/+sBlSCpvab0zm6+LgGxBLk56ox2H3mvRHkHKgpyDH9qAMDB25YVC2+c/IgBPWPjqXPoO6dgzgGcxcVhaBOHFo+TivEOn8N9TNipvYqqdcq38V+41Xzt2WqDanRlJKq7kUq8tJKSrUKlpa6/1C5xFtycWk2taewIfUsuWqkaH0x3RTdDTB2TCUP8tBvD8aQJggvyY4kol+X3pcEdyiwKMyB5qYwzGYCKsPjJ2wV3nO9q8tX95D9YLONvXOng6uBe6lbss3XjeSbqBxYUWLY2Y+v9K4a0xry1KsIR3B1vNMfIK1Vgx6tN6JrE5HSs6x+CgRk429MprcjIDPEN6hRxLxgE+Z5vfpm2hsBW9XPQjZeGBtedv9RzfPpLSykYfLnRHYvu99ugNoJzRsBFz9/AqwOY0HiM2YeNB2NUixAjAh1eiWptuTQEgKph+ovespZs9G5hPOx3wg5hCDJ0Ntt/YS8qfwdVeBgDSYIAqjckbvEq2WcIX6VtEK0mvg2DAxQa/FKJ9+BtkfePfjjPIk88UssdTpOIP8qeDUbJHHByPcwfNGLr8Et8VZtANkB/Y5nNGYzfF8N/y8+zN3++LJUeUySGwVKmSp4dzllLUi2LRdNq0qxWvVPBJxG0nZsu0w4LBWX1DUxp2qnmDmiljKtoQSVXv4H202aG/LHBRjJGATxXFxClXh2QN1CLODwphhzHJ0xVD3G9C5KD+s6g3QRmPovU9VU3w=='

STAGE_SECONDS=60
STATUS_SECONDS=5
PHASE='INPUT_VALIDATION'
CODES=frozenset(('UNBOUND','OBSERVATION_BINDING','ARGUMENTS','ROOT_HOST','ISOLATED','SOURCE_SET','SOURCE_PIN','RESPONSE',
 'REDIRECT','ENCODING','LENGTH','DEADLINE','EXISTING_TIMER','ANCESTRY','XATTR','PATH_RACE','PARENT_NAMES',
 'DIRECTORY','INVENTORY','PREPARATION_OUTPUT_SCOPE','PREPARATION_RESULT_SCOPE','REVIEW_INPUT','FILE_AUTHORITY','FILE_RACE','FILE_BYTES','SHORT_WRITE','COMPILER_BINDING','COMPILER_SOURCE','COMPILER_CACHE','COMPILER_STATE','COMPILER_RECHECK','EXTRACTOR_PIN','OWNED_PARENT','STATUS_BOUND','LABEL_SOURCE_BOUND'))

PHASES=frozenset(('INPUT_VALIDATION','DOWNLOAD_ALL','LOAD_VERIFIED_PREPARER','STAGE_COMPILER','STAGE_EXACT','PREPARE_PRIVATE_PLAN','VERIFY_STAGING_AFTER_PREPARATION','DELIVER_STATUS'))
ERROR_CLASSES=frozenset(('ValueError','KeyError','TypeError','OSError','FileNotFoundError','PermissionError','TimeoutError','InterruptedError','KeyboardInterrupt','SystemExit','Hold','DeadlineError','CleanupError','DiagnosticHold'))
PUBLIC_CODE_PATHS=frozenset(('epoch7_recovery_entry.py', 'helpers/epoch3_service_containment.py', 'helpers/epoch7_acceptance_rows.py', 'helpers/epoch7_additive_identity.py', 'helpers/epoch7_additive_server.py', 'helpers/epoch7_approval.py', 'helpers/epoch7_bindings.py', 'helpers/epoch7_bounded_stager.py', 'helpers/epoch7_command_runner.py', 'helpers/epoch7_complete_approval.py', 'helpers/epoch7_delta.py', 'helpers/epoch7_exact_access.py', 'helpers/epoch7_host_containment.py', 'helpers/epoch7_host_driver.py', 'helpers/epoch7_host_factory.py', 'helpers/epoch7_host_observer.py', 'helpers/epoch7_host_phases.py', 'helpers/epoch7_injected_recovery.py', 'helpers/epoch7_live_controls.py', 'helpers/epoch7_nginx_recipe.py', 'helpers/epoch7_openclaw_recipe.py', 'helpers/epoch7_owner_prerequisite.py', 'helpers/epoch7_pre_active_guards.py', 'helpers/epoch7_protected_fs.py', 'helpers/epoch7_python_identity.py', 'helpers/epoch7_quiet_startup.py', 'helpers/epoch7_recovery_sequence.py', 'helpers/epoch7_resource_observer.py', 'helpers/epoch7_resource_plan.py', 'helpers/epoch7_runtime_acceptance.py', 'helpers/epoch7_runtime_effects.py', 'helpers/epoch7_service_contract.py', 'helpers/epoch7_service_roles.py', 'helpers/epoch7_snapshot.py', 'helpers/epoch7_timer_tail.py', 'helpers/epoch7_unit_transitions.py', 'helpers/exact_access_plan.py', 'helpers/node_sqlite_probe.py', 'helpers/observe_epoch7.py', 'helpers/openclaw_metadata.py', 'helpers/probe_driver.py', 'helpers/probe_helpers.py', 'helpers/probe_metadata.py', 'helpers/protected_command_evidence.py', 'helpers/reviewed_database.py', 'helpers/reviewed_publisher.py', 'helpers/reviewed_scanner.py', 'helpers/snapshot_io.py', 'helpers/unit_metadata.py', 'xuanjun-p2-package/stage1/activation_control.py', 'xuanjun-p2-package/stage1/callback_schema_gate.py', 'xuanjun-p2-package/stage1/codex_app_server_worker.py', 'xuanjun-p2-package/stage1/codex_worker.py', 'xuanjun-p2-package/stage1/dependency_evidence_view.py', 'xuanjun-p2-package/stage1/development_loop.py', 'xuanjun-p2-package/stage1/development_pipeline.py', 'xuanjun-p2-package/stage1/development_service.py', 'xuanjun-p2-package/stage1/execution_ledger.py', 'xuanjun-p2-package/stage1/execution_supervision.py', 'xuanjun-p2-package/stage1/github_issue_consumer.py', 'xuanjun-p2-package/stage1/ledger_backup.py', 'xuanjun-p2-package/stage1/ledger_cutover_transaction.py', 'xuanjun-p2-package/stage1/ledger_install_stage.py', 'xuanjun-p2-package/stage1/ledger_read_client.py', 'xuanjun-p2-package/stage1/ledger_read_projection.py', 'xuanjun-p2-package/stage1/ledger_read_transport.py', 'xuanjun-p2-package/stage1/ledger_server_identity.py', 'xuanjun-p2-package/stage1/ledger_service.py', 'xuanjun-p2-package/stage1/legacy_host_adapter.py', 'xuanjun-p2-package/stage1/legacy_quiescence.py', 'xuanjun-p2-package/stage1/mechanical_wake.py', 'xuanjun-p2-package/stage1/mechanical_wake_service.py', 'xuanjun-p2-package/stage1/native_child_adapter.py', 'xuanjun-p2-package/stage1/native_gateway_controller.py', 'xuanjun-p2-package/stage1/native_github_notifier.py', 'xuanjun-p2-package/stage1/native_ledger_bridge.py', 'xuanjun-p2-package/stage1/native_ledger_operations.py', 'xuanjun-p2-package/stage1/native_peer_identity.py', 'xuanjun-p2-package/stage1/native_pipeline_runtime.py', 'xuanjun-p2-package/stage1/native_snapshot_access.py', 'xuanjun-p2-package/stage1/owner_approval_dispatch.py', 'xuanjun-p2-package/stage1/owner_callback_server.py', 'xuanjun-p2-package/stage1/owner_dashboard.py', 'xuanjun-p2-package/stage1/owner_feishu_bridge_cycle.py', 'xuanjun-p2-package/stage1/owner_feishu_claim_guard.py', 'xuanjun-p2-package/stage1/owner_feishu_history.py', 'xuanjun-p2-package/stage1/owner_feishu_https.py', 'xuanjun-p2-package/stage1/owner_feishu_ledger_endpoint.py', 'xuanjun-p2-package/stage1/owner_feishu_transport.py', 'xuanjun-p2-package/stage1/owner_notification_outbox.py', 'xuanjun-p2-package/stage1/owner_process_identity.py', 'xuanjun-p2-package/stage1/owner_update_router.py', 'xuanjun-p2-package/stage1/p2_auxiliary_isolation.py', 'xuanjun-p2-package/stage1/p2_bootstrap_files.py', 'xuanjun-p2-package/stage1/p2_fixed_host_runtime.py', 'xuanjun-p2-package/stage1/p2_gateway_relay.py', 'xuanjun-p2-package/stage1/p2_install_entrypoint.py', 'xuanjun-p2-package/stage1/p2_legacy_adoption.py', 'xuanjun-p2-package/stage1/p2_prerequisites.py', 'xuanjun-p2-package/stage1/p2_publisher_bootstrap.py', 'xuanjun-p2-package/stage1/p2_rpm_prerequisites.py', 'xuanjun-p2-package/stage1/p2_sandbox_profile.py', 'xuanjun-p2-package/stage1/p2_service_context_preflight.py', 'xuanjun-p2-package/stage1/p2_tls_lifecycle.py', 'xuanjun-p2-package/stage1/root_broker.py', 'xuanjun-p2-package/stage1/run_usage_projection.py', 'xuanjun-p2-package/stage1/task_cost_projection.py', 'xuanjun-p2-package/stage1/task_supervisor_inventory_adapter.py', 'xuanjun-p2-package/stage1/telegram_owner_transport.py', 'xuanjun-p2-package/stage1/uk_owner_callback_core.py', 'xuanjun-p2-package/stage1/uk_owner_notify_worker.py'))

class Hold(ValueError):pass
class DeadlineError(Exception):pass
class CleanupError(Exception):pass
class StatusDeliveryError(Exception):pass

def need(value,code):
    if not value:raise Hold(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stamp(info):return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
def check(end):need(time.monotonic()<end,'DEADLINE')
def no_attributes(fd):
    for key in ('system.posix_acl_access','system.posix_acl_default','security.capability'):
        try:os.getxattr(fd,key)
        except OSError as error:need(error.errno in (errno.ENODATA,errno.ENOTSUP),'XATTR')
        else:raise Hold('XATTR')
def close_all(fds,primary=None):
    failed=False
    for fd in reversed(fds):
        try:os.close(fd)
        except BaseException:failed=True
    if failed:
        if primary is None:raise CleanupError()
        primary.delivery_cleanup_failed=True

@contextlib.contextmanager
def budget(seconds):
    need(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'EXISTING_TIMER')
    old=signal.getsignal(signal.SIGALRM);end=time.monotonic()+seconds;primary=None
    def expired(unused_signum,unused_frame):raise DeadlineError()
    try:
        signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,seconds,.1)
        yield end;check(end)
    except BaseException as error:primary=error;raise
    finally:
        failed=False
        try:signal.setitimer(signal.ITIMER_REAL,0)
        except BaseException:failed=True
        try:signal.signal(signal.SIGALRM,old)
        except BaseException:failed=True
        if failed:
            if primary is None:raise CleanupError()
            primary.delivery_cleanup_failed=True

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise Hold('REDIRECT')

def bound():
    need(PINS_BOUND is True and all(type(v) is str and re.fullmatch('[0-9a-f]{40}',v) for v in (PUBLICATION_COMMIT,ARCHIVE_COMMIT)),'UNBOUND')

def validate_sources(cache):
    need(type(cache) is dict and set(cache)==set(SOURCES),'SOURCE_SET')
    for name,(digest,size) in SOURCES.items():
        need(type(cache[name]) is bytes and len(cache[name])==size and sha(cache[name])==digest,'SOURCE_PIN')
    return cache

def fetch_sources(end):
    bound();cache={}
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    for name,(digest,size) in sorted(SOURCES.items()):
        check(end);url=RAW_PREFIX+PUBLICATION_COMMIT+'/'+PUBLIC_PREFIX+name
        request=urllib.request.Request(url,headers={'Accept-Encoding':'identity'})
        response=None;primary=None
        try:
            response=opener.open(request,timeout=min(10,max(.001,end-time.monotonic())))
            need(response.status==200 and response.geturl()==url,'RESPONSE')
            need(response.headers.get('Content-Encoding','identity')=='identity','ENCODING')
            length=response.headers.get('Content-Length');need(length is None or length==str(size),'LENGTH')
            raw=response.read(size+1);check(end)
            need(len(raw)==size and sha(raw)==digest,'SOURCE_PIN');cache[name]=raw
        except BaseException as error:primary=error;raise
        finally:
            if response is not None:
                try:response.close()
                except BaseException:
                    if primary is None:raise CleanupError()
                    primary.delivery_cleanup_failed=True
    check(end);return validate_sources(cache)

def fetch_archive(end):
    bound();url=RAW_PREFIX+ARCHIVE_COMMIT+'/'+ARCHIVE_PATH
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    response=None;primary=None
    try:
        response=opener.open(urllib.request.Request(url,headers={'Accept-Encoding':'identity'}),timeout=min(10,max(.001,end-time.monotonic())))
        need(response.status==200 and response.geturl()==url,'RESPONSE')
        need(response.headers.get('Content-Encoding','identity')=='identity','ENCODING')
        length=response.headers.get('Content-Length');need(length is None or length==str(ARCHIVE_SIZE),'LENGTH')
        raw=response.read(ARCHIVE_SIZE+1);check(end)
        need(len(raw)==ARCHIVE_SIZE and sha(raw)==ARCHIVE_SHA,'SOURCE_PIN');return raw
    except BaseException as error:primary=error;raise
    finally:
        if response is not None:
            try:response.close()
            except BaseException:
                if primary is None:raise CleanupError()
                primary.delivery_cleanup_failed=True

def safe_extractor_bytes():
    blob=zlib.decompressobj();code=blob.decompress(base64.b64decode(EXTRACTOR_Z,validate=True),EXTRACTOR_SIZE+1)
    need(blob.eof and not blob.unused_data and not blob.unconsumed_tail and len(code)==EXTRACTOR_SIZE and sha(code)==EXTRACTOR_SHA,'EXTRACTOR_PIN')
    return code

def compiler_inputs(raw):
    need(type(raw) is bytes and len(raw)==ARCHIVE_SIZE and sha(raw)==ARCHIVE_SHA,'SOURCE_PIN')
    code=safe_extractor_bytes()
    extractor=types.ModuleType('verified_compiler_extractor');extractor.__file__='<verified-compiler-extractor>'
    exec(compile(code,extractor.__file__,'exec'),extractor.__dict__)
    need(extractor.ROOT_NAME=='epoch7-recovery-candidate-r7-parentfix','COMPILER_BINDING')
    files,dirs=extractor.inspect_archive(raw,ARCHIVE_SHA,COMPILER_ENTRY_SHA,COMPILER_MANIFEST_SHA)
    need(len(files)==COMPILER_CACHE_COUNT+1,'COMPILER_CACHE')
    entry=types.ModuleType('verified_compiler_entry');entry.__file__=COMPILER_ROOT+'/epoch7_recovery_entry.py'
    exec(compile(files['epoch7_recovery_entry.py'],entry.__file__,'exec'),entry.__dict__)
    manifest=entry.decode(files['recovery-kit-manifest.json']);entry.validate_manifest(manifest)
    need(manifest['kit_source_commit']==COMPILER_SOURCE and manifest['kit_source_tree']==COMPILER_TREE and len(manifest['files'])==COMPILER_CACHE_COUNT,'COMPILER_SOURCE')
    return extractor,entry,files

def compiler_summary(state):
    need(state in ('NOT_STAGED','EXTRACTION_ATTEMPTED_NOT_VERIFIED','VERIFY_EXISTING_FAILED','EXTRACTED_AND_VERIFIED','VERIFIED_EXISTING'),'COMPILER_STATE')
    return {'state':state,'path':COMPILER_ROOT,'archive_sha256':ARCHIVE_SHA,'kit_manifest_sha256':COMPILER_MANIFEST_SHA,
            'entry_sha256':COMPILER_ENTRY_SHA,'kit_source_commit':COMPILER_SOURCE,'kit_source_tree':COMPILER_TREE,
            'source_files':COMPILER_CACHE_COUNT,'runtime_effects':'NOT_EXECUTED'}

def verify_compiler(entry,files,end):
    check(end)
    try:kit=entry.verify_kit(COMPILER_ROOT,COMPILER_MANIFEST_SHA)
    except BaseException as error:
        # The frozen reader may fail during constructor/close; retain uncertainty.
        error.delivery_cleanup_failed=True;raise
    expected={name:raw for name,raw in files.items() if name!='recovery-kit-manifest.json'}
    need(kit.cache==expected and len(kit.cache)==COMPILER_CACHE_COUNT and
         kit.manifest['kit_source_commit']==COMPILER_SOURCE and kit.manifest['kit_source_tree']==COMPILER_TREE,'COMPILER_RECHECK')
    check(end);return kit

def stage_compiler(raw,extractor,entry,files,end):
    state='NOT_STAGED';entered=False
    try:
        entered=True
        with extractor.ProtectedDirectory(CAND,((0,0),)) as tree:
            try:os.stat('epoch7-recovery-candidate-r7-parentfix',dir_fd=tree.fd,follow_symlinks=False)
            except FileNotFoundError:present=False
            else:present=True
            tree.check()
        entered=False;check(end)
        state='VERIFY_EXISTING_FAILED' if present else 'EXTRACTION_ATTEMPTED_NOT_VERIFIED'
        if not present:
            entered=True
            extractor.extract(raw,COMPILER_ROOT,ARCHIVE_SHA,COMPILER_ENTRY_SHA,COMPILER_MANIFEST_SHA)
            entered=False;check(end)
        verify_compiler(entry,files,end)
        return compiler_summary('VERIFIED_EXISTING' if present else 'EXTRACTED_AND_VERIFIED')
    except BaseException as error:
        if entered or state=='EXTRACTION_ATTEMPTED_NOT_VERIFIED':error.delivery_cleanup_failed=True
        error.compiler_staging=compiler_summary(state);raise


def authority(fd,mode=None):
    info=os.fstat(fd)
    need(stat.S_ISDIR(info.st_mode) and info.st_uid==info.st_gid==0 and not info.st_mode&0o7022 and
         (mode is None or stat.S_IMODE(info.st_mode)==mode),'ANCESTRY')
    no_attributes(fd);return stamp(info)

def names(fd,maximum):
    row=os.listdir(fd);need(len(row)<=maximum and len(row)==len(set(row)) and all(type(v) is str and 0<len(v)<=255 and '/' not in v and '\x00' not in v for v in row),'PARENT_NAMES')
    return tuple(sorted(row))

def parent_walk(held,end):
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);held.append(fd)
    rows=[(fd,None,None,'/',authority(fd))];path=''
    for name in CAND[1:].split('/'):
        check(end);parent=fd;path+='/'+name
        fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);held.append(fd)
        row=authority(fd);need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==row,'PATH_RACE')
        rows.append((fd,parent,name,path,row))
    return rows

def recheck_parents(rows,parent_after):
    for fd,parent,name,path,before in rows:
        actual=authority(fd);wanted=parent_after if path==CAND else before
        need(actual==wanted,'PATH_RACE')
        if parent is not None:need(stamp(os.stat(name,dir_fd=parent,follow_symlinks=False))==actual,'PATH_RACE')

def read_file(directory,name,raw,end):
    check(end);before=os.stat(name,dir_fd=directory,follow_symlinks=False);fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory);primary=None
    try:
        info=os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink,info.st_size)==(0,0,0o600,1,len(raw)),'FILE_AUTHORITY')
        need(stamp(before)==stamp(info),'FILE_RACE');no_attributes(fd);parts=[];count=0
        while True:
            check(end);part=os.read(fd,min(16384,len(raw)+1-count))
            if not part:break
            count+=len(part);need(count<=len(raw),'FILE_BYTES');parts.append(part)
        need(b''.join(parts)==raw,'FILE_BYTES');no_attributes(fd)
        need(stamp(os.fstat(fd))==stamp(info)==stamp(os.stat(name,dir_fd=directory,follow_symlinks=False)),'FILE_RACE')
        check(end);return stamp(info)
    except BaseException as error:primary=error;raise
    finally:close_all([fd],primary)

def stage(cache,end,allow_create=True):
    """Exclusive fixed directory; a partial attempt is retained and reported."""
    validate_sources(cache);need(os.geteuid()==os.getegid()==0,'ROOT_HOST')
    held=[];created=[];primary=None;result=None
    try:
        rows=parent_walk(held,end);parent=rows[-1][0];parent_before=rows[-1][4];before_names=names(parent,1024)
        need(authority(parent)==parent_before,'PATH_RACE');leaf='epoch7-preparation-candidate-r7-fresh-parent'
        try:before=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
        except FileNotFoundError:
            need(allow_create is True,'DIRECTORY')
            check(end);os.mkdir(leaf,0o700,dir_fd=parent);created.append(PREP_ROOT);before=os.stat(leaf,dir_fd=parent,follow_symlinks=False);new=True
        else:new=False
        need(stat.S_ISDIR(before.st_mode),'DIRECTORY')
        directory=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);held.append(directory)
        start=authority(directory,0o700);need(stamp(before)==start,'PATH_RACE')
        need(names(directory,3)==(() if new else tuple(sorted(SOURCES))),'INVENTORY')
        if new:
            for name in sorted(SOURCES):
                check(end);raw=cache[name];fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory);created.append(PREP_ROOT+'/'+name);file_primary=None
                try:
                    info=os.fstat(fd);need(stat.S_ISREG(info.st_mode) and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,0o600,1),'FILE_AUTHORITY');no_attributes(fd)
                    offset=0
                    while offset<len(raw):
                        check(end);count=os.write(fd,raw[offset:offset+16384]);need(type(count) is int and 0<count<=min(16384,len(raw)-offset),'SHORT_WRITE');offset+=count
                    os.fsync(fd);check(end)
                except BaseException as error:file_primary=error;raise
                finally:close_all([fd],file_primary)
            os.fsync(directory);os.fsync(parent);check(end)
        current=authority(directory,0o700)
        need(current[:6]==start[:6] and (new or current==start),'DIRECTORY')
        expected_names=tuple(sorted(SOURCES));need(names(directory,3)==expected_names,'INVENTORY')
        observed={name:read_file(directory,name,cache[name],end) for name in sorted(SOURCES)}
        for name in sorted(SOURCES):need(stamp(os.stat(name,dir_fd=directory,follow_symlinks=False))==observed[name],'FILE_RACE')
        need(authority(directory,0o700)==current and names(directory,3)==expected_names and
             stamp(os.stat(leaf,dir_fd=parent,follow_symlinks=False))==current,'PATH_RACE')
        parent_after=authority(parent)
        if new:
            need(parent_after[:5]==parent_before[:5] and parent_after[5]==parent_before[5]+1 and names(parent,1024)==tuple(sorted(before_names+(leaf,))),'OWNED_PARENT')
        else:need(parent_after==parent_before and names(parent,1024)==before_names,'OWNED_PARENT')
        recheck_parents(rows,parent_after);check(end)
        result={'state':'STAGED_EXACT' if new else 'REUSED_EXACT','path':PREP_ROOT,
                'files':{name:{'sha256':SOURCES[name][0],'bytes':SOURCES[name][1]} for name in sorted(SOURCES)},'created_paths':list(created)}
        return result
    except BaseException as error:primary=error;error.delivery_created_paths=list(created);raise
    finally:
        try:close_all(held,primary)
        except BaseException as error:error.delivery_created_paths=list(created);raise

def preparer(cache):
    validate_sources(cache);module=types.ModuleType('verified_epoch7_preparer');module.__file__=PREP_ROOT+'/epoch7_prepare.py'
    exec(compile(cache['epoch7_prepare.py'],module.__file__,'exec'),module.__dict__);return module

def public_labels(cache):
    labels=set(CODES)
    for raw in cache.values():
        need(type(raw) is bytes and len(raw)<=1048576,'LABEL_SOURCE_BOUND')
        for node in ast.walk(ast.parse(raw.decode('utf-8'))):
            value=node.s if isinstance(node,ast.Str) else None
            if type(value) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,119}',value):
                labels.add(value)
                for prefix in ('EPOCH7_PREP_','TOPOLOGY_','EPOCH7_EXTRACT_'):labels.add(prefix+value)
    return frozenset(labels)

def code_locations(error):
    rows=[];tb=error.__traceback__;count=0
    while tb is not None and count<64:
        count+=1;frame=tb.tb_frame;name=frame.f_code.co_filename;label=None
        if frame.f_globals is globals():label='delivery/epoch7_prepare_delivery.py'
        elif name=='<verified-compiler-extractor>':label='delivery/extract_epoch7_compiler_kit.py'
        elif name=='<verified-preparation-delivery>':label='delivery/epoch7_prepare_delivery.py'
        elif name in tuple(PREP_ROOT+'/'+item for item in ('epoch7_prepare.py','epoch7_prepare_data.py','epoch7_topology_projection.py')):
            label='preparation/'+name.rsplit('/',1)[1]
        elif name.startswith(COMPILER_ROOT+'/') and name[len(COMPILER_ROOT)+1:] in PUBLIC_CODE_PATHS:
            label='compiler-kit/'+name[len(COMPILER_ROOT)+1:]
        elif name.startswith(KIT_ROOT+'/') and name[len(KIT_ROOT)+1:] in PUBLIC_CODE_PATHS:
            label='kit/'+name[len(KIT_ROOT)+1:]
        elif name in ('<hash-pinned-build_epoch5_runtime>','<hash-pinned-inspect_epoch3>',
                      '<hash-pinned-prepare_epoch5_bindings>','<hash-pinned-epoch5_plan>',
                      '<hash-pinned-identity-renderer>'):
            label='historical/'+name[1:-1]
        if label is not None and type(tb.tb_lineno) is int and 0<tb.tb_lineno<=100000:
            rows.append({'source':label,'line':tb.tb_lineno})
        tb=tb.tb_next
    return rows[-8:]

def failure(error,outer,preparer,labels):
    inner=getattr(preparer,'CURRENT_PHASE',None)
    if preparer is None or type(inner) is not str or inner not in preparer.PHASES:inner='UNAVAILABLE'
    allowed=set(labels)|set(CODES)
    args=error.args if type(error.args) is tuple else ()
    label=args[0] if len(args)==1 and type(error) in (ValueError,Hold) else None
    if type(label) is not str or label not in allowed:label=None
    kind=type(error).__name__;kind=kind if kind in ERROR_CLASSES else 'DEPENDENCY_ERROR'
    cleanup=isinstance(error,CleanupError) or bool(getattr(error,'delivery_cleanup_failed',False)) or bool(getattr(error,'preparation_cleanup_failed',False))
    if preparer is not None:cleanup=cleanup or isinstance(error,preparer.CleanupError)
    return {'schema':1,'state':'HOLD','phase':outer if outer in PHASES else 'INPUT_VALIDATION',
        'preparation_phase':inner,'failure_code':kind,'failure_label':label,
        'code_locations':code_locations(error),'cleanup_unknown':cleanup,
        'observation_sha256':OBSERVATION_SHA256,'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}

def retained_staging(error):
    """Only the fixed public staging inventory may survive a failed projection."""
    allowed=set((PREP_ROOT,))|set(PREP_ROOT+'/'+name for name in SOURCES)
    value=getattr(error,'delivery_created_paths',[])
    paths=[item for item in value if type(item) is str and item in allowed] if type(value) is list and len(value)<=4 else []
    result={'created_paths':paths,'staging':None}
    value=getattr(error,'delivery_staging',None)
    if type(value) is dict and value.get('state') in ('STAGED_EXACT','REUSED_EXACT') and value.get('path')==PREP_ROOT:
        files={name:{'sha256':SOURCES[name][0],'bytes':SOURCES[name][1]} for name in sorted(SOURCES)}
        if value.get('files')==files and value.get('created_paths')==paths:
            result['staging']={'state':value['state'],'path':PREP_ROOT,'files':files,'created_paths':list(paths)}
    return result

def retained_outputs(error):
    """Keep only bounded fixed private-output path/hash/length metadata."""
    prefixes={'epoch7-approved-plan-':2*1024*1024,'epoch7-resume-inputs-':64*1024*1024,'epoch7-review-packet-':2*1024*1024}
    def path_scope(path):
        need(type(path) is str and os.path.dirname(path)==CAND,'PREPARATION_OUTPUT_SCOPE')
        name=os.path.basename(path)
        matches=[prefix for prefix in prefixes if re.fullmatch(re.escape(prefix)+'[0-9a-f]{16}\\.private\\.json',name)]
        need(len(matches)==1,'PREPARATION_OUTPUT_SCOPE');return matches[0]
    created=getattr(error,'preparation_created_paths',[]);rows=getattr(error,'preparation_outputs',[])
    need(type(created) is list and len(created)<=3 and len(set(created))==len(created),'PREPARATION_OUTPUT_SCOPE')
    for path in created:path_scope(path)
    need(type(rows) is list and len(rows)<=3,'PREPARATION_OUTPUT_SCOPE');safe=[];seen=set()
    for row in rows:
        need(type(row) is dict and set(row)=={'path','sha256','bytes'},'PREPARATION_OUTPUT_SCOPE')
        prefix=path_scope(row['path']);pin=row['sha256'];size=row['bytes']
        need(type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin) and type(size) is int and 0<size<=prefixes[prefix], 'PREPARATION_OUTPUT_SCOPE')
        need(row['path']==CAND+'/'+prefix+pin[:16]+'.private.json' and row['path'] in created and row['path'] not in seen,'PREPARATION_OUTPUT_SCOPE')
        seen.add(row['path']);safe.append(dict(row))
    return {'completed_outputs':safe,'created_output_paths':list(created),'preparation_output_evidence':'RETAINED_BOUNDED_METADATA'}


def deliver_status(value):
    try:
        with budget(STATUS_SECONDS) as end:
            raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')+b'\n'
            need(len(raw)<=131072,'STATUS_BOUND');offset=0
            while offset<len(raw):
                check(end);count=os.write(1,raw[offset:offset+16384]);need(type(count) is int and 0<count<=min(16384,len(raw)-offset),'SHORT_WRITE');offset+=count
            check(end)
    except BaseException:raise StatusDeliveryError() from None

def run(argv=None):
    global PHASE
    PHASE='INPUT_VALIDATION'
    class Parser(argparse.ArgumentParser):
        def error(self,unused):raise Hold('ARGUMENTS')
    parser=Parser(add_help=False);parser.add_argument('--observation',required=True);parser.add_argument('--observation-sha256',required=True);parser.add_argument('--topology-review-id',type=int,required=True);parser.add_argument('--retained-renewal-timer',choices=('enable-after-reviewed-checks',),required=True);args=parser.parse_args(argv)
    bound()
    need(type(args.topology_review_id) is int and 0<args.topology_review_id<10**20 and args.retained_renewal_timer=='enable-after-reviewed-checks','REVIEW_INPUT')
    need(type(args.observation) is str and os.path.dirname(args.observation)==CAND and re.fullmatch('epoch7-observation-[0-9a-f]{16}\\.private\\.json',os.path.basename(args.observation)) and re.fullmatch('[0-9a-f]{64}',args.observation_sha256),'ARGUMENTS')
    need(args.observation==OBSERVATION_PATH and args.observation_sha256==OBSERVATION_SHA256,'OBSERVATION_BINDING')
    need(os.geteuid()==os.getegid()==0 and socket.gethostname()==HOST,'ROOT_HOST')
    need(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,'ISOLATED')
    staged=None;compiler_staged=None;module=None;prepared=None;labels=frozenset(CODES)
    try:
        with budget(STAGE_SECONDS) as end:
            PHASE='DOWNLOAD_ALL';cache=fetch_sources(end);archive=fetch_archive(end);extractor,compiler_entry,compiler_files=compiler_inputs(archive);labels=public_labels(dict(cache,extractor_source=safe_extractor_bytes()))
            PHASE='LOAD_VERIFIED_PREPARER';module=preparer(cache);check(end)
            PHASE='STAGE_COMPILER';compiler_staged=stage_compiler(archive,extractor,compiler_entry,compiler_files,end)
            PHASE='STAGE_EXACT';staged=stage(cache,end)
        PHASE='PREPARE_PRIVATE_PLAN'
        prepare_args=types.SimpleNamespace(operation='prepare',observation=args.observation,
            observation_sha256=args.observation_sha256,topology_review_id=args.topology_review_id,retained_renewal_timer=args.retained_renewal_timer)
        with module.budget() as end:
            prepared=module.run_preparation(prepare_args,end)
            need(type(prepared) is dict and prepared.get('state')=='PREPARED_NOT_ADMITTED' and prepared.get('install_admission')=='NOT_GRANTED' and prepared.get('production_resume')=='NOT_EXECUTED' and type(prepared.get('outputs')) is list and len(prepared['outputs'])==3,'PREPARATION_RESULT_SCOPE')
            retained_outputs(types.SimpleNamespace(preparation_outputs=prepared['outputs'],preparation_created_paths=[row.get('path') for row in prepared['outputs'] if type(row) is dict]))
            # The preparation summary is returned only while the fixed staging
            # inventory still equals the originally downloaded source bytes.
            PHASE='VERIFY_STAGING_AFTER_PREPARATION';stage(cache,end,allow_create=False);verify_compiler(compiler_entry,compiler_files,end)
        result={'schema':1,'state':'PREPARED_NOT_ADMITTED','staging':staged,'compiler_staging':compiler_staged,'preparation':prepared,
                'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
    except BaseException as error:
        error.delivery_preparer=module;error.delivery_labels=labels
        if compiler_staged is not None:error.compiler_staging=compiler_staged
        if type(prepared) is dict and type(prepared.get('outputs')) is list:
            error.preparation_outputs=prepared['outputs']
            error.preparation_created_paths=[row.get('path') for row in prepared['outputs'] if type(row) is dict]
        if module is not None and isinstance(error,module.CleanupError):error.delivery_cleanup_failed=True
        if staged is not None:error.delivery_created_paths=staged['created_paths'];error.delivery_staging=staged
        raise
    PHASE='DELIVER_STATUS';deliver_status(result);return 0

def entrypoint(argv=None):
    try:return run(argv)
    except StatusDeliveryError:return 2
    except BaseException as error:
        retained={'created_paths':[],'staging':None}
        try:retained=retained_staging(error)
        except BaseException:pass
        try:
            status=failure(error,PHASE,getattr(error,'delivery_preparer',None),getattr(error,'delivery_labels',frozenset(CODES)))
        except BaseException:
            status={'schema':1,'state':'HOLD','phase':PHASE if PHASE in PHASES else 'INPUT_VALIDATION',
                'preparation_phase':'UNAVAILABLE','failure_code':'DIAGNOSTIC_PROJECTION_FAILED',
                'failure_label':None,'code_locations':[],'cleanup_unknown':True,
                'install_admission':'NOT_GRANTED','production_resume':'NOT_EXECUTED'}
        status.update(retained)
        status['compiler_staging']=None
        try:
            current=getattr(error,'compiler_staging',None)
            if type(current) is dict and current.get('state') in ('NOT_STAGED','EXTRACTION_ATTEMPTED_NOT_VERIFIED','VERIFY_EXISTING_FAILED','EXTRACTED_AND_VERIFIED','VERIFIED_EXISTING') and current==compiler_summary(current['state']):status['compiler_staging']=dict(current)
        except BaseException:status['cleanup_unknown']=True
        try:status.update(retained_outputs(error))
        except BaseException:status.update(completed_outputs=[],created_output_paths=[],preparation_output_evidence='UNKNOWN',cleanup_unknown=True)
        try:deliver_status(status)
        except StatusDeliveryError:pass
        return 2

if __name__=='__main__':sys.exit(entrypoint())
