#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
from pathlib import Path

try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore


RE_LOCALE_DIR = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")
BASE_DOMAIN = "https://noticatcher.com"
APP_NAME = "NotiCatcher"
OG_IMAGE_URL = f"{BASE_DOMAIN}/img/main1.jpg"
ANDROID_APP_URL = "https://play.google.com/store/apps/details?id=com.flutterflow.noticatcher"
ORGANIZATION_ID = f"{BASE_DOMAIN}/#organization"
WEBSITE_ID = f"{BASE_DOMAIN}/#website"
NOINDEX_FOLLOW_META = '<meta content="noindex,follow" name="robots"/>'
LOCALE_HOMEPAGE_RE = re.compile(r"^[^/\\]+/index\.html$")
STRUCTURED_DATA_START = "<!-- noticatcher-structured-data:start -->"
STRUCTURED_DATA_END = "<!-- noticatcher-structured-data:end -->"
STRUCTURED_DATA_BLOCK_RE = re.compile(
    rf"\s*{re.escape(STRUCTURED_DATA_START)}.*?{re.escape(STRUCTURED_DATA_END)}\s*",
    flags=re.DOTALL,
)
FAQ_ITEM_RE = re.compile(
    r'<button class="faq-question"[^>]*>\s*(.*?)\s*<i\b[^>]*></i>\s*</button>\s*<div class="faq-answer">\s*<p>(.*?)</p>',
    flags=re.IGNORECASE | re.DOTALL,
)

FAQ_SOURCE_EN = (
    "These include crypto exchanges (Binance, Bybit, Coinbase, etc.), trading platforms "
    "(TradingView, Robinhood, etc.), wallet apps (MetaMask, Trust Wallet, etc.), and Telegram. "
    "You can view the full list on the {PRICING_LINK}."
)

EXTRA_ITEMS_EN = {
    "autoLoginTokenMissing": "Auto-login token is missing. Please try again from the app.",
    "autoLoginFailed": "Auto-login failed. Please try again.",
    "signingIn": "Signing in...",
    "creatingAccount": "Creating account...",
    "sending": "Sending...",
    "passwordsDoNotMatch": "Passwords do not match.",
    "passwordResetSent": "Password reset link sent! Check your inbox.",
    "googleSignInFailed": "Google sign-in failed. Please try again.",
    "noDataAvailable": "No data available",
    "noKeywordDataForThisPeriod": "No keyword data for this period",
    "cancelingSuffix": "Canceling",
    "changingSuffix": "Changing",
    "cancellationScheduled": "Cancellation Scheduled",
    "cancelConfirmTitle": "Cancel Subscription?",
    "cancelConfirmBody": "Your subscription will remain active until {date}. After that, it will not renew.",
    "cancelConfirmBodyNoDate": "Your subscription will remain active until the end of the current billing period. After that, it will not renew.",
    "toastCancelScheduled": "Subscription cancellation scheduled.",
    "toastAlreadyCanceled": "Cancellation is already scheduled.",
    "errCancelFailed": "Failed to cancel subscription.",
    "faqRestrictedAppsAnswer": FAQ_SOURCE_EN,
}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def arb_to_folder_locale(arb_locale: str) -> str:
    s = (arb_locale or "").strip()
    if not s:
        return ""
    return s.replace("_", "-").lower()


