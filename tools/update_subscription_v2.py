"""Render subscription copy from the shared policy without replacing unrelated content."""
import html
import json
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / 'assets/subscription-policy.json').read_text(encoding='utf-8'))
COPY = json.loads((ROOT / 'assets/subscription-copy.json').read_text(encoding='utf-8'))
PLAY = 'https://play.google.com/store/apps/details?id=com.flutterflow.noticatcher'

def text(copy, key, **params):
    value = copy[key]
    for name, replacement in params.items():
        value = value.replace('{' + name + '}', str(replacement))
    return html.escape(value)

def money(value):
    return f'${value:.2f}'

def fragment(value):
    return BeautifulSoup(value, 'html.parser')

def price_grid(copy):
    cards = [f'<div class="price-card free-tier"><div class="card-tier">Free</div>'
             f'<h2>{text(copy,"v2TrialTitle")}</h2><p>{text(copy,"v2FreeBenefits")}</p>'
             f'<p>{text(copy,"v2DataNotice")}</p><a class="btn btn-glass" href="{PLAY}">{text(copy,"v2Download")}</a></div>']
    for name, plan in POLICY['plans'].items():
        savings = round(100 * (1 - plan['annual'] / (12 * plan['monthly'])))
        cards.append(f'<div class="price-card {"recommended" if name == "pro" else "special"}">'
          f'<div class="card-tier">{name.title()}</div><p>{text(copy,"v2ProBenefits" if name == "pro" else "v2BasicBenefits")}</p>'
          f'<p class="v2-price">{text(copy,"v2IntroPrice",intro=money(plan["intro"]),price=money(plan["monthly"]))}</p>'
          f'<p class="v2-price">{text(copy,"v2AnnualPrice",price=money(plan["annual"]))}</p>'
          f'<p>{text(copy,"v2Savings",percent=savings)}</p><a class="btn btn-primary" href="{PLAY}">{text(copy,"v2Download")}</a></div>')
    return '<div class="pricing-grid">' + ''.join(cards) + '</div>'

def update_schema(soup, copy):
    def visit(value):
        if isinstance(value, dict):
            if value.get('@type') == 'FAQPage':
                value['mainEntity'] = [{'@type': 'Question', 'name': node.select_one('.faq-question').get_text(' ', strip=True),
                  'acceptedAnswer': {'@type': 'Answer', 'text': node.select_one('.faq-answer').get_text(' ', strip=True)}}
                  for node in soup.select('.faq-item')]
            if value.get('@type') in ('SoftwareApplication', 'MobileApplication', 'Product') and 'offers' in value:
                value['offers'] = [{'@type':'Offer', 'name':name.title() + ' / ' + period,
                  'price':str(plan[period]), 'priceCurrency':'USD', 'url':PLAY,
                  'description':copy['v2ReferencePrice']}
                  for name, plan in POLICY['plans'].items() for period in ('monthly', 'annual')]
                if not POLICY.get('playReleaseReady', False):
                    for offer in value['offers']: offer['availability'] = 'https://schema.org/PreOrder'
            for item in value.values(): visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
    for script in soup.find_all('script', type='application/ld+json'):
        value = json.loads(script.string)
        visit(value)
        script.string = json.dumps(value, ensure_ascii=False, indent=2)

