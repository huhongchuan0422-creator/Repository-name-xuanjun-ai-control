const assert=require('node:assert/strict');const create=require('./center-web-port');const bridge=require('./session-bridge');
const port=create();const session=bridge(port);let revoked=0,finalized=0;
session.attachPage({customerSessionRevoked(){throw Error('SYNTHETIC_BROKEN_PAGE')}});
session.attachPage({customerSessionRevoked(){revoked++}});
port.onRevoke(()=>{throw Error('SYNTHETIC_BROKEN_LISTENER')});port.onRevoke(()=>{finalized++});
assert.doesNotThrow(()=>port.clear());assert.equal(revoked,1);assert.equal(finalized,1);assert.equal(port.isAuthenticated(),false);console.log('PASS: throwing page/listener does not interrupt remaining revocation and final cleanup');
