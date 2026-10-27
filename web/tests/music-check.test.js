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
  pause() { this.paused = true; }
  async play() { this.paused = false; await this.emit("play"); }
  load() {}
  removeAttribute(name) { delete this[name]; }
}

function setup({ microphone = false, permissionError = null, pendingPermission = false, mimeType = "audio/webm;codecs=opus", maxUploadMB = 32 } = {}) {
  const nodes = new Map();
  const node = (id) => { if (!nodes.has(id)) nodes.set(id, new Node()); return nodes.get(id); };
  const calls = [], timers = [], storage = new Map();
  let ready, now = 1000, resolvePermission;
  const windowHandlers = {}, recorders = [], mediaRequests = [];
  const track = { stopped: false, listeners: {}, stop() { this.stopped = true; }, addEventListener(name, fn) { this.listeners[name] = fn; } };
  const stream = { getTracks: () => [track] };
  class Recorder {
    static isTypeSupported(type) { return type === mimeType; }
    constructor(stream, options) { this.stream = stream; this.mimeType = options.mimeType; this.state = "inactive"; this.listeners = {}; recorders.push(this); }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    start() { this.state = "recording"; }
    data(blob) { this.listeners.dataavailable({ data: blob }); }
    stop() { this.state = "inactive"; this.listeners.stop(); }
  }
  class ClockDate extends Date { static now() { return now; } }
  const finished = { id: "test-job", code: "17", filename: "song.mp3", status: "completed", expires_at: 2000000000,
    result: { outcome: "completed", catalog_size: 2, window_seconds: 20, hop_seconds: 5,
      matches: [{ reference: "<img onerror=alert(1)>", distance: .125,
        query_start: 5, query_end: 25, reference_start: 10, reference_end: 30, preview_available: true }] } };
  const responses = [];
  const context = vm.createContext({
    console, Blob, URL: { createObjectURL: () => "blob:demo", revokeObjectURL() {} },
    Date: ClockDate,
    File: class extends Blob { constructor(parts, name, options) { super(parts, options); this.name = name; } },
    ...(microphone ? { MediaRecorder: Recorder } : {}),
    navigator: { ...(microphone ? { mediaDevices: { getUserMedia: async (constraints) => {
      mediaRequests.push(constraints);
      if (permissionError) throw { name: permissionError };
      if (pendingPermission) return await new Promise((resolve) => { resolvePermission = () => resolve(stream); });
      return stream;
    } } } : {}), clipboard: { writeText: async () => {} } },
    localStorage: { getItem: (key) => storage.get(key) || null,
      setItem: (key, val) => storage.set(key, val), removeItem: (key) => storage.delete(key) },
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; }, clearTimeout() {},
    setInterval: () => 1, clearInterval() {},
    document: { querySelector: (id) => ["#result-hint", "#job-code-hint"].includes(id) ? null : node(id), createElement: () => new Node(),
      addEventListener: (event, fn) => { if (event === "DOMContentLoaded") ready = fn; } },
    window: { isSecureContext: true, addEventListener(name, fn) { windowHandlers[name] = fn; } },
    fetch: async (url, options) => {
      calls.push({ url, options });
      let body;
      if (url.endsWith("public/capabilities")) body = { music_check: { available: true, max_upload_mb: maxUploadMB, message: "Готово" } };
      else if (url.includes("public/templates")) body = [];
      else { body = responses.shift(); assert.ok(body, `Unexpected request ${url}`); }
      return { ok: true, status: 200, json: async () => body, blob: async () => body };
    },
  });
  for (const name of ["api.js", "check.js"]) vm.runInContext(fs.readFileSync(path.join(__dirname, "../static/js", name), "utf8"), context);
  return { node, calls, timers, storage, responses, finished, ready: () => ready(),
    media: { track, recorders, requests: mediaRequests, advance: (seconds) => { now += seconds * 1000; },
      resolve: () => resolvePermission(), hide: () => windowHandlers.pagehide() } };
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
  assert.equal(app.node("#job-number").value, "17");
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


