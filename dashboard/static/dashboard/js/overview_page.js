const pageDataEl = document.getElementById('pageData');
const pageData = pageDataEl ? JSON.parse(pageDataEl.textContent) : {};

let campusFlowChart = null;
let topHostelsChart = null;
let forecastStripChart = null;
let currentFlowRange = '24h';
let currentHostelsRange = '24h';

const flowRangeConfigs = {
    '24h': {
        count: 24,
        base: 5200,
        amplitude: 1550,
        leakWindows: [[7, 8], [16, 17]],
        labels: Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`),
    },
    '7d': {
        count: 7,
        base: 124000,
        amplitude: 18000,
        leakWindows: [[2, 2], [5, 5]],
        labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    },
    '30d': {
        count: 30,
        base: 118000,
        amplitude: 16000,
        leakWindows: [[10, 11], [22, 23]],
        labels: Array.from({ length: 30 }, (_, i) => `D${i + 1}`),
    },
};

document.addEventListener('DOMContentLoaded', function() {
    renderOverviewCharts();
    attachEventListeners();
    setupThemePersistence();
});

function chartPalette() {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    return {
        tick: dark ? '#a8bfd9' : '#4f6176',
        legend: dark ? '#dcecff' : '#24374b',
        grid: dark ? 'rgba(126, 148, 170, 0.18)' : 'rgba(126, 148, 170, 0.28)',
        tooltip: dark ? 'rgba(8, 18, 38, 0.92)' : 'rgba(0, 0, 0, 0.84)',
        forecast: dark ? '#9dd2e2' : '#78b4c2',
        anomaly: '#de5b5b',
        barMain: '#67b4f1',
        barTop: '#f0a94a',
    };
}

function attachEventListeners() {
    const chartRangeButtons = document.querySelectorAll('.chart-range-btn');
    chartRangeButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const range = this.getAttribute('data-range') || '24h';
            setActiveButton(chartRangeButtons, this);
            currentFlowRange = range;
            renderCampusFlowChart(range);
        });
    });

    const hostelsRangeButtons = document.querySelectorAll('.hostels-range-btn');
    hostelsRangeButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            const range = this.getAttribute('data-hostels-range') || '24h';
            setActiveButton(hostelsRangeButtons, this);
            currentHostelsRange = range;
            renderTopHostelsChart(range);
        });
    });

    const alertsBell = document.getElementById('alertsBell');
    if (alertsBell) {
        alertsBell.addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = '/ops/alerts-center/';
        });
    }

    const searchInput = document.getElementById('globalSearch');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(function(e) {
            const query = e.target.value.trim().toLowerCase();
            if (query.length > 2) {
                performSearch(query);
            }
        }, 400));
    }

    const userChip = document.getElementById('userChip');
    if (userChip) {
        userChip.addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = '/accounts/profile/';
        });
    }

    attachAlertActions();
}

function setupThemePersistence() {
    const html = document.documentElement;
    const isDark = localStorage.getItem('hydroops_theme') === 'dark';
    if (isDark) {
        html.setAttribute('data-theme', 'dark');
    }

    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            window.setTimeout(renderOverviewCharts, 20);
        });
    }
}

function setActiveButton(buttons, activeButton) {
    buttons.forEach(button => button.classList.remove('active'));
    activeButton.classList.add('active');
}

function debounce(func, delay) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, delay);
    };
}

function performSearch(query) {
    console.log('Searching for:', query);
}

function renderOverviewCharts() {
    if (typeof Chart === 'undefined') {
        console.warn('Chart.js not loaded');
        return;
    }

    destroyCharts();
    renderCampusFlowChart(currentFlowRange);
    renderTopHostelsChart(currentHostelsRange);
    renderForecastStripChart();
}

function destroyCharts() {
    if (campusFlowChart) {
        campusFlowChart.destroy();
        campusFlowChart = null;
    }
    if (topHostelsChart) {
        topHostelsChart.destroy();
        topHostelsChart = null;
    }
    if (forecastStripChart) {
        forecastStripChart.destroy();
        forecastStripChart = null;
    }
}

function renderCampusFlowChart(range) {
    const lineCanvas = document.getElementById('campusFlowChart');
    if (!lineCanvas) return;

    if (campusFlowChart) {
        campusFlowChart.destroy();
        campusFlowChart = null;
    }

    const ctx = lineCanvas.getContext('2d');
    const palette = chartPalette();
    const flow = buildParallelFlowSeries(range);

    const gradInlet = ctx.createLinearGradient(0, 0, 0, 260);
    gradInlet.addColorStop(0, 'rgba(60, 215, 220, 0.28)');
    gradInlet.addColorStop(1, 'rgba(60, 215, 220, 0)');

    const gradHostel = ctx.createLinearGradient(0, 0, 0, 260);
    gradHostel.addColorStop(0, 'rgba(148, 103, 222, 0.28)');
    gradHostel.addColorStop(1, 'rgba(148, 103, 222, 0)');

    const yMax = Math.ceil(Math.max(...flow.inlet) * 1.15);

    campusFlowChart = new Chart(lineCanvas, {
        type: 'line',
        data: {
            labels: flow.labels,
            datasets: [
                {
                    label: 'Inlet',
                    data: flow.inlet,
                    borderColor: '#2ed4d3',
                    backgroundColor: gradInlet,
                    fill: true,
                    borderWidth: 3,
                    pointRadius(context) {
                        return flow.anomalyIndices.includes(context.dataIndex) ? 4 : 0;
                    },
                    pointHoverRadius(context) {
                        return flow.anomalyIndices.includes(context.dataIndex) ? 6 : 4;
                    },
                    pointBackgroundColor(context) {
                        return flow.anomalyIndices.includes(context.dataIndex) ? palette.anomaly : '#2ed4d3';
                    },
                    pointBorderColor(context) {
                        return flow.anomalyIndices.includes(context.dataIndex) ? '#a73030' : '#2ed4d3';
                    },
                    pointBorderWidth(context) {
                        return flow.anomalyIndices.includes(context.dataIndex) ? 1.5 : 0;
                    },
                    tension: 0.42,
                },
                {
                    label: 'Sum of Hostels',
                    data: flow.hostels,
                    borderColor: '#9b7bdd',
                    backgroundColor: gradHostel,
                    fill: true,
                    borderWidth: 3,
                    pointRadius(context) {
                        return flow.anomalyIndices.includes(context.dataIndex) ? 4 : 0;
                    },
                    pointHoverRadius(context) {
                        return flow.anomalyIndices.includes(context.dataIndex) ? 6 : 4;
                    },
                    pointBackgroundColor(context) {
                        return flow.anomalyIndices.includes(context.dataIndex) ? palette.anomaly : '#9b7bdd';
                    },
                    pointBorderColor(context) {
                        return flow.anomalyIndices.includes(context.dataIndex) ? '#a73030' : '#9b7bdd';
                    },
                    pointBorderWidth(context) {
                        return flow.anomalyIndices.includes(context.dataIndex) ? 1.5 : 0;
                    },
                    tension: 0.42,
                },
            ],
        },
        options: {
            maintainAspectRatio: false,
            responsive: true,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            animation: {
                duration: 1050,
                easing: 'easeOutCubic',
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: {
                        color: palette.tick,
                        maxRotation: 0,
                        font: { size: 12 },
                    },
                },
                y: {
                    beginAtZero: true,
                    max: yMax,
                    ticks: {
                        color: palette.tick,
                        font: { size: 12 },
                        callback(value) {
                            if (value === 0) return '0';
                            if (yMax >= 100000) return `${(value / 1000).toFixed(0)}k`;
                            return `${(value / 1000).toFixed(1)}k`;
                        },
                    },
                    grid: { color: palette.grid },
                },
            },
            plugins: {
                legend: {
                    position: 'top',
                    align: 'start',
                    labels: {
                        boxWidth: 8,
                        boxHeight: 8,
                        usePointStyle: true,
                        pointStyle: 'circle',
                        color: palette.legend,
                        font: { size: 13, weight: '600' },
                    },
                },
                tooltip: {
                    enabled: true,
                    backgroundColor: palette.tooltip,
                    padding: 8,
                    titleFont: { size: 13 },
                    bodyFont: { size: 12 },
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    callbacks: {
                        label(context) {
                            const value = context.parsed.y || 0;
                            return `${context.dataset.label}: ${(value / 1000).toFixed(1)}k L`;
                        },
                        afterBody(items) {
                            if (!items.length) return [];
                            const index = items[0].dataIndex;
                            if (flow.anomalyIndices.includes(index)) {
                                return ['Insight: unusual spike in inlet-hostel gap (possible leakage).'];
                            }
                            return ['Insight: normal parallel flow behavior.'];
                        },
                    },
                },
                filler: { propagate: true },
            },
        },
        plugins: [chartInsightPlugin],
    });

    campusFlowChart.$flowMeta = {
        anomalyIndices: flow.anomalyIndices,
        peakInletIndex: flow.peakInletIndex,
        peakHostelIndex: flow.peakHostelIndex,
    };

    updateFlowKpiTexts(flow);
}

function renderTopHostelsChart(range) {
    const barCanvas = document.getElementById('topHostelsChart');
    if (!barCanvas) return;

    if (topHostelsChart) {
        topHostelsChart.destroy();
        topHostelsChart = null;
    }

    const palette = chartPalette();
    const ranked = buildHostelRankingSeries(range);

    const barColors = ranked.values.map((_, idx) => idx === 0 ? palette.barTop : palette.barMain);

    topHostelsChart = new Chart(barCanvas, {
        type: 'bar',
        data: {
            labels: ranked.labels,
            datasets: [{
                label: `Usage (${range})`,
                data: ranked.values,
                backgroundColor: barColors,
                borderRadius: 8,
                borderSkipped: false,
                maxBarThickness: 22,
            }],
        },
        options: {
            indexAxis: 'y',
            maintainAspectRatio: false,
            responsive: true,
            layout: {
                padding: {
                    right: 74,
                },
            },
            animation: {
                duration: 950,
                easing: 'easeOutQuart',
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    enabled: true,
                    backgroundColor: palette.tooltip,
                    padding: 10,
                    titleFont: { size: 13, weight: '700' },
                    bodyFont: { size: 12 },
                    callbacks: {
                        title(items) {
                            return ranked.hostels[items[0].dataIndex]?.name || 'Hostel';
                        },
                        label(context) {
                            const idx = context.dataIndex;
                            const item = ranked.hostels[idx];
                            if (!item) return '';

                            return [
                                `Rank: #${idx + 1}`,
                                `Usage: ${formatUsage(item.usage, range)}`,
                                `Share: ${item.share.toFixed(1)}% of top usage`,
                                `Change: ${item.changePct > 0 ? '+' : ''}${item.changePct.toFixed(1)}% vs previous ${range}`,
                            ];
                        },
                    },
                },
            },
            scales: {
                y: {
                    grid: { display: false },
                    ticks: {
                        color: palette.tick,
                        font: { size: 12, weight: '600' },
                    },
                },
                x: {
                    beginAtZero: true,
                    suggestedMax: Math.ceil((Math.max(...ranked.values, 1) * 1.12) / 1000) * 1000,
                    ticks: {
                        color: palette.tick,
                        font: { size: 11 },
                        callback(value) {
                            return `${(value / 1000).toFixed(1)}k`;
                        },
                    },
                    grid: { color: palette.grid },
                },
            },
        },
        plugins: [topHostelsLabelPlugin],
    });

    topHostelsChart.$hostelMeta = ranked;
}

