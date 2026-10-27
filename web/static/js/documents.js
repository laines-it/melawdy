document.addEventListener("DOMContentLoaded", () => {
  const $ = (selector) => document.querySelector(selector);
  const api = window.MelawdyAPI.request;
  const model = window.DocumentModel;
  const query = new URLSearchParams(window.location.search);
  const controls = new Map();
  const form = $("#document-form");
  let template, sections = [], params = {}, documentId = null, sectionIndex = 0;
  let busy = false, dirty = false, offset = 0, catalogBusy = false, pendingAction = null;
  let ownerId = null, authLost = false, loadingVersion = 0;

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function state(title, description, { retry = false, login = false } = {}) {
    $("#document-state").hidden = false;
    $("#document-state").setAttribute("aria-busy", "false");
    $("#state-title").textContent = title;
    $("#state-description").textContent = description;
    $("#retry-documents").hidden = !retry;
    $("#login-to-open").hidden = !login;
  }
  function fail(error) {
    $("#status").textContent = error.status === 401 ? "Войдите в аккаунт, чтобы продолжить. Заполненные поля сохранены на странице." : error.message;
  }
  function changed() {
    dirty = true;
    $("#save-state").textContent = "Есть несохранённые изменения";
    $("#status").textContent = "";
  }
  function setBusy(value) {
    busy = value;
    $("#save-document").disabled = value;
    $("#generate-document").disabled = value;
    $("#generate-document").textContent = value ? "Подготавливаем документ…" : "Собрать документ →";
    form.inert = value;
    form.setAttribute("aria-busy", String(value));
  }

  // ---- Имя файла из Content-Disposition ----
  // Бэкенд отдаёт: attachment; filename="document-<id>.<ext>"
  function filenameFromBlob(blob) {
    if (blob && typeof blob.filename === "string" && blob.filename) return blob.filename;
    return null;
  }
  function safeFilename(base) {
    return String(base || "document")
      .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 120) || "document";
  }

  async function loadCatalog() {
    if (catalogBusy) return;
    catalogBusy = true;
    $("#more-templates").disabled = true;
    try {
      const records = await api(`public/templates?limit=24&offset=${offset}`);
      for (const record of records) {
        const card = element("a", undefined, "document-template-card");
        card.href = `./documents?template=${encodeURIComponent(record.id)}`;
        const icon = element("span", "▤", "document-template-icon");
        icon.setAttribute("aria-hidden", "true");
        card.append(icon, element("h2", record.title),
          element("p", record.description || "Заполните параметры и сформируйте документ по шаблону."),
          element("span", "Создать документ →"));
        $("#template-list").append(card);
      }
      offset += records.length;
      $("#more-templates").hidden = records.length < 24;
      $("#document-state").hidden = true;
      if (!offset) state("Шаблоны скоро появятся", "Пока нет опубликованных документов. Загляните позже или обратитесь к администратору.");
    } catch (error) {
      state("Не удалось загрузить шаблоны", error.message, { retry: true });
    } finally {
      catalogBusy = false;
      $("#more-templates").disabled = false;
    }
  }

  function buildField(field, index) {
    const wrapper = element("div", undefined, "document-field");
    const id = `document-field-${index}`;
    const label = `${field.label || field.name}${field.required ? " *" : ""}`;
    const value = model.get(params, field.name);
    let input;
    let inputs;
    if (field.type === "radio") {
      input = element("fieldset");
      input.append(element("legend", label));
      inputs = (field.options || []).map((option, optionIndex) => {
        const choice = typeof option === "object" ? option : { value: option, label: option };
        const row = element("label", undefined, "document-choice");
        const radio = element("input");
        radio.type = "radio";
        radio.name = field.name;
        radio.id = `${id}-${optionIndex}`;
        radio.value = String(choice.value);
        radio.checked = value != null && String(value) === radio.value;
        radio.required = Boolean(field.required);
        row.append(radio, document.createTextNode(choice.label || String(choice.value)));
        input.append(row);
        return radio;
      });
    } else if (field.type === "boolean") {
      input = element("input");
      input.type = "checkbox";
      input.checked = value === true;
      input.required = Boolean(field.required);
      const row = element("label", undefined, "document-choice");
      row.append(input, document.createTextNode(label));
      wrapper.append(row);
    } else {
      const labelNode = element("label", label);
      labelNode.htmlFor = id;
      wrapper.append(labelNode);
      if (field.type === "select") {
        input = element("select");
        const empty = element("option", "Выберите вариант");
        empty.value = "";
        input.append(empty);
        for (const option of field.options || []) {
          const choice = typeof option === "object" ? option : { value: option, label: option };
          const node = element("option", choice.label || String(choice.value));
          node.value = String(choice.value);
          input.append(node);
        }
      } else if (field.type === "textarea") {
        input = element("textarea");
        input.rows = 3;
      } else {
        input = element("input");
        input.type = ["number", "email", "tel", "date"].includes(field.type) ? field.type : "text";
      }
      input.value = value ?? "";
      if (field.min != null) input.min = field.min;
      if (field.max != null) input.max = field.max;
      if (field.type === "number") input.step = field.step ?? "any";
      if (["text", "textarea", "email", "tel"].includes(field.type || "text")) input.maxLength = field.max_length || 2000;
      input.required = Boolean(field.required);
      input.placeholder = field.placeholder || "";
    }
    input.id = id;
    if (input.tagName !== "FIELDSET") input.name = field.name;
    if (field.type !== "boolean") wrapper.append(input);
    if (field.hint) {
      const hint = element("small", field.hint);
      hint.id = `${id}-hint`;
      wrapper.append(hint);
      input.setAttribute("aria-describedby", hint.id);
    }
    inputs ||= [input];
    controls.set(field.name, { field, wrapper, input, inputs, section: sectionIndex });
    for (const control of inputs) control.addEventListener("input", () => {
      const raw = field.type === "radio" ? inputs.find((radio) => radio.checked)?.value : input.value;
      const next = field.type === "boolean" ? input.checked : field.type === "number" && raw !== "" ? Number(raw) : raw;
      model.set(params, field.name, next);
      changed();
      updateConditions();
      updatePreview();
    });
    return wrapper;
  }

  function buildForm() {
    sections = model.sections(template);
    for (const section of sections) for (const field of section.fields) {
      if (model.get(params, field.name) === undefined && field.default !== undefined) model.set(params, field.name, field.default);
    }
    controls.clear();
    $("#document-fields").replaceChildren();
    $("#document-sections").replaceChildren();
    sections.forEach((section, index) => {
      sectionIndex = index;
      const button = element("button", undefined, "document-section-link");
      button.type = "button";
      button.setAttribute("aria-label", section.title);
      button.setAttribute("aria-controls", `document-section-${index}`);
      const icon = element("span", section.icon || ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"][index], "document-section-icon");
      icon.setAttribute("aria-hidden", "true");
      const check = element("span", "", "document-section-check");
      check.setAttribute("aria-label", "Раздел заполнен");
      button.append(icon, element("span", section.title), check);
      button.addEventListener("click", () => selectSection(index, true));
      $("#document-sections").append(button);
      const group = element("fieldset", undefined, "document-field-group");
      group.id = `document-section-${index}`;
      group.append(element("legend", section.title));
      if (section.description) group.append(element("p", section.description));
      let lastCard = null, card;
      for (const field of section.fields) {
        if (field.group && field.group !== lastCard) {
          card = element("div", undefined, "document-field-card");
          card.append(element("h3", field.group));
          group.append(card);
        }
        (field.group ? card : group).append(buildField(field, controls.size));
        lastCard = field.group;
      }
      if (!section.fields.length) group.append(element("p", "В этом разделе нет полей для заполнения. Текст включается в документ автоматически."));
      $("#document-fields").append(group);
    });
    sectionIndex = 0;
    updateConditions();
    selectSection(0);
    updatePreview();
  }

  function selectSection(index, scroll = false) {
    sectionIndex = Math.max(0, Math.min(sections.length - 1, index));
    [...$("#document-fields").children].forEach((group, i) => { group.hidden = i !== sectionIndex; });
    [...$("#document-sections").children].forEach((button, i) => {
      if (i === sectionIndex) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    });
    $("#previous-section").disabled = sectionIndex === 0;
    $("#next-section").disabled = sectionIndex === sections.length - 1;
    highlightSection(scroll);
  }
  function highlightSection(scroll) {
    const blocks = [...$("#document-preview").children].filter((node) => node.dataset.section);
    let selected;
    for (const block of blocks) {
      const active = block.dataset.section === sections[sectionIndex]?.id;
      block.classList.toggle("is-active", active);
      if (active && !selected) selected = block;
    }
    if (scroll && selected) $("#preview-scroll").scrollTo({ top: selected.offsetTop - $("#document-preview").offsetTop, behavior: "auto" });
  }
  function updateConditions() {
    for (const { field, wrapper, inputs } of controls.values()) {
      wrapper.hidden = !model.when(field.when, params);
      const value = model.get(params, field.name);
      for (const input of inputs) {
        input.disabled = wrapper.hidden;
        input.setCustomValidity(field.required && typeof value === "string" && !value.trim() ? "Заполните поле." : "");
      }
    }
    for (const card of document.querySelectorAll(".document-field-card")) {
      card.hidden = [...card.querySelectorAll(".document-field")].every((field) => field.hidden);
    }
  }

  function appendTemplateText(target, text) {
    const regex = /\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}/g;
    let from = 0;
    for (const match of text.matchAll(regex)) {
      target.append(document.createTextNode(text.slice(from, match.index)));
      const value = model.get(params, match[1]);
      target.append(element("mark", model.display(value), value != null && value !== "" ? "is-filled" : ""));
      from = match.index + match[0].length;
    }
    target.append(document.createTextNode(text.slice(from)));
  }
  function updatePreview() {
    const preview = $("#document-preview");
    preview.replaceChildren();
    const blocks = model.sourceBlocks(template).filter((block) => model.when(block.when, params));
    let first = true;
    for (const block of blocks) {
      const section = element("section", undefined, "document-paper-section");
      section.dataset.section = String(block.section || block.id || "");
      for (const paragraph of String(block.template || "").split(/\n\n/)) {
        if (!paragraph.trim()) continue;
        const heading = first && !paragraph.includes("\n") && paragraph.length < 160;
        const tag = heading ? "h2" : /^\d+\.\s+[А-ЯЁA-Z][А-ЯЁA-Z\s.,—–()]+$/.test(paragraph.trim()) ? "h3" : "p";
        const node = element(tag);
        const placeAndDate = paragraph.match(/^(.*\{\{\s*city\s*\}\})[\s,]+(\{\{\s*date\s*\}\}.*)$/);
        if (placeAndDate) {
          node.classList.add("document-place-date");
          const place = element("span");
          const date = element("span", undefined, "document-preamble-date");
          appendTemplateText(place, placeAndDate[1]);
          appendTemplateText(date, placeAndDate[2]);
          node.append(place, date);
        } else {
          appendTemplateText(node, paragraph);
        }
        section.append(node);
        first = false;
      }
      preview.append(section);
    }
    if (!preview.textContent.trim()) preview.append(element("p", "Для этих параметров в шаблоне пока нет текста."));
    highlightSection(false);
    const required = [...controls.values()].filter((entry) => entry.field.required && !entry.wrapper.hidden);
    const filled = required.filter(({ field, inputs }) => {
      const value = model.get(params, field.name);
      return value !== undefined && value !== null && value !== "" && inputs.every((input) => input.checkValidity());
    }).length;
    $("#progress-label").textContent = `${filled} из ${required.length}`;
    $("#document-progress").max = required.length || 1;
    $("#document-progress").value = required.length ? filled : 1;
    [...$("#document-sections").children].forEach((button, index) => {
      const fields = required.filter((entry) => entry.section === index);
      const complete = fields.length > 0 && fields.every(({ field, inputs }) =>
        model.get(params, field.name) != null && model.get(params, field.name) !== "" && inputs.every((input) => input.checkValidity()));
      button.lastElementChild.textContent = complete ? "✓" : "";
      button.lastElementChild.hidden = !complete;
    });
  }

  async function openEditor() {
    const version = ++loadingVersion;
    $("#catalog").hidden = true;
    $("#editor").hidden = true;
    $("#status").textContent = "";
    $("#document-state").setAttribute("aria-busy", "true");
    const sourceId = query.get("template");
    const savedId = query.get("document");
    if (!model.validId(query.has("document") ? savedId : sourceId)) {
      state("Документ не выбран", "Вернитесь к выбору документа и откройте нужный шаблон.");
      return;
    }
    try {
      let saved;
      if (savedId) {
        await window.ZPAuth.ready.catch(() => {});
        if (!window.ZPAuth.isLoggedIn()) {
          state("Войдите, чтобы открыть документ", "Ваши документы доступны только в вашем аккаунте.", { login: true });
          return;
        }
        saved = await api(`cabinet/documents/${savedId}`);
        ownerId = String(window.ZPAuth.getUser().id);
        if (!saved.template_id) {
          state("У документа нет шаблона", "Этот документ создан вне конструктора. Выберите опубликованный шаблон для нового документа.");
          return;
        }
      }
      const record = await api(`public/templates/${encodeURIComponent(saved ? saved.template_id : sourceId)}`);
      if (version !== loadingVersion) return;
      template = record;
      params = saved?.content_json || {};
      documentId = savedId;
      authLost = false;
      $("#document-title").value = saved?.title || template.title;
      $("#document-heading").textContent = template.title;
      document.title = `${template.title} — Законпозитор`;
      buildForm();
      dirty = false;
      $("#save-state").textContent = saved ? "Черновик сохранён в личном кабинете" : "Черновик ещё не сохранён";
      $("#document-state").hidden = true;
      $("#editor").hidden = false;
    } catch (error) {
      state(error.status === 404 ? "Документ или шаблон не найден" : "Не удалось открыть документ", error.message,
        { retry: error.status !== 404, login: error.status === 401 });
    }
  }

  async function saveDraft() {
    const title = $("#document-title").value.trim();
    if (!title) {
      $("#document-title").focus();
      throw new Error("Укажите название документа.");
    }
    const body = { title, content_json: params };
    if (!documentId) {
      body.document_type = template.document_type || "contract";
      body.template_id = template.id;
    }
    const saved = await api(documentId ? `cabinet/documents/${documentId}` : "cabinet/documents", {
      method: documentId ? "PATCH" : "POST", body: JSON.stringify(body),
    });
    documentId = String(saved.id);
    ownerId = String(window.ZPAuth.getUser().id);
    window.history.replaceState(null, "", `/documents?document=${encodeURIComponent(documentId)}`);
    query.delete("template");
    query.set("document", documentId);
    dirty = false;
    $("#save-state").textContent = "Сохранено в личном кабинете";
  }
  function validate() {
    if (!$("#document-title").checkValidity()) { $("#document-title").reportValidity(); return false; }
    for (const entry of controls.values()) for (const input of entry.inputs) {
      if (!input.checkValidity()) {
        setView(false);
        selectSection(entry.section, true);
        input.reportValidity();
        input.focus();
        return false;
      }
    }
    return true;
  }
  function askLogin(action) {
    pendingAction = action;
    $("#document-login-status").textContent = "";
    if (!$("#login-dialog").open) $("#login-dialog").showModal();
  }
  function selectedFormat() {
    const raw = ($("#download-format")?.value || "docx").toLowerCase();
    if (raw !== "docx" && raw !== "pdf") {
      throw new Error("Выберите формат файла: Word (DOCX) или PDF.");
    }
    return raw;
  }
  async function perform(action) {
    if (busy) return;
    $("#status").textContent = "";
    if (!$("#document-title").value.trim()) { $("#document-title").reportValidity(); $("#document-title").focus(); fail(new Error("Укажите название документа.")); return; }
    if (action === "export" && !validate()) return;
    setBusy(true);
    try {
      await window.ZPAuth.ready.catch(() => {});
      if (!window.ZPAuth.isLoggedIn()) { askLogin(action); return; }
      if (authLost || (ownerId && ownerId !== String(window.ZPAuth.getUser().id))) {
        throw new Error("Аккаунт изменился. Откройте документ заново из своего личного кабинета.");
      }
      await saveDraft();
      if (action === "export") {
        const ext = selectedFormat();
        const queryString = ext === "pdf" ? "?format=pdf" : "";
        const blob = await api(`cabinet/documents/${documentId}/download${queryString}`, { responseType: "blob" });
        const url = URL.createObjectURL(blob);
        const link = element("a");
        link.href = url;
        link.download = filenameFromBlob(blob)
          || `${safeFilename($("#document-title").value)}.${ext}`;
        document.body.append(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
        $("#save-state").textContent = `Документ сохранён. Файл ${ext.toUpperCase()} готов к скачиванию`;
      }
    } catch (error) { fail(error); }
    finally { setBusy(false); }
  }
  function setView(text) {
    $(".document-workspace").classList.toggle("is-text-view", text);
    $("#parameters-panel").hidden = text;
    $("#builder-view").setAttribute("aria-pressed", String(!text));
    $("#text-view").setAttribute("aria-pressed", String(text));
  }
  $("#builder-view").addEventListener("click", () => setView(false));
  $("#text-view").addEventListener("click", () => setView(true));
  $("#previous-section").addEventListener("click", () => selectSection(sectionIndex - 1, true));
  $("#next-section").addEventListener("click", () => selectSection(sectionIndex + 1, true));
  $("#document-title").addEventListener("input", changed);
  $("#save-document").addEventListener("click", () => perform("save"));
  form.addEventListener("submit", (event) => { event.preventDefault(); perform("export"); });
  $("#expand-document").addEventListener("click", () => {
    $("#full-preview").replaceChildren(...[...$("#document-preview").children].map((node) => node.cloneNode(true)));
    $("#preview-dialog").showModal();
  });
  $("#more-templates").addEventListener("click", loadCatalog);
  $("#retry-documents").addEventListener("click", () => query.has("template") || query.has("document") ? openEditor() : loadCatalog());
  $("#login-to-open").addEventListener("click", () => askLogin("open"));
  $("#document-login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("#document-login-submit");
    if (button.disabled) return;
    button.disabled = true;
    try {
      await window.ZPAuth.login($("#document-email").value.trim(), $("#document-password").value);
      $("#document-password").value = "";
      $("#login-dialog").close();
      const action = pendingAction;
      pendingAction = null;
      if (action === "open") await openEditor();
      else if (action) await perform(action);
    } catch (error) { $("#document-login-status").textContent = error.message; }
    finally { button.disabled = false; }
  });
  $("#login-dialog").addEventListener("close", () => { $("#document-password").value = ""; pendingAction = null; });
  document.addEventListener("auth-change", (event) => {
    const user = event.detail?.user;
    if (ownerId && (!user || String(user.id) !== ownerId)) {
      authLost = true;
      loadingVersion++;
      $("#editor").hidden = true;
      $("#preview-dialog").close();
      state("Сеанс завершён", "Откройте документ из личного кабинета после входа в свой аккаунт.", { login: true });
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (dirty) { event.preventDefault(); event.returnValue = ""; }
  });
  window.addEventListener("focus", () => {
    if ($("#login-dialog").open) window.ZPAuth.refresh().then(() => {
      if (!window.ZPAuth.isLoggedIn()) return;
      const action = pendingAction;
      $("#login-dialog").close();
      if (action === "open") openEditor();
      else if (action) perform(action);
    }).catch((error) => { $("#document-login-status").textContent = error.message; });
  });
  if (query.has("template") || query.has("document")) openEditor();
  else loadCatalog();
});