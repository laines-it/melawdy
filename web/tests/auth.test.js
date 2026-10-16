const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function response(status, body = {}) {
  return { status, ok: status >= 200 && status < 300, json: async () => body };
}

function runtime(responses) {
  const listeners = new Map();
  const actions = [{ dataset: {}, textContent: "" }];
  const names = [{ hidden: true, textContent: "" }];
  const calls = [];
  const status = { textContent: "" };
  const document = {
    addEventListener(name, callback) {
      if (!listeners.has(name)) listeners.set(name, []);
      listeners.get(name).push(callback);
    },
    dispatchEvent(event) {
      for (const callback of listeners.get(event.type) || []) callback(event);
    },
    querySelectorAll(selector) {
      return selector === "[data-auth-action]" ? actions : selector === "[data-user-name]" ? names : [];
    },
    querySelector() { return status; },
  };
  const context = vm.createContext({
    document,
    window: {},
    CustomEvent: class { constructor(type, properties) { this.type = type; Object.assign(this, properties); } },
    localStorage: { getItem() { throw new Error("Browser storage must not authenticate users"); } },
    fetch: async (url, options) => {
      calls.push({ url, options });
      const next = responses.shift();
      if (next instanceof Error) throw next;
      assert.ok(next, `Unexpected request: ${url}`);
      return next;
    },
  });
  for (const file of ["api.js", "auth.js"]) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../static/js", file), "utf8"), context);
  }
  document.dispatchEvent({ type: "DOMContentLoaded" });
  return { auth: context.window.ZPAuth, api: context.window.MelawdyAPI, calls, actions, names };
}

const session = { user: { id: 7, full_name: "Администратор", email: "admin@example.test", user_type: "admin" },
                  csrf_token: "server-csrf-token" };

test("rejected server login cannot fall back to demo credentials", async () => {
  const { auth, actions } = runtime([response(401), response(401, { detail: "Неверный email или пароль" })]);
  await auth.ready;
  await assert.rejects(auth.login("admin", "admin"), /Неверный email или пароль/);
  assert.equal(auth.isLoggedIn(), false);
  assert.equal(auth.getCsrfToken(), "");
  assert.equal(actions[0].dataset.authState, "logged-out");
});

test("login and logout use server sessions, cookies and CSRF", async () => {
  const { auth, calls, actions, names } = runtime([response(401), response(200, session), response(204)]);
  await auth.ready;
  await auth.login("admin@example.test", "password");
  assert.equal(auth.getUser().id, 7);
  assert.equal(actions[0].dataset.authState, "logged-in");
  assert.equal(names[0].textContent, "Администратор");
  assert.equal(names[0].hidden, false);
  await auth.logout();
  assert.equal(calls[0].url, "/api/v1/auth/me");
  assert.equal(calls[1].url, "/api/v1/auth/login");
  assert.equal(calls[2].url, "/api/v1/auth/logout");
  assert.equal(calls[2].options.headers["X-CSRF-Token"], session.csrf_token);
  assert.equal(calls[2].options.credentials, "same-origin");
  assert.equal(calls[2].options.cache, "no-store");
  assert.equal(auth.isLoggedIn(), false);
  assert.equal(names[0].hidden, true);
});

test("page reload restores the server CSRF token", async () => {
  const { auth, api, calls } = runtime([response(200, session), response(201, { id: "1" })]);
  await auth.ready;
  await api.request("public/fees/calculations", { method: "POST", body: "{}" });
  assert.equal(calls[1].options.headers["X-CSRF-Token"], session.csrf_token);
});

test("failed logout does not report a successful local logout", async () => {
  const { auth } = runtime([response(200, session), response(503)]);
  await auth.ready;
  await assert.rejects(auth.logout(), /503/);
  assert.equal(auth.isLoggedIn(), true);
});

test("expired server session clears the profile and CSRF token", async () => {
  const { auth, api, names } = runtime([response(200, session), response(401)]);
  await auth.ready;
  await assert.rejects(api.request("account/overview"));
  assert.equal(auth.isLoggedIn(), false);
  assert.equal(auth.getCsrfToken(), "");
  assert.equal(names[0].hidden, true);
});

test("login can retry after the initial session check loses its connection", async () => {
  const { auth } = runtime([new Error("offline"), response(200, session)]);
  await assert.rejects(auth.ready, /Сервер недоступен/);
  await auth.login("admin@example.test", "password");
  assert.equal(auth.isLoggedIn(), true);
});

test("HTML proxy errors preserve the HTTP error status", async () => {
  const invalidJson = response(502);
  invalidJson.json = async () => { throw new SyntaxError("HTML"); };
  const { auth } = runtime([invalidJson]);
  await assert.rejects(auth.ready, (error) => error.status === 502 && /502/.test(error.message));
});

test("registration creates a regular authenticated session through the API", async () => {
  const regularSession = { ...session, user: { ...session.user, user_type: "individual" } };
  const { auth, calls } = runtime([response(401), response(201, regularSession)]);
  await auth.ready;
  const payload = { email: "new@example.test", full_name: "Новый пользователь", password: "password", user_type: "individual" };
  await auth.register(payload);
  assert.equal(calls[1].url, "/api/v1/auth/register");
  assert.equal(calls[1].options.method, "POST");
  assert.deepEqual(JSON.parse(calls[1].options.body), payload);
  assert.equal(auth.getUser().user_type, "individual");
  assert.equal(auth.getCsrfToken(), regularSession.csrf_token);
});

test("duplicate registration preserves the server error and stays logged out", async () => {
  const { auth } = runtime([response(401), response(409, { detail: "Пользователь с таким email уже существует" })]);
  await auth.ready;
  await assert.rejects(auth.register({ email: "existing@example.test" }), /уже существует/);
  assert.equal(auth.isLoggedIn(), false);
});
