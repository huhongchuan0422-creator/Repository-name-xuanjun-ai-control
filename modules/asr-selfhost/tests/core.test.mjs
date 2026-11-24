import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createDraft} from '../web/core.mjs';

test("visible interim is revised, not duplicated", () => {
  const d = createDraft("备注：");
  const id = d.begin();
  assert.equal(d.receive(id, {draft: '示例三种'}).text, '备注：示例三种');
  assert.equal(d.receive(id, {confirmed: '示例三中',draft:'，明天见'}).text, '备注：示例三中，明天见');
  assert.equal(d.receive(id, {confirmed: '示例三中，明天见。', done: true}).text, '备注：示例三中，明天见。');
});
test("manual edit wins even when final correction changes the recorded prefix", () => {
  const d = createDraft(); const id = d.begin();
  d.receive(id, {draft: '示例三种'});
  d.edit('我的手改：示例三中');
  const s = d.receive(id,{confirmed:'示例三中，不是二中。',done:true});
  assert.equal(s.text,'我的手改：示例三中');
  assert.equal(s.pending,'示例三中，不是二中。');
  assert.equal(s.appendable,false);
  assert.equal(d.appendSuggestion().text,s.text);
});
test("explicit append adds only newly recognized suffix, once", () => {
  const d = createDraft(); const id = d.begin();
  d.receive(id,{confirmed:'示例三中'}); d.edit('学校：示例三中');
  d.receive(id,{confirmed:'示例三中，不是二中。',done:true});
  assert.equal(d.view().pending,'，不是二中。');
  assert.equal(d.appendSuggestion().text,'学校：示例三中，不是二中。');
  assert.equal(d.appendSuggestion().text,'学校：示例三中，不是二中。');
});
test("late previous result cannot enter a later take", () => {
  const d = createDraft(); let old=d.begin();
  d.receive(old,{draft:'我的初稿'}); d.invalidate();
  const next=d.begin(); d.receive(next,{draft:'补充'});
  assert.equal(d.receive(old,{confirmed:'旧迟到',done:true}).text,'我的初稿补充');
});
