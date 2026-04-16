(function initProfileAvatarInitials() {
	const avatar = document.querySelector("[data-avatar-initials]");
	if (!avatar) {
		return;
	}

	const heading = document.querySelector(".ac-hero-top h2");
	const source = heading ? heading.textContent.trim() : avatar.textContent.trim();
	if (!source) {
		return;
	}

	const parts = source.split(/\s+/).filter(Boolean);
	const initials = parts.length >= 2
		? `${parts[0][0]}${parts[1][0]}`
		: parts[0].slice(0, 2);
	avatar.textContent = initials.toUpperCase();
})();

(function initLoginPasswordToggle() {
	const toggle = document.getElementById("toggleLoginPassword");
	const input = document.getElementById("id_password");
	if (!toggle || !input) {
		return;
	}

	toggle.addEventListener("click", () => {
		const isHidden = input.getAttribute("type") === "password";
		input.setAttribute("type", isHidden ? "text" : "password");
		toggle.textContent = isHidden ? "Hide" : "Show";
		toggle.setAttribute("aria-pressed", isHidden ? "true" : "false");
	});
})();

(function initLandingThemeToggle() {
	const html = document.documentElement;
	const toggle = document.getElementById("landingThemeToggle");
	if (!toggle) {
		return;
	}

	const label = toggle.querySelector("[data-theme-label]");
	const icon = toggle.querySelector(".ac-theme-dot");

	function render(theme) {
		if (label) {
			label.textContent = theme === "light" ? "Light" : "Dark";
		}
		if (icon) {
			icon.textContent = theme === "light" ? "☀" : "☾";
		}
	}

	render(html.getAttribute("data-theme") || "light");

	toggle.addEventListener("click", () => {
		const current = html.getAttribute("data-theme") || "light";
		const next = current === "light" ? "dark" : "light";
		html.setAttribute("data-theme", next);
		localStorage.setItem("hydroops_theme", next);
		render(next);
	});
})();

(function initLandingWordCycle() {
	const el = document.getElementById("landingWord");
	if (!el) {
		return;
	}

	const words = ["Intelligence", "Optimization", "Forecasting", "Sustainability"];
	let idx = 0;

	setInterval(() => {
		idx = (idx + 1) % words.length;
		el.textContent = words[idx];
	}, 1800);
})();

(function initLandingCounters() {
	const counters = document.querySelectorAll("[data-counter]");
	if (!counters.length) {
		return;
	}

	counters.forEach((node) => {
		const target = Number(node.getAttribute("data-counter")) || 0;
		const duration = 1200;
		const start = performance.now();

		function tick(now) {
			const progress = Math.min((now - start) / duration, 1);
			const value = Math.round(target * progress);
			node.textContent = value.toLocaleString();
			if (progress < 1) {
				requestAnimationFrame(tick);
			}
		}

		requestAnimationFrame(tick);
	});
})();
