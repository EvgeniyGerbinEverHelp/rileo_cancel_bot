import re

import openpyxl

from config import settings

# Хвост JS-style регулярки: закрывающий слеш с флагами/запятой (/i, , /i , /,i)
_FLAG_TAIL = re.compile(r"/[i,\s]*$")


class EligibilityChecker:
    """Проверка тикета на eligibility по ключевым словам из xlsx (флоу 5.0).

    Eligible, если текст содержит ключевое слово из колонки Cancel и не содержит
    слов из колонок Refund / Trigger / Tech Issue.
    """

    def __init__(self):
        self.cancel_patterns: list[str] = []
        self.block_patterns: list[str] = []
        self._load()

    @staticmethod
    def _clean_regex(raw) -> str | None:
        """Приводит JS-style /pattern/i, к чистому regex для Python."""
        if raw is None:
            return None
        s = str(raw).strip()
        if not s or s.lower() == "nan":
            return None
        if s.startswith("/"):
            s = s[1:]
        s = _FLAG_TAIL.sub("", s)
        s = s.strip().rstrip(",").strip()
        return s or None

    def _load(self):
        try:
            wb = openpyxl.load_workbook(
                settings.KEYWORDS_FILE, data_only=True, read_only=True
            )
            ws = wb[settings.KEYWORDS_SHEET_NAME]
            rows = list(ws.iter_rows(values_only=True))
            wb.close()
            if not rows:
                print("⚠️ Keywords sheet is empty")
                return

            headers = [str(h).strip() if h else "" for h in rows[0]]
            idx = {h: i for i, h in enumerate(headers)}
            cancel_i = idx.get("Cancel")
            block_i = [idx[c] for c in ("Refund", "Trigger", "Tech Issue") if c in idx]

            for row in rows[1:]:
                if cancel_i is not None and cancel_i < len(row):
                    p = self._clean_regex(row[cancel_i])
                    if p:
                        self.cancel_patterns.append(p)
                for bi in block_i:
                    if bi < len(row):
                        p = self._clean_regex(row[bi])
                        if p:
                            self.block_patterns.append(p)

            print(
                f"✅ Eligibility loaded: {len(self.cancel_patterns)} cancel / "
                f"{len(self.block_patterns)} block patterns"
            )
        except FileNotFoundError:
            print(f"❌ CRITICAL: keywords file '{settings.KEYWORDS_FILE}' not found")
        except Exception as e:
            print(f"❌ Error loading keywords: {e}")

    def check(self, text: str, is_followup: bool = False) -> tuple[bool, str]:
        """Возвращает (eligible, reason).

        Blacklist проверяется всегда (в т.ч. на каждый ответ пользователя).
        Whitelist проверяется только для первого сообщения: на follow-up достаточно
        того, что пользователь не написал ничего из blacklist.
        """
        if not text:
            return False, "Empty text"

        for p in self.block_patterns:
            try:
                if re.search(p, text, re.IGNORECASE):
                    return False, f"Blocked by pattern: {p}"
            except re.error:
                continue

        if is_followup:
            return True, "Follow-up message passed blacklist check"

        for p in self.cancel_patterns:
            try:
                if re.search(p, text, re.IGNORECASE):
                    return True, f"Matched cancel pattern: {p}"
            except re.error:
                continue

        return False, "No cancel keywords found"


checker = EligibilityChecker()
