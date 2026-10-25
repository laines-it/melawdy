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
    this._className = "";
    this.href = "";
    this.id = "";
    this.dataset = {};
    this._parentNode = null;
  }

  get children() { return this.childNodes.filter((child) => child.tagName); }
  get firstChild() { return this.childNodes[0] || null; }
  get parentNode() { return this._parentNode; }
  set parentNode(value) { this._parentNode = value; }

  get className() { return this._className; }
  set className(value) {
    this._className = value;
    this.attributes["class"] = value;
  }

  get classList() {
    const self = this;
    return {
      add(cls) {
        const classes = self.className.split(/\s+/).filter(Boolean);
        if (!classes.includes(cls)) {
          classes.push(cls);
          self.className = classes.join(" ");
        }
      },
      remove(cls) {
        const classes = self.className.split(/\s+/).filter(Boolean);
        self.className = classes.filter(c => c !== cls).join(" ");
      },
      contains(cls) {
        return self.className.split(/\s+/).includes(cls);
      }
    };
  }

  set textContent(value) {
    this.replaceChildren();
    if (String(value)) this.appendChild({ textContent: String(value), tagName: undefined, parentNode: null });
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

  setAttribute(name, value) {
    this.attributes[name] = value;
    if (name === "href") this.href = value;
    if (name === "id") this.id = value;
    if (name === "class") this.className = value;
    if (name.startsWith("data-")) {
      const key = name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
      this.dataset[key] = value;
    }
  }

  removeAttribute(name) {
    delete this.attributes[name];
    if (name === "href") this.href = "";
    if (name === "id") this.id = "";
    if (name === "class") this.className = "";
  }

  addEventListener(name, callback) { this.listeners[name] = callback; }

  querySelectorAll(selector) {
    const matches = [];
    const walk = (node) => {
      if (node.tagName) {
        if (selector.startsWith(".")) {
          if (node.classList.contains(selector.slice(1))) matches.push(node);
        } else if (node.tagName === selector.toUpperCase()) {
          matches.push(node);
        }
      }
      if (node.childNodes) node.childNodes.forEach(walk);
    };
    walk(this);
    return matches;
  }

  closest(selector) {
    let current = this;
    while (current) {
      if (selector.startsWith(".")) {
        if (current.classList.contains(selector.slice(1))) return current;
      } else if (current.tagName === selector.toUpperCase()) {
        return current;
      }
      current = current.parentNode;
    }
    return null;
  }
}

async function runtime(search, responses, pathname = "/article") {
  const elements = new Map();
  const calls = [];
  let start;
  const listeners = new Map();
  const events = [];
  const document = {
    title: "Статья — Законпозитор",
    addEventListener(name, callback) {
      if (name === "DOMContentLoaded") start = callback;
      else {
        if (!listeners.has(name)) listeners.set(name, []);
        listeners.get(name).push(callback);
      }
    },
    dispatchEvent(event) {
      events.push(event.type);
      for (const callback of listeners.get(event.type) || []) callback(event);
      return true;
    },
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    createElement: (tag) => new Element(tag),
    createTextNode: (text) => ({ textContent: text, tagName: undefined, parentNode: null }),
  };
  for (const selector of ["#article", "#retry-article", "#related-articles", "#article-empty"]) {
    document.querySelector(selector).hidden = true;
  }
  const window = { location: { search, pathname }, MelawdyAPI: { async request(url) {
    calls.push(url);
    const next = responses.shift();
    assert.ok(next, `Unexpected request: ${url}`);
    if (next instanceof Error) throw next;
    return next;
  } } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../static/js/article.js"), "utf8"),
                    { window, document, URLSearchParams, CustomEvent: class { constructor(type) { this.type = type; } } });
  start();
  await new Promise(setImmediate);
  await new Promise(setImmediate);
  return { document, calls, events, get: (selector) => document.querySelector(selector) };
}

const article = { id: "42", updated_at: "2026-10-20T12:00:00Z", published_at: "2026-10-18T12:00:00Z", title: "Как оформить соавторство", summary: "Описание статьи",
                  category: { id: "3", name: "Договорённости" },
                  chunks: ["## Равные права\n\nВводный раздел.",
                           "Первый абзац.\nПродолжение.\n\nВторой абзац.",
                           "## Следующий раздел\n\n- Исходники\n- Переписка\n\n<script>alert(1)</script>"] };

