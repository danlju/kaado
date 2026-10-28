document.addEventListener("click", async (event) => {
  const button = event.target.closest(".generate-furigana");
  if (!button) return;

  const form = button.closest("form");
  const japaneseField = form.querySelector("#id_front");
  const furiganaField = form.querySelector("#id_front_furigana");
  const status = form.querySelector(".generation-status");
  const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;

  button.disabled = true;
  status.textContent = button.dataset.generating;
  status.classList.remove("status-error");

  try {
    const response = await fetch(button.dataset.url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({ text: japaneseField.value }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || button.dataset.error);

    furiganaField.value = result.furigana;
    status.textContent = button.dataset.generated;
  } catch (error) {
    status.textContent = error.message || button.dataset.error;
    status.classList.add("status-error");
  } finally {
    button.disabled = false;
  }
});

const themeToggle = document.querySelector("#theme-toggle");
if (themeToggle) {
  const setTheme = (theme) => {
    document.documentElement.dataset.theme = theme;
    const isDark = theme === "dark";
    themeToggle.setAttribute("aria-pressed", String(isDark));
    themeToggle.setAttribute("aria-label", isDark ? themeToggle.dataset.switchLight : themeToggle.dataset.switchDark);
    themeToggle.querySelector(".theme-icon").textContent = isDark ? "☀" : "☾";
    themeToggle.querySelector(".theme-label").textContent = isDark ? themeToggle.dataset.labelLight : themeToggle.dataset.labelDark;
  };

  setTheme(document.documentElement.dataset.theme || "light");
  themeToggle.addEventListener("click", () => {
    const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    try {
      localStorage.setItem("kaado-theme", nextTheme);
    } catch (error) {
      // The current page still changes theme if local storage is unavailable.
    }
    setTheme(nextTheme);
  });
}

const languageSelect = document.querySelector("#language-select");
if (languageSelect) {
  languageSelect.addEventListener("change", () => languageSelect.form.requestSubmit());
}
