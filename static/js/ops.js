(function initForecastChart() {
    const canvas = document.getElementById("forecastChart");
    const dataNode = document.getElementById("forecastChartData");
    const controlsForm = document.getElementById("forecastControlsForm");
    if (!canvas || !dataNode || typeof Chart === "undefined") {
        return;
    }

    const payload = JSON.parse(dataNode.textContent || "{}");
    const labels = payload.labels || [];
    const values = payload.values || [];

    function palette() {
        const dark = document.documentElement.getAttribute("data-theme") === "dark";
        return {
            line: dark ? "#48f0eb" : "#158f9c",
            tick: dark ? "#b6cbe0" : "#46698d",
            grid: dark ? "rgba(122, 150, 199, 0.26)" : "rgba(122, 150, 199, 0.22)",
            areaTop: dark ? "rgba(72, 240, 235, 0.42)" : "rgba(21, 143, 156, 0.22)",
            areaBottom: "rgba(50, 236, 231, 0.02)",
        };
    }

    let chart = null;

    function render() {
        if (chart) {
            chart.destroy();
        }

        const ctx = canvas.getContext("2d");
        const p = palette();
        const grad = ctx.createLinearGradient(0, 0, 0, 290);
        grad.addColorStop(0, p.areaTop);
        grad.addColorStop(1, p.areaBottom);

        chart = new Chart(canvas, {
            type: "line",
            data: {
                labels,
                datasets: [
                    {
                        label: "Predicted",
                        data: values,
                        borderColor: p.line,
                        backgroundColor: grad,
                        borderWidth: 4,
                        pointRadius: 0,
                        fill: true,
                        tension: 0.42,
                    },
                ],
            },
            options: {
                maintainAspectRatio: false,
                plugins: {
                    legend: {display: false},
                    tooltip: {
                        enabled: true,
                        backgroundColor: "rgba(8, 18, 38, 0.95)",
                    },
                },
                scales: {
                    x: {
                        grid: {display: false},
                        ticks: {
                            color: p.tick,
                            maxRotation: 0,
                        },
                    },
                    y: {
                        beginAtZero: true,
                        grid: {color: p.grid},
                        ticks: {
                            color: p.tick,
                            callback(value) {
                                return value === 0 ? "0" : `${value}`;
                            },
                        },
                    },
                },
            },
        });
    }

    render();

    function submitControls() {
        if (!controlsForm) {
            return;
        }
        if (typeof controlsForm.requestSubmit === "function") {
            controlsForm.requestSubmit();
        } else {
            controlsForm.submit();
        }
    }

    const scopeSelect = document.getElementById("forecastScopeSelect");
    const hostelSelect = document.getElementById("forecastHostelSelect");
    const unitSelect = document.getElementById("forecastUnitSelect");
    const horizonSelect = document.getElementById("forecastHorizonSelect");

    function syncSelectors() {
        if (!scopeSelect || !hostelSelect || !unitSelect) {
            return;
        }

        const scope = scopeSelect.value;
        const scopeCampus = scope === "CAMPUS";
        const scopeHostel = scope === "HOSTEL";
        const scopeUnit = scope === "UNIT";

        hostelSelect.disabled = scopeCampus;
        unitSelect.disabled = scopeCampus || scopeHostel;

        if (scopeCampus) {
            hostelSelect.value = "";
            unitSelect.value = "";
        } else if (scopeHostel) {
            unitSelect.value = "";
        }
    }

    [scopeSelect, hostelSelect, unitSelect, horizonSelect].forEach((control) => {
        if (!control) {
            return;
        }
        control.addEventListener("change", () => {
            if (control === scopeSelect) {
                syncSelectors();
            }
            if (control === hostelSelect && scopeSelect && hostelSelect.value) {
                scopeSelect.value = "HOSTEL";
            }
            if (control === unitSelect && scopeSelect && unitSelect.value) {
                scopeSelect.value = "UNIT";
            }
            syncSelectors();
            submitControls();
        });
    });

    syncSelectors();

    const toggle = document.getElementById("themeToggle");
    if (toggle) {
        toggle.addEventListener("click", () => {
            window.setTimeout(render, 20);
        });
    }
})();
