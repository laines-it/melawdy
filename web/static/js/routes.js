(function (root) {
  // Единый источник чистых URL.
  const routes = {
    home: "/",
    documents: "/documents",
    calculator: "/calculator",
    search: "/search",
    account: "/account",
    login: "/login",
    register: "/register",
    admin: "/admin",
    check: "/check",
    article: (id) => `/article/${encodeURIComponent(id)}`,
  };
  root.ZPRoutes = routes;
})(window);