def update_page(path, lang, page):
    copy = COPY[lang]
    soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'html.parser')
    auth = soup.select_one('#auth-link')
    if auth and page != 'myinfo':
        auth['href'] = PLAY
        auth.string = copy['v2Download']
    if page != 'myinfo':
        for script in soup.select('script[type="module"]'):
            if page == 'price' or 'firebase-config' in script.get('src', ''):
                script.decompose()
    footer = soup.select_one('#wisesignal-legal-footer')
    if footer and not soup.select_one('#subscription-v2-links'):
        legal_lang = 'ko' if lang == 'ko' else 'en'
        footer.append(fragment(f'<p id="subscription-v2-links"><a href="/{legal_lang}/privacy/">{text(copy,"v2Privacy")}</a> · '
          f'<a href="/{legal_lang}/terms/">{text(copy,"v2Terms")}</a> · '
          f'<a href="/{lang}/myinfo/">{text(copy,"v2ExistingCustomers")}</a></p>'))
    if page == 'price':
        grid = soup.select_one('.pricing-grid')
        assert grid is not None, path
        grid.replace_with(fragment(price_grid(copy)))
        intro = soup.select_one('.pricing-header') or soup.select_one('.page-header')
        if intro:
            for p in intro.find_all('p'): p.decompose()
            intro.append(fragment(f'<p>{text(copy,"v2ReferencePrice")}</p><p>{text(copy,"v2IntroEligibility")}</p>'))
            if not POLICY.get('playReleaseReady', False):
                intro.append(fragment(f'<p role="status" class="release-pending-v2" style="border:1px solid #f59e0b;padding:1rem;border-radius:12px;">{text(copy,"v2ReleasePending")}</p>'))
        modal_text = soup.select_one('#apps-modal .modal-body p')
        if modal_text: modal_text.string = copy['v2FreeBenefits'] + ' ' + copy['v2BasicBenefits'] + ' ' + copy['v2ProBenefits']
        for obsolete in soup.select('#checkout-overlay, #checkout-debug-panel'):
            obsolete.decompose()
        if not soup.select_one('script[data-subscription-navigation]'):
            soup.body.append(fragment('<script data-subscription-navigation>document.getElementById("mobile-menu-btn")?.addEventListener("click",()=>document.getElementById("nav-links")?.classList.toggle("active"));</script>'))
        if not soup.select_one('#subscription-v2-style'):
            soup.head.append(fragment('<style id="subscription-v2-style">.v2-price{font-size:1.2rem;line-height:1.65;margin:1.2rem 0}.price-card p{line-height:1.65}.price-card .btn{margin-top:1rem}.pricing-grid{align-items:stretch}</style>'))
    if page == 'faq':
        items = soup.select('.faq-item')
        replacements = {
          2:(copy['v2TrialTitle'], copy['v2TrialBody'] + ' ' + copy['v2DataNotice']),
          3:('Basic / Pro', copy['v2BasicBenefits'] + ' ' + copy['v2ProBenefits'] + ' ' + copy['v2ReferencePrice']),
          4:(copy['v2StatusTitle'], copy['v2ContinueCancel'] + '. ' + copy['v2LegacyBody']),
          7:(copy['v2Privacy'], copy['v2DataNotice']),
        }
        for index, (question, answer) in replacements.items():
            if index >= len(items): continue
            button = items[index].select_one('.faq-question'); button.clear()
            button.append(question); button.append(fragment('<i class="bx bx-chevron-down"></i>'))
            body = items[index].select_one('.faq-answer'); body.clear()
            body.append(fragment('<p>' + html.escape(answer) + '</p>'))
            if index == 3: body.append(fragment(f'<p><a href="/{lang}/price/">Basic / Pro</a></p>'))
    if page == 'myinfo':
        for node in soup.select('[data-tab="signup"], #btn-google-signup'):
            node.decompose()
        form = soup.select_one('#form-signup')
        if form: form['style'] = 'display:none!important'
        header = soup.select_one('.login-header p')
        if header: header.string = copy['v2ExistingCustomers'] + '. ' + copy['v2LegacyBody']
        if not soup.select_one('#legacy-transfer-v2'):
            target = soup.select_one('#logged-in-view')
            target.append(fragment(f'<section id="legacy-transfer-v2" style="margin:2rem 0;padding:1.5rem;border:1px solid #64748b;border-radius:16px;">'
              f'<h2>{text(copy,"v2LegacyTitle")}</h2><p>{text(copy,"v2LegacyBody")}</p>'
              f'<button type="button" class="btn btn-primary" id="generate-transfer-v2">{text(copy,"v2GenerateCode")}</button>'
              f'<label style="display:block;margin-top:1rem">{text(copy,"v2LegacyCode")} '
              '<input id="transfer-code-v2" readonly autocomplete="off" style="display:block;width:100%;font-family:monospace;padding:.7rem;"/></label>'
              f'<p>{text(copy,"v2CodeExpires")}</p><p id="transfer-status-v2" role="status"></p></section>'))
            module = soup.find('script', type='module')
            module.string = module.get_text() + '''
// Existing subscribers only: issue a short-lived, one-use connection code.
document.getElementById('generate-transfer-v2').addEventListener('click', async (event) => {
  const button = event.currentTarget;
  const status = document.getElementById('transfer-status-v2');
  const output = document.getElementById('transfer-code-v2');
  status.textContent = ''; output.value = ''; button.disabled = true;
  try {
    if (!auth.currentUser) throw new Error('AUTH_REQUIRED');
    const token = await auth.currentUser.getIdToken(true);
    const response = await fetch('https://us-central1-noticatcher-eb157.cloudfunctions.net/notiIssueLegacyTransferCode', {
      method: 'POST', headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + token}, body: '{}'
    });
    if (!response.ok) throw new Error('CONNECTION_FAILED');
    const data = await response.json(); output.value = data.code; output.focus(); output.select();
  } catch (_) { status.textContent = ''' + json.dumps(copy['v2Retry'], ensure_ascii=False) + '''; }
  finally { button.disabled = false; }
});
'''
    update_schema(soup, copy)
    path.write_text('\n'.join(line.rstrip() for line in str(soup).splitlines())+'\n', encoding='utf-8')

def main():
    count = 0
    for price in ROOT.glob('*/price/index.html'):
        lang = price.parent.parent.name
        if lang not in COPY: raise ValueError('Missing translations: ' + lang)
        for page in ('home', 'price', 'faq', 'download', 'myinfo'):
            path = ROOT / lang / ('index.html' if page == 'home' else page + '/index.html')
            if path.exists(): update_page(path, lang, page); count += 1
    print('Updated pages:', count)

if __name__ == '__main__': main()
