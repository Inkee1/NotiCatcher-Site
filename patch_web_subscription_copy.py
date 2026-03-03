#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:
    BeautifulSoup = None  # type: ignore

try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore


RE_LOCALE_DIR = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")

RUNTIME_EN = {
    "toastUpdated": "Plan updated.",
    "toastScheduled": "Plan will change on next billing date.",
    "errPlanChangeFailed": "Failed to change plan.",
    "errPortalFailed": "Failed to open billing portal.",
    "errRequestFailed": "Request failed. Please try again.",
    "errLoginRequiredSubscribe": "You need to log in before subscribing.\n\nYou'll be taken to the login page now.",
    "msgAlreadySubscribed": "You are already subscribed.",
    "errCheckoutMissingUrl": "Checkout session created, but missing redirect URL. Please contact support.",
    "errCheckoutFailed": "Checkout failed. Please try again.",
    # Auth (myinfo) messages
    "authEmailAlreadyInUse": "This email is already in use.",
    "authInvalidEmail": "Please enter a valid email address.",
    "authWeakPassword": "Password is too weak (min 6 chars).",
    "authUserNotFound": "No account found with this email.",
    "authWrongPassword": "Incorrect password.",
    "authInvalidCredential": "Invalid email or password.",
    "authTooManyRequests": "Too many attempts. Please try again later.",
    "authNetworkRequestFailed": "Network error. Please check your connection.",
    # Must keep {code} placeholder
    "authGenericWithCode": "An error occurred. Please try again ({code}).",
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def translate_runtime_strings(*, client: "OpenAI", locale: str, phrases: dict[str, str]) -> dict[str, str]:
    """
    Translate a small set of UI runtime strings into target locale.
    Returns a dict with the same keys.
    """
    # For English, keep as-is.
    if locale.lower() == "en":
        return dict(phrases)

    system = (
        "You translate short UI messages for a subscription settings web page.\n"
        "Return ONLY valid JSON. No markdown.\n"
        "Keep it concise and natural.\n"
        "If the source contains a placeholder like {code}, preserve it exactly.\n"
    )
    user = {
        "target_locale": locale,
        "items": [{"key": k, "text": v} for k, v in phrases.items()],
        "rules": [
            "Preserve {code} exactly if present.",
        ],
    }

    # light retry
    last_err: Exception | None = None
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(
                model="gpt-5.2",
                messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or ""
            data = json.loads(content)
            out = {}
            for obj in data.get("items", []):
                if not isinstance(obj, dict):
                    continue
                k = str(obj.get("key") or "")
                t = str(obj.get("translation") or obj.get("text") or "")
                if k in phrases and t.strip():
                    out[k] = t.strip()
            # fill fallbacks
            for k, v in phrases.items():
                out.setdefault(k, v)
            return out
        except Exception as exc:
            last_err = exc
            time.sleep(min(8.0, 2.0**attempt))
    raise RuntimeError(f"Failed to translate runtime strings for {locale}: {last_err}")


def _strip_tags(html: str) -> str:
    if not html:
        return ""
    # Remove script/style quickly
    html = re.sub(r"<(script|style)\b[\s\S]*?</\1\s*>", "", html, flags=re.IGNORECASE)
    # Remove tags
    txt = re.sub(r"<[^>]+>", "", html)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _extract_first(pattern: re.Pattern[str], text: str) -> str:
    m = pattern.search(text)
    return (m.group(1) if m else "").strip()


def _extract_button_label_by_id(html: str, element_id: str) -> str:
    # Capture inner HTML then strip tags, keeping actual visible text.
    pat = re.compile(
        r'<button\b[^>]*\bid\s*=\s*["\']'
        + re.escape(element_id)
        + r'["\'][^>]*>([\s\S]*?)</button\s*>',
        re.IGNORECASE,
    )
    inner = _extract_first(pat, html)
    return _strip_tags(inner)


def _extract_div_text_by_id(html: str, element_id: str) -> str:
    pat = re.compile(
        r'<div\b[^>]*\bid\s*=\s*["\']'
        + re.escape(element_id)
        + r'["\'][^>]*>([\s\S]*?)</div\s*>',
        re.IGNORECASE,
    )
    inner = _extract_first(pat, html)
    return _strip_tags(inner)


def _extract_action_card_heading(myinfo_html: str) -> str:
    # <div class="action-card"><h3>...</h3>
    pat = re.compile(r'<div\b[^>]*class\s*=\s*["\'][^"\']*\baction-card\b[^"\']*["\'][^>]*>[\s\S]*?<h3[^>]*>([\s\S]*?)</h3\s*>', re.IGNORECASE)
    inner = _extract_first(pat, myinfo_html)
    return _strip_tags(inner)


def _extract_feature_bullets(price_html: str, card_class: str, max_items: int = 3) -> list[str]:
    """
    Extract bullet strings from the pricing card's <ul class="card-features">.
    card_class: 'special' (Basic) or 'recommended' (Pro)
    """
    if BeautifulSoup is not None:
        soup = BeautifulSoup(price_html, "html.parser")
        card = soup.select_one(f"div.price-card.{card_class}")
        if not card:
            return []
        ul = card.select_one("ul.card-features")
        if not ul:
            return []
        out: list[str] = []
        for li in ul.select("li"):
            txt = li.get_text(" ", strip=True)
            txt = re.sub(r"\s+", " ", txt).strip()
            if not txt:
                continue
            out.append(txt)
            if len(out) >= max_items:
                break
        return out

    # Find the card block
    card_pat = re.compile(
        r'<div\b[^>]*class\s*=\s*["\'][^"\']*\bprice-card\b[^"\']*\b'
        + re.escape(card_class)
        + r'\b[^"\']*["\'][^>]*>([\s\S]*?)</div\s*>',
        re.IGNORECASE,
    )
    card_html = _extract_first(card_pat, price_html)
    if not card_html:
        return []

    ul_pat = re.compile(r'<ul\b[^>]*class\s*=\s*["\'][^"\']*\bcard-features\b[^"\']*["\'][^>]*>([\s\S]*?)</ul\s*>', re.IGNORECASE)
    ul_html = _extract_first(ul_pat, card_html)
    if not ul_html:
        return []

    li_pat = re.compile(r"<li\b[^>]*>([\s\S]*?)</li\s*>", re.IGNORECASE)
    items: list[str] = []
    for m in li_pat.finditer(ul_html):
        txt = _strip_tags(m.group(1))
        if not txt:
            continue
        # Skip disabled-feature lines if possible (they often duplicate)
        if "Unlimited financial" in txt and "Telegram" in txt and card_class == "special":
            # keep; might be meaningful in some languages, but Basic card has a disabled line
            pass
        items.append(txt)
        if len(items) >= max_items:
            break
    return items


@dataclass(frozen=True)
class LocaleCopy:
    locale: str
    subscribe_basic: str
    subscribe_pro: str
    trial_note: str
    manage_label: str
    upgrade_to_pro: str
    switch_to_basic: str
    basic_bullets: list[str]
    pro_bullets: list[str]
    runtime_i18n: dict[str, str]


def build_locale_copy(locale: str, *, price_html: str, myinfo_html: str) -> LocaleCopy:
    if BeautifulSoup is not None:
        price_soup = BeautifulSoup(price_html, "html.parser")
        myinfo_soup = BeautifulSoup(myinfo_html, "html.parser")

        def btn_label(soup, _id: str, fallback: str) -> str:
            el = soup.select_one(f"#{_id}")
            if not el:
                return fallback
            txt = el.get_text(" ", strip=True)
            return re.sub(r"\s+", " ", txt).strip() or fallback

        def div_text(soup, _id: str) -> str:
            el = soup.select_one(f"#{_id}")
            if not el:
                return ""
            return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()

        subscribe_basic = btn_label(price_soup, "btn-basic-cta", "Subscribe")
        subscribe_pro = btn_label(price_soup, "btn-pro-cta", "Subscribe")
        trial_note = div_text(price_soup, "pro-trial-note") or div_text(price_soup, "basic-trial-note") or ""

        manage_label = ""
        action_h3 = myinfo_soup.select_one("div.action-card h3")
        if action_h3:
            manage_label = re.sub(r"\s+", " ", action_h3.get_text(" ", strip=True)).strip()
        manage_label = manage_label or "Manage"

        upgrade_to_pro = btn_label(myinfo_soup, "btn-change-pro", "Upgrade to Pro")
        switch_to_basic = btn_label(myinfo_soup, "btn-change-basic", "Switch to Basic")
    else:
        subscribe_basic = _extract_button_label_by_id(price_html, "btn-basic-cta") or "Subscribe"
        subscribe_pro = _extract_button_label_by_id(price_html, "btn-pro-cta") or "Subscribe"
        trial_note = (
            _extract_div_text_by_id(price_html, "pro-trial-note")
            or _extract_div_text_by_id(price_html, "basic-trial-note")
            or ""
        )

        manage_label = _extract_action_card_heading(myinfo_html) or "Manage"
        upgrade_to_pro = _extract_button_label_by_id(myinfo_html, "btn-change-pro") or "Upgrade to Pro"
        switch_to_basic = _extract_button_label_by_id(myinfo_html, "btn-change-basic") or "Switch to Basic"

    basic_bullets = _extract_feature_bullets(price_html, "special", max_items=3)
    pro_bullets = _extract_feature_bullets(price_html, "recommended", max_items=3)

    return LocaleCopy(
        locale=locale,
        subscribe_basic=subscribe_basic,
        subscribe_pro=subscribe_pro,
        trial_note=trial_note,
        manage_label=manage_label,
        upgrade_to_pro=upgrade_to_pro,
        switch_to_basic=switch_to_basic,
        basic_bullets=basic_bullets,
        pro_bullets=pro_bullets,
        runtime_i18n=dict(RUNTIME_EN),
    )


RE_PRICE_LABELS_BLOCK = re.compile(
    r"""
    # Inside applyPricingUIFromUserDoc, the default label assignments (English hardcoded)
    let\s+showTrial\s*=\s*\([^\n;]+\)\s*;\s*
    let\s+basicLabel\s*=\s*'[^']*'\s*;\s*
    let\s+proLabel\s*=\s*'[^']*'\s*;\s*
    let\s+basicAction\s*=\s*\{[\s\S]*?\}\s*;\s*
    let\s+proAction\s*=\s*\{[\s\S]*?\}\s*;\s*
    """,
    re.IGNORECASE | re.VERBOSE,
)

RE_PRICE_COPY_OBJ = re.compile(
    r"""
    const\s+__WEB_SUB_COPY\s*=\s*\{[\s\S]*?\}\s*;
    """,
    re.IGNORECASE | re.VERBOSE,
)

RE_PRICE_COPY_DECL = re.compile(r"\bconst\s+__WEB_SUB_COPY\b", re.IGNORECASE)

RE_PRICE_GLOBAL_COPY_ANCHOR = re.compile(
    r"""
    const\s+noteProTrial\s*=\s*document\.getElementById\('pro-trial-note'\)\s*;\s*
    """,
    re.IGNORECASE | re.VERBOSE,
)


def patch_price_page(price_html: str, copy: LocaleCopy) -> tuple[str, bool]:
    # Inject a copy object near the top of applyPricingUIFromUserDoc
    inject_pat = re.compile(r"function\s+applyPricingUIFromUserDoc\s*\(\s*data\s*\)\s*\{", re.IGNORECASE)
    m = inject_pat.search(price_html)
    if not m:
        return price_html, False

    copy_js = (
        "        const __WEB_SUB_COPY = {\n"
        f"                subscribeBasic: {copy.subscribe_basic!r},\n"
        f"                subscribePro: {copy.subscribe_pro!r},\n"
        f"                manage: {copy.manage_label!r},\n"
        f"                upgradeToPro: {copy.upgrade_to_pro!r},\n"
        f"                toastUpdated: {copy.runtime_i18n.get('toastUpdated', RUNTIME_EN['toastUpdated'])!r},\n"
        f"                toastScheduled: {copy.runtime_i18n.get('toastScheduled', RUNTIME_EN['toastScheduled'])!r},\n"
        f"                errPlanChangeFailed: {copy.runtime_i18n.get('errPlanChangeFailed', RUNTIME_EN['errPlanChangeFailed'])!r},\n"
        f"                errPortalFailed: {copy.runtime_i18n.get('errPortalFailed', RUNTIME_EN['errPortalFailed'])!r},\n"
        f"                errRequestFailed: {copy.runtime_i18n.get('errRequestFailed', RUNTIME_EN['errRequestFailed'])!r},\n"
        f"                errLoginRequiredSubscribe: {copy.runtime_i18n.get('errLoginRequiredSubscribe', RUNTIME_EN['errLoginRequiredSubscribe'])!r},\n"
        f"                msgAlreadySubscribed: {copy.runtime_i18n.get('msgAlreadySubscribed', RUNTIME_EN['msgAlreadySubscribed'])!r},\n"
        f"                errCheckoutMissingUrl: {copy.runtime_i18n.get('errCheckoutMissingUrl', RUNTIME_EN['errCheckoutMissingUrl'])!r},\n"
        f"                errCheckoutFailed: {copy.runtime_i18n.get('errCheckoutFailed', RUNTIME_EN['errCheckoutFailed'])!r},\n"
        "        };\n"
    )

    # Remove any existing copy object (older injections may be inside functions).
    price_html = RE_PRICE_COPY_OBJ.sub("", price_html, count=1)

    # Inject global copy object once near top of module script.
    if not RE_PRICE_COPY_DECL.search(price_html):
        price_html, n_anchor = RE_PRICE_GLOBAL_COPY_ANCHOR.subn(
            lambda m2: m2.group(0) + "\n\n" + copy_js + "\n",
            price_html,
            count=1,
        )
        if n_anchor == 0:
            # fallback: inject after applyPricingUIFromUserDoc line
            insert_at = m.end()
            price_html = price_html[:insert_at] + "\n\n" + copy_js + "\n" + price_html[insert_at:]

    # Replace default label block with localized defaults and simplified labels
    def_block = (
        "            // Defaults (new user / no subscription): show trial CTAs + show trial note.\n"
        "            let showTrial = (!hasUsedTrial && !hasEverPaid && !hadStripeHistory);\n"
        "            let basicLabel = __WEB_SUB_COPY.subscribeBasic;\n"
        "            let proLabel = __WEB_SUB_COPY.subscribePro;\n"
        "            let basicAction = { type: 'checkout', plan: 'basic' };\n"
        "            let proAction = { type: 'checkout', plan: 'pro' };\n"
    )

    new_html, n = RE_PRICE_LABELS_BLOCK.subn(def_block, price_html, count=1)
    # If already patched once, label block might not match; that's ok for idempotent updates.
    if n == 0:
        new_html = price_html

    # Now simplify other label assignments (Manage Plan / Upgrade to Pro / Resume... etc)
    new_html = re.sub(r"basicLabel\s*=\s*'Manage Plan'\s*;", "basicLabel = __WEB_SUB_COPY.manage;", new_html)
    new_html = re.sub(r"proLabel\s*=\s*'Manage Plan'\s*;", "proLabel = __WEB_SUB_COPY.manage;", new_html)
    new_html = re.sub(r"proLabel\s*=\s*'Upgrade to Pro'\s*;", "proLabel = __WEB_SUB_COPY.upgradeToPro;", new_html)

    # Any remaining checkout labels like Resume/Go Pro/Start Basic Now → just use subscribe labels
    new_html = re.sub(r"basicLabel\s*=\s*'(Resume Basic|Start Basic Now|Start Free Trial)'\s*;", "basicLabel = __WEB_SUB_COPY.subscribeBasic;", new_html)
    new_html = re.sub(r"proLabel\s*=\s*'(Resume Pro|Go Pro Now|Start Pro Free)'\s*;", "proLabel = __WEB_SUB_COPY.subscribePro;", new_html)

    # Localize subscription-related alerts in this page
    new_html = new_html.replace(
        'alert((e && e.message) ? e.message : "Failed to open billing portal.");',
        "alert((e && e.message) ? e.message : __WEB_SUB_COPY.errPortalFailed);",
    )
    new_html = new_html.replace(
        'alert((e && e.message) ? e.message : "Failed to change plan.");',
        "alert((e && e.message) ? e.message : __WEB_SUB_COPY.errPlanChangeFailed);",
    )
    new_html = new_html.replace(
        "alert(\"You need to log in before subscribing.\\n\\nYou'll be taken to the login page now.\");",
        "alert(__WEB_SUB_COPY.errLoginRequiredSubscribe);",
    )
    new_html = new_html.replace(
        'alert(data.message || "You are already subscribed.");',
        "alert(data.message || __WEB_SUB_COPY.msgAlreadySubscribed);",
    )
    new_html = new_html.replace(
        'alert("Checkout session created, but missing redirect URL. Please contact support.");',
        "alert(__WEB_SUB_COPY.errCheckoutMissingUrl);",
    )
    new_html = new_html.replace(
        'alert((e && e.message) ? e.message : "Checkout failed. Please try again.");',
        "alert((e && e.message) ? e.message : __WEB_SUB_COPY.errCheckoutFailed);",
    )

    # Fix locale-aware redirects to myinfo (some pages hardcode /en/myinfo/)
    new_html = re.sub(
        r"window\.location\.href\s*=\s*`/en/myinfo/\?next=\$\{encodeURIComponent\(next\)\}`\s*;",
        f"window.location.href = `/{copy.locale}/myinfo/?next=${{encodeURIComponent(next)}}`;",
        new_html,
        flags=re.IGNORECASE,
    )
    new_html = re.sub(
        r"window\.location\.href\s*=\s*`/en/myinfo/\?next=\$\{encodeURIComponent\(next\)\}`\s*;",
        f"window.location.href = `/{copy.locale}/myinfo/?next=${{encodeURIComponent(next)}}`;",
        new_html,
        flags=re.IGNORECASE,
    )
    new_html = re.sub(
        r"window\.location\.href\s*=\s*`/en/myinfo/\?next=\$\{encodeURIComponent\(next\)\}`",
        f"window.location.href = `/{copy.locale}/myinfo/?next=${{encodeURIComponent(next)}}`",
        new_html,
        flags=re.IGNORECASE,
    )

    return new_html, True


RE_MYINFO_WEB_SECTION = re.compile(
    r"""
    \s*//\s*---\s*Web\s+subscription\s+copy[\s\S]*?
    (?=onAuthStateChanged\s*\()
    """,
    re.IGNORECASE | re.VERBOSE,
)

RE_MYINFO_FIREBASE_ERROR_SECTION = re.compile(
    r"""
    function\s+firebaseErrorMsg\s*\(\s*code\s*\)\s*\{
    [\s\S]*?
    (?=function\s+formatDate\s*\()
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _js_array(items: list[str]) -> str:
    return "[" + ", ".join(repr(x) for x in items) + "]"


def patch_myinfo_page(myinfo_html: str, copy: LocaleCopy) -> tuple[str, bool]:
    # Replace old success alerts with lightweight toast hooks (localized via existing labels)
    myinfo_html = myinfo_html.replace(
        'alert("Plan updated. It may take a few seconds to reflect.");',
        "__showPlanToast('✓ ' + __WEB_SUB_COPY.toastUpdated);",
    )
    myinfo_html = myinfo_html.replace(
        'alert("Plan will change on next billing date.");',
        "__showPlanToast('✓ ' + __WEB_SUB_COPY.toastScheduled);",
    )
    myinfo_html = myinfo_html.replace(
        'alert((e && e.message) ? e.message : "Failed to change plan.");',
        "__showPlanToast('✗ ' + __WEB_SUB_COPY.errPlanChangeFailed);",
    )
    myinfo_html = myinfo_html.replace(
        'alert((e && e.message) ? e.message : "Failed to open billing portal.");',
        "__showPlanToast('✗ ' + __WEB_SUB_COPY.errPortalFailed);",
    )

    injected = (
        "\n"
        "        // --- Web subscription copy (localized per locale) ---\n"
        "        const __WEB_SUB_COPY = {\n"
        f"            subscribeBasic: {copy.subscribe_basic!r},\n"
        f"            subscribePro: {copy.subscribe_pro!r},\n"
        f"            trialNote: {copy.trial_note!r},\n"
        f"            manage: {copy.manage_label!r},\n"
        f"            upgradeToPro: {copy.upgrade_to_pro!r},\n"
        f"            switchToBasic: {copy.switch_to_basic!r},\n"
        f"            basicBullets: {_js_array(copy.basic_bullets)},\n"
        f"            proBullets: {_js_array(copy.pro_bullets)},\n"
        f"            toastUpdated: {copy.runtime_i18n.get('toastUpdated', RUNTIME_EN['toastUpdated'])!r},\n"
        f"            toastScheduled: {copy.runtime_i18n.get('toastScheduled', RUNTIME_EN['toastScheduled'])!r},\n"
        f"            errPlanChangeFailed: {copy.runtime_i18n.get('errPlanChangeFailed', RUNTIME_EN['errPlanChangeFailed'])!r},\n"
        f"            errPortalFailed: {copy.runtime_i18n.get('errPortalFailed', RUNTIME_EN['errPortalFailed'])!r},\n"
        f"            errRequestFailed: {copy.runtime_i18n.get('errRequestFailed', RUNTIME_EN['errRequestFailed'])!r},\n"
        f"            authEmailAlreadyInUse: {copy.runtime_i18n.get('authEmailAlreadyInUse', RUNTIME_EN['authEmailAlreadyInUse'])!r},\n"
        f"            authInvalidEmail: {copy.runtime_i18n.get('authInvalidEmail', RUNTIME_EN['authInvalidEmail'])!r},\n"
        f"            authWeakPassword: {copy.runtime_i18n.get('authWeakPassword', RUNTIME_EN['authWeakPassword'])!r},\n"
        f"            authUserNotFound: {copy.runtime_i18n.get('authUserNotFound', RUNTIME_EN['authUserNotFound'])!r},\n"
        f"            authWrongPassword: {copy.runtime_i18n.get('authWrongPassword', RUNTIME_EN['authWrongPassword'])!r},\n"
        f"            authInvalidCredential: {copy.runtime_i18n.get('authInvalidCredential', RUNTIME_EN['authInvalidCredential'])!r},\n"
        f"            authTooManyRequests: {copy.runtime_i18n.get('authTooManyRequests', RUNTIME_EN['authTooManyRequests'])!r},\n"
        f"            authNetworkRequestFailed: {copy.runtime_i18n.get('authNetworkRequestFailed', RUNTIME_EN['authNetworkRequestFailed'])!r},\n"
        f"            authGenericWithCode: {copy.runtime_i18n.get('authGenericWithCode', RUNTIME_EN['authGenericWithCode'])!r},\n"
        "        };\n\n"
        "        function __showPlanToast(text) {\n"
        "            try {\n"
        "                const id = 'plan-toast';\n"
        "                let el = document.getElementById(id);\n"
        "                if (!el) {\n"
        "                    el = document.createElement('div');\n"
        "                    el.id = id;\n"
        "                    el.style.position = 'fixed';\n"
        "                    el.style.left = '50%';\n"
        "                    el.style.bottom = '22px';\n"
        "                    el.style.transform = 'translateX(-50%)';\n"
        "                    el.style.zIndex = '9999';\n"
        "                    el.style.padding = '10px 14px';\n"
        "                    el.style.borderRadius = '12px';\n"
        "                    el.style.background = 'rgba(15, 23, 42, 0.92)';\n"
        "                    el.style.border = '1px solid rgba(148,163,184,0.22)';\n"
        "                    el.style.color = 'rgba(226,232,240,0.95)';\n"
        "                    el.style.fontSize = '0.9rem';\n"
        "                    el.style.maxWidth = '92vw';\n"
        "                    el.style.textAlign = 'center';\n"
        "                    el.style.boxShadow = '0 12px 30px rgba(0,0,0,0.35)';\n"
        "                    el.style.opacity = '0';\n"
        "                    el.style.transition = 'opacity 200ms ease, transform 200ms ease';\n"
        "                    document.body.appendChild(el);\n"
        "                }\n"
        "                el.textContent = String(text || '');\n"
        "                el.style.opacity = '1';\n"
        "                el.style.transform = 'translateX(-50%) translateY(-4px)';\n"
        "                clearTimeout(el.__t);\n"
        "                el.__t = setTimeout(() => {\n"
        "                    el.style.opacity = '0';\n"
        "                    el.style.transform = 'translateX(-50%) translateY(0px)';\n"
        "                }, 1800);\n"
        "            } catch (_) {}\n"
        "        }\n\n"
        "        function __buildPlanConfirmMessage(targetPlan) {\n"
        "            const t = String(targetPlan || '').toLowerCase();\n"
        "            const title = (t === 'pro') ? __WEB_SUB_COPY.upgradeToPro : __WEB_SUB_COPY.switchToBasic;\n"
        "            const parts = [title, ''];\n"
        "            parts.push('Basic');\n"
        "            for (const b of (__WEB_SUB_COPY.basicBullets || [])) parts.push('- ' + b);\n"
        "            parts.push('');\n"
        "            parts.push('Pro');\n"
        "            for (const b of (__WEB_SUB_COPY.proBullets || [])) parts.push('- ' + b);\n"
        "            return parts.join('\\n');\n"
        "        }\n\n"
        "        async function confirmAndChangePlan(plan) {\n"
        "            const msg = __buildPlanConfirmMessage(plan);\n"
        "            const ok = confirm(msg);\n"
        "            if (!ok) return;\n"
        "            return changePlan(String(plan || '').toLowerCase());\n"
        "        }\n\n"
        "        const btnPro = document.getElementById(\"btn-change-pro\");\n"
        "        if (btnPro) btnPro.addEventListener(\"click\", () => confirmAndChangePlan(\"pro\"));\n"
        "        const btnBasic = document.getElementById(\"btn-change-basic\");\n"
        "        if (btnBasic) btnBasic.addEventListener(\"click\", () => confirmAndChangePlan(\"basic\"));\n\n"
        "        function __syncManageButtonUI() {\n"
        "            try {\n"
        "                const manageBtn = document.getElementById('btn-manage-subscription');\n"
        "                if (!manageBtn) return;\n"
        "                const g = String(window.__currentGrade || 'free').toLowerCase();\n"
        "                if (g === 'free') {\n"
        "                    manageBtn.classList.remove('btn-cancel');\n"
        "                    manageBtn.classList.add('btn-upgrade');\n"
        "                    manageBtn.innerHTML = `<i class='bx bx-crown'></i> ${__WEB_SUB_COPY.subscribePro}`;\n"
        "                } else {\n"
        "                    manageBtn.classList.remove('btn-upgrade');\n"
        "                    manageBtn.classList.add('btn-cancel');\n"
        "                }\n"
        "            } catch (_) {}\n"
        "        }\n\n"
        "        __syncManageButtonUI();\n\n"
    )

    if RE_MYINFO_WEB_SECTION.search(myinfo_html):
        new_html = RE_MYINFO_WEB_SECTION.sub(lambda _m: injected, myinfo_html, count=1)
    else:
        # If injection section not found, do nothing (unexpected file shape).
        return myinfo_html, False

    # Localize firebase auth error messages using __WEB_SUB_COPY.
    firebase_err_fn = (
        "        function firebaseErrorMsg(code) {\n"
        "            const map = {\n"
        "                'auth/email-already-in-use': __WEB_SUB_COPY.authEmailAlreadyInUse,\n"
        "                'auth/invalid-email': __WEB_SUB_COPY.authInvalidEmail,\n"
        "                'auth/weak-password': __WEB_SUB_COPY.authWeakPassword,\n"
        "                'auth/user-not-found': __WEB_SUB_COPY.authUserNotFound,\n"
        "                'auth/wrong-password': __WEB_SUB_COPY.authWrongPassword,\n"
        "                'auth/invalid-credential': __WEB_SUB_COPY.authInvalidCredential,\n"
        "                'auth/too-many-requests': __WEB_SUB_COPY.authTooManyRequests,\n"
        "                'auth/network-request-failed': __WEB_SUB_COPY.authNetworkRequestFailed,\n"
        "            };\n"
        "            const c = String(code || '');\n"
        "            if (map[c]) return map[c];\n"
        "            const tpl = __WEB_SUB_COPY.authGenericWithCode || 'An error occurred. Please try again ({code}).';\n"
        "            return tpl.replace('{code}', c);\n"
        "        }\n"
    )
    new_html = RE_MYINFO_FIREBASE_ERROR_SECTION.sub(lambda _m: firebase_err_fn + "\n        ", new_html, count=1)

    # Clean duplicate window.__currentGrade injections if present (from previous patches)
    new_html = re.sub(
        r"(window\.__currentGrade\s*=\s*String\(grade\s*\|\|\s*'free'\)\.toLowerCase\(\);\s*[\r\n]+(?:\s*if\s*\(typeof __syncManageButtonUI === 'function'\) __syncManageButtonUI\(\);\s*[\r\n]+)?)\1+",
        r"\1",
        new_html,
        flags=re.IGNORECASE,
    )

    # Ensure manage button click: Free -> go price/, else openBillingPortal()
    new_html = re.sub(
        r'const\s+manageBtn\s*=\s*document\.getElementById\("btn-manage-subscription"\)\s*;\s*[\s\S]*?if\s*\(manageBtn\)\s*manageBtn\.addEventListener\("click",\s*openBillingPortal\)\s*;\s*',
        (
            '        const manageBtn = document.getElementById("btn-manage-subscription");\n'
            '        async function __handleManageSubscriptionClick() {\n'
            "            try {\n"
            "                const g = String(window.__currentGrade || 'free').toLowerCase();\n"
            "                if (g === 'free') {\n"
            "                    window.location.href = 'price/';\n"
            "                    return;\n"
            "                }\n"
            "            } catch (_) {}\n"
            "            return openBillingPortal();\n"
            "        }\n"
            '        if (manageBtn) manageBtn.addEventListener("click", __handleManageSubscriptionClick);\n\n'
        ),
        new_html,
        count=1,
        flags=re.IGNORECASE,
    )

    return new_html, True


def iter_locales(site_root: Path) -> list[str]:
    out: list[str] = []
    for p in site_root.iterdir():
        if not p.is_dir():
            continue
        name = p.name.strip().lower()
        if not RE_LOCALE_DIR.fullmatch(name):
            continue
        if (p / "price" / "index.html").exists() and (p / "myinfo" / "index.html").exists():
            out.append(name)
    out.sort()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Make web subscription copy consistent per locale (no app ARB).")
    ap.add_argument("--site-root", type=Path, default=Path("."), help="NotiSite3 root.")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-runtime-translate", action="store_true", help="Do not call translation API for runtime messages.")
    args = ap.parse_args(argv)

    root = args.site_root.resolve()
    locales = iter_locales(root)
    changed = 0
    skipped = 0

    cache_path = root / ".web_runtime_i18n_cache.json"
    cache = _load_json(cache_path)
    client = OpenAI() if (OpenAI is not None and not args.no_runtime_translate and os.environ.get("OPENAI_API_KEY")) else None

    for loc in locales:
        price_path = root / loc / "price" / "index.html"
        myinfo_path = root / loc / "myinfo" / "index.html"

        price_html = price_path.read_text(encoding="utf-8")
        myinfo_html = myinfo_path.read_text(encoding="utf-8")
        copy0 = build_locale_copy(loc, price_html=price_html, myinfo_html=myinfo_html)

        runtime_i18n = dict(RUNTIME_EN)
        cached = cache.get(loc)
        has_full_cache = isinstance(cached, dict) and all(isinstance(cached.get(k), str) for k in RUNTIME_EN.keys())
        if has_full_cache:
            runtime_i18n = {k: str(cached[k]) for k in RUNTIME_EN.keys()}
        elif client is not None:
            runtime_i18n = translate_runtime_strings(client=client, locale=loc, phrases=RUNTIME_EN)
            cache[loc] = runtime_i18n
            _save_json(cache_path, cache)

        copy = LocaleCopy(**{**copy0.__dict__, "runtime_i18n": runtime_i18n})

        new_price, did_price = patch_price_page(price_html, copy)
        new_myinfo, did_myinfo = patch_myinfo_page(myinfo_html, copy)

        did_any = did_price or did_myinfo
        if not did_any:
            skipped += 1
            continue

        changed += 1
        if args.dry_run:
            print(f"[dry-run] would patch locale: {loc}")
            continue

        if did_price:
            price_path.write_text(new_price, encoding="utf-8")
        if did_myinfo:
            myinfo_path.write_text(new_myinfo, encoding="utf-8")

    print(f"Done. Locales patched: {changed} | Skipped: {skipped} | Total locales: {len(locales)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

