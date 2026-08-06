import time

from config import settings
from macros_loader import MACROS_DB
from solidgate_client import (
    cancel_subscription,
    get_customer_subscriptions,
    parse_subscription,
)
from name_resolver import personalize, resolve_first_name
from zendesk_client import escalate_ticket, get_requester_name, update_ticket

# Теги-макросы из таблицы (вкладка Macros)
TAG_STEP_1 = "rileo_cancellation_bot"               # Step 1.1 Cancel
TAG_STEP_2 = "rileo_cancellation_confirmation_bot"  # Step 1.2 Confirm Cancellation

VERIFY_DELAY_SEC = 10
_CANCELLED_STATUSES = ("cancelled", "canceled")


def _custom_fields() -> list:
    """Поля Zendesk, которые бот заполняет при завершении флоу."""
    cf = []
    if settings.REQUEST_TYPE_VALUE:
        cf.append({"id": settings.FIELD_REQUEST_TYPE, "value": settings.REQUEST_TYPE_VALUE})
    if settings.PRODUCT_VALUE:
        cf.append({"id": settings.FIELD_PRODUCT, "value": settings.PRODUCT_VALUE})
    return cf


def _is_cancelled(sub: dict) -> bool:
    """Подписка уже отменена (hard) либо запланирована к отмене (soft).

    После soft cancel статус остаётся active/paused, поэтому ориентируемся
    на cancelled_at / cancellation_requested_at, а не только на статус.
    """
    if sub["status"] in _CANCELLED_STATUSES:
        return True
    return bool(sub.get("cancelled_at") or sub.get("cancellation_requested_at"))


def execute_cancel_flow(ticket_id: int, customer_id: str, ticket_text: str = ""):
    """Cancel Subscription Flow (5.2.1 / 5.2.2)."""
    print(f"🚀 Cancel flow for customer {customer_id}")
    subs = get_customer_subscriptions(customer_id)

    if subs is None:
        if settings.CO_PILOT_MODE:
            update_ticket(
                ticket_id,
                internal_note="🤖 [Co-pilot] Solidgate API error — would escalate.",
            )
        else:
            escalate_ticket(
                ticket_id,
                "🤖 [Bot]: Solidgate API error — could not fetch subscriptions.",
            )
        return

    # Классификация подписок: какие отменять и как.
    #   active     -> soft cancel (отмена в конце оплаченного периода);
    #   paused     -> hard cancel — у paused-подписки нет активного биллинг-периода,
    #                 soft cancel к ней неприменим (Solidgate вернёт 200, но не отменит);
    #   redemption -> hard cancel (по BRD).
    to_cancel: list[tuple[str, bool]] = []  # (subscription_id, hard)
    for sub_id, raw in subs.items():
        s = parse_subscription(raw)
        if _is_cancelled(s):
            print(f"  • {sub_id}: {s['status']} — already cancelled, skip")
            continue
        if s["status"] in ("redemption", "paused"):
            to_cancel.append((sub_id, True))
            print(f"  • {sub_id}: {s['status']} — HARD cancel")
        elif s["status"] == "active":
            to_cancel.append((sub_id, False))
            print(f"  • {sub_id}: active — SOFT cancel")
        else:
            print(f"  • {sub_id}: {s['status']} — no action")

    # --- Нечего отменять -> Step 1.2 (подписка уже отменена) ---
    if not to_cancel:
        macro = MACROS_DB.get(TAG_STEP_2, {})
        if settings.CO_PILOT_MODE:
            update_ticket(
                ticket_id,
                internal_note=_copilot_note(
                    "Step 1.2 — subscription already cancelled", macro, []
                ),
            )
            return
        _send_macro(ticket_id, macro, TAG_STEP_2, ticket_text)
        return

    # --- Co-pilot: только описываем предполагаемое действие, ничего не отменяем ---
    if settings.CO_PILOT_MODE:
        update_ticket(
            ticket_id,
            internal_note=_copilot_note(
                "Step 1.1 — cancel subscription", MACROS_DB.get(TAG_STEP_1, {}), to_cancel
            ),
        )
        return

    # --- Полный режим: отменяем подписки ---
    for sub_id, hard in to_cancel:
        cancel_subscription(sub_id, hard)

    print(f"⏳ Waiting {VERIFY_DELAY_SEC}s before verification...")
    time.sleep(VERIFY_DELAY_SEC)

    # Подтверждаем отмену по факту (cancelled_at / статус в Solidgate), а НЕ по
    # коду ответа: Solidgate может вернуть 200, фактически не отменив подписку.
    if _verify(customer_id, [sid for sid, _ in to_cancel]):
        print("✅ Cancellation confirmed")
        _send_macro(ticket_id, MACROS_DB.get(TAG_STEP_1, {}), TAG_STEP_1, ticket_text)
    else:
        ids = ", ".join(sid for sid, _ in to_cancel)
        print(f"❌ Cancellation NOT confirmed for: {ids}")
        escalate_ticket(
            ticket_id,
            f"🤖 [Bot]: subscription cancellation failed for: {ids}",
            extra_tags=["bot_subscription_cancellation_failed"],
        )