function buildHostelRankingSeries(range) {
    const rows = Array.isArray(pageData.hostel_rows) ? pageData.hostel_rows : [];
    const source = rows.length
        ? [...rows].sort((a, b) => (b.today_usage || 0) - (a.today_usage || 0)).slice(0, 8)
        : [
            { hostel_name: 'Hajveri', today_usage: 18200 },
            { hostel_name: 'Rehmat', today_usage: 15100 },
            { hostel_name: 'Razi', today_usage: 13950 },
            { hostel_name: 'Liaquat', today_usage: 11700 },
            { hostel_name: 'Attar', today_usage: 10900 },
            { hostel_name: 'Ghazali', today_usage: 9650 },
            { hostel_name: 'Beruni', today_usage: 9250 },
            { hostel_name: 'Zakaria', today_usage: 8830 },
        ];

    const rangeFactor = range === '7d' ? 6.7 : range === '30d' ? 28.0 : 1.0;

    const scaled = source.map((row, idx) => {
        const base = Number(row.today_usage || 0);
        const volatility = 1 + ((Math.sin((idx + 2) * 1.7) + 1) * 0.05);
        const usage = Math.max(50, Math.round(base * rangeFactor * volatility));
        const previous = usage * (0.9 + (((idx * 13) % 7) * 0.03));
        const changePct = ((usage - previous) / Math.max(previous, 1)) * 100;

        return {
            name: row.hostel_name || row.hostel_code || `Hostel ${idx + 1}`,
            usage,
            changePct,
        };
    });

    scaled.sort((a, b) => b.usage - a.usage);

    const total = scaled.reduce((acc, item) => acc + item.usage, 0) || 1;

    const hostels = scaled.map(item => ({
        ...item,
        share: (item.usage / total) * 100,
    }));

    return {
        labels: hostels.map((item, idx) => `#${idx + 1} ${item.name}`),
        values: hostels.map(item => item.usage),
        hostels,
        range,
    };
}

