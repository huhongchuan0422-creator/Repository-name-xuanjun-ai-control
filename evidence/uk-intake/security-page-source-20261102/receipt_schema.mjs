/** Original shared-state DB only; call inside original managed write admission. */
import {MIGRATION_SQL} from './durable_receipt_adapter.mjs';
const columns=['request_id','owner_id','session_binding','purpose','ui_version','created_at_ms','expires_at_ms','status','committed_at_ms'];
export function ensureAcceptanceReceiptSchema(db){
 const found=db.prepare("SELECT sql FROM sqlite_master WHERE type='table' AND name='safe_input_request_receipts'").get();
 if(!found){db.exec(MIGRATION_SQL);return;}
 const normalized=s=>s.replace(/IF\s+NOT\s+EXISTS\s+/gi,'').replace(/\s+/g,' ').replace(/;\s*$/,'').trim();
 if(normalized(found.sql)!==normalized(MIGRATION_SQL))throw Error('RECEIPT_SCHEMA_MISMATCH');
 const info=db.prepare('PRAGMA table_info(safe_input_request_receipts)').all();
 if(info.length!==columns.length||info.some((c,i)=>c.name!==columns[i])||info[0].pk!==1)throw Error('RECEIPT_SCHEMA_MISMATCH');
}
