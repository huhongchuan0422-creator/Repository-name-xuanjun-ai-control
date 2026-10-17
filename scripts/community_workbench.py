"""Read models for the existing community workbench; no parallel business store."""
import csv
import io
from scripts.community_merchant_contract import scope,valid_id


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
    return dict(orders=[dict(zip(('reference','amount_minor','currency','state'),r)) for r in rows[:limit]],
                has_more=len(rows)>limit,next_cursor=rows[limit-1][0] if len(rows)>limit else None,
                simulation_only=True,provider_settlement_verified=False)


def orders_export(db,identity,limit,after_id,status):
    result=orders_page(db,identity,limit,after_id,status)
    out=io.StringIO(newline='');writer=csv.writer(out)
    writer.writerow(('reference','amount_minor','currency','simulation_state','provider_settlement_verified'))
    for row in result['orders']:
        def cell(value):
            value=str(value)
            return "'"+value if value.lstrip().startswith(('=','+','-','@','\t','\r')) else value
        writer.writerow([cell(row[k]) for k in ('reference','amount_minor','currency','state')]+['false'])
    return dict(csv=out.getvalue(),filename='community-simulated-orders-page.csv',
                has_more=result['has_more'],next_cursor=result['next_cursor'],
                row_count=len(result['orders']),simulation_only=True,provider_settlement_verified=False)


def merchant_settings(db,identity):
    t,m,s=scope(identity)
    row=db.execute('SELECT name,description,contact,status,version FROM merchant_profiles WHERE tenant_id=? AND merchant_id=? AND store_id=?',(t,m,s)).fetchone()
    items=db.execute('SELECT item_id,name,status,sort_order,version FROM catalog_items WHERE tenant_id=? AND merchant_id=? AND store_id=? ORDER BY item_id LIMIT 200',(t,m,s)).fetchall()
    return dict(profile=None if row is None else dict(zip(('name','description','contact','status','version'),row)),
                items=[dict(zip(('id','name','status','sort','version'),r)) for r in items],
                simulation_only=True,provider_settlement_verified=False)
