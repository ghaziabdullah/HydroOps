(function initHostelsPage() {
    const table = document.getElementById('hostelsComparisonTable');
    if (!table) {
        return;
    }

    const tbody = table.querySelector('tbody');
    const sortButtons = table.querySelectorAll('.hs-sort-btn');
    const filterButtons = document.querySelectorAll('.hs-filter-toggle');
    const clearFiltersButton = document.getElementById('hsClearFilters');
    const searchInput = document.getElementById('hsTableSearch');
    const rows = () => Array.from(tbody.querySelectorAll('tr[data-hostel]'));

    const activeFilters = new Map();
    let activeKey = '';
    let activeDir = 'asc';

    initTooltips();
    initRowNavigation();
    initSorting();
    initFilterToggles();
    initSearch();
    animateTankMeters();

    function initTooltips() {
        if (!window.bootstrap || typeof bootstrap.Tooltip === 'undefined') {
            return;
        }

        const tooltipTargets = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        tooltipTargets.forEach((el) => {
            new bootstrap.Tooltip(el);
        });
    }

    function initRowNavigation() {
        rows().forEach((row) => {
            row.addEventListener('click', function(event) {
                if (event.target.closest('a, button, input, .modal, .hs-action-group')) {
                    return;
                }

                const url = row.dataset.href;
                if (url) {
                    window.location.href = url;
                }
            });
        });
    }

    function initSorting() {
        sortButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const key = button.dataset.sortKey;
                const type = button.dataset.sortType || 'text';
                sortRows(key, type);
            });
        });

        sortRows('alerts', 'number');
    }

    function parseValue(row, key, type) {
        const raw = row.dataset[key] || '';
        if (type === 'number') {
            const value = Number(raw);
            return Number.isNaN(value) ? 0 : value;
        }
        return raw.toLowerCase();
    }

    function sortRows(key, type) {
        const visibleRows = rows();
        if (!visibleRows.length) {
            return;
        }

        if (activeKey === key) {
            activeDir = activeDir === 'asc' ? 'desc' : 'asc';
        } else {
            activeKey = key;
            activeDir = type === 'text' ? 'asc' : 'desc';
        }

        visibleRows.sort((a, b) => {
            const valueA = parseValue(a, key, type);
            const valueB = parseValue(b, key, type);
            if (valueA < valueB) return activeDir === 'asc' ? -1 : 1;
            if (valueA > valueB) return activeDir === 'asc' ? 1 : -1;
            return 0;
        });

        visibleRows.forEach((row) => tbody.appendChild(row));
        updateSortIndicators();
    }

    function updateSortIndicators() {
        sortButtons.forEach((button) => {
            const indicator = button.querySelector('.hs-sort-indicator');
            const isActive = button.dataset.sortKey === activeKey;
            button.classList.toggle('active', isActive);
            if (!indicator) return;
            indicator.textContent = isActive ? (activeDir === 'asc' ? '▲' : '▼') : '↕';
        });
    }

    function initFilterToggles() {
        filterButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const key = button.dataset.filterKey;
                const value = button.dataset.filterValue;
                if (!key || !value) return;

                if (!activeFilters.has(key)) {
                    activeFilters.set(key, new Set());
                }

                const values = activeFilters.get(key);
                if (button.classList.contains('active')) {
                    button.classList.remove('active');
                    values.delete(value);
                } else {
                    button.classList.add('active');
                    values.add(value);
                }

                if (values.size === 0) {
                    activeFilters.delete(key);
                }

                applyFiltersAndSearch();
            });
        });

        if (clearFiltersButton) {
            clearFiltersButton.addEventListener('click', () => {
                activeFilters.clear();
                filterButtons.forEach((button) => button.classList.remove('active'));
                applyFiltersAndSearch();
            });
        }
    }

    function initSearch() {
        if (!searchInput) {
            return;
        }

        searchInput.addEventListener('input', debounce(applyFiltersAndSearch, 140));
    }

    function applyFiltersAndSearch() {
        const searchTerm = (searchInput ? searchInput.value : '').trim().toLowerCase();

        rows().forEach((row) => {
            const matchFilter = matchesAllFilters(row);
            const searchableText = [
                row.dataset.hostel,
                row.dataset.severity,
                row.dataset.risk,
                row.dataset.alerts,
                row.dataset.critical,
            ]
                .join(' ')
                .toLowerCase();
            const matchSearch = !searchTerm || searchableText.includes(searchTerm);
            toggleRowVisibility(row, matchFilter && matchSearch);
        });
    }

    function matchesAllFilters(row) {
        for (const [key, allowedValues] of activeFilters.entries()) {
            const rowValue = row.dataset[key];
            if (!allowedValues.has(rowValue)) {
                return false;
            }
        }
        return true;
    }

    function toggleRowVisibility(row, shouldShow) {
        if (shouldShow) {
            row.classList.remove('hs-row-collapsed');
            requestAnimationFrame(() => row.classList.remove('hs-row-hidden'));
            return;
        }

        row.classList.add('hs-row-hidden');
        window.setTimeout(() => {
            if (row.classList.contains('hs-row-hidden')) {
                row.classList.add('hs-row-collapsed');
            }
        }, 170);
    }

    function animateTankMeters() {
        const fills = document.querySelectorAll('.hs-tank-meter span[data-fill-width]');
        if (!fills.length) {
            return;
        }

        requestAnimationFrame(() => {
            fills.forEach((fill) => {
                fill.style.width = `${fill.dataset.fillWidth}%`;
            });
        });
    }

    function debounce(func, delay) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), delay);
        };
    }
})();
