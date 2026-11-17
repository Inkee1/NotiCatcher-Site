"""Localize the home page promo copy with Codex CLI.

Reads tools/home_promo/source.json (en master, ko reference) and writes
tools/home_promo/locales/<site-dir>.json for every site locale except en/ko.
Each language is one `codex exec` run with a JSON output schema derived from the
English copy; answers that change the structure or drop required terms are
retried with the problem spelled out. Then run build.py.

Usage: python tools/home_promo/localize_with_codex.py [site-dir ...]
"""

import concurrent.futures as cf
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / "source.json"
OUT_DIR = HERE / "locales"

# site directory -> language name for the prompt
LANGS = {
    "am": "Amharic", "ar": "Arabic", "bg": "Bulgarian", "bn": "Bengali", "cs": "Czech",
    "da": "Danish", "de": "German", "el": "Greek", "es": "Spanish (Spain)",
    "es-419": "Spanish (Latin America)", "et": "Estonian", "fa": "Persian", "fi": "Finnish",
    "fil": "Filipino", "fr": "French", "gu": "Gujarati", "he": "Hebrew", "hi": "Hindi",
    "hr": "Croatian", "hu": "Hungarian", "id": "Indonesian", "it": "Italian", "ja": "Japanese",
    "km": "Khmer", "kn": "Kannada", "lo": "Lao", "lt": "Lithuanian", "lv": "Latvian",
    "ml": "Malayalam", "mr": "Marathi", "ms": "Malay", "my": "Burmese", "nl": "Dutch",
    "no": "Norwegian (Bokmal)", "pa": "Punjabi (Gurmukhi)", "pl": "Polish",
    "pt": "Portuguese (Portugal)", "pt-br": "Portuguese (Brazil)", "ro": "Romanian",
    "ru": "Russian", "sk": "Slovak", "sl": "Slovenian", "sr": "Serbian (Cyrillic)",
    "sv": "Swedish", "sw": "Swahili", "ta": "Tamil", "te": "Telugu", "th": "Thai",
    "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu", "vi": "Vietnamese",
    "zh": "Simplified Chinese", "zh-hans": "Simplified Chinese", "zh-hant": "Traditional Chinese (Taiwan)",
}

# Fields that may legitimately be empty (text around the highlighted keyword).
OPTIONAL = {"before", "after"}


def schema_for(value):
    if isinstance(value, dict):
        return {
            "type": "object",
            "additionalProperties": False,
            "required": list(value),
            "properties": {k: schema_for(v) for k, v in value.items()},
        }
    if isinstance(value, list):
        return {"type": "array", "minItems": len(value), "maxItems": len(value), "items": schema_for(value[0])}
    return {"type": "string"}


def shape_problems(ref, got, path="copy"):
    if isinstance(ref, dict):
        if not isinstance(got, dict) or set(ref) != set(got):
            return [f"{path} must have exactly the keys {sorted(ref)}"]
        return [p for k in ref for p in shape_problems(ref[k], got[k], f"{path}.{k}")]
    if isinstance(ref, list):
        if not isinstance(got, list) or len(got) != len(ref):
            return [f"{path} must be a list of {len(ref)} items"]
        return [p for i, (r, g) in enumerate(zip(ref, got)) for p in shape_problems(r, g, f"{path}[{i}]")]
    if not isinstance(got, str):
        return [f"{path} must be a string"]
    if not got.strip() and path.rsplit(".", 1)[-1] not in OPTIONAL:
        return [f"{path} is empty"]
    return []


def violations(en, data):
    problems = shape_problems(en, data)
    if problems:
        return problems
    for item in [data["quiet"]["ring"], *data["personas"]["items"]]:
        if item["keyword"] != item["keyword"].strip():
            problems.append(f'keyword "{item["keyword"]}" must not start or end with spaces')
    checks = [
        ("quiet.body", data["quiet"]["body"], "NotiCatcher"),
        ("personas.note", data["personas"]["note"], "Pro"),
        ("personas.note", data["personas"]["note"], "NotiCatcher"),
        ("cta.body", data["cta"]["body"], "7"),
        ("cta.play", data["cta"]["play"], "Google Play"),
    ]
    for field, text, term in checks:
        if term not in text:
            problems.append(f'{field} must contain "{term}"')
    return problems


