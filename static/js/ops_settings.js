(function initSettingsPage() {
    const saveButtons = Array.from(document.querySelectorAll("[data-save-all]"));
    const saveState = document.querySelector("[data-save-state]");
    const form = document.getElementById("thresholdRulesForm");

    if (!form) {
        return;
    }

    const controls = Array.from(form.querySelectorAll("input, select, textarea"));
    const initialSnapshot = new Map();

    controls.forEach((control) => {
        if (!control.name) {
            return;
        }
        if (control.type === "checkbox") {
            initialSnapshot.set(control.name, control.checked ? "1" : "0");
        } else {
            initialSnapshot.set(control.name, control.value);
        }
    });

    function hasUnsavedChanges() {
        return controls.some((control) => {
            if (!control.name) {
                return false;
            }
            const initialValue = initialSnapshot.get(control.name);
            const currentValue = control.type === "checkbox" ? (control.checked ? "1" : "0") : control.value;
            return initialValue !== currentValue;
        });
    }

    function syncSaveState() {
        const dirty = hasUnsavedChanges();
        saveButtons.forEach((button) => {
            button.disabled = false;
            button.innerHTML = dirty
                ? '<span class="spinner-border spinner-border-sm me-1 d-none" aria-hidden="true"></span>Save all changes'
                : 'Save all changes';
        });
        if (saveState) {
            saveState.textContent = dirty ? "Unsaved changes" : "All changes saved";
            saveState.classList.toggle("is-dirty", dirty);
        }
    }

    controls.forEach((control) => {
        control.addEventListener("input", syncSaveState);
        control.addEventListener("change", syncSaveState);
    });

    saveButtons.forEach((button) => {
        button.addEventListener("click", () => {
            button.disabled = true;
            button.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>Saving...';
        });
    });

    syncSaveState();
})();
