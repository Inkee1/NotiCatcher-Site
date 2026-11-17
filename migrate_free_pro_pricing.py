from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent

TRIAL_COPY = {
    "en": "Financial apps &amp; Telegram: first 3 catches free",
    "ko": "금융 앱·텔레그램: 최초 3회 무료 체험",
}

RESTRICTED_COPY = {
    "en": (
        'These apps are categorized as "Financial &amp; Telegram." Free users '
        "can try the first 3 keyword catches; Pro users have unlimited catches."
    ),
    "ko": (
        '다음 앱은 "금융 앱·텔레그램"로 분류됩니다. 무료 사용자는 최초 3회의 '
        "키워드 알람을 체험할 수 있고, Pro 사용자는 무제한으로 이용할 수 있습니다."
    ),
}

FAQ_COPY = {
    "en": (
        (
            "How do the 3 free catches work?",
            "Free users get three lifetime keyword-alarm catches from financial apps and Telegram. General apps remain unlimited. After the three catches are used, Pro is required for financial apps and Telegram.",
        ),
        (
            "What is the difference between monthly and annual Pro?",
            "Both options unlock the same unlimited financial-app and Telegram catches. Monthly Pro is $2.99 per month; Annual Pro is $19.99 per year.",
        ),
    ),
    "ko": (
        (
            "무료 알람 3회 체험은 어떻게 작동하나요?",
            "무료 사용자는 금융 앱과 텔레그램의 키워드 알람을 누적 3회 체험할 수 있습니다. 일반 앱은 계속 무제한이며, 3회를 모두 사용한 뒤 금융 앱과 텔레그램 알람을 받으려면 Pro가 필요합니다.",
        ),
        (
            "Pro 월간과 연간의 차이는 무엇인가요?",
            "기능은 동일하며 금융 앱과 텔레그램 알람을 무제한으로 이용할 수 있습니다. 월간은 월 $2.99, 연간은 연 $19.99입니다.",
        ),
    ),
}

GLOBAL_BROKER_NAMES = [
    "IBKR Mobile",
    "Schwab Mobile",
    "thinkorswim",
    "Fidelity Investments",
    "E*TRADE",
    "Trading 212",
    "XTB",
    "DEGIRO",
    "moomoo",
    "Zerodha Kite",
    "Upstox",
    "Groww",
    "Angel One",
    "MetaTrader 4",
    "MetaTrader 5",
    "cTrader",
    "OANDA",
]


def replace_pricing_cards(html: str, locale: str) -> str:
    pattern = re.compile(
        r"<!-- Pricing Cards -->.*?<!-- App Category Note -->",
        re.DOTALL,
    )
    match = pattern.search(html)
    if not match:
        raise RuntimeError("pricing card block not found")

    soup = BeautifulSoup(match.group(0), "html.parser")
    cards = soup.select("div.pricing-grid > div.price-card")
    if len(cards) < 3:
        raise RuntimeError("expected three legacy pricing cards")

    free_card, monthly_card, annual_card = cards[:3]
    monthly_feature = monthly_card.select_one("ul.card-features li")
    annual_features = annual_card.select("ul.card-features li")
    if monthly_feature is None or not annual_features:
        raise RuntimeError("legacy feature copy not found")

    current_label = free_card.select_one("button").get_text(" ", strip=True)
    monthly_label = monthly_card.select_one("button").get_text(" ", strip=True)
    annual_label = annual_card.select_one("button").get_text(" ", strip=True)
    recommended = annual_card.select_one(".card-badge")
    recommended_label = recommended.get_text(" ", strip=True) if recommended else "Best value"

    free_general = str(monthly_feature)
    pro_features = "\n".join(str(item) for item in annual_features)
    trial_copy = TRIAL_COPY.get(locale, TRIAL_COPY["en"])

    block = f'''<!-- Pricing Cards -->
<div class="pricing-grid">
<!-- Free -->
<div class="price-card free-tier">
<div class="card-tier free-color">Free</div>
<div class="card-price">Free</div>
<ul class="card-features">
{free_general}
<li><i class="bx bxs-info-circle limit"></i> <span>{trial_copy}</span></li>
</ul>
<button class="btn btn-glass btn-buy" disabled>{current_label}</button>
</div>
<!-- Pro monthly -->
<div class="price-card special">
<div class="card-tier">Pro · Monthly</div>
<div class="card-price">$2.99 <span>/ month</span></div>
<ul class="card-features">
{pro_features}
</ul>
<button class="btn btn-primary btn-buy" id="btn-basic-cta" style="background: var(--secondary);">
<i class="bx bx-rocket"></i> {monthly_label}
</button>
</div>
<!-- Pro annual -->
<div class="price-card recommended">
<div class="card-badge">{recommended_label}</div>
<div class="card-tier">Pro · Annual</div>
<div class="card-price">$19.99 <span>/ year</span></div>
<ul class="card-features">
{pro_features}
</ul>
<button class="btn btn-primary btn-buy" id="btn-pro-cta">
<i class="bx bx-crown"></i> {annual_label}
</button>
</div>
</div>
<!-- App Category Note -->'''
    return html[: match.start()] + block + html[match.end() :]


