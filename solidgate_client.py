import base64
import hashlib
import hmac
import json

import requests

from config import settings

BASE_URL = "https://subscriptions.solidgate.com/api/v1/subscription"
TIMEOUT = 30


def _signature(body: str) -> str:
    """HMAC-SHA512 подпись запроса для Solidgate."""
    data = settings.SOLIDGATE_PUBLIC_KEY + body + settings.SOLIDGATE_PUBLIC_KEY
    digest = hmac.new(
        settings.SOLIDGATE_SECRET_KEY.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha512,
    ).digest()
    return base64.b64encode(digest.hex().encode("utf-8")).decode("utf-8")


def _headers(body: str) -> dict:
    return {
        "merchant": settings.SOLIDGATE_PUBLIC_KEY,
        "signature": _signature(body),
        "Content-Type": "application/json",
    }


def get_customer_subscriptions(customer_id: str) -> dict | None:
    """Подписки клиента из Solidgate. None — ошибка API; {} — подписок нет."""
    body = json.dumps({"customer_account_id": customer_id}, separators=(",", ":"))
    try:
        resp = requests.post(
            f"{BASE_URL}/list", headers=_headers(body), data=body, timeout=TIMEOUT
        )
        if resp.status_code == 200:
            data = resp.json()
            return data if isinstance(data, dict) else {}
        print(f"❌ Solidgate list failed [{resp.status_code}]: {resp.text}")
        return None
    except Exception as e:
        print(f"❌ Solidgate list error: {e}")
        return None


def cancel_subscription(subscription_id: str, hard: bool) -> bool:
    """Отмена подписки в Solidgate.

    hard=False -> Soft Cancel (force=false): отмена в конце оплаченного периода.
    hard=True  -> Hard Cancel / Cancel Now (force=true): немедленная отмена.
    """
    body = json.dumps(
        {
            "subscription_id": subscription_id,
            "force": hard,
            "cancel_code": settings.CANCEL_CODE,
        },
        separators=(",", ":"),
    )
    mode = "HARD" if hard else "SOFT"
    try:
        resp = requests.post(
            f"{BASE_URL}/cancel", headers=_headers(body), data=body, timeout=TIMEOUT
        )
        if resp.status_code == 200:
            print(f"✅ {mode} cancel ok: {subscription_id}")
            return True
        print(
            f"❌ {mode} cancel failed [{resp.status_code}] {subscription_id}: {resp.text}"
        )
        return False
    except Exception as e:
        print(f"❌ {mode} cancel error {subscription_id}: {e}")
        return False


def parse_subscription(raw: dict) -> dict:
    """Достаёт ключевые поля подписки независимо от формы ответа Solidgate
    (плоский объект либо вложенный под ключом 'subscription')."""
    if not isinstance(raw, dict):
        return {
            "status": "",
            "cancelled_at": None,
            "cancellation_requested_at": None,
            "payment_type": None,
        }
    sub = raw.get("subscription", raw)
    if not isinstance(sub, dict):
        sub = raw
    return {
        "status": str(sub.get("status", "")).strip().lower(),
        "cancelled_at": sub.get("cancelled_at"),
        "cancellation_requested_at": sub.get("cancellation_requested_at"),
        "payment_type": sub.get("payment_type"),
    }
