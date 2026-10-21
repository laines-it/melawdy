(function () {
  // Русская локализация типовых сообщений валидации FastAPI/Pydantic.
  function localizeDetail(message) {
    if (!message) return "";
    const text = String(message);
    const map = [
      ["field required", "обязательное поле"],
      ["value is not a valid email address", "некорректный адрес электронной почты"],
      ["value is not a valid integer", "ожидается целое число"],
      ["value is not a valid float", "ожидается число"],
      ["value is not a valid boolean", "ожидается логическое значение"],
      ["value is not a valid string", "ожидается строка"],
      ["string too short", "слишком короткое значение"],
      ["string too long", "слишком длинное значение"],
      ["ensure this value is greater than or equal to", "значение меньше допустимого"],
      ["ensure this value is less than or equal to", "значение больше допустимого"],
      ["Input should be a valid integer", "ожидается целое число"],
      ["Input should be a valid string", "ожидается строка"],
      ["Input should be a valid boolean", "ожидается логическое значение"],
      ["Input should be a valid number", "ожидается число"],
      ["Input should be a valid email address", "некорректный адрес электронной почты"],
    ];
    let result = text;
    for (const [en, ru] of map) {
      const re = new RegExp(en.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
      result = result.replace(re, ru);
    }
    return result;
  }

  async function request(path, options = {}) {
    const { responseType, ...fetchOptions } = options;
    const headers = { ...options.headers };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    const csrfToken = window.ZPAuth?.getCsrfToken();
    if (csrfToken && !["GET", "HEAD"].includes(options.method || "GET")) {
      headers["X-CSRF-Token"] = csrfToken;
    }
    let response;
    try {
      response = await fetch(`/api/v1/${path}`, {
        ...fetchOptions, headers, credentials: "same-origin", cache: "no-store",
      });
    } catch {
      throw new Error("Сервер недоступен. Попробуйте ещё раз позже.");
    }
    if (!response.ok) {
      if (response.status === 401 && path !== "auth/login") window.ZPAuth?.clearSession();
      const data = await response.json().catch(() => ({}));
      const detail = Array.isArray(data.detail)
        ? data.detail.map((item) => `${item.loc.join(".")}: ${localizeDetail(item.msg)}`).join("; ")
        : data.detail;
      const error = new Error(localizeDetail(detail) || `Ошибка сервера: ${response.status}`);
      error.status = response.status;
      throw error;
    }
    if (responseType === "blob") return response.blob();
    return response.status === 204 ? null : response.json();
  }

  window.MelawdyAPI = { request };
})();