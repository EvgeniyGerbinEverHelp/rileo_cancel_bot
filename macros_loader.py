import re

import openpyxl

from config import settings

_MULTI_NL = re.compile(r"\n{2,}")


def _to_html(raw) -> str:
    """Текст макроса из таблицы -> HTML для Zendesk html_body."""
    if raw is None:
        return ""
    text = str(raw).replace("\r\n", "\n")
    text = _MULTI_NL.sub("\n\n", text)
    return text.replace("\n", "<br>")


def load_macros() -> dict:
    """Грузит макросы из xlsx. Ключ словаря — tag из колонки 'Actions: Add tags'."""
    macros: dict = {}
    try:
        wb = openpyxl.load_workbook(
            settings.KEYWORDS_FILE, data_only=True, read_only=True
        )
        ws = wb[settings.MACROS_SHEET_NAME]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if not rows:
            return macros

        headers = [str(h).strip() if h else "" for h in rows[0]]
        idx = {h: i for i, h in enumerate(headers)}
        i_name = idx.get("Macro Name")
        i_text = idx.get("Actions: Comment/description")
        i_tag = idx.get("Actions: Add tags")

        for row in rows[1:]:
            tag = ""
            if i_tag is not None and i_tag < len(row) and row[i_tag]:
                tag = str(row[i_tag]).strip()
            if not tag:
                continue
            name = (
                str(row[i_name]).strip()
                if i_name is not None and i_name < len(row) and row[i_name]
                else ""
            )
            text = (
                _to_html(row[i_text])
                if i_text is not None and i_text < len(row)
                else ""
            )
            macros[tag] = {"name": name, "text": text, "tag": tag}

        print(f"✅ Loaded {len(macros)} macros: {list(macros.keys())}")
    except Exception as e:
        print(f"❌ Error loading macros: {e}")
    return macros


MACROS_DB = load_macros()
