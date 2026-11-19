"""Send visitors to their own language.

Two places pick a language from the browser:
  * /index.html (the root) redirects to /<lang>/.
  * every /en/**/index.html that lists hreflang alternates redirects a visitor
    who landed there directly (search result, shared link) to the same page in
    their language.

Both use the same rule: among the browser's preferred languages that the site
supports, prefer the one spoken where the device's time zone is (a Korean
time zone with "en-US, ko-KR" picks ko); otherwise take the first supported one.
A language chosen in the site's language menu (localStorage "lang_manual")
always wins, and crawlers are never redirected.

The scripts are injected between <!-- noticatcher-locale-redirect:start/end -->
markers, so this is safe to re-run.

It also writes the same time-zone table into every */js/lang-widget.js (between
/* tz-langs:start/end */) so the language menu suggests the same language first.

Usage: python -I tools/locale_redirect.py
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
START = "<!-- noticatcher-locale-redirect:start -->"
END = "<!-- noticatcher-locale-redirect:end -->"

# Main time zones of countries whose main language the site supports.
TIME_ZONES = {
    "ko": "Asia/Seoul",
    "ja": "Asia/Tokyo",
    "zh-hans": "Asia/Shanghai Asia/Chongqing Asia/Harbin Asia/Urumqi",
    "zh-hant": "Asia/Taipei Asia/Hong_Kong Asia/Macau",
    "th": "Asia/Bangkok",
    "vi": "Asia/Ho_Chi_Minh Asia/Saigon",
    "id": "Asia/Jakarta Asia/Makassar Asia/Jayapura Asia/Pontianak",
    "ms": "Asia/Kuala_Lumpur Asia/Kuching",
    "fil": "Asia/Manila",
    "km": "Asia/Phnom_Penh",
    "lo": "Asia/Vientiane",
    "my": "Asia/Yangon Asia/Rangoon",
    "bn": "Asia/Dhaka",
    "ur": "Asia/Karachi",
    "fa": "Asia/Tehran",
    "he": "Asia/Jerusalem Asia/Tel_Aviv",
    "ar": "Asia/Riyadh Asia/Baghdad Asia/Kuwait Asia/Qatar Asia/Bahrain Asia/Muscat Asia/Dubai Asia/Amman "
          "Asia/Beirut Asia/Damascus Africa/Cairo Africa/Algiers Africa/Casablanca Africa/Tunis Africa/Tripoli Africa/Khartoum",
    "tr": "Europe/Istanbul",
    "ru": "Europe/Moscow Europe/Samara Europe/Volgograd Asia/Yekaterinburg Asia/Omsk Asia/Novosibirsk Asia/Krasnoyarsk "
          "Asia/Irkutsk Asia/Yakutsk Asia/Vladivostok",
    "uk": "Europe/Kiev Europe/Kyiv",
    "pl": "Europe/Warsaw",
    "cs": "Europe/Prague",
    "sk": "Europe/Bratislava",
    "hu": "Europe/Budapest",
    "ro": "Europe/Bucharest",
    "bg": "Europe/Sofia",
    "el": "Europe/Athens",
    "hr": "Europe/Zagreb",
    "sl": "Europe/Ljubljana",
    "sr": "Europe/Belgrade",
    "lt": "Europe/Vilnius",
    "lv": "Europe/Riga",
    "et": "Europe/Tallinn",
    "fi": "Europe/Helsinki",
    "sv": "Europe/Stockholm",
    "no": "Europe/Oslo",
    "da": "Europe/Copenhagen",
    "nl": "Europe/Amsterdam",
    "de": "Europe/Berlin Europe/Vienna",
    "fr": "Europe/Paris",
    "it": "Europe/Rome",
    "es": "Europe/Madrid",
    "pt": "Europe/Lisbon",
    "pt-br": "America/Sao_Paulo America/Fortaleza America/Recife America/Bahia America/Manaus America/Belem",
    "es-419": "America/Mexico_City America/Bogota America/Lima America/Santiago America/Argentina/Buenos_Aires "
              "America/Buenos_Aires America/Caracas America/Guayaquil America/La_Paz America/Montevideo "
              "America/Asuncion America/Guatemala America/Costa_Rica America/Panama",
    "am": "Africa/Addis_Ababa",
    "sw": "Africa/Nairobi Africa/Dar_es_Salaam",
}

# Shared by both scripts: resolve(tag, has) and preferred(has).
CORE = """
var ALIAS={nb:"no",nn:"no",tl:"fil",iw:"he","in":"id"};
var TZ=%TZ%;
var TZ_LANG={};for(var k in TZ){TZ[k].split(" ").forEach(function(z){TZ_LANG[z]=k;});}
function norm(t){return(t||"").toString().trim().toLowerCase().replace(/_/g,"-");}
function resolve(tag,has){
  var l=norm(tag);if(!l)return"";
  var head=l.split("-")[0];if(ALIAS[head])l=ALIAS[head]+l.slice(head.length);
  if(has("zh-hant")&&/^zh-(hant|tw|hk|mo)(-|$)/.test(l))return"zh-hant";
  if(has("zh-hans")&&/^zh-(hans|cn|sg)(-|$)/.test(l))return"zh-hans";
  if(has("es-419")&&/^es-(?!es(-|$))/.test(l))return"es-419";
  if(has("pt-br")&&/^pt-br(-|$)/.test(l))return"pt-br";
  while(l){if(has(l))return l;var i=l.lastIndexOf("-");if(i<0)break;l=l.slice(0,i);}
  return"";
}
function preferred(has){
  var list=(navigator.languages&&navigator.languages.length)?navigator.languages:[navigator.language||""];
  var found=[];
  for(var i=0;i<list.length;i++){var r=resolve(list[i],has);if(r&&found.indexOf(r)<0)found.push(r);}
  var tz="";try{tz=Intl.DateTimeFormat().resolvedOptions().timeZone||"";}catch(e){}
  var local=TZ_LANG[tz];
  if(local&&found.indexOf(local)>=0)return local;
  return found[0]||"";
}
""".replace("%TZ%", json.dumps(TIME_ZONES, separators=(",", ":")))

ROOT_SCRIPT = """<script>
(function(){
%CORE%
var SUPPORTED=%SUPPORTED%;
function has(l){return SUPPORTED.indexOf(l)>=0;}
var manual="";try{manual=localStorage.getItem("lang_manual")||"";}catch(e){}
var lang=resolve(new URLSearchParams(location.search).get("lang"),has)||resolve(manual,has)||preferred(has)||"en";
var path=location.pathname||"/";
var base=path.endsWith("/")?path:/\\.html?$/i.test(path)?path.replace(/[^/]*$/,""):path+"/";
var target=new URL("./"+lang+"/",location.origin+base).toString();
// If a language folder is missing (partial deploy), fall back to English instead of a 404.
fetch(target,{method:"HEAD",cache:"no-store"}).then(function(r){
  location.replace(r&&r.ok?target:new URL("./en/",location.origin+base).toString());
}).catch(function(){location.replace(target);});
})();
</script>"""

EN_SCRIPT = """<script>
(function(){
try{
if(/bot|crawl|spider|slurp|mediapartners/i.test(navigator.userAgent))return;
%CORE%
var alt={};
document.querySelectorAll('link[rel="alternate"][hreflang]').forEach(function(l){var h=norm(l.getAttribute("hreflang"));if(h!=="x-default")alt[h]=l.href;});
function has(l){return !!alt[l];}
var manual="";try{manual=localStorage.getItem("lang_manual")||"";}catch(e){}
var lang=resolve(manual,has);
if(!lang){
  // Moving around inside the site (or arriving from the root redirect) keeps the page the visitor is on.
  if(document.referrer){try{if(new URL(document.referrer).origin===location.origin)return;}catch(e){}}
  lang=preferred(has);
}
if(!lang||lang==="en")return;
var u=new URL(alt[lang]);u.search=location.search;u.hash=location.hash;
location.replace(u.toString());
}catch(e){}
})();
</script>"""


def put_block(text, block, anchor_re):
    if START in text:
        return re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    m = re.search(anchor_re, text, flags=re.S)
    if not m:
        raise RuntimeError("anchor not found")
    return text[: m.start()] + block + text[m.end():]


def write(path, text, original):
    if "\r\n" in original:
        text = re.sub(r"(?<!\r)\n", "\r\n", text)
    if text != original:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return True
    return False


def main():
    root_index = ROOT / "index.html"
    with open(root_index, encoding="utf-8", newline="") as fh:
        original = fh.read()
    supported = json.loads(re.search(r"const SUPPORTED = (\[.*?\]);", original).group(1)) if "const SUPPORTED" in original \
        else json.loads(re.search(r"var SUPPORTED=(\[.*?\]);", original).group(1))
    block = START + "\n" + ROOT_SCRIPT.replace("%CORE%", CORE.strip()).replace("%SUPPORTED%", json.dumps(supported)) + "\n" + END
    # First run replaces the original inline redirect script that follows the <noscript> fallback.
    text = put_block(original, block, r"<script>\s*const SUPPORTED.*?</script>")
    changed = ["index.html"] if write(root_index, text, original) else []

    en_block = START + "\n" + EN_SCRIPT.replace("%CORE%", CORE.strip()) + "\n" + END + "\n"
    for page in sorted((ROOT / "en").rglob("index.html")):
        with open(page, encoding="utf-8", newline="") as fh:
            original = fh.read()
        if 'hreflang="ko"' not in original:
            continue  # pages without translations (privacy, terms) stay as they are
        if START in original:
            text = put_block(original, en_block.rstrip("\n"), None)
        else:
            text = original.replace("</head>", en_block + "</head>", 1)
        if write(page, text, original):
            changed.append(str(page.relative_to(ROOT)))
    tz_json = json.dumps(TIME_ZONES, separators=(",", ":"), ensure_ascii=False)
    for widget in sorted(ROOT.glob("*/js/lang-widget.js")):
        with open(widget, encoding="utf-8", newline="") as fh:
            original = fh.read()
        text = re.sub(r"/\* tz-langs:start \*/.*?/\* tz-langs:end \*/",
                      lambda _: "/* tz-langs:start */" + tz_json + "/* tz-langs:end */", original, flags=re.S)
        if write(widget, text, original):
            changed.append(str(widget.relative_to(ROOT)))
    print("updated:", ", ".join(changed) or "nothing")


if __name__ == "__main__":
    main()
