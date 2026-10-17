"""Read models for the existing community workbench; no parallel business store."""
import csv
import io
from scripts.community_merchant_contract import scope,valid_id
from scripts.community_order_provider_projection import provider_evidence


def orders_page(db,identity,limit,after_id,status):
    t,m,s=scope(identity)
    if (type(limit) is not int or not 1<=limit<=200 or type(after_id) is not str
            or after_id and not valid_id(after_id) or type(status) is not str
            or status not in ('ALL','PENDING','SUCCESS','FAILED','CANCELLED','REFUNDED')):
        raise ValueError('INVALID_ORDER_PAGE')
    sql='SELECT reference,amount_minor,currency,state FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference>?'
    args=[t,m,s,after_id]
    if status!='ALL':sql+=' AND state=?';args.append(status)
    rows=db.execute(sql+' ORDER BY reference LIMIT ?',(*args,limit+1)).fetchall()
    records=[]
    for r in rows[:limit]:
        record=dict(zip(('reference','amount_minor','currency','state'),r))
        verified=provider_evidence(db,identity,r[0]) is not None
        record.update(simulation_only=not verified,provider_order_verified=verified,provider_payment_verified=verified and record['state'] in ('SUCCESS','REFUNDED'))
        records.append(record)
    return dict(orders=records,
                has_more=len(rows)>limit,next_cursor=rows[limit-1][0] if len(rows)>limit else None,
                simulation_only=all(r['simulation_only'] for r in records),provider_settlement_verified=False)


def orders_export(db,identity,limit,after_id,status):
    result=orders_page(db,identity,limit,after_id,status)
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(('reference','amount_minor','currency','state','simulation_only','provider_settlement_verified'))
    for row in result['orders']:
        def cell(value):
            value=str(value)
            return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value
        writer.writerow([cell(row[k]) for k in ('reference','amount_minor','currency','state')]+[str(row['simulation_only']).lower(),'false'])
    return dict(csv=out.getvalue(),filename='community-orders-page.csv',
                has_more=result['has_more'],next_cursor=result['next_cursor'],
                row_count=len(result['orders']),simulation_only=result['simulation_only'],provider_settlement_verified=False)


def merchant_settings(db,identity):
    t,m,s=scope(identity)
    row=db.execute('SELECT name,description,contact,status,version FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?',(t,m,s)).fetchone()
    items=db.execute('SELECT item_id,name,status,sort_order,version FROM catalog_items WHERE tenant_id=? AND merchant_id=? AND store_id=? ORDER BY item_id LIMIT 200',(t,m,s)).fetchall()
    return dict(profile=None if row is None else dict(zip(('name','description','contact','status','version'),row)),
                items=[dict(zip(('id','name','status','sort','version'),r)) for r in items],
                simulation_only=True,provider_settlement_verified=False)


def order_detail(orders,refunds,identity,reference):
    """Scoped order history and original refund-preview journal, no money mutation."""
    from scripts.community_order_store import state
    if not valid_id(reference):raise ValueError('INVALID_REFERENCE')
    t,m,s=scope(identity)
    order=state(orders,identity,reference)
    events=orders.execute('SELECT event_id,from_state,to_state,evidence_source FROM order_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=? ORDER BY event_id LIMIT 201',(t,m,s,reference)).fetchall()
    refund_rows=refunds.execute('SELECT event_id,amount_minor,evidence_kind FROM refund_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=? ORDER BY event_id LIMIT 201',(t,m,s,reference)).fetchall()
    total=refunds.execute('SELECT COALESCE(SUM(amount_minor),0) FROM refund_events WHERE tenant_id=? AND merchant_id=? AND store_id=? AND reference=?',(t,m,s,reference)).fetchone()[0]
    if not 0<=total<=order['amount_minor']:raise ValueError('INVALID_REFUND_PREVIEW_TOTAL')
    return dict(reference=reference,order=order,
        events=[dict(zip(('event_id','from_state','to_state','evidence_source'),r)) for r in events[:200]],
        events_truncated=len(events)>200,
        refund_previews=[dict(zip(('event_id','amount_minor','evidence_kind'),r)) for r in refund_rows[:200]],
        refund_history_truncated=len(refund_rows)>200,refund_preview_total_minor=total,
        remaining_preview_minor=order['amount_minor']-total,
        simulation_only=provider_evidence(orders,identity,reference) is None,
        provider_order_verified=provider_evidence(orders,identity,reference) is not None,
        provider_payment_verified=provider_evidence(orders,identity,reference) is not None and order['state'] in ('SUCCESS','REFUNDED'),
        provider_refund_executed=False,provider_split_executed=False)


def order_summary(db,identity):
    """Original order totals, with signed provider observations kept distinct."""
    t,m,s=scope(identity)
    counts={name:0 for name in ('PENDING','SUCCESS','FAILED','CANCELLED','REFUNDED')}
    verified_counts=dict(counts)
    total=verified_paid=verified_refunds=0
    import json
    for ref,amount,status in db.execute('SELECT reference,amount_minor,state FROM orders WHERE tenant_id=? AND merchant_id=? AND store_id=?',(t,m,s)):
        counts[status]+=1;total+=amount
        if provider_evidence(db,identity,ref) is not None:
            verified_counts[status]+=1
            if status in ('SUCCESS','REFUNDED'):verified_paid+=amount
    for raw, in db.execute('SELECT evidence_source FROM order_events WHERE tenant_id=? AND merchant_id=? AND store_id=?',(t,m,s)):
        try:event=json.loads(raw)
        except (ValueError,TypeError):continue
        if type(event) is dict and event.get('source')=='WECHAT_SIGNED_REFUND_RESULT':verified_refunds+=event['refund_minor']
    return dict(counts=counts,order_total_minor=total,provider_verified_counts=verified_counts,
        provider_paid_observations_minor=verified_paid,provider_refund_observations_minor=verified_refunds,
        provider_net_observations_minor=verified_paid-verified_refunds,
        simulation_only=not any(verified_counts.values()),provider_settlement_verified=False,real_revenue_minor=None)
