(function () {
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
        ? data.detail.map((item) => `${item.loc.join(".")}: ${item.msg}`).join("; ")
        : data.detail;
      const error = new Error(detail || `Ошибка сервера: ${response.status}`);
      error.status = response.status;
      throw error;
    }
    if (responseType === "blob") {
      const blob = await response.blob();
      const disposition = response.headers?.get("Content-Disposition") || "";
      const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(disposition);
      if (match) blob.filename = decodeURIComponent(match[1]);
      return blob;
    }
    return response.status === 204 ? null : response.json();
  }
  window.MelawdyAPI = { request };
})();
