document.addEventListener("click", async (event) => {
  const button = event.target.closest(".generate-furigana");
  if (!button) return;

  const form = button.closest("form");
  const japaneseField = form.querySelector("#id_front");
  const furiganaField = form.querySelector("#id_front_furigana");
  const status = form.querySelector(".generation-status");
  const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]").value;

  button.disabled = true;
  status.textContent = "Generating…";
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
    if (!response.ok) throw new Error(result.error || "Could not generate furigana.");

    furiganaField.value = result.furigana;
    status.textContent = "Generated. Check the readings, then save the card.";
  } catch (error) {
    status.textContent = error.message || "Could not generate furigana.";
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
    themeToggle.setAttribute("aria-label", `Switch to ${isDark ? "light" : "dark"} mode`);
    themeToggle.querySelector(".theme-icon").textContent = isDark ? "☀" : "☾";
    themeToggle.querySelector(".theme-label").textContent = isDark ? "Light mode" : "Dark mode";
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