def replace_schema_offers(html: str) -> str:
    def update_json(match: re.Match[str]) -> str:
        raw = match.group(1)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return match.group(0)

        graph = data.get("@graph", []) if isinstance(data, dict) else []
        for node in graph:
            offers = node.get("offers") if isinstance(node, dict) else None
            if not isinstance(offers, list) or len(offers) < 3:
                continue
            offers[0]["name"] = "Free"
            offers[0]["price"] = "0.00"
            offers[1]["name"] = "Pro Monthly"
            offers[1]["price"] = "2.99"
            offers[2]["name"] = "Pro Annual"
            offers[2]["price"] = "19.99"
        encoded = json.dumps(data, ensure_ascii=False, indent=2)
        return f'<script type="application/ld+json">\n{encoded}\n</script>'

    return re.sub(
        r'<script\s+type="application/ld\+json">\s*(.*?)\s*</script>',
        update_json,
        html,
        flags=re.DOTALL,
    )


def replace_pricing_script(html: str) -> str:
    html = re.sub(
        r"let ctaAction = \{\s*basic: \{ type: 'checkout', plan: 'basic' \},\s*"
        r"pro: \{ type: 'checkout', plan: 'pro' \}\s*\};",
        "let ctaAction = {\n"
        "            basic: { type: 'checkout', plan: 'monthly' },\n"
        "            pro: { type: 'checkout', plan: 'annual' }\n"
        "        };",
        html,
    )

    function_pattern = re.compile(
        r"        function applyPricingUIFromUserDoc\(data\) \{.*?"
        r"\n        async function openBillingPortal\(\) \{",
        re.DOTALL,
    )
    replacement = '''        function applyPricingUIFromUserDoc(data) {
            const grade = String(data?.grade || 'free').toLowerCase();
            const subStatus = String(data?.subscriptionStatus || '').toLowerCase();
            const isPaidGrade = grade === 'basic' || grade === 'pro';
            const hasActiveEntitlement = isPaidGrade &&
                (subStatus === 'active' || subStatus === 'trialing');

            let monthlyLabel = __WEB_SUB_COPY.subscribeBasic;
            let annualLabel = __WEB_SUB_COPY.subscribePro;
            let monthlyAction = { type: 'checkout', plan: 'monthly' };
            let annualAction = { type: 'checkout', plan: 'annual' };

            if (hasActiveEntitlement) {
                monthlyLabel = __WEB_SUB_COPY.manage;
                annualLabel = __WEB_SUB_COPY.manage;
                monthlyAction = { type: 'portal' };
                annualAction = { type: 'portal' };
            }

            setButton(btnBasic, "<i class='bx bx-rocket'></i>", monthlyLabel);
            setButton(btnPro, "<i class='bx bx-crown'></i>", annualLabel);
            setTrialNotesVisible(false);
            setPricingButtonsDisabled(false);
            ctaAction = { basic: monthlyAction, pro: annualAction };
        }

        async function openBillingPortal() {'''
    html, count = function_pattern.subn(replacement, html, count=1)
    if count != 1:
        raise RuntimeError("pricing UI function not found")
    return html


def add_global_brokers(html: str) -> str:
    if "IBKR Mobile" in html:
        return html
    categories = list(re.finditer(r'<div class="app-category">', html))
    if len(categories) < 4:
        raise RuntimeError("restricted app categories not found")
    insert_at = categories[3].start()
    names = "".join(f"<span>{name}</span>" for name in GLOBAL_BROKER_NAMES)
    block = (
        '<div class="app-category">Global Stock &amp; Forex Brokers</div>\n'
        f'<div class="app-list">\n{names}\n</div>\n'
    )
    return html[:insert_at] + block + html[insert_at:]


