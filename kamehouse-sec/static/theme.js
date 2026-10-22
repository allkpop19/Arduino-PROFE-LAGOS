"use strict";
// Preferencia local; funciona aunque el navegador no permita guardar datos.
(() => {
  const key = "casa-theme";
  let theme = "light";
  try { theme = localStorage.getItem(key) === "dark" ? "dark" : "light"; } catch {}

  function apply(value) {
    theme = value;
    document.documentElement.dataset.theme = value;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", value === "dark" ? "#101010" : "#ffffff");
    const button = document.getElementById("theme-toggle");
    if (button) {
      button.textContent = value === "dark" ? "☀ Modo claro" : "◐ Modo oscuro";
      button.setAttribute("aria-pressed", String(value === "dark"));
      button.title = value === "dark" ? "Volver a azul y amarillo" : "Fondo oscuro e interfaz en blanco y negro";
    }
  }

  apply(theme);
  document.addEventListener("DOMContentLoaded", () => {
    apply(theme);
    document.getElementById("theme-toggle").addEventListener("click", () => {
      apply(theme === "dark" ? "light" : "dark");
      try { localStorage.setItem(key, theme); } catch {}
    });
  });
})();
