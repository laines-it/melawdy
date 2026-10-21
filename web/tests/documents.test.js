const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const model = require("../static/js/document-model.js");
const cases = require("./fixtures/document-render-cases.json");

for (const vector of cases) test(`preview contract: ${vector.name}`, () => {
  assert.equal(model.render(vector.template, vector.params), vector.expected);
});

test("field inference preserves nested paths and deduplicates repeated placeholders", () => {
  const sections = model.sections({ body: "{{city}} {{author.name}} {{city}}" });
  assert.deepEqual(sections[0].fields.map((field) => field.name), ["city", "author.name"]);
  const params = {};
  model.set(params, "author.name", "Иванов");
  assert.deepEqual(params, { author: { name: "Иванов" } });
});

test("fields controlling conditional blocks are inferred with every available choice", () => {
  const sections = model.sections({ structure_json: { blocks: [
    { when: "license == exclusive", template: "Исключительная" },
    { when: "license == non_exclusive", template: "Простая" },
  ] } });
  assert.deepEqual(sections[0].fields[0].options, ["exclusive", "non_exclusive"]);
});

test("prototype paths cannot alter the page runtime", () => {
  const params = {};
  for (const name of ["__proto__.polluted", "constructor.prototype.polluted", "a.__proto__.polluted"]) model.set(params, name, true);
  assert.equal({}.polluted, undefined);
  assert.deepEqual(params, {});
  assert.deepEqual(model.sections({ body: "{{__proto__.polluted}}" })[0].fields, []);
});

test("inferred boolean conditions permit both true and false", () => {
  const field = model.sections({ structure_json: { blocks: [{ when: "proxy == true", template: "Представитель" }] } })[0].fields[0];
  assert.equal(field.type, "boolean");
  assert.equal(field.default, false);
  assert.equal(field.required, false);
});


test("configured sections keep order and only unconfigured placeholders are appended", () => {
  const fixture = require("../../docs/examples/coauthors-template.json");
  const sections = model.sections(fixture);

  assert.equal(sections.length, 12);
  assert.equal(sections[0].id, "preamble");
  assert.equal(sections.at(-1).id, "signatures");

  const ids = sections.map((section) => section.id);
  assert.deepEqual(ids, [...new Set(ids)]);

  const extra = model.sections({
    ...fixture,
    body: "",
    structure_json: {
      blocks: [{ template: "{{unconfigured}}" }],
    },
  });

  assert.equal(extra.at(-1).fields[0].name, "unconfigured");
});


test("document ids are validated without lossy Number conversion", () => {
  for (const id of ["1", "9223372036854775807"]) assert.equal(model.validId(id), true);
  for (const id of [null, "", "0", "01", "-1", "1/2", "9223372036854775808"]) assert.equal(model.validId(id), false);
});

test("DOCX requests retain server session, CSRF/error handling and return a binary blob", async () => {
  const calls = [];
  const blob = { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" };
  let cleared = false;
  let next = { ok: true, status: 200, blob: async () => blob, json: () => { throw new Error("DOCX is not JSON"); } };
  const window = { ZPAuth: { getCsrfToken: () => "csrf", clearSession: () => { cleared = true; } } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/js/api.js"), "utf8"), {
    window, fetch: async (url, options) => { calls.push({ url, options }); return next; },
  });
  assert.equal(await window.MelawdyAPI.request("cabinet/documents/7/download", { responseType: "blob" }), blob);
  assert.equal(calls[0].options.credentials, "same-origin");
  assert.equal(calls[0].options.cache, "no-store");
  assert.equal(calls[0].options.responseType, undefined);
  await window.MelawdyAPI.request("cabinet/documents/7", { method: "PATCH", body: "{}", responseType: "blob" });
  assert.equal(calls[1].options.headers["X-CSRF-Token"], "csrf");
  next = { ok: false, status: 401, json: async () => ({ detail: "Войдите" }) };
  await assert.rejects(window.MelawdyAPI.request("cabinet/documents/7/download", { responseType: "blob" }), /Войдите/);
  assert.equal(cleared, true);
});
