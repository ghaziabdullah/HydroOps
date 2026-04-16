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
    const shell = document.querySelector(".app-shell");
    const sidebar = document.querySelector(".app-sidebar");
    const desktopToggle = document.getElementById("sidebarToggle");
    const mobileToggle = document.getElementById("mobileSidebarToggle");
    const backdrop = document.getElementById("sidebarBackdrop");
    if (!shell || !sidebar) {
        return;
    }

    function isMobileViewport() {
        return window.matchMedia("(max-width: 992px)").matches;
    }

    function openMobileSidebar() {
        shell.classList.add("mobile-sidebar-open");
        if (mobileToggle) {
            mobileToggle.setAttribute("aria-expanded", "true");
        }
    }

    function closeMobileSidebar() {
        shell.classList.remove("mobile-sidebar-open");
        if (mobileToggle) {
            mobileToggle.setAttribute("aria-expanded", "false");
        }
    }

    if (desktopToggle) {
        desktopToggle.addEventListener("click", () => {
            if (isMobileViewport()) {
                openMobileSidebar();
                return;
            }
            sidebar.classList.toggle("collapsed");
        });
    }

    if (mobileToggle) {
        mobileToggle.addEventListener("click", () => {
            if (shell.classList.contains("mobile-sidebar-open")) {
                closeMobileSidebar();
            } else {
                openMobileSidebar();
            }
        });
    }

    if (backdrop) {
        backdrop.addEventListener("click", () => {
            closeMobileSidebar();
        });
    }

    sidebar.querySelectorAll(".nav-link-item").forEach((link) => {
        link.addEventListener("click", () => {
            if (isMobileViewport()) {
                closeMobileSidebar();
            }
        });
    });

    window.addEventListener("resize", () => {
        if (!isMobileViewport()) {
            closeMobileSidebar();
        }
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