def _verify(customer_id: str, sub_ids: list[str]) -> bool:
    """Перепроверка через Solidgate API: зафиксирована ли отмена у всех подписок."""
    subs = get_customer_subscriptions(customer_id)
    if not subs:
        return False
    for sid in sub_ids:
        raw = subs.get(sid)
        if not raw or not _is_cancelled(parse_subscription(raw)):
            print(f"  ⚠️ {sid}: cancellation not confirmed via API")
            return False
    return True


def _send_macro(ticket_id: int, macro: dict, macro_tag: str, ticket_text: str = ""):
    """Отправляет ответ-макрос клиенту и решает тикет (Step 1.1 / 1.2)."""
    text = macro.get("text") or "Your subscription has been cancelled."
    # Имя подставляем сами: плейсхолдер Zendesk тянет ник/email из профиля.
    first_name = resolve_first_name(ticket_text, get_requester_name(ticket_id))
    print(f"👤 Greeting name for #{ticket_id}: {first_name or '(обезличенное)'}")
    text = personalize(text, first_name)
    tags = [macro_tag, "bot_started", "bot_finished"]
    try:
        update_ticket(
            ticket_id,
            tags_to_add=tags,
            public_reply=text,
            ticket_status="solved",
            group_id=settings.GROUP_ID or None,
            brand_id=settings.BRAND_ID or None,
            custom_fields=_custom_fields(),
        )
    except Exception as e:
        # Zendesk мог частично выполнить запрос (коммент запостился, статус — нет).
        # Не пересылаем public_reply повторно, чтобы клиент не получил дубль ответа.
        print(f"⚠️ Zendesk update failed ({e}). Fixing status/tags without reposting reply.")
        update_ticket(
            ticket_id,
            tags_to_add=tags + ["bot_escalated"],
            assignee="remove",
            # Тикет мог уже уйти в Solved — форсим Open, иначе агенты его не увидят.
            ticket_status="open",
        )


def _copilot_note(action: str, macro: dict, to_cancel: list) -> str:
    """Internal note для режима co-pilot — что бот сделал бы в полном режиме."""
    lines = [
        "🤖 [Co-pilot] Cancel Subscription Flow",
        f"Proposed action: {action}",
    ]
    if to_cancel:
        items = ", ".join(
            f"{sid} ({'HARD' if hard else 'SOFT'})" for sid, hard in to_cancel
        )
        lines.append(f"Subscriptions to cancel: {items}")
    lines.append(f"Macro: {macro.get('name', '—')}")
    lines.append("")
    lines.append("--- Reply that would be sent to the customer ---")
    lines.append(macro.get("text", "").replace("<br>", "\n"))
    return "\n".join(lines)