test("reference fragment loads with owner authentication only on click and replays from cache", async () => {
  const app = setup(); await app.ready();
  const file = new Blob(["audio"]); file.name = "song.mp3";
  app.node("#file-input").files = [file]; await app.node("#file-input").emit("change");
  app.responses.push({ ...app.finished, status: "queued", result: null, access_token: "owner-secret" }, app.finished);
  await app.node("#check-btn").emit("click");
  await new Promise((resolve) => setImmediate(resolve));
  assert.ok(!app.calls.some((call) => call.url.endsWith("/matches/0/audio")));
  const card = app.node("#matches-list").children[0];
  const button = card.children.find((child) => child.textContent === "Послушать найденный отрывок");
  assert.ok(button);
  const player = card.children.at(-1);
  app.responses.push(new Blob(["ID3clip"], { type: "audio/mpeg" }));
  await button.emit("click");
  const call = app.calls.find((call) => call.url.endsWith("/matches/0/audio"));
  assert.equal(call.options.headers["X-Music-Job-Token"], "owner-secret");
  assert.equal(player.hidden, false); assert.equal(player.paused, false);
  assert.equal(app.node("#query-audio").paused, true);
  player.currentTime = 7;
  await button.emit("click");
  assert.equal(player.currentTime, 0);
  assert.equal(app.calls.filter((call) => call.url.endsWith("/matches/0/audio")).length, 1);
  await card.children[3].emit("click");
  assert.equal(player.paused, true);
  assert.equal(app.node("#query-audio").currentTime, 5);
  app.node("#query-audio").currentTime = 25;
  await app.node("#query-audio").emit("timeupdate");
  assert.equal(app.node("#query-audio").paused, true);
});


test("similarity percentages classify boundary values and keep original distances in reports", async () => {
  const values = [
    { distance: 0, percent: "100", tier: "high", level: "Значительное" },
    { distance: 0.75, percent: "75", tier: "high", level: "Значительное" },
    { distance: 0.753, percent: "74,9", tier: "medium", level: "Частичное" },
    { distance: 1.5, percent: "50", tier: "medium", level: "Частичное" },
    { distance: 1.503, percent: "49,9", tier: "low", level: "Незначительное" },
    { distance: 3, percent: "0", tier: "low", level: "Незначительное" },
    { distance: 6, percent: "-100", tier: "low", level: "Незначительное" },
  ];
  for (let start = 0; start < values.length; start += 3) {
    const app = setup(); await app.ready();
    app.finished.result.matches = values.slice(start).map(({ distance }) => ({ ...app.finished.result.matches[0], distance, preview_available: false }));
    const file = new Blob(["audio"]); file.name = "song.mp3";
    app.node("#file-input").files = [file]; await app.node("#file-input").emit("change");
    app.responses.push({ ...app.finished, status: "queued", result: null, access_token: "owner-secret" }, app.finished);
    await app.node("#check-btn").emit("click");
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(app.node("#matches-list").children.length, Math.min(3, values.length - start));
    app.node("#matches-list").children.forEach((card, index) => {
      const value = values[start + index];
      assert.equal(card.className, `match-item match-item--${value.tier}`);
      assert.equal(card.children[2].textContent, `Сходство: ${value.percent}% · ${value.level}`);
      assert.equal(app.finished.result.matches[index].distance, value.distance);
    });
  }
});


test("microphone creates a preview and uploads supported WebM only after explicit submission", async () => {
  const app = setup({ microphone: true }); await app.ready();
  assert.equal(app.node("#record-start").disabled, false);
  await app.node("#record-start").emit("click");
  assert.equal(app.node("#check-btn").disabled, true);
  assert.equal(app.node("#choose-files-btn").disabled, true);
  assert.equal(app.media.requests[0].video, false);
  assert.equal(app.media.requests[0].audio.noiseSuppression, false);
  app.media.advance(21);
  app.media.recorders[0].data(new Blob(["microphone audio"]));
  await app.node("#record-stop").emit("click");
  assert.equal(app.media.track.stopped, true);
  assert.equal(app.node("#record-preview").hidden, false);
  assert.equal(app.node("#check-btn").disabled, false);
  assert.equal(app.calls.some((call) => call.url.endsWith("music-check/jobs")), false);
  app.responses.push({ ...app.finished, status: "queued", result: null, access_token: "owner" }, app.finished);
  await app.node("#check-btn").emit("click");
  await new Promise((resolve) => setImmediate(resolve));
  const request = app.calls.find((call) => call.url.endsWith("music-check/jobs"));
  assert.match(request.options.body.name, /^recording-.*\.webm$/);
  assert.equal(request.options.body.type, "audio/webm;codecs=opus");
  assert.equal(await request.options.body.text(), "microphone audio");
});