def build_prompt(language, en, ko, feedback):
    parts = [
        f"You are a native {language} marketing copywriter localizing a product website.",
        f"Localize the home page copy of the Android app NotiCatcher into {language}.",
        "",
        "What the app does: when a notification, text message, or incoming call contains a keyword the user chose,",
        "NotiCatcher rings an alarm or vibrates even while the phone is on silent; every other notification stays quiet.",
        "",
        "Rules:",
        f"- Write fluent, warm, conversational {language} for a landing page. Do not translate word for word; keep headings short and punchy.",
        "- Keep the exact JSON structure, keys, and number of list items.",
        "- Notification examples are split into before + keyword + after. Together they must read as one natural notification line in",
        f"  {language}; the keyword is the word the user set up, and it is shown highlighted. 'before' or 'after' may be an empty string.",
        "  Adjust word order freely between the three parts so the sentence is grammatical.",
        "- Localize names in the examples so they feel local: the boss sender, Mom, the salary amount and its currency format.",
        "- 'app' fields are the app name shown on a notification. Keep Slack and Telegram as they are. Replace WhatsApp with the",
        "  messenger most people use in this language's main market (for example LINE, WhatsApp, Viber, Zalo); generic names such as",
        "  Shopping, Group chat, News, Game, Phone, Messages, Bank should be translated as the short labels a phone would show.",
        "- Keep these unchanged: NotiCatcher, Pro, Google Play, Slack, Telegram, BTC.",
        "- Do not add or remove features, claims, numbers, or conditions. Facts: 7-day free trial with every feature, no payment method",
        "  needed; unlimited alarms from financial apps and Telegram need the Pro plan; caller alarms need NotiCatcher set as the caller",
        "  ID and spam app; matching happens on the device and notification content is not sent to servers.",
        "- No emoji, no ALL CAPS words, no superlatives such as 'best' or '#1'.",
        "",
        "English source (master):",
        json.dumps(en, ensure_ascii=False, indent=2),
        "",
        "Korean version written by the developer (reference for tone: friendly, empathetic, speaks to people who keep their phone on silent):",
        json.dumps(ko, ensure_ascii=False, indent=2),
        "",
        "Return only the JSON object.",
    ]
    if feedback:
        parts += ["", "Your previous answer broke these rules; fix them and keep everything else:", *[f"- {p}" for p in feedback]]
    return "\n".join(parts)


def run_codex(prompt, schema_path, workdir):
    codex = shutil.which("codex.cmd") or shutil.which("codex")
    out_file = pathlib.Path(workdir) / "last.json"
    cmd = [
        codex, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only",
        "-C", str(workdir), "--output-schema", str(schema_path), "-o", str(out_file), "-",
    ]
    proc = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True, timeout=420)
    if not out_file.exists():
        raise RuntimeError(f"codex exited {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[-800:]}")
    text = out_file.read_text(encoding="utf-8").strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def localize(lang, en, ko, schema_path):
    language = LANGS[lang]
    feedback = []
    for attempt in range(1, 4):
        with tempfile.TemporaryDirectory(prefix=f"codex-{lang}-") as workdir:
            try:
                data = run_codex(build_prompt(language, en, ko, feedback), schema_path, workdir)
            except Exception as exc:  # noqa: BLE001 - report and retry
                feedback = [f"no valid JSON answer ({exc})"]
                continue
        feedback = violations(en, data)
        if not feedback:
            out = {"language": language, "generatedBy": "codex exec", "copy": data}
            (OUT_DIR / f"{lang}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return lang, f"ok (attempt {attempt})"
    return lang, "FAILED: " + "; ".join(feedback)


def main():
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    en, ko = source["en"], source["ko"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    langs = sys.argv[1:] or list(LANGS)
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = pathlib.Path(tmp) / "schema.json"
        schema_path.write_text(json.dumps(schema_for(en)), encoding="utf-8")
        with cf.ThreadPoolExecutor(max_workers=8) as pool:
            for lang, status in pool.map(lambda code: localize(code, en, ko, schema_path), langs):
                print(f"{lang}: {status}", flush=True)


if __name__ == "__main__":
    main()
