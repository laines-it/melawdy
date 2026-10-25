const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

class Node {
  constructor() { this.listeners = {}; this.children = []; this.textContent = ""; this.value = ""; this.hidden = true; this.disabled = false; this.classList = { toggle() {} }; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
  async emit(name, event = {}) { await this.listeners[name]?.(event); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
  select() {}
  click() {}
}

function setup() {
  const nodes = new Map();
  const node = (id) => { if (!nodes.has(id)) nodes.set(id, new Node()); return nodes.get(id); };
  const calls = [], timers = [], storage = new Map();
  let ready;
  const finished = { id: "test-job", filename: "song.mp3", status: "completed", expires_at: 2000000000,
    result: { outcome: "completed", catalog_size: 2, window_seconds: 20, hop_seconds: 5,
      matches: [{ reference: "<img onerror=alert(1)>", distance: .125,
        query_start: 5, query_end: 25, reference_start: 10, reference_end: 30 }] } };
  const responses = [];
  const context = vm.createContext({
    console, Blob, URL: { createObjectURL: () => "blob:demo", revokeObjectURL() {} },
    navigator: { clipboard: { writeText: async () => {} } },
    localStorage: { getItem: (key) => storage.get(key) || null,
      setItem: (key, val) => storage.set(key, val), removeItem: (key) => storage.delete(key) },
    setTimeout: (fn) => { timers.push(fn); return timers.length; }, clearTimeout() {},
    document: { querySelector: node, createElement: () => new Node(),
      addEventListener: (event, fn) => { if (event === "DOMContentLoaded") ready = fn; } },
    window: { addEventListener() {} },
    fetch: async (url, options) => {
      calls.push({ url, options });
      let body;
      if (url.endsWith("public/capabilities")) body = { music_check: { available: true, max_upload_mb: 32, message: "Готово" } };
      else if (url.includes("public/templates")) body = [];
      else { body = responses.shift(); assert.ok(body, `Unexpected request ${url}`); }
      return { ok: true, status: 200, json: async () => body };
    },
  });
  for (const name of ["api.js", "check.js"]) vm.runInContext(fs.readFileSync(path.join(__dirname, "../static/js", name), "utf8"), context);
  return { node, calls, timers, storage, responses, finished, ready: () => ready() };
}

test("upload is binary; polling displays actual matches as text and keeps owner token private", async () => {
  const app = setup();
  await app.ready();
  const file = new Blob(["audio"], { type: "audio/mpeg" }); file.name = "song.mp3";
  app.node("#file-input").files = [file];
  await app.node("#file-input").emit("change");
  assert.equal(app.node("#check-btn").disabled, false);
  app.responses.push({ ...app.finished, status: "queued", result: null, access_token: "owner-secret" });
  app.responses.push(app.finished);
  await app.node("#check-btn").emit("click");
  await new Promise((resolve) => setImmediate(resolve));
  const upload = app.calls.find((call) => call.url.endsWith("music-check/jobs"));
  assert.equal(upload.options.body, file);
  assert.equal(upload.options.headers["Content-Type"], "application/octet-stream");
  const poll = app.calls.find((call) => call.url.endsWith("music-check/jobs/test-job"));
  assert.equal(poll.options.headers["X-Music-Job-Token"], "owner-secret");
  assert.equal(app.node("#job-state").textContent, "Обработка завершена");
  const match = app.node("#matches-list").children[0];
  assert.equal(match.children[0].textContent, "<img onerror=alert(1)>");
  assert.match(app.node("#result-summary").textContent, /Проверено записей: 2/);
  assert.equal(app.node("#job-number").value, "test-job");
});

test("unsupported and oversized files never create jobs", async () => {
  const app = setup(); await app.ready();
  app.node("#file-input").files = [{ name: "bad.html", size: 4 }];
  await app.node("#file-input").emit("change");
  assert.match(app.node("#upload-status").textContent, /Выберите MP3/);
  app.node("#file-input").files = [{ name: "big.mp3", size: 33 * 1024 * 1024 }];
  await app.node("#file-input").emit("change");
  assert.match(app.node("#upload-status").textContent, /не больше 32/);
  assert.ok(app.calls.every((call) => !call.url.endsWith("music-check/jobs")));
});
