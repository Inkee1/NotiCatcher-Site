(() => {
  const STORAGE_KEY = "lang";
  const MANUAL_STORAGE_KEY = "lang_manual";
  const LANGUAGE_LABELS = {
    am: "አማርኛ",
    ar: "العربية",
    bg: "Български",
    bn: "বাংলা",
    cs: "Čeština",
    da: "Dansk",
    de: "Deutsch",
    el: "Ελληνικά",
    en: "English",
    es: "Español",
    "es-419": "Español (Latinoamérica)",
    et: "Eesti",
    fa: "فارسی",
    fi: "Suomi",
    fil: "Filipino",
    fr: "Français",
    gu: "ગુજરાતી",
    he: "עברית",
    hi: "हिन्दी",
    hr: "Hrvatski",
    hu: "Magyar",
    id: "Bahasa Indonesia",
    it: "Italiano",
    ja: "日本語",
    km: "ខ្មែរ",
    kn: "ಕನ್ನಡ",
    ko: "한국어",
    lo: "ລາວ",
    lt: "Lietuvių",
    lv: "Latviešu",
    ml: "മലയാളം",
    mr: "मराठी",
    ms: "Bahasa Melayu",
    my: "မြန်မာဘာသာ",
    nl: "Nederlands",
    no: "Norsk",
    pa: "ਪੰਜਾਬੀ",
    pl: "Polski",
    pt: "Português",
    "pt-br": "Português (Brasil)",
    ro: "Română",
    ru: "Русский",
    sk: "Slovenčina",
    sl: "Slovenščina",
    sr: "Српски",
    sv: "Svenska",
    sw: "Kiswahili",
    ta: "தமிழ்",
    te: "తెలుగు",
    th: "ไทย",
    tr: "Türkçe",
    uk: "Українська",
    ur: "اردو",
    vi: "Tiếng Việt",
    zh: "中文",
    "zh-hans": "简体中文",
    "zh-hant": "繁體中文",
  };

  function normalizeLang(tag) {
    return (tag || "")
      .toString()
      .trim()
      .toLowerCase()
      .replace(/_/g, "-");
  }

  function formatTag(lang) {
    const parts = normalizeLang(lang).split("-").filter(Boolean);
    if (!parts.length) return "";
    return parts
      .map((part) => {
        if (/^\d+$/.test(part)) return part;
        if (part.length === 4) {
          return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
        }
        return part.toUpperCase();
      })
      .join("-");
  }

  function getCurrentLang() {
    const htmlLang = normalizeLang(document.documentElement.getAttribute("lang"));
    if (htmlLang) return htmlLang;

    const seg = (location.pathname || "/").split("/").filter(Boolean)[0];
    return normalizeLang(seg) || "en";
  }

  function nativeNameFor(lang) {
    const l = normalizeLang(lang);
    if (LANGUAGE_LABELS[l]) return LANGUAGE_LABELS[l];
    try {
      if (typeof Intl !== "undefined" && typeof Intl.DisplayNames === "function") {
        const name = new Intl.DisplayNames([l], { type: "language" }).of(l);
        if (name) return name;
      }
    } catch {}
    return l || "Language";
  }

  function labelFor(lang) {
    const l = normalizeLang(lang);
    const tag = formatTag(l);
    return {
      name: nativeNameFor(l),
      tag,
      sortTag: tag.toUpperCase(),
    };
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

  function resolveSupportedLang(tag, supportedLangs) {
    let l = normalizeLang(tag);
    if (!l) return "";

    const special = resolveSpecialLang(l, supportedLangs);
    if (special) return special;
    if (supportedLangs.has(l)) return l;

    while (l.includes("-")) {
      l = l.substring(0, l.lastIndexOf("-"));
      const fallback = resolveSpecialLang(l, supportedLangs);
      if (fallback) return fallback;
      if (supportedLangs.has(l)) return l;
    }

    return supportedLangs.has(l) ? l : "";
  }

  function resolveSpecialLang(lang, supportedLangs) {
    const l = normalizeLang(lang);
    if (!l) return "";

    if (supportedLangs.has("zh-hant") && /^zh-(hant|tw|hk|mo)(-|$)/.test(l)) return "zh-hant";
    if (supportedLangs.has("zh-hans") && /^zh-(hans|cn|sg)(-|$)/.test(l)) return "zh-hans";
    if (supportedLangs.has("es-419") && /^es-(?!es(-|$))/.test(l)) return "es-419";
    if (supportedLangs.has("pt-br") && /^pt-br(-|$)/.test(l)) return "pt-br";
    if (supportedLangs.has("ko") && /^ko-kr(-|$)/.test(l)) return "ko";

    return "";
  }

  function getLocalLang(items, currentLang) {
    const supportedLangs = new Set(items.map((it) => normalizeLang(it.lang)).filter(Boolean));
    const browserLangs =
      typeof navigator !== "undefined" && Array.isArray(navigator.languages) && navigator.languages.length
        ? navigator.languages
        : [typeof navigator !== "undefined" ? navigator.language || "" : ""];

    for (const candidate of browserLangs) {
      const resolved = resolveSupportedLang(candidate, supportedLangs);
      if (resolved) return resolved;
    }

    return resolveSupportedLang(currentLang, supportedLangs) || "en";
  }

  function menuPriority(lang, localLang) {
    if (lang === localLang) return 0;
    if (localLang !== "en" && lang === "en") return 1;
    return 2;
  }

  function sortItems(items, currentLang) {
    const localLang = getLocalLang(items, currentLang);
    return [...items].sort((a, b) => {
      const aLang = normalizeLang(a.lang);
      const bLang = normalizeLang(b.lang);
      const priorityDiff = menuPriority(aLang, localLang) - menuPriority(bLang, localLang);
      if (priorityDiff !== 0) return priorityDiff;

      const aLabel = labelFor(aLang);
      const bLabel = labelFor(bLang);
      const tagDiff = aLabel.sortTag.localeCompare(bLabel.sortTag, "en", {
        sensitivity: "base",
        numeric: true,
      });
      if (tagDiff !== 0) return tagDiff;

      return aLabel.name.localeCompare(bLabel.name, undefined, {
        sensitivity: "base",
      });
    });
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
    const orderedItems = sortItems(items, current);
    const navLinks = document.querySelector(".navbar .nav-links");
    const mountInNav = navLinks instanceof HTMLElement;

    const root = document.createElement("div");
    root.className = "lang-fab" + (mountInNav ? " lang-fab--nav" : "");
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

    // Put the browser's local language first, English second, then sort the rest by code.
    for (const it of orderedItems) {
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
              try { localStorage.setItem(STORAGE_KEY, lang); localStorage.setItem(MANUAL_STORAGE_KEY, lang); } catch {}
              location.href = dest;
              return;
            }
            try { localStorage.setItem(STORAGE_KEY, "en"); localStorage.setItem(MANUAL_STORAGE_KEY, "en"); } catch {}
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

    document.addEventListener("click", (e) => {
      if (!root.contains(e.target)) setOpen(false);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setOpen(false);
    });

    root.appendChild(btn);
    root.appendChild(menu);
    if (mountInNav) {
      navLinks.prepend(root);
      return;
    }
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

