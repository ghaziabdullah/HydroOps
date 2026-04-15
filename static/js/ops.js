(function initForecastChart() {
    const canvas = document.getElementById("forecastChart");
    const dataNode = document.getElementById("forecastChartData");
    if (!canvas || !dataNode || typeof Chart === "undefined") {
        return;
    }

    const payload = JSON.parse(dataNode.textContent || "{}");
    const labels = payload.labels || [];
    const values = payload.values || [];

    function palette() {
        const dark = document.documentElement.getAttribute("data-theme") === "dark";
        return {
            line: "#32ece7",
            tick: dark ? "#a4bada" : "#5a7395",
            grid: dark ? "rgba(122, 150, 199, 0.23)" : "rgba(122, 150, 199, 0.18)",
            areaTop: dark ? "rgba(50, 236, 231, 0.46)" : "rgba(50, 236, 231, 0.28)",
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
                        backgroundColor: "rgba(8, 18, 38, 0.92)",
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
                                return value === 0 ? "0" : `${value}k`;
                            },
                        },
                    },
                },
            },
        });
    }

    render();

    const toggle = document.getElementById("themeToggle");
    if (toggle) {
        toggle.addEventListener("click", () => {
            window.setTimeout(render, 20);
        });
    }
})();
