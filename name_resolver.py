"""Определение имени клиента для приветствия в макросе.

Zendesk подставляет в {{ticket.requester.first_name}} имя из профиля, а оно часто
мусорное: ник ("251 /"), сам email ("tassilo.greimel@t-online.de") или капс ("VIKA").
Поэтому имя выбирает бот: сначала из подписи в тексте письма, затем из профиля
(если оно вообще похоже на имя), и в любом случае нормализует регистр.
Если пригодного имени нет — приветствие обезличенное ("Hi there,").
"""

import re

PLACEHOLDER_RE = re.compile(r"\{\{\s*ticket\.requester\.first_name\s*\}\}")
FALLBACK_NAME = "there"

# Буква любого алфавита (не цифра и не подчёркивание).
_L = r"[^\W\d_]"
_NAME_TOKEN = rf"{_L}{{2,}}(?:['’\-]{_L}{{2,}})*"

# Слова, которые формально выглядят как имя, но им не являются.
_NOT_A_NAME = {
    "team", "support", "customer", "service", "sir", "madam", "hello", "hi",
    "dear", "thanks", "thank", "thankyou", "regards", "regard", "sincerely",
    "cheers", "greetings", "best", "kind", "warm", "wishes", "yours", "truly",
    "you", "your", "me", "my", "all", "everyone", "admin", "user", "client",
    "guys", "please", "subscription", "account", "cancel", "cancellation",
    "payment", "refund", "money", "help", "info", "noreply", "and", "the",
    "mr", "mrs", "ms", "miss", "dr", "sent", "from", "on", "via", "gracias",
    "saludos", "danke", "merci", "grazie", "rileo", "ruut", "wisey",
}

# Прощания, после которых человек обычно подписывается именем.
_SIGNOFF = (
    r"(?:thank\s*you|thanks|best\s+regards|kind\s+regards|warm\s+regards|"
    r"regards|sincerely|cheers|yours\s+(?:truly|sincerely)|best\s+wishes|"
    r"cordialement|salutations|atentamente|un\s+saludo|saludos|gracias|"
    r"grazie|cordiali\s+saluti|distinti\s+saluti|"
    r"mit\s+freundlichen\s+gr(?:ü|ue)ßen|viele\s+gr(?:ü|ue)ße|danke)"
)

# После прощания допускаем разделители вида ",", "&", "-", перевод строки.
_SIGNATURE_RE = re.compile(
    rf"\b{_SIGNOFF}\b[\s,;:!.&\-–—]*({_NAME_TOKEN}(?:\s+{_NAME_TOKEN})?)",
    re.IGNORECASE,
)


def _is_plausible_name(token: str) -> bool:
    token = token.strip().strip("'’-")
    if len(token) < 2 or len(token) > 30:
        return False
    if "@" in token or any(ch.isdigit() for ch in token):
        return False
    return token.lower() not in _NOT_A_NAME


def normalize_case(name: str) -> str:
    """VIKA -> Vika, maydela -> Maydela, jean-luc -> Jean-Luc.

    Имя со смешанным регистром (McDonald, O'Brien) не трогаем — человек написал
    его осознанно. Для не-латиницы (CJK, кириллица) регистр меняется корректно
    средствами Python либо остаётся как есть.
    """
    if not (name.isupper() or name.islower()):
        return name
    return re.sub(
        rf"{_L}+", lambda m: m.group(0)[:1].upper() + m.group(0)[1:].lower(), name
    )


def name_from_text(text: str) -> str | None:
    """Имя из подписи в теле письма ("Thanks, Tanvir" -> Tanvir)."""
    if not text:
        return None
    # Отсекаем процитированную переписку — там чужие подписи.
    cut = re.split(r"\n\s*(?:>|On .{0,80}\bwrote:|-{3,}\s*Original)", text, maxsplit=1)[0]
    for match in _SIGNATURE_RE.finditer(cut or text):
        first = match.group(1).split()[0]
        if _is_plausible_name(first):
            return first
    return None


def name_from_profile(profile_name: str | None) -> str | None:
    """Имя из профиля Zendesk — только если это действительно имя, а не ник/email."""
    if not profile_name:
        return None
    raw = profile_name.strip()
    if "@" in raw or any(ch.isdigit() for ch in raw):
        return None
    parts = raw.split()
    if not parts:
        return None
    first = parts[0]
    return first if _is_plausible_name(first) else None


def resolve_first_name(ticket_text: str, profile_name: str | None = None) -> str | None:
    """Имя для приветствия: подпись в тексте важнее имени в профиле."""
    for candidate in (name_from_text(ticket_text), name_from_profile(profile_name)):
        if candidate:
            return normalize_case(candidate)
    return None


def personalize(macro_text: str, first_name: str | None) -> str:
    """Подставляет имя вместо плейсхолдера Zendesk в тексте макроса."""
    if not macro_text:
        return macro_text
    return PLACEHOLDER_RE.sub(first_name or FALLBACK_NAME, macro_text)
