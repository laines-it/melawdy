/**
 * Простая система авторизации для демонстрации.
 *
 * Работает в двух режимах:
 *  1. Если доступен API /api/v1/auth/* — использует его.
 *  2. Если API недоступен — fallback на admin/admin с хранением в localStorage.
 *
 * Состояние пользователя хранится в localStorage под ключом "zp_user".
 */
(function () {
  const STORAGE_KEY = "zp_user";
  const DEMO_LOGIN = "admin";
  const DEMO_PASSWORD = "admin";

  // --- Работа с хранилищем ---
  function getUser() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  function setUser(user) {
    if (user) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    updateUI();
  }

  // --- Проверка входа ---
  function isLoggedIn() {
    return Boolean(getUser());
  }

  // --- Простой вход (fallback) ---
  function simpleLogin(login, password) {
    if (login === DEMO_LOGIN && password === DEMO_PASSWORD) {
      return {
        full_name: "Администратор",
        email: "admin@zakonpozitor.ru",
        role: "admin",
      };
    }
    return null;
  }

  // --- Обновление UI на всех страницах ---
  function updateUI() {
    const user = getUser();
    const loggedIn = Boolean(user);

    // Кнопка "Войти →" / "Выйти →" в шапке
    document.querySelectorAll("[data-auth-action]").forEach((el) => {
      if (loggedIn) {
        el.textContent = "Выйти →";
        el.setAttribute("href", "#logout");
        el.dataset.authState = "logged-in";
      } else {
        el.textContent = "Войти →";
        el.setAttribute("href", "./account.html");
        el.dataset.authState = "logged-out";
      }
    });

    // Имя пользователя в шапке (если есть)
    document.querySelectorAll("[data-user-name]").forEach((el) => {
      if (loggedIn && user) {
        el.textContent = user.full_name || user.email;
        el.hidden = false;
      } else {
        el.hidden = true;
      }
    });

    // Секции "только для авторизованных" / "только для гостей"
    document.querySelectorAll("[data-auth-required]").forEach((el) => {
      el.hidden = !loggedIn;
    });
    document.querySelectorAll("[data-auth-guest]").forEach((el) => {
      el.hidden = loggedIn;
    });
  }

  // --- Обработка клика по кнопке "Войти/Выйти" ---
  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-auth-action]");
    if (!link) return;

    if (link.dataset.authState === "logged-in") {
      event.preventDefault();
      if (confirm("Выйти из аккаунта?")) {
        setUser(null);
        // Если мы на account.html — показать форму входа
        if (typeof window.onAuthLogout === "function") {
          window.onAuthLogout();
        } else {
          // Иначе просто перезагрузим/перейдём на главную
          if (window.location.pathname.includes("admin")) {
            window.location.reload();
          } else {
            window.location.href = "./index.html";
          }
        }
      }
    }
    // Если logged-out — просто переходим по ссылке (./account.html)
  });

  // --- Публичный API для других скриптов ---
  window.ZPAuth = {
    getUser,
    setUser,
    isLoggedIn,
    simpleLogin,
    updateUI,
    DEMO_LOGIN,
    DEMO_PASSWORD,
  };

  // --- Обновляем UI при загрузке ---
  document.addEventListener("DOMContentLoaded", updateUI);
})();