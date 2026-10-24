(function () {
  let session = null;
  let logoutPending = false;

  function updateUI() {
    const user = session?.user;
    document.querySelectorAll("[data-auth-action]").forEach((link) => {
      link.textContent = user ? "Выйти →" : "Войти →";
      link.href = user ? "#logout" : "/login";
      link.dataset.authState = user ? "logged-in" : "logged-out";
    });
    document.querySelectorAll("[data-user-name]").forEach((element) => {
      element.textContent = user ? user.full_name || user.email : "";
      element.hidden = !user;
    });
    document.querySelectorAll("[data-auth-required]").forEach((element) => { element.hidden = !user; });
    document.querySelectorAll("[data-auth-guest]").forEach((element) => { element.hidden = Boolean(user); });
  }

  function setSession(value) {
    session = value;
    updateUI();
    document.dispatchEvent(new CustomEvent("auth-change", { detail: value }));
  }

  async function refresh() {
    try {
      setSession(await window.MelawdyAPI.request("auth/me"));
    } catch (error) {
      setSession(null);
      if (error.status !== 401) throw error;
    }
    return session;
  }

  async function login(email, password) {
    await ready.catch(() => {});
    setSession(await window.MelawdyAPI.request("auth/login", {
      method: "POST", body: JSON.stringify({ email, password }),
    }));
    return session;
  }

  async function logout() {
    await window.MelawdyAPI.request("auth/logout", { method: "POST" });
    setSession(null);
  }

  async function register(payload) {
    await ready.catch(() => {});
    setSession(await window.MelawdyAPI.request("auth/register", {
      method: "POST", body: JSON.stringify(payload),
    }));
    return session;
  }

  document.addEventListener("click", async (event) => {
    const link = event.target.closest("[data-auth-action]");
    if (!link || link.dataset.authState !== "logged-in") return;
    event.preventDefault();
    if (logoutPending) return;
    logoutPending = true;
    try {
      await logout();
    } catch (error) {
      const status = document.querySelector("#status");
      if (status) status.textContent = error.message;
      else window.alert(error.message);
    } finally {
      logoutPending = false;
    }
  });

  let ready;
  window.ZPAuth = {
    getUser: () => session?.user || null,
    getCsrfToken: () => session?.csrf_token || "",
    isLoggedIn: () => Boolean(session?.user),
    clearSession: () => setSession(null),
    login, register, logout, refresh, updateUI,
  };
  ready = new Promise((resolve) => document.addEventListener("DOMContentLoaded", resolve))
    .then(refresh);
  window.ZPAuth.ready = ready;
  ready.catch(() => {});
})();
