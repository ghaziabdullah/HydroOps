(function initAlertsCenterPage() {
    const panel = document.getElementById("alertDetailPanel");
    const filterForm = document.querySelector(".ac-filters");
    const rows = Array.from(document.querySelectorAll(".ac-alert-row"));
    const checks = Array.from(document.querySelectorAll(".ac-row-check"));
    const selectAll = document.getElementById("acSelectAll");
    const ackSelectedBtn = document.getElementById("ackSelectedBtn");
    const detailAckBtn = document.getElementById("detailAcknowledgeBtn");

    if (!panel) {
        return;
    }

    const detailNodes = {
        status: document.getElementById("detailStatus"),
        type: document.getElementById("detailType"),
        scope: document.getElementById("detailScope"),
        severity: document.getElementById("detailSeverity"),
        started: document.getElementById("detailStarted"),
        message: document.getElementById("detailMessage"),
    };

    function getCsrfToken() {
        const cookie = document.cookie
            .split(";")
            .map((part) => part.trim())
            .find((part) => part.startsWith("csrftoken="));
        return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
    }

    function initFilters() {
        if (!filterForm) {
            return;
        }

        const chips = Array.from(filterForm.querySelectorAll(".ac-filter-chip"));
        chips.forEach((chip) => {
            const input = chip.querySelector("input[type='checkbox']");
            if (!input) {
                return;
            }

            const syncChipState = () => chip.classList.toggle("active", input.checked);
            input.addEventListener("change", syncChipState);
            syncChipState();
        });

        const liveControls = Array.from(
            filterForm.querySelectorAll("select[name='severity'], select[name='status'], select[name='hostel_id'], select[name='range']")
        );
        liveControls.forEach((control) => {
            control.addEventListener("change", () => filterForm.submit());
        });
    }

    function updateBulkState() {
        if (!ackSelectedBtn) {
            return;
        }

        const selectedCount = checks.filter((check) => check.checked).length;
        ackSelectedBtn.disabled = selectedCount === 0;
        ackSelectedBtn.textContent = selectedCount > 0 ? `Acknowledge selected (${selectedCount})` : "Acknowledge selected";
    }

    function applyRowToDetail(row) {
        if (!row) {
            return;
        }

        rows.forEach((item) => item.classList.remove("is-selected"));
        row.classList.add("is-selected");

        if (!detailNodes.type) {
            return;
        }

        detailNodes.type.textContent = row.dataset.alertType || "-";
        detailNodes.scope.textContent = row.dataset.alertScope || "-";
        detailNodes.severity.textContent = row.dataset.alertSeverity || "-";
        detailNodes.started.textContent = row.dataset.alertStarted || "-";
        detailNodes.message.textContent = row.dataset.alertMessage || panel.dataset.empty || "-";
        detailNodes.status.textContent = row.dataset.alertStatus || "-";

        if (detailAckBtn) {
            detailAckBtn.dataset.ackUrl = row.dataset.alertAckUrl || "";
            const isAck = row.dataset.alertAck === "true";
            detailAckBtn.disabled = isAck;
            detailAckBtn.textContent = isAck ? "Already acknowledged" : "Acknowledge";
        }
    }

    async function acknowledgeUrl(url) {
        if (!url) {
            return false;
        }

        try {
            const response = await fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrfToken(),
                },
                credentials: "same-origin",
            });
            return response.ok;
        } catch (error) {
            return false;
        }
    }

    rows.forEach((row) => {
        row.addEventListener("click", (event) => {
            if (event.target.closest("button") || event.target.closest("input")) {
                return;
            }
            applyRowToDetail(row);
        });

        const rowAck = row.querySelector(".js-row-ack");
        if (rowAck) {
            rowAck.addEventListener("click", async () => {
                rowAck.disabled = true;
                const ok = await acknowledgeUrl(row.dataset.alertAckUrl || "");
                if (!ok) {
                    rowAck.disabled = false;
                    return;
                }

                row.dataset.alertAck = "true";
                row.dataset.alertStatus = "Acknowledged";
                const statusPill = row.querySelector(".ac-status-pill");
                if (statusPill) {
                    statusPill.textContent = "Acknowledged";
                    statusPill.classList.remove("status-open");
                    statusPill.classList.add("status-ack");
                }

                rowAck.textContent = "Done";
                rowAck.classList.remove("btn-outline-secondary");
                rowAck.classList.add("btn-outline-success");

                if (row.classList.contains("is-selected")) {
                    applyRowToDetail(row);
                }
            });
        }
    });

    checks.forEach((check) => check.addEventListener("change", updateBulkState));

    if (selectAll) {
        selectAll.addEventListener("change", () => {
            checks.forEach((check) => {
                check.checked = selectAll.checked;
            });
            updateBulkState();
        });
    }

    if (detailAckBtn) {
        detailAckBtn.addEventListener("click", async () => {
            if (detailAckBtn.disabled) {
                return;
            }
            detailAckBtn.disabled = true;
            const ok = await acknowledgeUrl(detailAckBtn.dataset.ackUrl || "");
            if (!ok) {
                detailAckBtn.disabled = false;
                return;
            }

            const selected = document.querySelector(".ac-alert-row.is-selected");
            if (selected) {
                selected.dataset.alertAck = "true";
                selected.dataset.alertStatus = "Acknowledged";
                const statusPill = selected.querySelector(".ac-status-pill");
                if (statusPill) {
                    statusPill.textContent = "Acknowledged";
                    statusPill.classList.remove("status-open");
                    statusPill.classList.add("status-ack");
                }
                const rowAck = selected.querySelector(".js-row-ack");
                if (rowAck) {
                    rowAck.textContent = "Done";
                    rowAck.disabled = true;
                }
                applyRowToDetail(selected);
            }
        });
    }

    if (rows.length > 0) {
        applyRowToDetail(rows[0]);
    }
    initFilters();
    updateBulkState();
})();
