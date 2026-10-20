import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import test from "node:test";

const script = fs.readFileSync(path.resolve("deploy/pr122-domestic-website/overlay/public/assets/tiktok-integration.js"), "utf8");

function element(initial = "stale") {
  return { textContent: initial, hidden: false, disabled: false, handlers: {}, addEventListener(name, fn) { this.handlers[name] = fn; } };
}

async function run(fetchImpl) {
  const values = {
    "[data-tiktok-status]": element(),
    "[data-tiktok-account]": element(),
    "[data-tiktok-display-name]": element(),
    "[data-tiktok-open-id]": element(),
    "[data-tiktok-scope]": element(),
    "[data-tiktok-disconnect]": element()
  };
  const context = { document: { querySelector(selector) { return values[selector]; } }, fetch: fetchImpl, Date, Error, Promise };
  vm.runInNewContext(script, context);
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  return values;
}

function assertFailClosed(values) {
  assert.equal(values["[data-tiktok-account]"].hidden, true);
  assert.equal(values["[data-tiktok-disconnect]"].disabled, true);
  assert.equal(values["[data-tiktok-display-name]"].textContent, "");
  assert.notEqual(values["[data-tiktok-status]"].textContent, "已连接 TikTok 账号");
}

test("network failure is unknown and never connected", async () => {
  const values = await run(() => Promise.reject(new Error("offline")));
  assertFailClosed(values);
  assert.match(values["[data-tiktok-status]"].textContent, /未知/);
});

test("non-json response is unknown and never connected", async () => {
  const values = await run(() => Promise.resolve({ ok: true, json: () => Promise.reject(new Error("invalid json")) }));
  assertFailClosed(values);
});

test("http failure is unknown and never connected", async () => {
  const values = await run(() => Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({ connected: true, account: {} }) }));
  assertFailClosed(values);
  assert.match(values["[data-tiktok-status]"].textContent, /未知/);
});

test("explicit disconnected response clears stale account", async () => {
  const values = await run(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ connected: false }) }));
  assertFailClosed(values);
  assert.equal(values["[data-tiktok-status]"].textContent, "未连接 TikTok");
});

test("connected response alone enables account controls", async () => {
  const values = await run(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ connected: true, account: { display_name: "demo", open_id_masked: "***42" }, scope: "user.info.basic" }) }));
  assert.equal(values["[data-tiktok-account]"].hidden, false);
  assert.equal(values["[data-tiktok-disconnect]"].disabled, false);
  assert.equal(values["[data-tiktok-status]"].textContent, "已连接 TikTok 账号");
});

test("disconnect failure becomes unknown and disables repeated action", async () => {
  let calls = 0;
  const values = await run(() => {
    calls += 1;
    if (calls === 1) return Promise.resolve({ ok: true, json: () => Promise.resolve({ connected: true, account: {} }) });
    return Promise.reject(new Error("timeout"));
  });
  values["[data-tiktok-disconnect]"].handlers.click();
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  assertFailClosed(values);
  assert.match(values["[data-tiktok-status]"].textContent, /结果未知/);
});
