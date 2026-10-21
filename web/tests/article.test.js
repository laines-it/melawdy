const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase();
    this.childNodes = [];
    this.hidden = false;
    this.attributes = {};
    this.listeners = {};
    this.dataset = {};
  }
  get children() { return this.childNodes.filter((child) => child.tagName); }
  get firstChild() { return this.childNodes[0] || null; }
  set textContent(value) {
    this.replaceChildren();
    if (String(value)) this.appendChild({ textContent: String(value) });
  }
  get textContent() { return this.childNodes.map((child) => child.textContent).join(""); }
  appendChild(child) {
    if (child.parentNode) child.parentNode.removeChild(child);
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }
  removeChild(child) {
    const index = this.childNodes.indexOf(child);
    assert.notEqual(index, -1, "Cannot remove a node from a different parent");
    this.childNodes.splice(index, 1);
    child.parentNode = null;
    return child;
  }
  append(...children) { children.forEach((child) => this.appendChild(child)); }
  replaceChildren(...children) {
    while (this.firstChild) this.removeChild(this.firstChild);
    this.append(...children);
  }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
}

async function runtime(search, responses, pathname = "/article.html", loggedIn = false) {
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
    createTextNode: (text) => ({ textContent: text }),
  };
  for (const selector of ["#article", "#retry-article", "#related-articles", "#article-empty"]) {
    document.querySelector(selector).hidden = true;
  }
  const window = { location: { search, pathname, hash: "" }, history: { replaceState(_state, _title, url) { window.location.pathname = url; } }, ZPAuth: { ready: Promise.resolve(), isLoggedIn: () => loggedIn }, MelawdyAPI: { async request(url) {
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
  return { document, window, calls, get: (selector) => document.querySelector(selector) };
}

const article = { id: "42", slug: "coauthors-agreement", title: "Как оформить соавторство", summary: "Описание статьи",
                  category: { id: "3", name: "Договорённости" },
                  chunks: ["## Равные права\n\nВводный раздел.",
                           "Первый абзац.\nПродолжение.\n\nВторой абзац.",
                           "## Следующий раздел\n\n- Исходники\n- Переписка\n\n<script>alert(1)</script>"] };

test("loads the URL id, renders every chunk in order and keeps stored HTML as text", async () => {
  const { get, document, window, calls } = await runtime("?id=42", [article, []]);
  assert.equal(calls[0], "public/articles/42");
  assert.equal(window.location.pathname, "/article/coauthors-agreement");
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
  let resolveArticle;
  const pendingArticle = new Promise((resolve) => { resolveArticle = resolve; });
  const { get, calls } = await runtime("?id=42", [new Error("Сервер недоступен"), pendingArticle, []]);
  assert.equal(get("#state-message").textContent, "Сервер недоступен");
  assert.equal(get("#retry-article").hidden, false);
  const retry = get("#retry-article").listeners.click();
  assert.equal(get("#article").hidden, true);
  assert.equal(get("#article-state").attributes["aria-busy"], "true");
  assert.equal(typeof retry?.then, "function");
  resolveArticle(article);
  await retry;
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
  assert.equal(items[0].children[0].href, "/article/7");
  assert.equal(get("#related-articles").hidden, false);
});

test("an article without chunks or a category renders an explicit empty state", async () => {
  const { get } = await runtime("?id=42", [{ ...article, category: null, summary: null, chunks: [] }, []]);
  assert.equal(get("#article-empty").hidden, false);
  assert.equal(get("#article-intro").hidden, true);
  assert.equal(get("#article-summary").hidden, true);
  assert.equal(get("#article-category-path").hidden, true);
});

test("Markdown titles, summaries and footnotes survive DOM node moves and reloads", async () => {
  const record = { ...article, title: "**Соавторство**", summary: "*Описание*",
    chunks: ["Текст[^law]\n\n[^law]: Правило **закона**"] };
  const { get } = await runtime("?id=42", [record, [], article, []]);
  assert.equal(get("#article-title").children[0].tagName, "STRONG");
  assert.equal(get("#article-title").textContent, "Соавторство");
  assert.equal(get("#article-summary").children[0].tagName, "EM");
  const intro = get("#article-intro-body");
  const ref = intro.children[0].children[0].children[0];
  assert.equal(ref.href, "#fn-law");
  const notes = get("#article-chunks").children[0];
  assert.equal(notes.className, "article-footnotes");
  const note = notes.children[1].children[0];
  assert.equal(note.id, "fn-law");
  assert.equal(note.textContent, "Правило закона ↩");
  await get("#retry-article").listeners.click();
  assert.equal(get("#article-title").textContent, article.title);
  assert.equal(get("#article-title").children.length, 0);
  assert.equal(get("#article-summary").textContent, article.summary);
  assert.equal(intro.children.length, 2);
  assert.equal(intro.children[0].tagName, "H2");
  assert.equal(get("#article-chunks").children.length, 2);
});

for (const slug of ["coauthors-agreement", "авторство-песни"]) {
  test(`loads the stored slug and excludes itself from related articles: ${slug}`, async () => {
    const current = { ...article, slug };
    const { calls, get } = await runtime("", [current, [current, { id: "7", slug: "other", title: "Другая" }]],
                                         `/article/${encodeURIComponent(slug)}`);
    assert.equal(calls[0], `public/articles/${encodeURIComponent(slug)}`);
    assert.equal(get("#article").hidden, false);
    assert.equal(get("#related-articles-list").children.length, 1);
    assert.equal(get("#related-articles-list").children[0].children[0].href, "/article/other");
  });
}

test("favorites use the article ID when opened by slug", async () => {
  const { calls, get } = await runtime("", [article, [], [{ content_item_id: "42" }], {}],
                                     "/article/coauthors-agreement", true);
  assert.equal(get("#fav-btn").attributes["aria-pressed"], "true");
  await get("#fav-btn").listeners.click();
  assert.equal(calls.at(-1), "cabinet/favorites/42");
});
