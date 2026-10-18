document.addEventListener("DOMContentLoaded", () => {
  const request = window.MelawdyAPI.request;
  const status = document.querySelector("#status");
  const offsets = { articles: 0, surveys: 0 };
  const loading = new Set();
  const pageSize = 25;

  function message(error) { status.textContent = error.message; }
  function node(tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    return element;
  }

  function articleLink(id, title) {
    const link = node("a", title);
    link.href = `./article.html?id=${encodeURIComponent(id)}`;
    return link;
  }

  async function load(kind, reset = false) {
    if (loading.has(kind)) return;
    loading.add(kind);
    const more = document.querySelector(`#more-${kind}`);
    more.disabled = true;
    try {
      const records = await request(`public/${kind}?limit=${pageSize}&offset=${reset ? 0 : offsets[kind]}`);
      const list = document.querySelector(`#${kind}`);
      if (reset) {
        offsets[kind] = 0;
        list.replaceChildren();
      }
      if (!records.length && offsets[kind] === 0) list.append(node("li", "Пока нет записей."));
      for (const record of records) {
        const item = document.createElement("li");
        if (kind === "articles") {
          item.append(articleLink(record.id, record.title));
        } else {
          const button = node("button", record.title);
          button.type = "button";
          button.addEventListener("click", () => showSurvey(record.id).catch(message));
          item.append(button);
        }
        list.append(item);
      }
      offsets[kind] += records.length;
      more.hidden = records.length < pageSize;
    } finally {
      loading.delete(kind);
      more.disabled = false;
    }
  }

  async function showSurvey(id) {
    const record = await request(`public/surveys/${encodeURIComponent(id)}`);
    const target = document.querySelector("#survey");
    target.replaceChildren(node("h3", record.title));
    target.append(node("p", `Версия ${record.version}. Предпросмотр опроса; отправка ответов пока не подключена.`));
    for (const question of record.questions) {
      const fieldset = document.createElement("fieldset");
      fieldset.disabled = true;
      fieldset.append(node("legend", question.text + (question.is_required ? " *" : "")));
      if (question.question_type === "text") {
        const text = document.createElement("textarea");
        text.setAttribute("aria-label", question.text);
        fieldset.append(text);
      } else {
        const options = question.question_type === "boolean" && !question.options.length
          ? [{ text: "Да", value: "true" }, { text: "Нет", value: "false" }] : question.options;
        for (const option of options) {
          const label = document.createElement("label");
          const input = document.createElement("input");
          input.type = question.question_type === "multiple_choice" ? "checkbox" : "radio";
          input.name = `question-${question.id}`;
          input.value = option.value;
          label.append(input, document.createTextNode(option.text));
          fieldset.append(label, document.createElement("br"));
        }
      }
      target.append(fieldset);
    }
    target.hidden = false;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function loadFaq() {
    const list = document.querySelector("#faq-list");
    const records = await request("public/faq");
    list.replaceChildren();
    if (!records.length) list.append(node("p", "Вопросы пока не опубликованы."));
    for (const record of records) {
      const card = document.createElement("details");
      card.className = "faq-card";
      const summary = node("summary", record.question);
      summary.className = "faq-question";
      const answer = node("p", record.answer);
      answer.className = "faq-answer";
      card.append(summary, answer);
      if (record.content_item_id) {
        card.append(articleLink(record.content_item_id, "Читать материал →"));
      }
      list.append(card);
    }
  }

  document.querySelector("#search-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const query = document.querySelector("#search-query").value.trim();
    if (!query) return;
    window.location.href = `./search.html?query=${encodeURIComponent(query)}`;
  });

  document.querySelector("#reload-articles").addEventListener("click", () => load("articles", true).catch(message));
  for (const kind of ["articles", "surveys"]) {
    document.querySelector(`#more-${kind}`).addEventListener("click", () => load(kind).catch(message));
    load(kind, true).catch(message);
  }
  loadFaq().catch(message);
});