const topHostelsLabelPlugin = {
    id: 'topHostelsLabelPlugin',
    afterDatasetsDraw(chart) {
        const meta = chart.$hostelMeta;
        if (!meta) return;

        const datasetMeta = chart.getDatasetMeta(0);
        if (!datasetMeta || !datasetMeta.data) return;

        const ctx = chart.ctx;
        datasetMeta.data.forEach((bar, idx) => {
            const item = meta.hostels[idx];
            if (!item) return;

            ctx.save();
            ctx.font = '600 11px Segoe UI';
            ctx.fillStyle = item.changePct >= 0 ? '#2f8f5f' : '#b54e4e';
            const delta = `${item.changePct >= 0 ? '+' : ''}${item.changePct.toFixed(1)}%`;
            ctx.fillText(delta, bar.x + 8, bar.y + 4);
            ctx.restore();
        });
    },
};

function renderForecastStripChart() {
    const stripCanvas = document.getElementById('forecastStripChart');
    if (!stripCanvas) return;

    const days = Array.from({ length: 7 }, (_, i) => String(i + 1));
    const forecastData = generateSimpleSeries(7, 1.5, 3.5);
    const palette = chartPalette();

    forecastStripChart = new Chart(stripCanvas, {
        type: 'line',
        data: {
            labels: days,
            datasets: [{
                label: 'Forecast (k L/day)',
                data: forecastData,
                borderColor: palette.forecast,
                backgroundColor: 'transparent',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 0,
                tension: 0.4,
                borderDash: [6, 4],
                fill: false,
            }],
        },
        options: {
            maintainAspectRatio: false,
            responsive: true,
            animation: {
                duration: 800,
                easing: 'easeOutSine',
            },
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false },
            },
            scales: {
                x: { display: false },
                y: { display: false },
            },
        },
    });
}