def migrate_price(path: Path) -> None:
    locale = path.parent.parent.name.lower()
    html = path.read_text(encoding="utf-8")
    if "Pro · Monthly" in html and "Pro · Annual" in html:
        html = replace_schema_offers(html)
        html = add_global_brokers(html)
        path.write_text(html, encoding="utf-8")
        return
    html = replace_pricing_cards(html, locale)
    html = replace_schema_offers(html)
    html = re.sub(
        r"<!-- Feature Comparison Table -->.*?<!-- Restricted Apps Modal -->",
        "<!-- Restricted Apps Modal -->",
        html,
        flags=re.DOTALL,
    )

    restricted = RESTRICTED_COPY.get(locale, RESTRICTED_COPY["en"])
    html = re.sub(
        r'(<div class="modal-body">\s*<p[^>]*>).*?(</p>)',
        lambda m: f"{m.group(1)}\n                    {restricted}\n                {m.group(2)}",
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = replace_pricing_script(html)
    html = add_global_brokers(html)
    path.write_text(html, encoding="utf-8")


def migrate_myinfo(path: Path) -> None:
    html = path.read_text(encoding="utf-8")
    html = html.replace('tierEl.textContent = "Basic";', 'tierEl.textContent = "Pro";')
    html = html.replace("tierEl.textContent = 'Basic';", "tierEl.textContent = 'Pro';")
    html = html.replace(
        "const showUpgrade = g === 'free' || g === 'basic';",
        "const showUpgrade = g === 'free';",
    )
    html = re.sub(
        r"changeSubscriptionBtn\.style\.display\s*=\s*\(g === 'pro'\) \? '' : 'none';",
        "changeSubscriptionBtn.style.display = 'none';",
        html,
    )
    html = re.sub(
        r'<button\s+class="btn-upgrade"\s+id="btn-change-subscription".*?</button>',
        '<button class="btn-upgrade" id="btn-change-subscription" style="display:none;">'
        '<i class="bx bx-rocket"></i> Manage billing cycle</button>',
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = re.sub(r"trialNote:\s*'[^']*',", "trialNote: '',", html)
    html = re.sub(r"switchToBasic:\s*'[^']*',", "switchToBasic: 'Manage billing cycle',", html)
    html = re.sub(r"basicBullets:\s*\[[^\]]*\],", "basicBullets: [],", html)
    path.write_text(html, encoding="utf-8")


def migrate_faq(path: Path) -> None:
    locale = path.parent.parent.name.lower()
    questions = FAQ_COPY.get(locale, FAQ_COPY["en"])
    html = path.read_text(encoding="utf-8")
    if all(question in html for question, _ in questions):
        return

    def update_schema(match: re.Match[str]) -> str:
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            return match.group(0)
        graph = data.get("@graph", []) if isinstance(data, dict) else []
        faq = next(
            (node for node in graph if isinstance(node, dict) and node.get("@type") == "FAQPage"),
            None,
        )
        if faq and isinstance(faq.get("mainEntity"), list) and len(faq["mainEntity"]) >= 5:
            replacements = [
                {
                    "@type": "Question",
                    "name": question,
                    "acceptedAnswer": {"@type": "Answer", "text": answer},
                }
                for question, answer in questions
            ]
            faq["mainEntity"][2:5] = replacements
        encoded = json.dumps(data, ensure_ascii=False, indent=2)
        return f'<script type="application/ld+json">\n{encoded}\n</script>'

    html = re.sub(
        r'<script\s+type="application/ld\+json">\s*(.*?)\s*</script>',
        update_schema,
        html,
        count=1,
        flags=re.DOTALL,
    )

    section_match = re.search(
        r'<div class="faq-section">.*?</div>\s*<div class="contact-section">',
        html,
        flags=re.DOTALL,
    )
    if not section_match:
        raise RuntimeError(f"FAQ section not found: {path}")
    fragment = BeautifulSoup(section_match.group(0), "html.parser")
    items = fragment.select(".faq-section .faq-item")
    if len(items) < 5:
        raise RuntimeError(f"expected legacy FAQ entries: {path}")

    for index, (question, answer) in zip((2, 3), questions):
        item = items[index]
        button = item.select_one(".faq-question")
        answer_box = item.select_one(".faq-answer")
        if button is None or answer_box is None:
            raise RuntimeError(f"malformed FAQ entry: {path}")
        button.clear()
        button.append(question + " ")
        icon = fragment.new_tag("i")
        icon["class"] = ["bx", "bx-chevron-down"]
        button.append(icon)
        answer_box.clear()
        paragraph = fragment.new_tag("p")
        paragraph.string = answer
        answer_box.append(paragraph)

    items[4].decompose()
    replacement = str(fragment)
    html = html[: section_match.start()] + replacement + html[section_match.end() :]
    path.write_text(html, encoding="utf-8")


def main() -> None:
    price_pages = sorted(ROOT.glob("*/price/index.html"))
    myinfo_pages = sorted(ROOT.glob("*/myinfo/index.html"))
    faq_pages = sorted(ROOT.glob("*/faq/index.html"))
    if not price_pages or not myinfo_pages or not faq_pages:
        raise RuntimeError("localized pages not found")
    for page in price_pages:
        migrate_price(page)
    for page in myinfo_pages:
        migrate_myinfo(page)
    for page in faq_pages:
        migrate_faq(page)
    print(
        f"migrated {len(price_pages)} price, {len(myinfo_pages)} myinfo, "
        f"and {len(faq_pages)} FAQ pages"
    )


if __name__ == "__main__":
    main()
