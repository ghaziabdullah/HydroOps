function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(";").shift();
    }
    return "";
}

(function initTheme() {
    const html = document.documentElement;
    const themeToggle = document.getElementById("themeToggle");
    const themeLabel = themeToggle ? themeToggle.querySelector("[data-theme-label]") : null;
    const themeIcon = themeToggle ? themeToggle.querySelector(".ov-theme-icon") : null;
    const saved = localStorage.getItem("hydroops_theme") || "light";
    html.setAttribute("data-theme", saved);

    function updateThemeUI(theme) {
        const label = theme === "light" ? "Light" : "Dark";
        if (themeLabel) {
            themeLabel.textContent = label;
        } else if (themeToggle) {
            themeToggle.textContent = label;
        }
        if (themeIcon) {
            themeIcon.textContent = theme === "light" ? "☀" : "☾";
        }
    }

    if (themeToggle) {
        updateThemeUI(saved);
        themeToggle.addEventListener("click", () => {
            const next = html.getAttribute("data-theme") === "light" ? "dark" : "light";
            html.setAttribute("data-theme", next);
            localStorage.setItem("hydroops_theme", next);
            updateThemeUI(next);
        });
    }
})();

(function initSidebarToggle() {
    const sidebar = document.querySelector(".app-sidebar");
    const button = document.getElementById("sidebarToggle");
    if (!sidebar || !button) {
        return;
    }
    button.addEventListener("click", () => {
        sidebar.classList.toggle("collapsed");
    });
})();

(function initCommonTopbarActions() {
    const alertsBell = document.getElementById("alertsBell");
    const userChip = document.getElementById("userChip");

    if (alertsBell) {
        alertsBell.addEventListener("click", () => {
            window.location.href = "/ops/alerts-center/";
        });
    }

    if (userChip) {
        userChip.addEventListener("click", () => {
            window.location.href = "/accounts/profile/";
        });
    }
})();

(function initActiveNavLink() {
    const path = window.location.pathname;
    document.querySelectorAll(".nav-link-item").forEach((link) => {
        if (path.startsWith(new URL(link.href).pathname)) {
            link.classList.add("active");
        }
    });
})();

document.body.addEventListener("htmx:configRequest", function(event) {
    event.detail.headers["X-CSRFToken"] = getCookie("csrftoken");
});