const chartInsightPlugin = {
    id: 'chartInsightPlugin',
    afterDatasetsDraw(chart) {
        const meta = chart.$flowMeta;
        if (!meta) return;

        const { ctx, chartArea, scales } = chart;
        if (!ctx || !chartArea || !scales.x || !scales.y) return;

        if (meta.anomalyIndices.length) {
            const first = meta.anomalyIndices[0];
            const last = meta.anomalyIndices[meta.anomalyIndices.length - 1];
            const xStart = scales.x.getPixelForValue(first);
            const xEnd = scales.x.getPixelForValue(last);

            ctx.save();
            ctx.fillStyle = 'rgba(220, 108, 108, 0.12)';
            ctx.strokeStyle = 'rgba(199, 116, 116, 0.45)';
            ctx.setLineDash([5, 4]);
            ctx.fillRect(xStart - 4, chartArea.top, (xEnd - xStart) + 8, chartArea.bottom - chartArea.top);
            ctx.strokeRect(xStart - 4, chartArea.top, (xEnd - xStart) + 8, chartArea.bottom - chartArea.top);
            ctx.setLineDash([]);
            ctx.restore();
        }

        drawPeakLabel(chart, 0, meta.peakInletIndex, 'Peak Inlet');
        drawPeakLabel(chart, 1, meta.peakHostelIndex, 'Peak Hostel');
    },
};

function drawPeakLabel(chart, datasetIndex, dataIndex, labelText) {
    const datasetMeta = chart.getDatasetMeta(datasetIndex);
    if (!datasetMeta || !datasetMeta.data || !datasetMeta.data[dataIndex]) return;

    const point = datasetMeta.data[dataIndex];
    const { ctx } = chart;

    ctx.save();
    ctx.fillStyle = 'rgba(26, 38, 52, 0.9)';
    roundRect(ctx, point.x - 44, point.y - 30, 88, 20, 6);
    ctx.fill();
    ctx.fillStyle = '#f2f8ff';
    ctx.font = '600 10px Segoe UI';
    ctx.fillText(labelText, point.x - 34, point.y - 16);
    ctx.restore();
}

