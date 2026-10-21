document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#auth-form");
  const status = document.querySelector("#status");
  const button = form.querySelector("button[type=submit]");
  const password = form.elements.namedItem("password");
  const confirmation = form.elements.namedItem("password_confirmation");
  let pending = false;

  function accountHref() {
    return (window.ZPRoutes && window.ZPRoutes.account) || "/account";
  }

  function validatePasswords() {
    if (confirmation) {
      confirmation.setCustomValidity(
        confirmation.value && confirmation.value !== password.value
          ? "Пароли не совпадают"
          : ""
      );
    }
  }

  form.addEventListener("input", () => {
    validatePasswords();
    status.textContent = "";
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    validatePasswords();
    if (pending || !form.reportValidity()) return;
    pending = true;
    button.disabled = true;
    status.textContent = "";
    try {
      const values = new FormData(form);
      if (form.dataset.mode === "register") {
        await window.ZPAuth.register({
          full_name: values.get("full_name"),
          email: values.get("email"),
          password: values.get("password"),
          user_type: values.get("user_type"),
        });
      } else {
        await window.ZPAuth.login(values.get("email"), values.get("password"));
      }
      form.reset();
      window.location.replace(accountHref());
    } catch (error) {
      status.textContent = error.message;
    } finally {
      pending = false;
      button.disabled = false;
    }
  });

  // FIX: защита от петли /login ↔ /account.
  // Если пользователь уже залогинен — это нормальный редирект на кабинет.
  // Но если он пришёл СЮДА именно с /account (парметр ?from=account),
  // значит личный кабинет не отрисовался — не зацикливаемся, показываем
  // сообщение и оставляем форму видимой, чтобы можно было выйти/перелогиниться.
  window.ZPAuth.ready
    .then(() => {
      if (!window.ZPAuth.isLoggedIn()) return;
      const from = new URLSearchParams(window.location.search).get("from");
      if (from === "account") {
        status.textContent =
          "Сессия активна, но личный кабинет не загрузился. Обновите страницу или выйдите и войдите снова.";
        return;
      }
      window.location.replace(accountHref());
    })
    .catch((error) => {
      status.textContent = error.message;
    });
});