let hostelUsageChartInstance = null;
let hostelPressureChartInstance = null;
let hostelForecastChartInstance = null;

function orgsPalette() {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    return {
        grid: dark ? "rgba(142, 158, 175, 0.22)" : "rgba(149, 167, 190, 0.24)",
        ticks: dark ? "#aebdcb" : "#4f6782",
        usage: "#2ee5da",
        compare: "#ad7cff",
        pressure: "#34e8df",
        forecast: dark ? "#8de7ff" : "#3b89c9",
    };
}

function parseHostelDashboardData() {
    const el = document.getElementById("hostelDashboardData");
    if (!el) {
        return null;
    }

    try {
        return JSON.parse(el.textContent);
    } catch (error) {
        return null;
    }
}

function buildLineOptions(palette, showLegend) {
    return {
        responsive: true,
        maintainAspectRatio: true,
        aspectRatio: 2.6,
        plugins: {
            legend: {
                display: showLegend,
                labels: {
                    color: palette.ticks,
                    usePointStyle: true,
                    boxWidth: 8,
                },
            },
        },
        scales: {
            x: {
                grid: { color: palette.grid },
                ticks: { color: palette.ticks },
            },
            y: {
                grid: { color: palette.grid },
                ticks: { color: palette.ticks },
            },
        },
    };
}

function renderHostelCharts() {
    const data = parseHostelDashboardData();
    if (!data || typeof Chart === "undefined") {
        return;
    }

    const palette = orgsPalette();
    const usageCanvas = document.getElementById("hostelUsageChart");
    const pressureCanvas = document.getElementById("hostelPressureChart");
    const forecastCanvas = document.getElementById("hostelForecastChart");

    if (usageCanvas) {
        if (hostelUsageChartInstance) {
            hostelUsageChartInstance.destroy();
        }

        hostelUsageChartInstance = new Chart(usageCanvas, {
            type: "line",
            data: {
                labels: data.usage.labels,
                datasets: [
                    {
                        label: "Usage",
                        data: data.usage.values,
                        borderColor: palette.usage,
                        backgroundColor: "rgba(46, 229, 218, 0.14)",
                        tension: 0.35,
                        fill: true,
                        pointRadius: 0,
                    },
                    {
                        label: "Baseline",
                        data: data.forecast.values.slice(0, data.usage.values.length),
                        borderColor: palette.compare,
                        tension: 0.35,
                        fill: false,
                        pointRadius: 0,
                    },
                ],
            },
            options: buildLineOptions(palette, true),
        });
    }

    if (pressureCanvas) {
        if (hostelPressureChartInstance) {
            hostelPressureChartInstance.destroy();
        }

        hostelPressureChartInstance = new Chart(pressureCanvas, {
            type: "line",
            data: {
                labels: data.pressure.labels,
                datasets: [
                    {
                        label: "Pressure",
                        data: data.pressure.values,
                        borderColor: palette.pressure,
                        backgroundColor: "rgba(52, 232, 223, 0.14)",
                        tension: 0.35,
                        fill: true,
                        pointRadius: 0,
                    },
                ],
            },
            options: buildLineOptions(palette, false),
        });
    }

    if (forecastCanvas) {
        if (hostelForecastChartInstance) {
            hostelForecastChartInstance.destroy();
        }

        hostelForecastChartInstance = new Chart(forecastCanvas, {
            type: "line",
            data: {
                labels: data.forecast.labels,
                datasets: [
                    {
                        label: "Forecast",
                        data: data.forecast.values,
                        borderColor: palette.forecast,
                        borderDash: [5, 4],
                        tension: 0.35,
                        fill: false,
                        pointRadius: 0,
                    },
                ],
            },
            options: buildLineOptions(palette, false),
        });
    }
}

(function initUnitChart() {
    const canvas = document.getElementById("unitForecastChart");
    if (!canvas || typeof Chart === "undefined") {
        return;
    }
    const palette = orgsPalette();
    new Chart(canvas, {
        type: "line",
        data: {
            labels: ["00", "04", "08", "12", "16", "20", "24"],
            datasets: [{
                label: "Predicted L/min",
                data: [24, 18, 36, 41, 35, 28, 22],
                borderColor: palette.usage,
                backgroundColor: "rgba(46, 229, 218, 0.14)",
                tension: 0.35,
                fill: true,
                pointRadius: 0,
            }],
        },
        options: buildLineOptions(palette, true),
    });
})();

renderHostelCharts();

(function initUnitsExplorerToggle() {
    const root = document.getElementById("unitsExplorerRoot");
    const toggle = document.getElementById("unitsViewToggle");
    if (!root || !toggle) {
        return;
    }

    const buttons = Array.from(toggle.querySelectorAll(".ux-view-btn"));
    const savedView = localStorage.getItem("hydroops_units_view") || "grid";
    applyView(savedView);

    buttons.forEach((button) => {
        button.addEventListener("click", () => {
            const view = button.getAttribute("data-view") || "grid";
            applyView(view);
            localStorage.setItem("hydroops_units_view", view);
        });
    });

    function applyView(view) {
        const normalizedView = view === "diagram" ? "diagram" : "grid";
        root.classList.add("is-switching");
        root.setAttribute("data-view", normalizedView);
        buttons.forEach((button) => {
            button.classList.toggle("active", button.getAttribute("data-view") === normalizedView);
        });
        window.setTimeout(() => root.classList.remove("is-switching"), 140);
    }
})();

const themeToggle = document.getElementById("themeToggle");
if (themeToggle) {
    themeToggle.addEventListener("click", () => {
        setTimeout(renderHostelCharts, 10);
    });
}
