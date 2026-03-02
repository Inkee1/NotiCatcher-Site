(() => {
  const STORAGE_KEY = "lang";

  function normalizeLang(tag) {
    return (tag || "")
      .toString()
      .trim()
      .toLowerCase()
      .replace(/_/g, "-");
  }

  function getCurrentLang() {
    const htmlLang = normalizeLang(document.documentElement.getAttribute("lang"));
    if (htmlLang) return htmlLang;

    const seg = (location.pathname || "/").split("/").filter(Boolean)[0];
    return normalizeLang(seg) || "en";
  }

  function labelFor(lang) {
    const l = normalizeLang(lang);
    const map = {
      en: { name: "English", tag: "EN" },
      ko: { name: "한국어", tag: "KO" },
      ja: { name: "日本語", tag: "JA" },
      "zh-hans": { name: "简体中文", tag: "ZH-Hans" },
      "zh-hant": { name: "繁體中文", tag: "ZH-Hant" },
      fr: { name: "Français", tag: "FR" },
      de: { name: "Deutsch", tag: "DE" },
      es: { name: "Español", tag: "ES" },
      it: { name: "Italiano", tag: "IT" },
      pt: { name: "Português", tag: "PT" },
      ru: { name: "Русский", tag: "RU" },
      vi: { name: "Tiếng Việt", tag: "VI" },
      id: { name: "Bahasa Indonesia", tag: "ID" },
      th: { name: "ไทย", tag: "TH" },
      tr: { name: "Türkçe", tag: "TR" },
      ar: { name: "العربية", tag: "AR" },
      hi: { name: "हिन्दी", tag: "HI" },
    };
    return map[l] || { name: l || "Language", tag: (l || "").toUpperCase() };
  }

  function uniqueByLang(items) {
    const seen = new Set();
    const out = [];
    for (const it of items) {
      const key = normalizeLang(it.lang);
      if (!key || key === "x-default") continue;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ lang: key, href: it.href });
    }
    return out;
  }

  function alternatesFromHead() {
    const links = Array.from(document.querySelectorAll('link[rel="alternate"][hreflang][href]'));
    const items = links.map((l) => ({
      lang: normalizeLang(l.getAttribute("hreflang")),
      href: l.getAttribute("href"),
    }));
    return uniqueByLang(items).map((it) => ({
      ...it,
      href: new URL(it.href, location.href).toString(),
    }));
  }

  function fallbackTargets(currentLang) {
    const supported = ["en", "ko", "ja"];
    const currentPath = location.pathname || "/";
    const hasLangPrefix = /^\/[a-z]{2,3}(?:-[a-z0-9]{2,8})*\//i.test(currentPath);

    return supported.map((lang) => {
      let path;
      if (hasLangPrefix) {
        path = currentPath.replace(/^\/[a-z]{2,3}(?:-[a-z0-9]{2,8})*\//i, `/${lang}/`);
      } else {
        path = `/${lang}/`;
      }
      const u = new URL(path, location.origin);
      u.search = location.search;
      u.hash = location.hash;
      return { lang, href: u.toString() };
    });
  }

  function build() {
    const current = getCurrentLang();
    const targets = alternatesFromHead();
    const items = targets.length ? targets : fallbackTargets(current);

    const root = document.createElement("div");
    root.className = "lang-fab";
    root.setAttribute("data-open", "false");

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "lang-fab__btn";
    btn.setAttribute("aria-label", "Change language");
    btn.setAttribute("aria-haspopup", "menu");
    btn.setAttribute("aria-expanded", "false");
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z" stroke="currentColor" stroke-width="1.8"/>
        <path d="M2 12h20" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <path d="M12 2c3 3 4.5 6.5 4.5 10S15 19 12 22c-3-3-4.5-6.5-4.5-10S9 5 12 2Z" stroke="currentColor" stroke-width="1.8"/>
      </svg>
    `.trim();

    const menu = document.createElement("div");
    menu.className = "lang-fab__menu";
    menu.setAttribute("role", "menu");

    for (const it of items) {
      const lang = normalizeLang(it.lang);
      const href = it.href;
      const l = labelFor(lang);

      const b = document.createElement("button");
      b.type = "button";
      b.className = "lang-fab__item" + (lang === current ? " is-active" : "");
      b.setAttribute("role", "menuitem");
      b.setAttribute("data-lang", lang);
      b.setAttribute("data-href", href);
      b.innerHTML = `
        <span class="lang-fab__label">
          <span class="lang-fab__name">${escapeHtml(l.name)}</span>
          <span class="lang-fab__tag">${escapeHtml(l.tag)}</span>
        </span>
        <span class="lang-fab__check" aria-hidden="true">✓</span>
      `.trim();

      b.addEventListener("click", () => {
        const u = new URL(href, location.href);
        u.search = location.search;
        u.hash = location.hash;

        // Defensive: verify target exists before persisting lang.
        // Prevents "missing site" being remembered and requiring cache/localStorage cleanup.
        const dest = u.toString();
        fetch(dest, { method: "HEAD", cache: "no-store" })
          .then((r) => {
            if (r && r.ok) {
              try { localStorage.setItem(STORAGE_KEY, lang); } catch {}
              location.href = dest;
              return;
            }
            try { localStorage.setItem(STORAGE_KEY, "en"); } catch {}
            location.href = new URL("/en/", location.origin).toString();
          })
          .catch(() => {
            // If HEAD isn't supported, proceed with navigation but don't persist a potentially bad lang.
            location.href = dest;
          });
      });

      menu.appendChild(b);
    }

    function setOpen(open) {
      root.setAttribute("data-open", open ? "true" : "false");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    }

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      setOpen(root.getAttribute("data-open") !== "true");
    });

    document.addEventListener("click", () => setOpen(false));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setOpen(false);
    });

    root.appendChild(btn);
    root.appendChild(menu);
    document.body.appendChild(root);
  }

  function escapeHtml(s) {
    return (s ?? "").toString().replace(/[&<>"']/g, (c) => {
      switch (c) {
        case "&":
          return "&amp;";
        case "<":
          return "&lt;";
        case ">":
          return "&gt;";
        case '"':
          return "&quot;";
        case "'":
          return "&#39;";
        default:
          return c;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build, { once: true });
  } else {
    build();
  }
})();