def load_arb_map(arb_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(arb_dir.glob("app_*.arb")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        raw = str(data.get("@@locale") or p.stem[len("app_") :])
        loc = arb_to_folder_locale(raw)
        if loc:
            out[loc] = data
    return out


def discover_locales(site_root: Path) -> list[str]:
    out: list[str] = []
    for p in site_root.iterdir():
        if not p.is_dir():
            continue
        name = p.name.strip().lower()
        if not RE_LOCALE_DIR.fullmatch(name):
            continue
        if (p / "index.html").exists():
            out.append(name)
    out.sort()
    return out


def ensure_ascii_ellipsis(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return "..."
    text = re.sub(r"(?:\s*(?:\.{3}|…))+?$", "", text).strip()
    return text + "..."


def cleanup_failed_with_code(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    text = text.replace("{code}", "").replace("({code})", "")
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    return text


def json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def translate_extra_items(*, client: "OpenAI | None", locale: str, cache: dict) -> dict[str, str]:
    if locale == "en":
        return dict(EXTRA_ITEMS_EN)

    cached = cache.get(locale)
    if isinstance(cached, dict) and all(isinstance(cached.get(k), str) for k in EXTRA_ITEMS_EN):
        return {k: str(cached[k]) for k in EXTRA_ITEMS_EN}

    if client is None:
        return dict(EXTRA_ITEMS_EN)

    system = (
        "You translate concise website UI copy and one FAQ answer for a multilingual static site.\n"
        "Return ONLY valid JSON with the exact same keys.\n"
        "Keep placeholders exactly as written, including {date} and {PRICING_LINK}.\n"
        "Keep these product/brand names unchanged: NotiCatcher, Basic, Pro, Binance, Bybit, Coinbase, TradingView, Robinhood, MetaMask, Trust Wallet, Telegram, Google.\n"
        "Use natural wording for websites and account pages.\n"
    )
    user = {
        "target_locale": locale,
        "items": [{"key": key, "text": value} for key, value in EXTRA_ITEMS_EN.items()],
    }

    last_err: Exception | None = None
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(
                model="gpt-5.2",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or ""
            data = json.loads(content)
            out: dict[str, str] = {}
            if isinstance(data.get("items"), list):
                for item in data.get("items", []):
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("key") or "")
                    value = item.get("translation") or item.get("text")
                    if key in EXTRA_ITEMS_EN and isinstance(value, str) and value.strip():
                        out[key] = value.strip()
            elif isinstance(data.get("items"), dict):
                for key, value in data.get("items", {}).items():
                    if key in EXTRA_ITEMS_EN and isinstance(value, str) and value.strip():
                        out[key] = value.strip()
            elif isinstance(data.get("translations"), dict):
                for key, value in data.get("translations", {}).items():
                    if key in EXTRA_ITEMS_EN and isinstance(value, str) and value.strip():
                        out[key] = value.strip()
            else:
                for key, value in data.items():
                    if key in EXTRA_ITEMS_EN and isinstance(value, str) and value.strip():
                        out[key] = value.strip()

            for key, default in EXTRA_ITEMS_EN.items():
                out.setdefault(key, default)

            if locale != "en" and all(out[key] == EXTRA_ITEMS_EN[key] for key in EXTRA_ITEMS_EN):
                raise RuntimeError("Translation response did not contain localized values.")

            cache[locale] = out
            return out
        except Exception as exc:
            last_err = exc
            time.sleep(min(8.0, 2.0**attempt))
    raise RuntimeError(f"Failed to translate extra items for {locale}: {last_err}")


def build_extra_copy(locale: str, *, arb: dict, translated: dict[str, str]) -> dict[str, str]:
    extra = dict(translated)

    sign_in_label = str(arb.get("authSubmitSignIn") or arb.get("authSignIn") or "").strip()
    if sign_in_label:
        extra["signingIn"] = ensure_ascii_ellipsis(sign_in_label)

    sign_up_label = str(arb.get("authSubmitSignUp") or arb.get("authSignUp") or "").strip()
    if sign_up_label:
        extra["creatingAccount"] = ensure_ascii_ellipsis(sign_up_label)

    password_reset_sent = str(arb.get("authPasswordResetSent") or "").strip()
    if password_reset_sent:
        extra["passwordResetSent"] = password_reset_sent

    google_failed = cleanup_failed_with_code(str(arb.get("authGoogleFailedWithCode") or ""))
    if google_failed:
        extra["googleSignInFailed"] = google_failed

    if not extra.get("errCancelFailed"):
        extra["errCancelFailed"] = str(arb.get("authRequestFailed") or EXTRA_ITEMS_EN["errCancelFailed"])

    return extra


def patch_faq_html(html_text: str, locale: str, extra: dict[str, str]) -> tuple[str, bool]:
    pattern = re.compile(
        r"<p>These include crypto exchanges \(Binance, Bybit, Coinbase, etc\.\), trading platforms "
        r"\(TradingView, Robinhood, etc\.\), wallet apps \(MetaMask, Trust Wallet, etc\.\), and Telegram\. "
        r"You can view the full list on the (?P<link><a href=\"/"
        + re.escape(locale)
        + r"/price/\" style=\"color: var\(--primary\);\">.*?</a>)\.</p>"
    )
    match = pattern.search(html_text)
    if not match:
        return html_text, False

    translated = extra["faqRestrictedAppsAnswer"].replace("{PRICING_LINK}", "___PRICING_LINK___")
    translated = html.escape(translated, quote=False).replace("___PRICING_LINK___", match.group("link"))
    new_paragraph = f"<p>{translated}</p>"
    return html_text[: match.start()] + new_paragraph + html_text[match.end() :], True


def patch_myinfo_html(html_text: str, extra: dict[str, str]) -> tuple[str, bool]:
    original = html_text

    replacements = {
        'showMsg("Auto-login token is missing. Please try again from the app.", "error");': (
            f"showMsg({json_string(extra['autoLoginTokenMissing'])}, \"error\");"
        ),
        'showMsg("Auto-login failed. Please try again." + detail, "error");': (
            f"showMsg({json_string(extra['autoLoginFailed'])} + detail, \"error\");"
        ),
        "showMsg('Google sign-in failed. Please try again.', 'error');": (
            f"showMsg({json_string(extra['googleSignInFailed'])}, 'error');"
        ),
        'showMsg("Google sign-in failed. Please try again.", \'error\');': (
            f"showMsg({json_string(extra['googleSignInFailed'])}, 'error');"
        ),
        'btn.innerHTML = \'<i class="bx bx-loader-alt bx-spin"></i> Signing In...\';': (
            "btn.innerHTML = '<i class=\"bx bx-loader-alt bx-spin\"></i> ' + "
            f"{json_string(extra['signingIn'])};"
        ),
        'btn.innerHTML = \'<i class="bx bx-loader-alt bx-spin"></i> \' + "Signing in...";': (
            "btn.innerHTML = '<i class=\"bx bx-loader-alt bx-spin\"></i> ' + "
            f"{json_string(extra['signingIn'])};"
        ),
        "showMsg('Passwords do not match.', 'error');": (
            f"showMsg({json_string(extra['passwordsDoNotMatch'])}, 'error');"
        ),
        'showMsg("Passwords do not match.", \'error\');': (
            f"showMsg({json_string(extra['passwordsDoNotMatch'])}, 'error');"
        ),
        'btn.innerHTML = \'<i class="bx bx-loader-alt bx-spin"></i> Creating Account...\';': (
            "btn.innerHTML = '<i class=\"bx bx-loader-alt bx-spin\"></i> ' + "
            f"{json_string(extra['creatingAccount'])};"
        ),
        'btn.innerHTML = \'<i class="bx bx-loader-alt bx-spin"></i> \' + "Creating account...";': (
            "btn.innerHTML = '<i class=\"bx bx-loader-alt bx-spin\"></i> ' + "
            f"{json_string(extra['creatingAccount'])};"
        ),
        'btn.innerHTML = \'<i class="bx bx-loader-alt bx-spin"></i> Sending...\';': (
            "btn.innerHTML = '<i class=\"bx bx-loader-alt bx-spin\"></i> ' + "
            f"{json_string(extra['sending'])};"
        ),
        'btn.innerHTML = \'<i class="bx bx-loader-alt bx-spin"></i> \' + "Sending...";': (
            "btn.innerHTML = '<i class=\"bx bx-loader-alt bx-spin\"></i> ' + "
            f"{json_string(extra['sending'])};"
        ),
        "showMsg('Password reset link sent! Check your inbox.', 'success');": (
            f"showMsg({json_string(extra['passwordResetSent'])}, 'success');"
        ),
        'showMsg("Password reset link sent! Check your inbox.", \'success\');': (
            f"showMsg({json_string(extra['passwordResetSent'])}, 'success');"
        ),
        'listEl.innerHTML = `<div class="keyword-empty"><i class=\'bx bx-info-circle\'></i>No data available</div>`;': (
            'listEl.innerHTML = "<div class=\\"keyword-empty\\"><i class=\'bx bx-info-circle\'></i>" + '
            f"{json_string(extra['noDataAvailable'])} + \"</div>\";"
        ),
        'listEl.innerHTML = "<div class=\\"keyword-empty\\"><i class=\'bx bx-info-circle\'></i>" + "No data available" + "</div>";': (
            'listEl.innerHTML = "<div class=\\"keyword-empty\\"><i class=\'bx bx-info-circle\'></i>" + '
            f"{json_string(extra['noDataAvailable'])} + \"</div>\";"
        ),
        'listEl.innerHTML = `<div class="keyword-empty"><i class=\'bx bx-info-circle\'></i>No keyword data for this period</div>`;': (
            'listEl.innerHTML = "<div class=\\"keyword-empty\\"><i class=\'bx bx-info-circle\'></i>" + '
            f"{json_string(extra['noKeywordDataForThisPeriod'])} + \"</div>\";"
        ),
        'listEl.innerHTML = "<div class=\\"keyword-empty\\"><i class=\'bx bx-info-circle\'></i>" + "No keyword data for this period" + "</div>";': (
            'listEl.innerHTML = "<div class=\\"keyword-empty\\"><i class=\'bx bx-info-circle\'></i>" + '
            f"{json_string(extra['noKeywordDataForThisPeriod'])} + \"</div>\";"
        ),
        'if (isCanceled) tierEl.textContent = tierEl.textContent + " (Canceling)";': (
            'if (isCanceled) tierEl.textContent = tierEl.textContent + " (" + '
            f"{json_string(extra['cancelingSuffix'])} + \")\";"
        ),
        'tierEl.textContent = tierEl.textContent + " (Changing)";': (
            'tierEl.textContent = tierEl.textContent + " (" + '
            f"{json_string(extra['changingSuffix'])} + \")\";"
        ),
    }

    for old, new in replacements.items():
        html_text = html_text.replace(old, new)

    button_text_block = (
        "            return {\n"
        "                upgrade: readText('btn-upgrade-subscription'),\n"
        "                cancel: readText('btn-cancel-subscription'),\n"
        "            };\n"
    )
    button_text_block_new = (
        "            return {\n"
        "                upgrade: readText('btn-upgrade-subscription'),\n"
        "                change: readText('btn-change-subscription'),\n"
        "                cancel: readText('btn-cancel-subscription'),\n"
        "            };\n"
    )
    html_text = html_text.replace(button_text_block, button_text_block_new)

    current_fallback_block = (
        "        __WEB_SUB_COPY.upgradeSubscription = __WEB_SUB_COPY.upgradeSubscription || __WEB_SUB_COPY.upgradeToPro || __WEB_SUB_BUTTON_TEXT.upgrade || 'Upgrade Subscription';\n"
        "        __WEB_SUB_COPY.changeSubscription = __WEB_SUB_COPY.changeSubscription || __WEB_SUB_COPY.manage || 'Change Subscription';\n"
        "        __WEB_SUB_COPY.cancelSubscription = __WEB_SUB_COPY.cancelSubscription || __WEB_SUB_BUTTON_TEXT.cancel || 'Cancel Subscription';\n"
        "        __WEB_SUB_COPY.cancellationScheduled = __WEB_SUB_COPY.cancellationScheduled || 'Cancellation Scheduled';\n"
        "        __WEB_SUB_COPY.cancelConfirmTitle = __WEB_SUB_COPY.cancelConfirmTitle || __WEB_SUB_COPY.cancelSubscription || 'Cancel Subscription?';\n"
        "        __WEB_SUB_COPY.cancelConfirmBody = __WEB_SUB_COPY.cancelConfirmBody || 'Your subscription will remain active until {date}. After that, it will not renew.';\n"
        "        __WEB_SUB_COPY.cancelConfirmBodyNoDate = __WEB_SUB_COPY.cancelConfirmBodyNoDate || 'Your subscription will remain active until the end of the current billing period. After that, it will not renew.';\n"
        "        __WEB_SUB_COPY.toastCancelScheduled = __WEB_SUB_COPY.toastCancelScheduled || 'Subscription cancellation scheduled.';\n"
        "        __WEB_SUB_COPY.toastAlreadyCanceled = __WEB_SUB_COPY.toastAlreadyCanceled || 'Cancellation is already scheduled.';\n"
        "        __WEB_SUB_COPY.errCancelFailed = __WEB_SUB_COPY.errCancelFailed || __WEB_SUB_COPY.errRequestFailed || 'Failed to cancel subscription.';\n"
    )
    new_fallback_block = (
        "        __WEB_SUB_COPY.upgradeSubscription = __WEB_SUB_COPY.upgradeSubscription || __WEB_SUB_BUTTON_TEXT.upgrade || __WEB_SUB_COPY.upgradeToPro || 'Upgrade Subscription';\n"
        "        __WEB_SUB_COPY.changeSubscription = __WEB_SUB_COPY.changeSubscription || __WEB_SUB_BUTTON_TEXT.change || __WEB_SUB_COPY.manage || 'Change Subscription';\n"
        "        __WEB_SUB_COPY.cancelSubscription = __WEB_SUB_COPY.cancelSubscription || __WEB_SUB_BUTTON_TEXT.cancel || 'Cancel Subscription';\n"
        f"        __WEB_SUB_COPY.cancellationScheduled = __WEB_SUB_COPY.cancellationScheduled || {json_string(extra['cancellationScheduled'])};\n"
        f"        __WEB_SUB_COPY.cancelConfirmTitle = __WEB_SUB_COPY.cancelConfirmTitle || {json_string(extra['cancelConfirmTitle'])};\n"
        f"        __WEB_SUB_COPY.cancelConfirmBody = __WEB_SUB_COPY.cancelConfirmBody || {json_string(extra['cancelConfirmBody'])};\n"
        f"        __WEB_SUB_COPY.cancelConfirmBodyNoDate = __WEB_SUB_COPY.cancelConfirmBodyNoDate || {json_string(extra['cancelConfirmBodyNoDate'])};\n"
        f"        __WEB_SUB_COPY.toastCancelScheduled = __WEB_SUB_COPY.toastCancelScheduled || {json_string(extra['toastCancelScheduled'])};\n"
        f"        __WEB_SUB_COPY.toastAlreadyCanceled = __WEB_SUB_COPY.toastAlreadyCanceled || {json_string(extra['toastAlreadyCanceled'])};\n"
        f"        __WEB_SUB_COPY.errCancelFailed = __WEB_SUB_COPY.errCancelFailed || __WEB_SUB_COPY.errRequestFailed || {json_string(extra['errCancelFailed'])} || 'Failed to cancel subscription.';\n"
    )
    html_text = html_text.replace(current_fallback_block, new_fallback_block)

    line_replacements = [
        (
            r"__WEB_SUB_COPY\.upgradeSubscription\s*=\s*__WEB_SUB_COPY\.upgradeSubscription\s*\|\|[^;]+;",
            "        __WEB_SUB_COPY.upgradeSubscription = __WEB_SUB_COPY.upgradeSubscription || __WEB_SUB_BUTTON_TEXT.upgrade || __WEB_SUB_COPY.upgradeToPro || 'Upgrade Subscription';",
        ),
        (
            r"__WEB_SUB_COPY\.changeSubscription\s*=\s*__WEB_SUB_COPY\.changeSubscription\s*\|\|[^;]+;",
            "        __WEB_SUB_COPY.changeSubscription = __WEB_SUB_COPY.changeSubscription || __WEB_SUB_BUTTON_TEXT.change || __WEB_SUB_COPY.manage || 'Change Subscription';",
        ),
        (
            r"__WEB_SUB_COPY\.cancelSubscription\s*=\s*__WEB_SUB_COPY\.cancelSubscription\s*\|\|[^;]+;",
            "        __WEB_SUB_COPY.cancelSubscription = __WEB_SUB_COPY.cancelSubscription || __WEB_SUB_BUTTON_TEXT.cancel || 'Cancel Subscription';",
        ),
        (
            r"__WEB_SUB_COPY\.cancellationScheduled\s*=\s*__WEB_SUB_COPY\.cancellationScheduled\s*\|\|[^;]+;",
            f"        __WEB_SUB_COPY.cancellationScheduled = __WEB_SUB_COPY.cancellationScheduled || {json_string(extra['cancellationScheduled'])};",
        ),
        (
            r"__WEB_SUB_COPY\.cancelConfirmTitle\s*=\s*__WEB_SUB_COPY\.cancelConfirmTitle\s*\|\|[^;]+;",
            f"        __WEB_SUB_COPY.cancelConfirmTitle = __WEB_SUB_COPY.cancelConfirmTitle || {json_string(extra['cancelConfirmTitle'])};",
        ),
        (
            r"__WEB_SUB_COPY\.cancelConfirmBody\s*=\s*__WEB_SUB_COPY\.cancelConfirmBody\s*\|\|[^;]+;",
            f"        __WEB_SUB_COPY.cancelConfirmBody = __WEB_SUB_COPY.cancelConfirmBody || {json_string(extra['cancelConfirmBody'])};",
        ),
        (
            r"__WEB_SUB_COPY\.cancelConfirmBodyNoDate\s*=\s*__WEB_SUB_COPY\.cancelConfirmBodyNoDate\s*\|\|[^;]+;",
            f"        __WEB_SUB_COPY.cancelConfirmBodyNoDate = __WEB_SUB_COPY.cancelConfirmBodyNoDate || {json_string(extra['cancelConfirmBodyNoDate'])};",
        ),
        (
            r"__WEB_SUB_COPY\.toastCancelScheduled\s*=\s*__WEB_SUB_COPY\.toastCancelScheduled\s*\|\|[^;]+;",
            f"        __WEB_SUB_COPY.toastCancelScheduled = __WEB_SUB_COPY.toastCancelScheduled || {json_string(extra['toastCancelScheduled'])};",
        ),
        (
            r"__WEB_SUB_COPY\.toastAlreadyCanceled\s*=\s*__WEB_SUB_COPY\.toastAlreadyCanceled\s*\|\|[^;]+;",
            f"        __WEB_SUB_COPY.toastAlreadyCanceled = __WEB_SUB_COPY.toastAlreadyCanceled || {json_string(extra['toastAlreadyCanceled'])};",
        ),
        (
            r"__WEB_SUB_COPY\.errCancelFailed\s*=\s*__WEB_SUB_COPY\.errCancelFailed\s*\|\|[^;]+;",
            f"        __WEB_SUB_COPY.errCancelFailed = __WEB_SUB_COPY.errCancelFailed || __WEB_SUB_COPY.errRequestFailed || {json_string(extra['errCancelFailed'])};",
        ),
    ]
    for pattern, replacement in line_replacements:
        html_text = re.sub(pattern, replacement, html_text, count=1)

    return html_text, html_text != original


def extract_title(html_text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_description(html_text: str) -> str:
    patterns = [
        r'<meta[^>]*name="description"[^>]*content="([^"]*)"',
        r'<meta[^>]*content="([^"]*)"[^>]*name="description"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def extract_canonical(html_text: str) -> str:
    patterns = [
        r'<link[^>]*rel="canonical"[^>]*href="([^"]*)"',
        r'<link[^>]*href="([^"]*)"[^>]*rel="canonical"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def insert_before_head_close(html_text: str, snippet: str) -> str:
    return re.sub(r"</head>", snippet + "\n</head>", html_text, count=1, flags=re.IGNORECASE)


def normalize_x_default_homepage(html_text: str) -> str:
    pattern = re.compile(
        rf'(<link\b(?=[^>]*\bhreflang=["\']x-default["\'])[^>]*\bhref=["\']){re.escape(BASE_DOMAIN)}/(["\'][^>]*>)',
        flags=re.IGNORECASE,
    )
    return pattern.sub(rf"\1{BASE_DOMAIN}/en/\2", html_text, count=1)


def extract_html_lang(html_text: str) -> str:
    match = re.search(r'<html[^>]*\blang="([^"]+)"', html_text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else "en"


def strip_html_fragment(fragment: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", fragment, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def structured_page_context(normalized_rel_path: str) -> tuple[str, str] | None:
    parts = normalized_rel_path.split("/")
    if len(parts) < 2:
        return None

    locale = (parts[0] or "").strip().lower()
    if not RE_LOCALE_DIR.fullmatch(locale):
        return None

    if len(parts) == 2 and parts[1] == "index.html":
        return locale, "home"

    if len(parts) == 3 and parts[2] == "index.html" and parts[1] in {"download", "faq", "price"}:
        return locale, parts[1]

    return None


def extract_faq_entities(html_text: str) -> list[dict]:
    entities: list[dict] = []
    for question_html, answer_html in FAQ_ITEM_RE.findall(html_text):
        question = strip_html_fragment(question_html)
        answer = strip_html_fragment(answer_html)
        if not question or not answer:
            continue
        entities.append(
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": answer,
                },
            }
        )
    return entities


def build_breadcrumb_schema(locale: str, title: str, canonical: str) -> dict:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": APP_NAME,
                "item": f"{BASE_DOMAIN}/{locale}/",
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": title,
                "item": canonical,
            },
        ],
    }


def build_structured_data_graph(html_text: str, normalized_rel_path: str, title: str, description: str, canonical: str) -> list[dict] | None:
    page_context = structured_page_context(normalized_rel_path)
    if not page_context:
        return None

    locale, page_kind = page_context
    lang = extract_html_lang(html_text) or locale

    organization = {
        "@type": "Organization",
        "@id": ORGANIZATION_ID,
        "name": APP_NAME,
        "url": BASE_DOMAIN,
        "logo": f"{BASE_DOMAIN}/img/appicon.png",
        "image": OG_IMAGE_URL,
    }
    website = {
        "@type": "WebSite",
        "@id": WEBSITE_ID,
        "url": BASE_DOMAIN,
        "name": APP_NAME,
        "publisher": {"@id": ORGANIZATION_ID},
    }

    graph: list[dict] = [organization, website]

    if page_kind == "faq":
        faq_entities = extract_faq_entities(html_text)
        if faq_entities:
            graph.append(
                {
                    "@type": "FAQPage",
                    "@id": f"{canonical}#faq",
                    "url": canonical,
                    "name": title,
                    "description": description,
                    "inLanguage": lang,
                    "isPartOf": {"@id": WEBSITE_ID},
                    "mainEntity": faq_entities,
                }
            )
        else:
            graph.append(
                {
                    "@type": "WebPage",
                    "@id": f"{canonical}#webpage",
                    "url": canonical,
                    "name": title,
                    "description": description,
                    "inLanguage": lang,
                    "isPartOf": {"@id": WEBSITE_ID},
                }
            )
        graph.append(build_breadcrumb_schema(locale, title, canonical))
        return graph

    app_schema = {
        "@type": "SoftwareApplication",
        "@id": f"{canonical}#app",
        "name": APP_NAME,
        "applicationCategory": "UtilitiesApplication",
        "operatingSystem": "Android",
        "url": canonical,
        "downloadUrl": ANDROID_APP_URL,
        "image": OG_IMAGE_URL,
        "description": description,
        "publisher": {"@id": ORGANIZATION_ID},
    }

    if page_kind == "price":
        app_schema["offers"] = [
            {
                "@type": "Offer",
                "name": "Free",
                "price": "0.00",
                "priceCurrency": "USD",
                "availability": "https://schema.org/InStock",
                "url": canonical,
            },
            {
                "@type": "Offer",
                "name": "Basic",
                "price": "2.99",
                "priceCurrency": "USD",
                "availability": "https://schema.org/InStock",
                "url": canonical,
            },
            {
                "@type": "Offer",
                "name": "Pro",
                "price": "6.99",
                "priceCurrency": "USD",
                "availability": "https://schema.org/InStock",
                "url": canonical,
            },
        ]

    graph.append(app_schema)
    graph.append(
        {
            "@type": "WebPage",
            "@id": f"{canonical}#webpage",
            "url": canonical,
            "name": title,
            "description": description,
            "inLanguage": lang,
            "isPartOf": {"@id": WEBSITE_ID},
            "about": {"@id": app_schema["@id"]},
        }
    )

    if page_kind != "home":
        graph.append(build_breadcrumb_schema(locale, title, canonical))

    return graph


def render_structured_data_block(graph: list[dict]) -> str:
    payload = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2)
    return (
        f"{STRUCTURED_DATA_START}\n"
        f"<script type=\"application/ld+json\">{payload}</script>\n"
        f"{STRUCTURED_DATA_END}"
    )


def upsert_structured_data(html_text: str, normalized_rel_path: str, title: str, description: str, canonical: str) -> str:
    html_text = STRUCTURED_DATA_BLOCK_RE.sub("", html_text)
    graph = build_structured_data_graph(
        html_text=html_text,
        normalized_rel_path=normalized_rel_path,
        title=title,
        description=description,
        canonical=canonical,
    )
    if not graph:
        return html_text
    return insert_before_head_close(html_text, render_structured_data_block(graph))


def ensure_meta_tag(html_text: str, rel_path: str) -> tuple[str, bool]:
    original = html_text
    normalized_rel_path = rel_path.replace("\\", "/")
    html_text = html_text.replace("</meta></head>", "</head>")

    font_match = re.search(r'<link\b[^>]*href="https://fonts\.googleapis\.com/css2[^"]*"[^>]*>', html_text, flags=re.IGNORECASE)
    if font_match:
        if "fonts.googleapis.com" not in html_text or 'rel="preconnect"' not in html_text:
            pass
        if "https://fonts.googleapis.com" not in html_text or "rel=\"preconnect\"" not in html_text:
            preconnects = (
                '<link href="https://fonts.googleapis.com" rel="preconnect"/>\n'
                '<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>\n'
            )
            if '<link href="https://fonts.googleapis.com" rel="preconnect"/>' not in html_text:
                insert = ""
                if '<link href="https://fonts.googleapis.com" rel="preconnect"/>' not in html_text:
                    insert += '<link href="https://fonts.googleapis.com" rel="preconnect"/>\n'
                if '<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>' not in html_text:
                    insert += '<link crossorigin="" href="https://fonts.gstatic.com" rel="preconnect"/>\n'
                html_text = html_text[: font_match.start()] + insert + html_text[font_match.start() :]

    if 'rel="icon"' not in html_text:
        html_text = insert_before_head_close(html_text, '<link href="/img/appicon.png" rel="icon" type="image/png"/>')

    title = extract_title(html_text)
    description = extract_description(html_text)
    canonical = extract_canonical(html_text)
    if not canonical:
        normalized = normalized_rel_path
        if normalized.endswith("/index.html"):
            normalized = normalized[: -len("index.html")]
        canonical = f"{BASE_DOMAIN}/{normalized.lstrip('/')}"

    if 'property="og:title"' not in html_text:
        og_block = (
            f'<meta content="{html.escape(title, quote=True)}" property="og:title"/>\n'
            f'<meta content="{html.escape(description, quote=True)}" property="og:description"/>\n'
            '<meta content="website" property="og:type"/>\n'
            f'<meta content="{html.escape(canonical, quote=True)}" property="og:url"/>\n'
            f'<meta content="{html.escape(OG_IMAGE_URL, quote=True)}" property="og:image"/>\n'
            '<meta content="NotiCatcher" property="og:site_name"/>\n'
            '<meta content="summary_large_image" name="twitter:card"/>\n'
            f'<meta content="{html.escape(title, quote=True)}" name="twitter:title"/>\n'
            f'<meta content="{html.escape(description, quote=True)}" name="twitter:description"/>\n'
            f'<meta content="{html.escape(OG_IMAGE_URL, quote=True)}" name="twitter:image"/>'
        )
        html_text = insert_before_head_close(html_text, og_block)

    html_text = upsert_structured_data(
        html_text=html_text,
        normalized_rel_path=normalized_rel_path,
        title=title,
        description=description,
        canonical=canonical,
    )

    if normalized_rel_path == "index.html" or LOCALE_HOMEPAGE_RE.fullmatch(normalized_rel_path):
        html_text = normalize_x_default_homepage(html_text)

    if (
        normalized_rel_path == "index.html"
        or normalized_rel_path.endswith("/myinfo/index.html")
    ) and 'name="robots"' not in html_text:
        html_text = insert_before_head_close(html_text, NOINDEX_FOLLOW_META)

    return html_text, html_text != original


def update_root_index(root_index_path: Path, locales: list[str]) -> bool:
    html_text = root_index_path.read_text(encoding="utf-8")
    supported = ["en"] + [loc for loc in locales if loc != "en"]
    replacement = "const SUPPORTED = [" + ", ".join(json.dumps(loc) for loc in supported) + "];"
    new_html, count = re.subn(r"const\s+SUPPORTED\s*=\s*\[[^\]]*\]\s*;", replacement, html_text, count=1, flags=re.DOTALL)
    if count == 0 or new_html == html_text:
        return False
    root_index_path.write_text(new_html, encoding="utf-8")
    return True


def generate_sitemap(site_root: Path, locales: list[str]) -> None:
    urls: list[str] = []
    page_suffixes = ["", "download/", "faq/", "price/"]
    ordered_locales = ["en"] + [loc for loc in locales if loc != "en"]
    for loc in ordered_locales:
        for suffix in page_suffixes:
            html_path = site_root / loc / suffix / "index.html"
            if html_path.exists():
                urls.append(f"{BASE_DOMAIN}/{loc}/" + suffix)

    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{url}</loc>")
        xml_lines.append("  </url>")
    xml_lines.append("</urlset>")
    (site_root / "sitemap.xml").write_text("\n".join(xml_lines) + "\n", encoding="utf-8")


def all_public_html_paths(site_root: Path, locales: list[str]) -> list[Path]:
    paths: list[Path] = [site_root / "index.html"]
    for loc in locales:
        paths.extend(
            [
                site_root / loc / "index.html",
                site_root / loc / "download" / "index.html",
                site_root / loc / "faq" / "index.html",
                site_root / loc / "price" / "index.html",
                site_root / loc / "myinfo" / "index.html",
            ]
        )
    return [p for p in paths if p.exists()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair locale copy leaks and apply site-wide SEO improvements.")
    parser.add_argument("--site-root", type=Path, default=Path("."))
    parser.add_argument(
        "--arb-dir",
        type=Path,
        default=Path(r"C:\Users\home\Desktop\DIV_ALARM\NotiCatcher\lib\l10n"),
    )
    args = parser.parse_args(argv)

    site_root = args.site_root.resolve()
    arb_dir = args.arb_dir.resolve()
    locales = discover_locales(site_root)
    arb_map = load_arb_map(arb_dir)
    cache_path = site_root / ".repair_locale_patch_cache.json"
    cache = _load_json(cache_path)
    client = OpenAI() if (OpenAI is not None and os.environ.get("OPENAI_API_KEY")) else None

    translated_cache_changed = False
    patched_myinfo = 0
    patched_faq = 0
    patched_head = 0

    for locale in locales:
        translated = translate_extra_items(client=client, locale=locale, cache=cache)
        extra = build_extra_copy(locale, arb=arb_map.get(locale) or {}, translated=translated)

        myinfo_path = site_root / locale / "myinfo" / "index.html"
        if myinfo_path.exists():
            html_text = myinfo_path.read_text(encoding="utf-8")
            new_html, changed = patch_myinfo_html(html_text, extra)
            if changed:
                myinfo_path.write_text(new_html, encoding="utf-8")
                patched_myinfo += 1

        faq_path = site_root / locale / "faq" / "index.html"
        if faq_path.exists():
            faq_html = faq_path.read_text(encoding="utf-8")
            new_faq, changed = patch_faq_html(faq_html, locale, extra)
            if changed:
                faq_path.write_text(new_faq, encoding="utf-8")
                patched_faq += 1

    if cache != _load_json(cache_path):
        translated_cache_changed = True
    if translated_cache_changed or not cache_path.exists():
        _save_json(cache_path, cache)

    for path in all_public_html_paths(site_root, locales):
        rel_path = str(path.relative_to(site_root))
        html_text = path.read_text(encoding="utf-8")
        new_html, changed = ensure_meta_tag(html_text, rel_path)
        if changed:
            path.write_text(new_html, encoding="utf-8")
            patched_head += 1

    root_changed = update_root_index(site_root / "index.html", locales)
    generate_sitemap(site_root, locales)

    print(
        f"Done. myinfo patched: {patched_myinfo}, faq patched: {patched_faq}, head/meta patched: {patched_head}, root updated: {root_changed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
