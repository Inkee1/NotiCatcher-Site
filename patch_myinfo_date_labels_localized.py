from __future__ import annotations

import re
from pathlib import Path


LABELS = {
    "am": {"end": "የማብቂያ ቀን", "renew": "የመታደሻ ቀን"},
    "ar": {"end": "تاريخ الانتهاء", "renew": "تاريخ التجديد"},
    "bg": {"end": "Крайна дата", "renew": "Дата за подновяване"},
    "bn": {"end": "শেষ তারিখ", "renew": "নবায়নের তারিখ"},
    "cs": {"end": "Datum ukončení", "renew": "Datum obnovení"},
    "da": {"end": "Slutdato", "renew": "Fornyelsesdato"},
    "de": {"end": "Enddatum", "renew": "Verlängerungsdatum"},
    "el": {"end": "Ημερομηνία λήξης", "renew": "Ημερομηνία ανανέωσης"},
    "en": {"end": "End date", "renew": "Renewal date"},
    "es": {"end": "Fecha de fin", "renew": "Fecha de renovación"},
    "es-419": {"end": "Fecha de fin", "renew": "Fecha de renovación"},
    "et": {"end": "Lõppkuupäev", "renew": "Uuendamise kuupäev"},
    "fa": {"end": "تاریخ پایان", "renew": "تاریخ تمدید"},
    "fi": {"end": "Päättymispäivä", "renew": "Uusiutumispäivä"},
    "fil": {"end": "Petsa ng pagtatapos", "renew": "Petsa ng pag-renew"},
    "fr": {"end": "Date de fin", "renew": "Date de renouvellement"},
    "gu": {"end": "સમાપ્તિ તારીખ", "renew": "નવનીકરણ તારીખ"},
    "he": {"end": "תאריך סיום", "renew": "תאריך חידוש"},
    "hi": {"end": "समाप्ति तिथि", "renew": "नवीनीकरण तिथि"},
    "hr": {"end": "Datum završetka", "renew": "Datum obnove"},
    "hu": {"end": "Lejárati dátum", "renew": "Megújítási dátum"},
    "id": {"end": "Tanggal berakhir", "renew": "Tanggal perpanjangan"},
    "it": {"end": "Data di fine", "renew": "Data di rinnovo"},
    "ja": {"end": "終了日", "renew": "更新日"},
    "km": {"end": "កាលបរិច្ឆេទផុតកំណត់", "renew": "កាលបរិច្ឆេទបន្ត"},
    "kn": {"end": "ಮುಕ್ತಾಯ ದಿನಾಂಕ", "renew": "ನವೀಕರಣ ದಿನಾಂಕ"},
    "ko": {"end": "종료일", "renew": "갱신일"},
    "lo": {"end": "ວັນສິ້ນສຸດ", "renew": "ວັນຕໍ່ອາຍຸ"},
    "lt": {"end": "Pabaigos data", "renew": "Atnaujinimo data"},
    "lv": {"end": "Beigu datums", "renew": "Atjaunošanas datums"},
    "ml": {"end": "അവസാന തീയതി", "renew": "പുതുക്കൽ തീയതി"},
    "mr": {"end": "समाप्ती तारीख", "renew": "नूतनीकरण तारीख"},
    "ms": {"end": "Tarikh tamat", "renew": "Tarikh pembaharuan"},
    "my": {"end": "သက်တမ်းကုန်ဆုံးရက်", "renew": "သက်တမ်းတိုးရက်"},
    "nl": {"end": "Einddatum", "renew": "Verlengingsdatum"},
    "no": {"end": "Sluttdato", "renew": "Fornyelsesdato"},
    "pa": {"end": "ਅੰਤ ਦੀ ਤਾਰੀਖ", "renew": "ਨਵੀਨੀਕਰਨ ਦੀ ਤਾਰੀਖ"},
    "pl": {"end": "Data zakończenia", "renew": "Data odnowienia"},
    "pt": {"end": "Data de término", "renew": "Data de renovação"},
    "pt-br": {"end": "Data de término", "renew": "Data de renovação"},
    "ro": {"end": "Data de sfârșit", "renew": "Data de reînnoire"},
    "ru": {"end": "Дата окончания", "renew": "Дата продления"},
    "sk": {"end": "Dátum ukončenia", "renew": "Dátum obnovenia"},
    "sl": {"end": "Datum konca", "renew": "Datum obnove"},
    "sr": {"end": "Datum završetka", "renew": "Datum obnove"},
    "sv": {"end": "Slutdatum", "renew": "Förnyelsedatum"},
    "sw": {"end": "Tarehe ya mwisho", "renew": "Tarehe ya kusasisha"},
    "ta": {"end": "முடிவு தேதி", "renew": "புதுப்பிப்பு தேதி"},
    "te": {"end": "ముగింపు తేదీ", "renew": "పునరుద్ధరణ తేదీ"},
    "th": {"end": "วันสิ้นสุด", "renew": "วันต่ออายุ"},
    "tr": {"end": "Bitiş tarihi", "renew": "Yenileme tarihi"},
    "uk": {"end": "Дата завершення", "renew": "Дата поновлення"},
    "ur": {"end": "اختتامی تاریخ", "renew": "تجدید کی تاریخ"},
    "vi": {"end": "Ngày kết thúc", "renew": "Ngày gia hạn"},
    "zh": {"end": "到期日", "renew": "续订日"},
    "zh-hans": {"end": "到期日", "renew": "续订日"},
    "zh-hant": {"end": "到期日", "renew": "續訂日"},
}


