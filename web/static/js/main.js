document.addEventListener("DOMContentLoaded", () => {
  const status = document.querySelector("#status");
  const offsets = { articles: 0, surveys: 0 };
  const pageSize = 25;
  async function api(path) {
    const response = await fetch(`/api/v1/public/${path}`);
    if (!response.ok) throw new Error("Не удалось загрузить данные. Проверьте доступность сервера.");
    return response.json();
  }
  function message(error) { status.textContent = error.message; }
  function node(tag, text) {
    const element = document.createElement(tag);
    element.textContent = text;
    return element;
  }
  async function load(kind, reset = false) {
    if (reset) {
      offsets[kind] = 0;
      document.querySelector(`#${kind}`).replaceChildren();
    }
    const records = await api(`${kind}?limit=${pageSize}&offset=${offsets[kind]}`);
    const list = document.querySelector(`#${kind}`);
    if (!records.length && offsets[kind] === 0) list.append(node("li", "Пока нет записей."));
    for (const record of records) {
      const item = document.createElement("li");
      const button = node("button", record.title);
      button.type = "button";
      button.addEventListener("click", () => show(kind, record.id).catch(message));
      item.append(button);
      list.append(item);
    }
    offsets[kind] += records.length;
    document.querySelector(`#more-${kind}`).hidden = records.length < pageSize;
  }
  async function show(kind, id) {
    const record = await api(`${kind}/${encodeURIComponent(id)}`);
    const target = document.querySelector(kind === "articles" ? "#article" : "#survey");
    target.replaceChildren(node("h3", record.title));
    if (kind === "articles") {
      if (record.summary) target.append(node("p", record.summary));
      for (const body of record.chunks) target.append(node("pre", body));
    } else {
      target.append(node("p", `Версия ${record.version}. Предпросмотр опроса; отправка ответов пока не подключена.`));
      for (const question of record.questions) {
        const fieldset = document.createElement("fieldset");
        fieldset.append(node("legend", question.text + (question.is_required ? " *" : "")));
        if (question.question_type === "text") {
          const text = document.createElement("textarea");
          text.setAttribute("aria-label", question.text);
          fieldset.append(text);
        } else {
          const options = question.question_type === "boolean" ?
            [{ text: "Да", value: "true" }, { text: "Нет", value: "false" }] : question.options;
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
    }
    target.hidden = false;
  }
  document.querySelector("#reload-articles").addEventListener("click", () => load("articles", true).catch(message));
  for (const kind of ["articles", "surveys"]) {
    document.querySelector(`#more-${kind}`).addEventListener("click", () => load(kind).catch(message));
    load(kind, true).catch(message);
  }
});