test("Safari-style MP4 recording keeps the correct audio container and m4a extension", async () => {
  const app = setup({ microphone: true, mimeType: "audio/mp4" }); await app.ready();
  await app.node("#record-start").emit("click"); app.media.advance(21);
  app.media.recorders[0].data(new Blob(["mp4 audio"]));
  await app.node("#record-stop").emit("click");
  assert.match(app.node("#selected-file").textContent, /\.m4a/);
  assert.equal(app.node("#check-btn").disabled, false);
});

test("microphone permission denial and missing support preserve ordinary file uploads", async () => {
  const denied = setup({ microphone: true, permissionError: "NotAllowedError" }); await denied.ready();
  await denied.node("#record-start").emit("click");
  assert.match(denied.node("#record-status").textContent, /Доступ к микрофону запрещён/);
  assert.equal(denied.node("#choose-files-btn").disabled, false);
  assert.equal(denied.node("#record-start").disabled, false);
  const unsupported = setup(); await unsupported.ready();
  assert.equal(unsupported.node("#record-start").disabled, true);
  assert.equal(unsupported.node("#choose-files-btn").disabled, false);
});

test("short recordings are rejected and microphone tracks stop", async () => {
  const app = setup({ microphone: true }); await app.ready();
  await app.node("#record-start").emit("click"); app.media.advance(8);
  app.media.recorders[0].data(new Blob(["short"]));
  await app.node("#record-stop").emit("click");
  assert.match(app.node("#record-status").textContent, /короче 20 секунд/);
  assert.equal(app.node("#check-btn").disabled, true);
  assert.equal(app.media.track.stopped, true);
});

test("cancelling a pending permission request stops tracks if access arrives later", async () => {
  const app = setup({ microphone: true, pendingPermission: true }); await app.ready();
  const request = app.node("#record-start").emit("click");
  await app.node("#record-cancel").emit("click");
  app.media.resolve(); await request;
  assert.equal(app.media.track.stopped, true);
  assert.equal(app.media.recorders.length, 0);
  assert.equal(app.node("#record-start").disabled, false);
  assert.equal(app.node("#check-btn").disabled, true);
});

test("leaving the page cancels recording without uploading audio", async () => {
  const app = setup({ microphone: true }); await app.ready();
  await app.node("#record-start").emit("click");
  app.media.hide();
  assert.equal(app.media.track.stopped, true);
  assert.equal(app.media.recorders[0].state, "inactive");
  assert.equal(app.calls.some((call) => call.url.endsWith("music-check/jobs")), false);
});

test("recording stops at the size limit and oversized audio cannot be submitted", async () => {
  const app = setup({ microphone: true, maxUploadMB: 1 }); await app.ready();
  await app.node("#record-start").emit("click"); app.media.advance(21);
  app.media.recorders[0].data(new Blob([new Uint8Array(1024 * 1024 + 1)]));
  assert.equal(app.media.track.stopped, true);
  assert.equal(app.node("#check-btn").disabled, true);
  assert.match(app.node("#record-status").textContent, /превышает 1 МБ/);
});

test("recording automatically stops after five minutes and can be submitted", async () => {
  const app = setup({ microphone: true }); await app.ready();
  await app.node("#record-start").emit("click");
  app.media.recorders[0].data(new Blob(["recorded audio"]));
  app.media.advance(300);
  app.timers.find((timer) => timer.ms === 300000).fn();
  assert.equal(app.media.track.stopped, true);
  assert.equal(app.node("#check-btn").disabled, false);
});