function buildParallelFlowSeries(range) {
    const config = flowRangeConfigs[range] || flowRangeConfigs['24h'];
    const inlet = [];
    const hostels = [];
    const anomalyIndices = [];

    for (let i = 0; i < config.count; i++) {
        const phase = (i / config.count) * Math.PI * 2;
        const macroWave = Math.sin(phase * 1.8) * config.amplitude;
        const microWave = Math.sin(phase * 5.4 + 0.5) * (config.amplitude * 0.12);
        const drift = Math.cos(phase * 0.9) * (config.amplitude * 0.08);

        const inletValue = Math.max(1, Math.round(config.base + macroWave + microWave + drift));

        let gapPct = 0.028 + Math.abs(Math.sin(phase * 2.2)) * 0.018;
        const inLeakWindow = config.leakWindows.some(([start, end]) => i >= start && i <= end);
        if (inLeakWindow) {
            gapPct += 0.07 + Math.abs(Math.sin(phase * 3.1)) * 0.04;
            anomalyIndices.push(i);
        }

        gapPct += Math.abs(Math.sin(phase * 4.6)) * 0.006;

        const hostelValue = Math.max(1, Math.round(inletValue * (1 - gapPct)));

        inlet.push(inletValue);
        hostels.push(Math.min(hostelValue, inletValue));
    }

    const peakInletValue = Math.max(...inlet);
    const peakHostelValue = Math.max(...hostels);

    return {
        labels: config.labels,
        inlet,
        hostels,
        anomalyIndices,
        peakInletIndex: inlet.indexOf(peakInletValue),
        peakHostelIndex: hostels.indexOf(peakHostelValue),
    };
}

function generateSimpleSeries(count, min, max) {
    const values = [];
    for (let i = 0; i < count; i++) {
        const phase = (i / count) * Math.PI * 2;
        const val = min + ((Math.sin(phase * 1.2) + 1) / 2) * (max - min);
        values.push(Number(val.toFixed(2)));
    }
    return values;
}

function updateFlowKpiTexts(flow) {
    const leakEl = document.getElementById('leakIndicator');
    const peakEl = document.getElementById('peakHour');
    if (!leakEl || !peakEl) return;

    const avgInlet = flow.inlet.reduce((acc, n) => acc + n, 0) / flow.inlet.length;
    const avgHostel = flow.hostels.reduce((acc, n) => acc + n, 0) / flow.hostels.length;
    const gapPct = ((avgInlet - avgHostel) / Math.max(avgInlet, 1)) * 100;

    const leakLabel = gapPct > 9 ? 'Critical' : gapPct > 6 ? 'Watch' : 'Normal';
    leakEl.textContent = `+${gapPct.toFixed(1)}% - ${leakLabel}`;

    const peakIdx = flow.peakInletIndex;
    const peakValue = flow.inlet[peakIdx] || 0;
    const peakLabel = flow.labels[peakIdx] || '-';
    const valueLabel = peakValue >= 100000
        ? `${(peakValue / 1000).toFixed(0)}k L/day`
        : `${(peakValue / 1000).toFixed(1)}k L/hr`;
    peakEl.textContent = `${peakLabel} - ${valueLabel}`;
}

function roundRect(ctx, x, y, width, height, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
}

function formatUsage(value, range) {
    if (range === '24h') {
        return `${value.toLocaleString()} L / day`;
    }
    if (range === '7d') {
        return `${value.toLocaleString()} L / week`;
    }
    return `${value.toLocaleString()} L / 30 days`;
}

function attachAlertActions() {
    const resolveButtons = document.querySelectorAll('.resolve-alert-btn');
    resolveButtons.forEach(button => {
        button.addEventListener('click', async function() {
            const alertId = this.getAttribute('data-alert-id');
            if (!alertId) return;

            this.disabled = true;
            this.textContent = 'Resolving...';

            try {
                const response = await fetch(`/ops/api/alerts/${alertId}/acknowledge/`, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                });

                if (!response.ok) {
                    throw new Error('Unable to resolve alert');
                }

                this.textContent = 'Resolved';
                const card = this.closest('.ov-alert-card');
                if (card) {
                    card.style.opacity = '0.6';
                    card.style.pointerEvents = 'none';
                }
            } catch (error) {
                console.error(error);
                this.disabled = false;
                this.textContent = 'Resolve';
            }
        });
    });
}

function getCsrfToken() {
    const name = 'csrftoken=';
    const decoded = decodeURIComponent(document.cookie || '');
    const parts = decoded.split(';');
    for (let i = 0; i < parts.length; i++) {
        const cookie = parts[i].trim();
        if (cookie.startsWith(name)) {
            return cookie.substring(name.length);
        }
    }
    return '';
}
