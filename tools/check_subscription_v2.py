"""Check public disclosures, structured prices and legacy management scripts."""
import json
import subprocess
import tempfile
from pathlib import Path
from bs4 import BeautifulSoup

root = Path(__file__).resolve().parents[1]
copy = json.loads((root/'assets/subscription-copy.json').read_text(encoding='utf-8'))
policy = json.loads((root/'assets/subscription-policy.json').read_text(encoding='utf-8'))
count = 0
for path in root.glob('*/price/index.html'):
    lang = path.parent.parent.name
    soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'html.parser')
    visible = soup.get_text(' ', strip=True)
    for price in ('$0.90', '$2.40', '$19.90', '$1.90', '$4.90', '$39.90'):
        assert price in visible, (lang, 'missing price', price)
    for stale in ('$2.99', '$19.99'):
        assert stale not in visible, (lang, 'stale price', stale)
    assert len(soup.select('.price-card')) == 3, lang
    assert copy[lang]['v2FreeBenefits'] in visible, lang
    assert copy[lang]['v2ReferencePrice'] in visible, lang
    if not policy.get('playReleaseReady', False):
        assert copy[lang]['v2ReleasePending'] in visible, lang
    assert not soup.select('.btn-buy, #btn-basic-cta, #btn-pro-cta'), lang
    assert 'notiCreateCheckoutSession' not in str(soup), lang
    assert soup.select_one('link[rel="canonical"]'), lang
    for script in soup.find_all('script', type='application/ld+json'): json.loads(script.string)
    faq = BeautifulSoup((path.parent.parent/'faq/index.html').read_text(encoding='utf-8'), 'html.parser')
    assert copy[lang]['v2TrialBody'] in faq.get_text(' ', strip=True), lang
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
print(f'PASS: {count} locales; prices, free policy, closed checkout, legacy management and JS syntax')
