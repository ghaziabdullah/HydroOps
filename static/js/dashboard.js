(function initCampusChart() {
    const canvas = document.getElementById("campusFlowChart");
    if (!canvas || typeof Chart === "undefined") {
        return;
    }

    const labels = ["00:00", "03:00", "06:00", "09:00", "12:00", "15:00", "18:00", "21:00"];
    const inlet = [5.2, 4.8, 6.1, 8.5, 7.3, 7.9, 8.7, 6.8];
    const sumHostels = [4.9, 4.4, 5.8, 7.8, 6.9, 7.0, 7.5, 6.2];

    new Chart(canvas, {
        type: "line",
        data: {
            labels,
            datasets: [
                { label: "Inlet", data: inlet, borderColor: "#14b8a6", tension: 0.35, fill: false },
                { label: "Sum of Hostels", data: sumHostels, borderColor: "#8b5cf6", tension: 0.35, fill: false },
            ],
        },
        options: {
            plugins: { legend: { position: "bottom" } },
            scales: { y: { beginAtZero: true } },
        },
    });
})();

(function initHostelsTableSorting() {
    const table = document.getElementById("hostelsComparisonTable");
    if (!table) {
        return;
    }

    const tbody = table.querySelector("tbody");
    const sortButtons = table.querySelectorAll(".hs-sort-btn");
    if (!tbody || !sortButtons.length) {
        return;
    }

    let activeKey = "";
    let activeDir = "asc";

    function parseValue(row, key, type) {
        const raw = row.dataset[key] || "";
        if (type === "number") {
            const value = Number(raw);
            return Number.isNaN(value) ? 0 : value;
        }
        return raw.toLowerCase();
    }

    function updateIndicators() {
        sortButtons.forEach((button) => {
            const indicator = button.querySelector(".hs-sort-indicator");
            const isActive = button.dataset.sortKey === activeKey;
            button.classList.toggle("active", isActive);
            if (indicator) {
                indicator.textContent = isActive ? (activeDir === "asc" ? "▲" : "▼") : "↕";
            }
        });
    }

    function sortRows(key, type) {
        const rows = Array.from(tbody.querySelectorAll("tr"));
        if (!rows.length) {
            return;
        }

        if (activeKey === key) {
            activeDir = activeDir === "asc" ? "desc" : "asc";
        } else {
            activeKey = key;
            activeDir = type === "text" ? "asc" : "desc";
        }

        rows.sort((a, b) => {
            const valueA = parseValue(a, key, type);
            const valueB = parseValue(b, key, type);
            if (valueA < valueB) {
                return activeDir === "asc" ? -1 : 1;
            }
            if (valueA > valueB) {
                return activeDir === "asc" ? 1 : -1;
            }
            return 0;
        });

        rows.forEach((row) => tbody.appendChild(row));
        updateIndicators();
    }

    sortButtons.forEach((button) => {
        button.addEventListener("click", () => {
            sortRows(button.dataset.sortKey, button.dataset.sortType);
        });
    });

    sortRows("usage", "number");
})();

(function animateTankMeters() {
    const fills = document.querySelectorAll(".hs-tank-meter span[data-fill-width]");
    if (!fills.length) {
        return;
    }

    requestAnimationFrame(() => {
        fills.forEach((fill) => {
            fill.style.width = `${fill.dataset.fillWidth}%`;
        });
    });
})();
