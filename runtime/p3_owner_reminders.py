"""Offline P3 reminder increment over the existing ledger/events/outbox.

No transport, daemon, credentials, approval action or database bootstrap.
All event readers and enabled transports are trusted host integrations, never
callbacks supplied by a task body. Real ChatGPT response input is not supplied.
"""
import json
import math
import re
from p3_lifecycle import digest,P3ContinuousLoop

DESTINATION='P3_OWNER_REMINDER'
MESSAGE='您有待确认或停滞事项，请查看原工作入口。电话接通不代表批准。'
DEFAULT_BANDS=((2,100),(5,60),(10,40),(None,30))
STABILITY_SECONDS=60


def identifier(v):
    return isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}',v) is not None


class OwnerReminders:
    def __init__(self,ledger,task_to_blocker,event_reader=None,adapter=None,enabled=False,ratio_bands=None,eligibility_reader=None):
        if (not isinstance(task_to_blocker,dict) or not task_to_blocker
                or any(k not in ledger.p3_pins or not identifier(v) or v=='portfolio-progress' for k,v in task_to_blocker.items())):
            raise ValueError('EXACT_EXISTING_TASK_BLOCKER_MAPPING_REQUIRED')
        if ledger.p3_supervisor is None:raise ValueError('ORIGINAL_OUTBOX_REQUIRED')
        self.ledger=ledger;self.supervisor=ledger.p3_supervisor
        self.mapping=dict(task_to_blocker);self.anchor=sorted(task_to_blocker)[0]
        self.reader=event_reader;self.adapter=adapter;self.enabled=enabled is True
        self.eligibility_reader=eligibility_reader
        self.bands=self.validate_bands(DEFAULT_BANDS if ratio_bands is None else ratio_bands)

    @staticmethod
    def validate_bands(bands):
        if not isinstance(bands,(list,tuple)) or not 1<=len(bands)<=20:raise ValueError('INVALID_RATIO_BANDS')
        result=[];previous=0;percent=100
        for index,item in enumerate(bands):
            if not isinstance(item,(list,tuple)) or len(item)!=2:raise ValueError('INVALID_RATIO_BAND')
            maximum,p=item
            if type(p) is not int or not 1<=p<=100 or p>percent:raise ValueError('INVALID_RATIO_PERCENT')
            if maximum is None:
                if index!=len(bands)-1:raise ValueError('UNBOUNDED_BAND_MUST_BE_LAST')
            elif type(maximum) is not int or maximum<=previous or index==len(bands)-1:
                raise ValueError('SORTED_TOTAL_RATIO_BANDS_REQUIRED')
            if maximum is not None:previous=maximum
            percent=p;result.append((maximum,p))
        if result[-1][0] is not None:raise ValueError('UNBOUNDED_BAND_REQUIRED')
        return tuple(result)

    def required_stalled(self,n):
        if type(n) is not int or n<0:raise ValueError('INVALID_POPULATION')
        if n==0:return 0,0
        for maximum,percent in self.bands:
            if maximum is None or n<=maximum:return (n*percent+99)//100,percent

    def _assert_config(self,db):
        pin=digest(self.mapping)
        row=db.execute("SELECT details FROM events WHERE event='P3_REMINDER_CONFIG' ORDER BY id LIMIT 1").fetchone()
        if row is None:
            self.ledger._event(db,self.anchor,'P3_REMINDER_CONFIG',self.ledger._now(),{'mapping_sha256':pin,'policy_sha256':digest(self.bands),'schema':2})
        elif json.loads(row['details'])!={'mapping_sha256':pin,'policy_sha256':digest(self.bands),'schema':2}:
            raise ValueError('REMINDER_MAPPING_CHANGED_RECONCILIATION_REQUIRED')

    def _events(self,db,kind):
        return [(r['id'],r['task_id'],json.loads(r['details'])) for r in db.execute(
            'SELECT id,task_id,details FROM events WHERE event=? ORDER BY id',(kind,))]

    def _requests(self,db):
        result={}
        for unused,task_id,e in self._events(db,'P3_CONFIRMATION_INPUT'):
            if task_id not in self.mapping:continue
            rid=e['request_id']
            if e['kind']=='confirmation_created':
                result[rid]=dict(e,closed=False,ack_seen=False)
            elif rid in result:
                if e['kind'] in ('confirmation_responded','confirmation_cancelled'):result[rid]['closed']=True
                if e['kind']=='ack_seen':result[rid]['ack_seen']=True
        return result

    def ingest(self,evidence_ref):
        if not identifier(evidence_ref) or not callable(self.reader):
            raise ValueError('CONFIRMATION_INPUT_NOT_CONNECTED')
        try:e=self.reader(evidence_ref)
        except Exception:raise ValueError('CONFIRMATION_INPUT_UNAVAILABLE')
        keys={'kind','event_id','request_id','task_id','blocker_id','occurred_at','verified'}
        if (not isinstance(e,dict) or set(e)!=keys or e.get('verified') is not True
                or e.get('kind') not in ('confirmation_created','confirmation_responded','confirmation_cancelled','ack_seen')
                or any(not identifier(e.get(k)) for k in ('event_id','request_id','task_id','blocker_id'))
                or e['task_id'] not in self.mapping or self.mapping[e['task_id']]!=e['blocker_id']
                or type(e.get('occurred_at')) not in (int,float) or not math.isfinite(e['occurred_at'])
                or e['occurred_at']<0 or e['occurred_at']>self.ledger._now()):
            raise ValueError('CONFIRMATION_EVENT_NOT_VERIFIED')
        e=dict(e)
        if e['kind']=='confirmation_created':e['deadline_at']=e['occurred_at']+300
        with self.ledger._transaction() as db:
            self.ledger._scope(e['task_id'])
            self._assert_config(db)
            for unused,task,old in self._events(db,'P3_CONFIRMATION_INPUT'):
                if old['event_id']==e['event_id']:
                    if old!=e:raise ValueError('EVENT_ID_CONFLICT')
                    return {'duplicate':True,'approval_performed':False}
            requests=self._requests(db);previous=requests.get(e['request_id'])
            if e['kind']=='confirmation_created':
                if previous is not None:raise ValueError('REQUEST_ID_ALREADY_EXISTS')
            elif (previous is None or previous['task_id']!=e['task_id']
                    or previous['blocker_id']!=e['blocker_id'] or e['occurred_at']<previous['occurred_at']):
                raise ValueError('EXACT_REQUEST_ID_REQUIRED')
            self.ledger._event(db,e['task_id'],'P3_CONFIRMATION_INPUT',self.ledger._now(),e)
            # Cancellation uses the same transaction as authenticated reply input.
            self._scan(db)
        return {'duplicate':False,'approval_performed':False}

    def _eligible(self,db,row):
        if row['state'] in ('DONE','FAILED','CANCELLED','FROZEN'):return 'EXCLUDED_TERMINAL_OR_FROZEN'
        try:self.ledger._bound(db,row['id'])
        except ValueError:return 'UNKNOWN'
        run=db.execute('SELECT effects,native_state FROM supervised_runs WHERE task_id=?',(row['id'],)).fetchone()
        if run is not None and (run['effects']=='UNKNOWN' or run['native_state']=='UNKNOWN'):return 'UNKNOWN'
        if callable(self.eligibility_reader):
            try:e=self.eligibility_reader(row['id'])
            except Exception:return 'UNKNOWN'
            if (not isinstance(e,dict) or set(e)!={'task_id','fence','state','verified'}
                    or e['verified'] is not True or e['task_id']!=row['id']
                    or type(e['fence']) is not int or e['fence']!=row['fence']
                    or e['state'] not in ('EXPECTED','EXTERNAL_WAIT','FROZEN','UNKNOWN')):return 'UNKNOWN'
            return e['state']
        if row['state']=='RUNNING':return 'EXPECTED'
        if row['state']=='PENDING':
            try:
                unused,graph=self.ledger._dag(db,focus=row['id'],quarantine=False)
                return 'EXPECTED' if all(db.execute('SELECT state FROM tasks WHERE id=?',(d,)).fetchone()['state']=='DONE' for d in graph[row['id']]) else 'EXTERNAL_WAIT'
            except (ValueError,PermissionError):return 'UNKNOWN'
        if row['state']=='WAITING_HUMAN':
            # The original 10-minute watchdog HOLD is not an intentional freeze.
            # Count it only when native effect classification is known and the
            # latest durable reason is specifically missing real progress.
            e=db.execute("SELECT event FROM events WHERE task_id=? AND event IN ('P3_NO_REAL_PROGRESS','P3_UNCERTAIN_EXIT_HOLD','EXECUTION_FINISHED','OWNER_APPROVE','OWNER_REJECT') ORDER BY id DESC LIMIT 1",(row['id'],)).fetchone()
            if e is not None and e['event']=='P3_NO_REAL_PROGRESS' and run is not None:return 'EXPECTED'
        if row['state'] in ('WAITING_HUMAN','PAUSED_RESOURCE'):return 'EXTERNAL_WAIT'
        return 'UNKNOWN'

    def _ratio_due(self,db,observations,excluded):
        now=self.ledger._now();n=len(observations);required,percent=self.required_stalled(n)
        population={'members':sorted(observations),'policy_sha256':digest(self.bands)}
        snapshots=self._events(db,'P3_PROGRESS_POPULATION')
        previous=snapshots[-1][2] if snapshots else None
        if previous is None or previous['population']!=population:
            previous={'population':population,'observed_at':now}
            self.ledger._event(db,self.anchor,'P3_PROGRESS_POPULATION',now,previous)
        stalled={t:v['progress_id'] for t,v in observations.items() if v['last_progress_at'] is not None and now-v['last_progress_at']>=1200}
        candidates=self._events(db,'P3_PROGRESS_THRESHOLD_CANDIDATE')
        candidate=candidates[-1][2] if candidates else None
        if candidate is not None and candidate['state']=='OPEN':
            unchanged=sum(stalled.get(t)==identity for t,identity in candidate['cohort'].items())
            if unchanged<candidate['required_count']:
                self.ledger._event(db,self.anchor,'P3_PROGRESS_THRESHOLD_CANDIDATE',now,dict(candidate,state='CLOSED'))
                candidate=None
        else:candidate=None
        if candidate is None and n and len(stalled)>=required:
            # A membership-sensitive threshold gets at most 60 seconds of
            # observation. Once qualified, its unchanged stalled cohort is
            # latched: unrelated task churn cannot restart/dilute this timer.
            wait=0 if now-previous['observed_at']>=STABILITY_SECONDS else STABILITY_SECONDS
            candidate={'state':'OPEN','cohort':stalled,'required_count':required,'n_at_qualification':n,
                'percent_at_qualification':percent,'qualified_at':now,'notify_at':now+wait}
            self.ledger._event(db,self.anchor,'P3_PROGRESS_THRESHOLD_CANDIDATE',now,candidate)
        unknown=sorted(set(t for t,v in observations.items() if v['last_progress_at'] is None)
                       |set(t for t,reason in excluded.items() if reason=='UNKNOWN'))
        visibility={'state':'UNKNOWN' if unknown else 'KNOWN','task_ids':unknown,
                    'counts_as_stalled':False,'phone_reminder':False}
        notices=self._events(db,'P3_PROGRESS_OBSERVABILITY')
        if not notices or notices[-1][2]!=visibility:
            self.ledger._event(db,self.anchor,'P3_PROGRESS_OBSERVABILITY',now,visibility)
        return bool(candidate and now>=candidate['notify_at']),stalled,{
            'observability':visibility,'eligible_count':n,'stalled_count':len(stalled),'required_count':required,'percent':percent,
            'excluded':excluded,'unknown_progress_tasks':[t for t,v in observations.items() if v['last_progress_at'] is None],'latched_qualification':candidate}

    def _groups(self,db):
        now=self.ledger._now();requests=[];overdue=[];observations={};excluded={}
        for rid,r in self._requests(db).items():
            if not r['closed']:
                requests.append(rid)
                if now>=r['deadline_at']:overdue.append(rid)
        for task_id in self.mapping:
            row=db.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
            status='UNKNOWN' if row is None else self._eligible(db,row)
            if status!='EXPECTED':excluded[task_id]=status;continue
            origin=None;last_output=None;seen_output=set();progress_id=None
            for e in db.execute("SELECT id,event,created,details FROM events WHERE task_id=? AND event IN ('EXECUTION_CLAIMED','P3_REAL_PROGRESS') ORDER BY id",(task_id,)):
                if e['event']!='P3_REAL_PROGRESS':
                    if origin is None:origin=e['created'];progress_id=digest(['origin',task_id,e['id']])
                else:
                    d=json.loads(e['details']);identity=(d['kind'],d['evidence_sha256'])
                    if identity not in seen_output:
                        seen_output.add(identity)
                        if last_output is None or e['created']>=last_output:
                            last_output=e['created'];progress_id=digest(identity)
            if origin is None:
                start=db.execute("SELECT created_at,event_key FROM supervision_events WHERE task_id=? AND kind='STARTED' ORDER BY sequence LIMIT 1",(task_id,)).fetchone()
                if start is not None:origin=start['created_at'];progress_id=digest(['start',start['event_key']])
            last=last_output if origin is None else origin if last_output is None else max(origin,last_output)
            # READY queues belong to N, but no real execution origin is UNKNOWN
            # progress, never fabricated 20-minute stopped-work evidence.
            observations[task_id]={'last_progress_at':last,'progress_id':progress_id}
        progress_due,stalled,diagnostics=self._ratio_due(db,observations,excluded)
        # One generic Owner-attention episode coalesces all covered blockers and
        # portfolio reasons. It never emits overlapping local + portfolio calls.
        return {'owner-attention':{'requests':requests,'overdue':overdue,'active':list(observations),
            'stalled':list(stalled),'progress_due':progress_due,'diagnostics':diagnostics}}

    @staticmethod
    def _due(group):
        return bool(group.get('overdue')) or group.get('progress_due') is True

    def _episodes(self,db):
        opened={}
        for unused,task,e in self._events(db,'P3_REMINDER_EPISODE'):
            if task!=self.anchor:continue
            if e['state']=='OPEN':opened[e['blocker_id']]=e
            elif opened.get(e['blocker_id'],{}).get('episode_id')==e['episode_id']:opened.pop(e['blocker_id'],None)
        return opened

    def _cancel(self,db,episode_id):
        for row in db.execute("SELECT e.event_key,e.details FROM supervision_events e JOIN supervision_delivery d ON d.event_key=e.event_key WHERE e.kind='P3_OWNER_REMINDER' AND d.destination=?",(DESTINATION,)).fetchall():
            if json.loads(row['details']).get('episode_id')==episode_id:
                # SENDING/UNCERTAIN/ACKED may already have an external effect.
                # Never turn those into safe-to-retry or claim a call was recalled.
                db.execute("UPDATE supervision_delivery SET state='CANCELLED' WHERE event_key=? AND destination=? AND state IN ('PENDING','CLAIMED','DELIVERY_FAILED')",(row['event_key'],DESTINATION))

    def _scan(self,db):
        self._assert_config(db)
        now=self.ledger._now();groups=self._groups(db);episodes=self._episodes(db);queued=[]
        for blocker in episodes:
            groups.setdefault(blocker,{'requests':[],'overdue':[],'active':[],'stalled':[]})
        for blocker,g in groups.items():
            reasons=self._reasons(g)
            all_attempts=[e for unused,task,e in self._events(db,'P3_REMINDER_ATTEMPT')]
            absent=set(e['attempt_sha256'] for unused,task,e in self._events(db,'P3_REMINDER_NOT_SENT_VERIFIED'))
            # ACK covers and UNKNOWN reserves; exact proven NOT_SENT has no
            # external effect and must not swallow a later eligible reminder.
            covered=set(r for e in all_attempts if digest(e) not in absent for r in e.get('covered_reasons',[]))
            uncovered=reasons-covered
            ep=episodes.get(blocker)
            if ep is not None:
                key=self.anchor+':inventory:'+ep['episode_id']
                attempts=[e for e in all_attempts if e['event_key']==key]
                delivery=db.execute('SELECT state FROM supervision_delivery WHERE event_key=? AND destination=?',(key,DESTINATION)).fetchone()
                if attempts:
                    # Unknown attempts retain the original outbox identity until
                    # exact reconciliation. ACK may admit genuinely new reasons.
                    replace=bool(delivery and delivery['state']=='ACKED' and uncovered)
                    close=not bool(reasons & set(attempts[-1].get('covered_reasons',[])))
                else:
                    replace=False
                    close=not bool(uncovered & set(ep.get('reason_ids',[])))
                if close or replace:
                    self._cancel(db,ep['episode_id'])
                    self.ledger._event(db,self.anchor,'P3_REMINDER_EPISODE',now,dict(ep,state='CLOSED'))
                    ep=None
            if ep is None and uncovered:
                seq=db.execute("SELECT COUNT(*) FROM events WHERE task_id=? AND event='P3_REMINDER_EPISODE'",(self.anchor,)).fetchone()[0]
                ep={'blocker_id':blocker,'episode_id':digest([self.anchor,blocker,seq]),'state':'OPEN','reason_ids':sorted(uncovered)}
                self.ledger._event(db,self.anchor,'P3_REMINDER_EPISODE',now,ep)
            if ep is not None and reasons:
                key=self.supervisor._event(db,self.anchor,'P3_OWNER_REMINDER',self._payload(ep['episode_id']),
                    destinations=(DESTINATION,),dedupe_key=ep['episode_id'])
                queued.append(key)
        return queued

    @staticmethod
    def _reasons(group):
        reasons=set('confirmation:'+r for r in group.get('overdue',[]))
        candidate=group.get('diagnostics',{}).get('latched_qualification')
        if group.get('progress_due') and candidate:
            reasons.add('progress:'+digest(candidate['cohort']))
        return reasons

    @staticmethod
    def _payload(episode_id):
        return {'episode_id':episode_id,'message':MESSAGE,'phone_preferred':True,'approval_performed':False}

    def scan(self):
        with self.ledger._transaction() as db:
            self.ledger._scope(self.anchor)
            queued=self._scan(db)
            diagnostics=self._groups(db)['owner-attention']['diagnostics']
            return {'queued':queued,'progress_observation':diagnostics,'external_delivery_performed':False}

    def _begin_send(self,claim,binding):
        if not self._binding_valid(binding):raise ValueError('VERIFIED_DELIVERY_BINDING_REQUIRED')
        with self.ledger._transaction() as db:
            self._scan(db)
            row=db.execute('SELECT * FROM supervision_delivery WHERE event_key=? AND destination=?',
                           (claim['event_key'],DESTINATION)).fetchone()
            if row is None or row['state']!='CLAIMED':return None
            if (not self.supervisor._claim_matches(row,claim) or row['claim_until']<=self.ledger._now()
                    or row['send_attempts']>=self.supervisor.max_delivery_attempts):raise ValueError('REMINDER_CLAIM_LOST')
            event=db.execute('SELECT details FROM supervision_events WHERE event_key=?',(claim['event_key'],)).fetchone()
            payload=json.loads(event['details'])
            # Original NOT_SENT reconciliation may authorize a transport retry
            # after this reminder episode was closed. Revalidate user intent,
            # not merely the outbox's CLAIMED state, at every send boundary.
            groups=self._groups(db);eligible=False
            for blocker,episode in self._episodes(db).items():
                g=groups.get(blocker,{})
                if (episode['episode_id']==payload.get('episode_id')
                        and self._due(g)):
                    eligible=True;break
            if not eligible:
                self._cancel(db,payload.get('episode_id'))
                return None
            attempts=[e for unused,task,e in self._events(db,'P3_REMINDER_ATTEMPT')
                      if e['event_key']==claim['event_key']]
            if attempts:
                previous=attempts[-1]
                absences=[e for unused,task,e in self._events(db,'P3_REMINDER_NOT_SENT_VERIFIED')]
                if not any(e['attempt_sha256']==digest(previous) for e in absences):
                    db.execute("UPDATE supervision_delivery SET state='HELD',last_error='BOUND_NOT_SENT_PROOF_REQUIRED' WHERE event_key=? AND destination=?",(claim['event_key'],DESTINATION))
                    return {'hold':'BOUND_NOT_SENT_PROOF_REQUIRED'}
            attempt={k:claim[k] for k in ('event_key','claim_token','claim_attempt','claim_epoch','authority_fence','authority_epoch')}
            attempt.update(covered_reasons=sorted(self._reasons(groups['owner-attention'])),covered_requests=sorted(groups['owner-attention'].get('overdue',[])),binding=binding,external_notification_id=digest(['P3_OWNER_NOTIFICATION',claim['event_key']]))
            self.ledger._event(db,self.anchor,'P3_REMINDER_ATTEMPT',self.ledger._now(),attempt)
            payload['external_notification_id']=attempt['external_notification_id']
            payload['attempt_nonce']=digest(attempt)
            # Existing original outbox boundary, atomically after cancellation check.
            db.execute("UPDATE supervision_delivery SET state='SENDING',send_attempts=send_attempts+1,sent_at=? WHERE event_key=? AND destination=?",
                       (self.ledger._now(),claim['event_key'],DESTINATION))
            return payload

    @staticmethod
    def _binding_valid(value):
        return (isinstance(value,dict) and set(value)=={'route','provider_binding','destination_binding','verified'}
                and value['route'] in ('PHONE','FALLBACK') and value['verified'] is True
                and all(isinstance(value[k],str) and re.fullmatch('[0-9a-f]{64}',value[k]) is not None
                        for k in ('provider_binding','destination_binding')))

    def reconcile_unknown(self,event_key,lookup,claimant='p3-reminder-reconciler'):
        """Lookup ONLY the persisted attempt's actual route/provider/destination.

        External callback receives no task/request/internal event identity. A
        channel-mismatched NOT_SENT cannot authorize any subsequent attempt.
        """
        if not callable(lookup):raise ValueError('BOUND_PROVIDER_LOOKUP_REQUIRED')
        with self.ledger._transaction() as db:
            attempts=[e for unused,task,e in self._events(db,'P3_REMINDER_ATTEMPT') if e['event_key']==event_key]
            if not attempts:raise ValueError('PERSISTED_ATTEMPT_BINDING_REQUIRED')
            attempt=attempts[-1]
        def bound_lookup(unused_destination,unused_identity):
            try:result=lookup(attempt['binding'],attempt['external_notification_id'],digest(attempt))
            except Exception:return 'UNKNOWN'
            if (not isinstance(result,dict) or result.get('verified') is not True
                    or result.get('binding')!=attempt['binding']
                    or result.get('notification_id')!=attempt['external_notification_id']
                    or result.get('attempt_nonce')!=digest(attempt)):return 'UNKNOWN'
            if result.get('status')=='SENT' and identifier(result.get('receipt_id')):return result['receipt_id']
            if result.get('status')!='NOT_SENT' or not identifier(result.get('proof_id')):return 'UNKNOWN'
            with self.ledger._transaction() as db:
                self.ledger._event(db,self.anchor,'P3_REMINDER_NOT_SENT_VERIFIED',self.ledger._now(),
                    {'attempt_sha256':digest(attempt),'proof_id':result['proof_id']})
            proof={k:attempt[k] for k in ('claim_token','claim_attempt','claim_epoch','authority_fence','authority_epoch')}
            proof.update(status='NOT_SENT',proof_id=result['proof_id'],delivery_identity=event_key)
            return proof
        return self.supervisor.reconcile_delivery(event_key,DESTINATION,claimant,bound_lookup)

    def send_one(self,claimant='p3-reminder'):
        if not self.enabled or self.adapter is None:
            return {'state':'CAPABILITY_UNAVAILABLE','dial_attempted':False,'approval_performed':False}
        # Host adapter must prove a configured route BEFORE the external boundary.
        try:binding=self.adapter.route()
        except Exception:return {'state':'CAPABILITY_UNAVAILABLE','dial_attempted':False,'approval_performed':False}
        if not self._binding_valid(binding):
            return {'state':'CAPABILITY_UNAVAILABLE','dial_attempted':False,'approval_performed':False}
        claim=self.supervisor.claim_delivery(claimant,DESTINATION)
        if claim is None:return {'state':'NO_PENDING_REMINDER','dial_attempted':False,'approval_performed':False}
        payload=self._begin_send(claim,binding)
        if payload is None:return {'state':'CANCELLED','dial_attempted':False,'approval_performed':False}
        if 'hold' in payload:return {'state':payload['hold'],'dial_attempted':False,'approval_performed':False}
        external_id=payload['external_notification_id']
        try:
            receipt=self.adapter.send(external_id,MESSAGE,binding,payload['attempt_nonce'])
            if (not isinstance(receipt,dict) or set(receipt)!={'notification_id','receipt_id','binding','attempt_nonce','accepted'}
                    or receipt['notification_id']!=external_id or receipt['binding']!=binding or receipt['attempt_nonce']!=payload['attempt_nonce']
                    or receipt['accepted'] is not True or not identifier(receipt['receipt_id'])):
                raise ValueError('INVALID_PROVIDER_ACK')
            self.supervisor.ack_delivery(claim,receipt['receipt_id'])
        except Exception:
            self.supervisor.mark_delivery_uncertain(claim,'PROVIDER_RESULT_UNKNOWN')
            return {'state':'UNKNOWN_NO_REDIAL','dial_attempted':binding['route']=='PHONE','external_delivery_attempted':True,'route':binding['route'],'approval_performed':False}
        return {'state':'PROVIDER_ACKED_NOT_APPROVAL','dial_attempted':binding['route']=='PHONE','external_delivery_attempted':True,'route':binding['route'],'approval_performed':False}


class ReminderIntegratedLoop(P3ContinuousLoop):
    """Optional hook in the SAME admitted loop; never a second scheduler/daemon."""
    def __init__(self,ledger,*args,reminders=None,**kwargs):
        if not isinstance(reminders,OwnerReminders) or reminders.ledger is not ledger:
            raise ValueError('SAME_LEDGER_REMINDER_HOOK_REQUIRED')
        self.reminders=reminders
        super().__init__(ledger,*args,**kwargs)

    def tick(self):
        result=super().tick()
        if result.get('stopping'):return result
        try:
            scan=self.reminders.scan()
            delivery=self.reminders.send_one()
            result['owner_reminder']={'scan':scan,'delivery':delivery}
        except Exception:
            # Original execution result/next dependency remains durable. Do not
            # publish adapter diagnostics or stop independent authorized work.
            result['owner_reminder']={'state':'REMINDER_HOLD','approval_performed':False}
        return result
