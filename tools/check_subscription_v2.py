"""Check regional-price guidance, plan benefits and legacy management access."""
import json
import re
import subprocess
import tempfile
from pathlib import Path
from bs4 import BeautifulSoup

root = Path(__file__).resolve().parents[1]
copy = json.loads((root/'assets/subscription-copy.json').read_text(encoding='utf-8'))
policy = json.loads((root/'assets/subscription-policy.json').read_text(encoding='utf-8'))

def check_no_fixed_prices(soup, location):
    visible = soup.get_text(' ', strip=True)
    assert not re.search(r'\$\s*\d|\bUSD\b|\d\s*[%％]', visible), (location, 'fixed price or discount')
    def visit(value):
        if isinstance(value, dict):
            assert not {'offers', 'price', 'lowPrice', 'highPrice', 'priceCurrency', 'priceSpecification'} & value.keys(), (location, 'structured price')
            for item in value.values(): visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
    for script in soup.find_all('script', type='application/ld+json'):
        visit(json.loads(script.string))

count = 0
for path in root.glob('*/price/index.html'):
    lang = path.parent.parent.name
    soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'html.parser')
    visible = soup.get_text(' ', strip=True)
    check_no_fixed_prices(soup, lang + '/price')
    assert len(soup.select('.price-card')) == 3, lang
    assert copy[lang]['v2FreeBenefits'] in visible, lang
    assert copy[lang]['v2ReferencePrice'] in visible, lang
    if not policy.get('playReleaseReady', False):
        assert copy[lang]['v2ReleasePending'] in visible, lang
    assert not soup.select('.btn-buy, #btn-basic-cta, #btn-pro-cta'), lang
    assert 'notiCreateCheckoutSession' not in str(soup), lang
    assert soup.select_one('link[rel="canonical"]'), lang
    for name in policy['plans']:
        card = next(card for card in soup.select('.price-card') if card.select_one('.card-tier').get_text(strip=True) == name.title())
        assert copy[lang]['v2ProBenefits' if name == 'pro' else 'v2BasicBenefits'] in card.get_text(' ', strip=True), (lang, name, 'benefits')
    for link in soup.select('.pricing-grid a'):
        assert link['href'] == 'https://play.google.com/store/apps/details?id=com.flutterflow.noticatcher', lang
    faq = BeautifulSoup((path.parent.parent/'faq/index.html').read_text(encoding='utf-8'), 'html.parser')
    check_no_fixed_prices(faq, lang + '/faq')
    assert copy[lang]['v2TrialBody'] in faq.get_text(' ', strip=True), lang
    assert copy[lang]['v2ReferencePrice'] in faq.get_text(' ', strip=True), lang
    legacy = BeautifulSoup((path.parent.parent/'myinfo/index.html').read_text(encoding='utf-8'), 'html.parser')
    assert legacy.select_one('#generate-transfer-v2'), lang
    assert legacy.select_one('#btn-cancel-subscription'), lang
    assert not legacy.select('[data-tab="signup"]'), lang
    for script in legacy.find_all('script', type='module'):
        if script.get('src'): continue
        with tempfile.TemporaryDirectory(prefix='noticatcher-js-') as directory:
            file = Path(directory)/'check.mjs'
            file.write_text(script.get_text(), encoding='utf-8')
            result = subprocess.run(['node', '--check', str(file)], capture_output=True, text=True)
            assert result.returncode == 0, (lang, result.stderr)
    count += 1
for lang in ('ko', 'en'):
    for page in ('privacy', 'terms'):
        assert (root/lang/page/'index.html').exists()
    terms = BeautifulSoup((root/lang/'terms/index.html').read_text(encoding='utf-8'), 'html.parser')
    check_no_fixed_prices(terms, lang + '/terms')
    assert terms.select_one('a[href="/' + lang + '/myinfo/"]'), lang
print(f'PASS: {count} locales; no fixed prices or discounts; regional guidance, benefits, closed checkout, legacy management and JS syntax')
