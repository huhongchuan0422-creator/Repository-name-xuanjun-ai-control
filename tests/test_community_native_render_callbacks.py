"""Synthetic adapter lifecycle only; product and provider actions are untouched."""
import pathlib,subprocess,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class NativeRenderCallbacks(unittest.TestCase):
 def test_nested_render_callbacks_settle_before_evidence_and_reject_infinite_updates(self):
  script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('tests/community_mini_native_render.cjs','utf8');
const start=source.indexOf('const adapter=')+14,end=source.indexOf(';\nconst script=',start),adapter=JSON.parse(source.slice(start,end));
const draw=adapter.slice(adapter.indexOf('async function draw()'),adapter.indexOf('async function load('));
const method=adapter.match(/setData\(p,afterRender\)\{[^}]+\}/)[0];
const setup=`const renderCallbacks=[];let renderDirty=false;const snapshots=[],acks=[];const active={name:'test',route:'test',data:{value:0},${method}};const calls=[],files={'pages/test/index.wxml':'x'};function nativeCss(){return '';}function renderNative(x){snapshots.push(x.data.value);}const document={createElement:()=>({}),body:{prepend(){}}},window={innerWidth:390};${draw}`;
async function evaluate(body){return vm.runInNewContext(setup+`async function test(){${body}}test();`,{structuredClone});}
(async()=>{
 const nested=await evaluate(`active.setData({value:1},()=>{acks.push(snapshots.at(-1));active.setData({value:2},()=>{acks.push(snapshots.at(-1));active.setData({value:3});});});await draw();return {snapshots,acks,evidence:window.__nativeEvidence.state.value,callbacks:renderCallbacks.length};`);
 assert.deepEqual(JSON.parse(JSON.stringify(nested)),{snapshots:[1,2,3],acks:[1,2],evidence:3,callbacks:0});
 const rapid=await evaluate(`active.setData({value:'A'});active.setData({value:'AB'});await draw();return window.__nativeEvidence.state.value;`);assert.equal(rapid,'AB');
 await assert.rejects(()=>evaluate(`const repeat=()=>active.setData({value:1},repeat);repeat();await draw();`),/NATIVE_RENDER_CALLBACK_DID_NOT_SETTLE/);
 console.log('PASS_RENDER_CALLBACK_ORDER_RAPID_INPUT_AND_BOUNDED_FAILURE');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
  result=subprocess.run(['node','-e',script],cwd=ROOT,text=True,capture_output=True,timeout=15)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  self.assertIn('PASS_RENDER_CALLBACK_ORDER_RAPID_INPUT_AND_BOUNDED_FAILURE',result.stdout)

 def test_sceneless_profile_fixture_reaches_visible_save_and_original_draft_handlers(self):
  script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync('tests/community_mini_native_render.cjs','utf8');
const start=source.indexOf('const adapter=')+14,end=source.indexOf(';\nconst script=',start);let adapter=JSON.parse(source.slice(start,end));
const root='clients/community-mini',path=require('path'),files={};
function collect(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){const file=path.join(dir,entry.name);if(entry.isDirectory())collect(file);else if(/\.(js|json|wxml|wxss)$/.test(entry.name)&&!entry.name.includes('.test.'))files[path.relative(root,file).split(path.sep).join('/')]=fs.readFileSync(file,'utf8');}}
collect(root);
const a=adapter.indexOf('async function draw(){'),b=adapter.indexOf('async function load(',a);
adapter=adapter.slice(0,a)+"async function draw(){for(let pass=0;pass<20;pass++){renderDirty=false;const done=renderCallbacks.splice(0);window.__nativeEvidence={state:structuredClone(active.data),calls:structuredClone(calls)};for(const callback of done)callback();if(!renderDirty)return;}throw Error('CALLBACK_UNSETTLED');}\n"+adapter.slice(b);
const window={},context={window,document:{body:{}},structuredClone,URLSearchParams,setTimeout:()=>1,clearTimeout(){},btoa:s=>Buffer.from(s).toString('base64')};
vm.runInNewContext('const files='+JSON.stringify(files)+';'+require('./tests/community_mini_native_render.cjs').splitChoiceSnapshot.toString()+';'+require('./tests/community_mini_native_render.cjs').splitChoiceDraft.toString()+';'+adapter,context);
(async()=>{for(let i=0;i<20&&!window.__nativeEvidence;i++)await new Promise(r=>setImmediate(r));
for(const [handler,dataset] of [['navigateSection',{section:'profile'}],['openMerchantEntry',{}]])await window.nativeEvent({handler,dataset});
assert.equal(window.__nativeEvidence.state.ready,true);assert.equal(window.__nativeEvidence.state.pending,false);
assert.ok(files['pages/merchant-join/index.wxml'].includes('bindtap="save"'));
await window.nativeEvent({handler:'save',dataset:{}});assert.ok(window.__nativeEvidence.state.application);assert.equal(window.__nativeEvidence.state.ready,true);
const ops=window.__nativeEvidence.calls.map(c=>c.suboperation);for(const op of ['save','wechat_save','read','wechat_read'])assert.ok(ops.includes(op),op);
console.log('PASS_ORIGINAL_VISIBLE_SAVE_AND_DRAFT_CHAIN');})().catch(e=>{console.error(e);process.exitCode=1;});
'''
  result=subprocess.run(['node','-e',script],cwd=ROOT,text=True,capture_output=True,timeout=15)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  self.assertIn('PASS_ORIGINAL_VISIBLE_SAVE_AND_DRAFT_CHAIN',result.stdout)
