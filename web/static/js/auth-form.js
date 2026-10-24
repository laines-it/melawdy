document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#auth-form");
  const status = document.querySelector("#status");
  const button = form.querySelector("button[type=submit]");
  const password = form.elements.namedItem("password");
  const confirmation = form.elements.namedItem("password_confirmation");
  let pending = false;

  function validatePasswords() {
    if (confirmation) {
      confirmation.setCustomValidity(confirmation.value && confirmation.value !== password.value
        ? "Пароли не совпадают" : "");
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
          full_name: values.get("full_name"), email: values.get("email"),
          password: values.get("password"), user_type: values.get("user_type"),
        });
      } else {
        await window.ZPAuth.login(values.get("email"), values.get("password"));
      }
      form.reset();
      window.location.replace("/account");
    } catch (error) {
      status.textContent = error.message;
    } finally {
      pending = false;
      button.disabled = false;
    }
  });
  window.ZPAuth.ready.then(() => {
    if (window.ZPAuth.isLoggedIn()) window.location.replace("/account");
  }).catch((error) => { status.textContent = error.message; });
});
