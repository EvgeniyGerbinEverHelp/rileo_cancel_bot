import re
from enum import Enum

from bq_client import get_customer_id_by_email

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


class UserStatus(Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    ALTERNATIVE_EMAIL_FOUND = "alternative_email_found"


def extract_emails(text: str) -> list[str]:
    """Все уникальные email из текста (с сохранением порядка)."""
    if not text:
        return []
    return list(dict.fromkeys(_EMAIL_RE.findall(text)))


def check_user_status(email: str, text: str) -> tuple[UserStatus, str | None]:
    """User Identification Flow (5.1).

    FOUND                   -> payload = customer_account_id
    ALTERNATIVE_EMAIL_FOUND -> payload = найденный альтернативный email
    NOT_FOUND               -> payload = None
    """
    customer_id = get_customer_id_by_email(email)
    if customer_id:
        print(f"✅ User found by primary email: {email}")
        return UserStatus.FOUND, customer_id

    # Основной email не найден — ищем альтернативные в теме и тексте письма.
    print(f"⚠️ Primary email '{email}' not found — searching alternative emails...")
    for alt in extract_emails(text):
        if alt.lower() == (email or "").lower():
            continue
        if get_customer_id_by_email(alt):
            print(f"✅ Alternative email found in Solidgate DB: {alt}")
            return UserStatus.ALTERNATIVE_EMAIL_FOUND, alt

    print("⚠️ No user found by primary or alternative emails")
    return UserStatus.NOT_FOUND, None