MANAGE_LINE_RE = re.compile(r"(?m)^(\s*)manage\s*:\s*(['\"]).*?\2\s*,\s*$")

LABEL_FUNC_RE = re.compile(
    r"""
    const\s+_label\s*=\s*\(\(\)\s*=>\s*\{\s*
        const\s+l\s*=\s*String\(document\.documentElement\.lang\s*\|\|\s*''\)\.toLowerCase\(\)\s*;\s*
        if\s*\(l\s*===\s*'ko'\)\s*return\s*_isCanceled\s*\?\s*'종료일'\s*:\s*'갱신일'\s*;\s*
        return\s*_isCanceled\s*\?\s*'End'\s*:\s*'Renews'\s*;\s*
    \}\)\(\)\s*;\s*
    """,
    re.VERBOSE,
)


def esc_js_single(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def patch_file(path: Path) -> tuple[bool, int]:
    locale = path.parent.parent.name.lower()
    if locale not in LABELS:
        return False, 0

    s = path.read_text(encoding="utf-8")
    out = s
    edits = 0

    # 1) Add end/renew labels into __WEB_SUB_COPY (once)
    if "endDateLabel" not in out and "renewDateLabel" not in out:
        m = MANAGE_LINE_RE.search(out)
        if m:
            indent = m.group(1)
            end = esc_js_single(LABELS[locale]["end"])
            renew = esc_js_single(LABELS[locale]["renew"])
            insert = (
                f"{indent}endDateLabel: '{end}',\n"
                f"{indent}renewDateLabel: '{renew}',\n"
            )
            # Insert right after the manage line.
            idx = m.end()
            out = out[:idx] + "\n" + insert + out[idx:]
            edits += 1

    # 2) Use localized labels from __WEB_SUB_COPY in the next-payment block
    if LABEL_FUNC_RE.search(out):
        # Preserve indentation by reusing the leading spaces before "const _label"
        out = LABEL_FUNC_RE.sub(
            "const _label = _isCanceled\n"
            "                    ? (__WEB_SUB_COPY.endDateLabel || 'End date')\n"
            "                    : (__WEB_SUB_COPY.renewDateLabel || 'Renewal date');\n",
            out,
            count=1,
        )
        edits += 1

    if out != s:
        path.write_text(out, encoding="utf-8")
        return True, edits

    return False, 0


def main() -> int:
    root = Path(__file__).resolve().parent
    files = sorted(root.rglob("myinfo/index.html"))
    changed = 0
    total_edits = 0
    for f in files:
        did, n = patch_file(f)
        if did:
            changed += 1
            total_edits += n
    print(f"Done. Updated {changed}/{len(files)} myinfo pages. edits={total_edits}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

