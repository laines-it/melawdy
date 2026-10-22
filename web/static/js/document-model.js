(function (root) {
  const placeholder = /\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}/g;
  const unsafeKeys = new Set(["__proto__", "constructor", "prototype"]);
  const labels = { city: "Город", date: "Дата соглашения", author1: "Соавтор 1 — Ф. И. О.",
    author2: "Соавтор 2 — Ф. И. О.", work_title: "Название произведения", work_type: "Тип произведения",
    full_name: "Ф. И. О.", name: "Наименование", email: "Электронная почта", phone: "Телефон",
    address: "Адрес", passport: "Паспортные данные", license_kind: "Вид лицензии" };

  function validId(value) {
    return typeof value === "string" && /^[1-9]\d{0,18}$/.test(value)
      && BigInt(value) <= 9223372036854775807n;
  }
  function safePath(path) {
    return typeof path === "string" && /^[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*$/.test(path)
      && path.split(".").every((part) => !unsafeKeys.has(part));
  }
  function get(params, path) {
    let value = params;
    for (const key of path.split(".")) {
      if (!value || typeof value !== "object" || !Object.hasOwn(value, key)) return undefined;
      value = value[key];
    }
    return value;
  }
  function set(params, path, value) {
    if (!safePath(path)) return;
    const keys = path.split(".");
    let target = params;
    for (const key of keys.slice(0, -1)) {
      if (!target[key] || typeof target[key] !== "object" || Array.isArray(target[key])) target[key] = {};
      target = target[key];
    }
    target[keys.at(-1)] = value;
  }
  // Keep these rules aligned with backend/render.py: preview and DOCX share a contract.

function when(expression, params) {
  if (!expression) return true;

  for (const part of expression.split("&&")) {
    const match =
      /^([a-zA-Z0-9_]+)\s*(==|!=|>=|<=|>|<)\s*([\p{L}\p{N}_]+)$/u
        .exec(part.trim());

    if (!match) return false;

    const [, field, operator, raw] = match;
    const value = params[field];

    if (operator === "==" || operator === "!=") {
      let equal;

      if (raw === "true" || raw === "false") {
        const boolValue = ["1", "true", "yes"].includes(
          String(value).toLowerCase()
        );
        equal = boolValue === (raw === "true");
      } else {
        equal = (value == null ? "" : display(value)) === raw;
      }

      if (operator === "==" && !equal) return false;
      if (operator === "!=" && equal) return false;

      continue;
    }

    const leftNumber = Number(value);
    const rightNumber = Number(raw);

    if (
      value == null ||
      value === "" ||
      !Number.isFinite(leftNumber) ||
      !Number.isFinite(rightNumber)
    ) {
      return false;
    }

    if (operator === ">=" && !(leftNumber >= rightNumber)) return false;
    if (operator === "<=" && !(leftNumber <= rightNumber)) return false;
    if (operator === ">" && !(leftNumber > rightNumber)) return false;
    if (operator === "<" && !(leftNumber < rightNumber)) return false;
  }

  return true;
}

  function display(value) {
    if (value == null || value === "") return "__________";
    if (typeof value === "boolean") return value ? "True" : "False";
    return String(value);
  }
  function sourceBlocks(template) {
    const blocks = template.structure_json?.blocks;
    return Array.isArray(blocks) && blocks.length ? blocks.filter((block) => block && typeof block === "object")
      : [{ id: "body", template: template.body || "" }];
  }
  function renderedBlocks(template, params) {
    return sourceBlocks(template).filter((block) => when(block.when, params)).map((block) => ({
      ...block, text: String(block.template || "").replace(placeholder, (_, path) => display(get(params, path))),
    }));
  }
  function render(template, params) { return renderedBlocks(template, params).map((block) => block.text).join("\n\n"); }

  function sections(template) {
    const configured = template.schema_json?.sections;
    const result = Array.isArray(configured) ? configured.map((section, index) => ({
      ...section, id: String(section.id || `section-${index}`), title: section.title || `Раздел ${index + 1}`,
      fields: (section.fields || []).filter((field) => safePath(field.name)),
    })) : [];
    const known = new Set(result.flatMap((section) => section.fields.map((field) => field.name)));
    const inferred = [];
    for (const block of sourceBlocks(template)) {
      for (const match of String(block.template || "").matchAll(placeholder)) {
        const name = match[1];
        if (!safePath(name) || known.has(name)) continue;
        known.add(name);
        inferred.push({ name, label: labels[name] || labels[name.split(".").at(-1)] || name.replaceAll("_", " "),
          type: "text", required: true });
      }
      const condition = /^([a-zA-Z0-9_]+)\s*(==|!=)\s*([\p{L}\p{N}_]+)$/u.exec((block.when || "").trim());
      if (condition && safePath(condition[1]) && !known.has(condition[1])) {
        const name = condition[1];
        known.add(name);
        const values = [...new Set(sourceBlocks(template).map((item) =>
          /^([a-zA-Z0-9_]+)\s*(==|!=)\s*([\p{L}\p{N}_]+)$/u.exec((item.when || "").trim()))
          .filter((item) => item?.[1] === name).map((item) => item[3]))];
        const boolean = values.every((value) => ["true", "false"].includes(value));
        inferred.push({ name, label: labels[name] || name.replaceAll("_", " "), required: !boolean,
          type: boolean ? "boolean" : "select", ...(boolean ? { default: false } : {}), options: values });
      }
    }
    if (inferred.length) result.push({ id: "parameters", title: result.length ? "Дополнительные параметры" : "Параметры документа", fields: inferred });
    if (!result.length) result.push({ id: "document", title: "Документ", fields: [] });
    return result;
  }
  const model = { validId, safePath, get, set, when, display, sourceBlocks, renderedBlocks, render, sections };
  if (typeof module !== "undefined" && module.exports) module.exports = model;
  else root.DocumentModel = model;
})(typeof window === "undefined" ? globalThis : window);
