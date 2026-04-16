(function initReportsPage() {
    const exportLinks = Array.from(document.querySelectorAll(".js-report-export"));
    const rowLinks = Array.from(document.querySelectorAll(".rp-row-link[data-href]"));
    const scopeSelect = document.getElementById("reportScopeSelect");
    const hostelSelect = document.getElementById("reportHostelSelect");
    const unitSelect = document.getElementById("reportUnitSelect");

    function syncScopeFields() {
        if (!scopeSelect || !hostelSelect || !unitSelect) {
            return;
        }

        const scope = scopeSelect.value;
        hostelSelect.disabled = scope === "campus";
        unitSelect.disabled = scope !== "unit";

        if (scope === "campus") {
            hostelSelect.value = "";
            unitSelect.value = "";
        }

        if (scope === "hostel") {
            unitSelect.value = "";
        }
    }

    rowLinks.forEach((row) => {
        row.addEventListener("click", (event) => {
            if (event.target.closest("a")) {
                return;
            }
            const href = row.getAttribute("data-href");
            if (href) {
                window.location.href = href;
            }
        });
    });

    exportLinks.forEach((link) => {
        link.addEventListener("click", () => {
            const dropdownButton = document.getElementById("reportsExportBtn");
            if (dropdownButton) {
                dropdownButton.disabled = true;
                dropdownButton.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Exporting...';
                window.setTimeout(() => {
                    dropdownButton.disabled = false;
                    dropdownButton.textContent = "Export";
                }, 1600);
            }
        });
    });

    if (scopeSelect) {
        scopeSelect.addEventListener("change", syncScopeFields);
        syncScopeFields();
    }
})();