test("loads the URL id, renders every chunk in order and keeps stored HTML as text", async () => {
  const { get, document, calls, events } = await runtime("?id=42", [article, []]);
  assert.equal(calls[0], "public/articles/42");
  assert.equal(document.title, `${article.title} — Законпозитор`);
  assert.equal(get("#article-title").textContent, article.title);
  assert.equal(get("#article-summary").textContent, article.summary);
  assert.equal(get("#article-category").textContent, "Договорённости");
  assert.equal(get("#article-actuality-date").textContent, "Актуальна на 20 октября 2026 г.");
  assert.equal(get("#article").hidden, false);
  assert.equal(get("#article-state").hidden, true);
  const body = get("#article-chunks");
  const sections = body.querySelectorAll(".article-chunk");
  assert.deepEqual(sections.map((section) => section.textContent), [
    "Равные праваВводный раздел.",
    "Первый абзац.\nПродолжение.Второй абзац.",
    "Следующий разделИсходникиПереписка<script>alert(1)</script>",
  ]);
  assert.deepEqual(body.querySelectorAll("h2").map((heading) => heading.textContent),
                   ["Равные права", "Следующий раздел"]);
  assert.equal(body.querySelectorAll("script").length, 0);
  assert.deepEqual(events, ["article-rendered"]);
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
  assert.equal(items[0].children[0].href, "./article.html?id=7");
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
    chunks: ["Текст[^law]", "[^law]: Правило **закона**"] };
  const { get, document, events } = await runtime("?id=42", [record, [], article, []]);
  assert.equal(document.title, "Соавторство — Законпозитор");
  assert.equal(get("#article-title").querySelectorAll("strong")[0].textContent, "Соавторство");
  assert.equal(get("#article-summary").querySelectorAll("em")[0].textContent, "Описание");
  const body = get("#article-chunks");
  const references = body.querySelectorAll(".footnote-ref");
  assert.equal(references.length, 1);
  assert.equal(references[0].href, "#fn-law");
  const notes = body.querySelectorAll(".article-footnotes");
  assert.equal(notes.length, 1);
  const note = notes[0].querySelectorAll("li").find((item) => item.id === "fn-law");
  assert.ok(note, "The reference points to an existing footnote");
  assert.equal(note.textContent, "Правило закона ↩");
  assert.equal(note.querySelectorAll("strong")[0].textContent, "закона");
  assert.equal(note.querySelectorAll(".footnote-back")[0].href, "#" + references[0].id);
  assert.deepEqual(body.querySelectorAll(".article-chunk").map((section) => section.textContent), ["Текст1"]);

  await get("#retry-article").listeners.click();
  assert.equal(get("#article-title").textContent, article.title);
  assert.equal(document.title, `${article.title} — Законпозитор`);
  assert.equal(get("#article-title").querySelectorAll("strong").length, 0);
  assert.equal(get("#article-summary").textContent, article.summary);
  assert.equal(body.querySelectorAll(".article-chunk").length, article.chunks.length);
  assert.equal(body.querySelectorAll(".article-footnotes").length, 0);
  assert.equal(body.querySelectorAll(".footnote-ref").length, 0);
  assert.deepEqual(events, ["article-rendered", "article-rendered"]);
});

test("loads a slug URL and keeps the numeric id for recommendations", async () => {
  const slugArticle = { ...article, slug: "coauthors" };
  const { calls, get } = await runtime("", [slugArticle, [slugArticle, { id: "7", slug: "author", title: "Авторство" }]],
                                       "/article/coauthors");
  assert.equal(calls[0], "public/articles/coauthors");
  assert.equal(get("#article").hidden, false);
  const items = get("#related-articles-list").children;
  assert.equal(items.length, 1);
  assert.equal(items[0].children[0].href, "/article/author");
});

test("encodes a Cyrillic slug and prefers it over the legacy query id", async () => {
  const { calls, get } = await runtime("?id=7", [article, []], "/article/" + encodeURIComponent("авторство"));
  assert.equal(calls[0], "public/articles/" + encodeURIComponent("авторство"));
  assert.equal(get("#article").hidden, false);
});