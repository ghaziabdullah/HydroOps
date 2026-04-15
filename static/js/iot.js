(function renderWaterQualityCharts() {
	if (typeof Chart === "undefined") {
		return;
	}

	const dataNode = document.getElementById("qualityChartData");
	if (!dataNode) {
		return;
	}

	const payload = JSON.parse(dataNode.textContent || "{}");
	const phSeries = payload.phTrend || {labels: [], values: []};
	const turbiditySeries = payload.turbidityTrend || {labels: [], values: []};

	let phChart = null;
	let turbidityChart = null;

	function currentPalette() {
		const dark = document.documentElement.getAttribute("data-theme") === "dark";
		return {
			tick: dark ? "#a8bfd9" : "#5b7699",
			grid: dark ? "rgba(119, 148, 203, 0.2)" : "rgba(123, 149, 185, 0.2)",
			line: "#28ece8",
			areaTop: dark ? "rgba(40, 236, 232, 0.42)" : "rgba(40, 236, 232, 0.3)",
			areaBottom: "rgba(40, 236, 232, 0.02)",
			red: dark ? "rgba(255, 72, 87, 0.33)" : "rgba(255, 72, 87, 0.2)",
			amber: dark ? "rgba(252, 226, 69, 0.25)" : "rgba(252, 226, 69, 0.2)",
			green: dark ? "rgba(28, 232, 186, 0.2)" : "rgba(28, 232, 186, 0.18)",
		};
	}

	const zoneBackgroundPlugin = {
		id: "zoneBackgroundPlugin",
		beforeDatasetsDraw(chart) {
			const {ctx, chartArea, scales} = chart;
			if (!chartArea || !scales.y) {
				return;
			}

			const palette = currentPalette();
			const y = scales.y;
			const yTop = chartArea.top;
			const yBottom = chartArea.bottom;
			const zone1 = y.getPixelForValue(y.min + (y.max - y.min) * 0.66);
			const zone2 = y.getPixelForValue(y.min + (y.max - y.min) * 0.33);

			ctx.save();
			ctx.fillStyle = palette.red;
			ctx.fillRect(chartArea.left, yTop, chartArea.right - chartArea.left, zone1 - yTop);
			ctx.fillStyle = palette.amber;
			ctx.fillRect(chartArea.left, zone1, chartArea.right - chartArea.left, zone2 - zone1);
			ctx.fillStyle = palette.green;
			ctx.fillRect(chartArea.left, zone2, chartArea.right - chartArea.left, yBottom - zone2);
			ctx.restore();
		},
	};

	function buildLineChart(canvasId, labels, values, min, max) {
		const node = document.getElementById(canvasId);
		if (!node) {
			return null;
		}

		const ctx = node.getContext("2d");
		const palette = currentPalette();
		const gradient = ctx.createLinearGradient(0, 0, 0, 250);
		gradient.addColorStop(0, palette.areaTop);
		gradient.addColorStop(1, palette.areaBottom);

		return new Chart(node, {
			type: "line",
			data: {
				labels,
				datasets: [
					{
						data: values,
						borderColor: palette.line,
						backgroundColor: gradient,
						fill: true,
						borderWidth: 3,
						pointRadius: 0,
						tension: 0.45,
					},
				],
			},
			options: {
				maintainAspectRatio: false,
				plugins: {
					legend: {display: false},
					tooltip: {
						enabled: true,
						backgroundColor: "rgba(10, 20, 40, 0.92)",
					},
				},
				scales: {
					x: {
						grid: {display: false},
						ticks: {color: palette.tick, maxRotation: 0},
					},
					y: {
						min,
						max,
						grid: {color: palette.grid},
						ticks: {color: palette.tick},
					},
				},
			},
			plugins: [zoneBackgroundPlugin],
		});
	}

	function render() {
		if (phChart) {
			phChart.destroy();
		}
		if (turbidityChart) {
			turbidityChart.destroy();
		}

		phChart = buildLineChart(
			"phTrendChart",
			phSeries.labels || [],
			phSeries.values || [],
			6.6,
			8.0,
		);

		turbidityChart = buildLineChart(
			"turbidityTrendChart",
			turbiditySeries.labels || [],
			turbiditySeries.values || [],
			0,
			1.0,
		);
	}

	render();

	const toggle = document.getElementById("themeToggle");
	if (toggle) {
		toggle.addEventListener("click", () => {
			window.setTimeout(render, 20);
		});
	}
})();
