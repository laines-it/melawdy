const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.hidden = false;
    this.attributes = {};
    this.listeners = {};
    this.text = "";
  }
  set textContent(value) { this.text = value; this.children = []; }
  get textContent() { return this.text + this.children.map((child) => child.textContent).join(""); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.text = ""; this.children = children; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
}

async function runtime(search, responses) {
  const elements = new Map();
  const calls = [];
  let start;
  const document = {
    title: "Статья — Законпозитор",
    addEventListener(name, callback) { if (name === "DOMContentLoaded") start = callback; },
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    createElement: (tag) => new Element(tag),
  };
  for (const selector of ["#article", "#retry-article", "#related-articles", "#article-empty"]) {
    document.querySelector(selector).hidden = true;
  }
  const window = { location: { search }, MelawdyAPI: { async request(url) {
    calls.push(url);
    const next = responses.shift();
    assert.ok(next, `Unexpected request: ${url}`);
    if (next instanceof Error) throw next;
    return next;
  } } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/js/article.js"), "utf8"),
                    { window, document, URLSearchParams });
  start();
  await new Promise(setImmediate);
  return { document, calls, get: (selector) => document.querySelector(selector) };
}

const article = { id: "42", title: "Как оформить соавторство", summary: "Описание статьи",
                  category: { id: "3", name: "Договорённости" },
                  chunks: ["## Равные права\n\nВводный раздел.",
                           "Первый абзац.\nПродолжение.\n\nВторой абзац.",
                           "## Следующий раздел\n\n- Исходники\n- Переписка\n\n<script>alert(1)</script>"] };

test("loads the URL id, renders every chunk in order and keeps stored HTML as text", async () => {
  const { get, document, calls } = await runtime("?id=42", [article, []]);
  assert.equal(calls[0], "public/articles/42");
  assert.equal(document.title, `${article.title} — Законпозитор`);
  assert.equal(get("#article-title").textContent, article.title);
  assert.equal(get("#article-summary").textContent, article.summary);
  assert.equal(get("#article-category").textContent, "Договорённости");
  assert.equal(get("#article-reading-time").textContent, "1 мин. чтения");
  assert.equal(get("#article").hidden, false);
  assert.equal(get("#article-state").hidden, true);
  assert.equal(get("#article-intro-body").children[0].tagName, "H2");
  const sections = get("#article-chunks").children;
  assert.equal(sections.length, 2);
  assert.deepEqual(sections[0].children.map((item) => item.textContent),
                   ["Первый абзац.\nПродолжение.", "Второй абзац."]);
  assert.deepEqual(sections[1].children.map((item) => item.tagName), ["H2", "UL", "P"]);
  assert.equal(sections[1].children[2].textContent, "<script>alert(1)</script>");
});

for (const search of ["", "?id=", "?id=0", "?id=-1", "?id=abc", "?id=1/2", "?id=9223372036854775808"]) {
  test(`invalid article id does not call the API: ${search}`, async () => {
    const { calls, get } = await runtime(search, []);
    assert.deepEqual(calls, []);
    assert.equal(get("#state-title").textContent, "Статья не выбрана");
    assert.equal(get("#article-state").attributes["aria-busy"], "false");
    assert.equal(get("#article").hidden, true);
  });
}

test("preserves bigint ids without converting them to imprecise JS numbers", async () => {
  const { calls } = await runtime("?id=9223372036854775807", [article, []]);
  assert.equal(calls[0], "public/articles/9223372036854775807");
});

test("a missing article shows a useful 404 state", async () => {
  const error = Object.assign(new Error("Статья не найдена"), { status: 404 });
  const { get, calls } = await runtime("?id=404", [error]);
  assert.equal(calls.length, 1);
  assert.equal(get("#state-title").textContent, "Статья не найдена");
  assert.equal(get("#retry-article").hidden, true);
  assert.equal(get("#article").hidden, true);
});

test("network errors can be retried successfully", async () => {
  const { get, calls } = await runtime("?id=42", [new Error("Сервер недоступен"), article, []]);
  assert.equal(get("#state-message").textContent, "Сервер недоступен");
  assert.equal(get("#retry-article").hidden, false);
  await get("#retry-article").listeners.click();
  assert.equal(calls[1], "public/articles/42");
  assert.equal(get("#article").hidden, false);
  assert.equal(get("#retry-article").hidden, true);
});

test("recommendation errors do not prevent reading the article", async () => {
  const { get } = await runtime("?id=42", [article, new Error("Ошибка рекомендаций")]);
  assert.equal(get("#article").hidden, false);
  assert.equal(get("#article-state").hidden, true);
  assert.equal(get("#related-articles").hidden, true);
});

test("recommendations link to other article ids and exclude the current article", async () => {
  const { get } = await runtime("?id=42", [article, [article, { id: "7", title: "Авторство" }]]);
  const items = get("#related-articles-list").children;
  assert.equal(items.length, 1);
  assert.equal(items[0].children[0].href, "./article.html?id=7");
  assert.equal(get("#related-articles").hidden, false);
});

test("an article without chunks or a category renders an explicit empty state", async () => {
  const { get } = await runtime("?id=42", [{ ...article, category: null, summary: null, chunks: [] }, []]);
  assert.equal(get("#article-empty").hidden, false);
  assert.equal(get("#article-intro").hidden, true);
  assert.equal(get("#article-summary").hidden, true);
  assert.equal(get("#article-category-path").hidden, true);
  assert.equal(get("#article-category").textContent, "База знаний");
});
