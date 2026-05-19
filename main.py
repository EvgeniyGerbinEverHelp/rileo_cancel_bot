import threading

import uvicorn
from fastapi import BackgroundTasks, FastAPI

from cancel_flow import execute_cancel_flow
from config import settings
from eligibility import checker
from identification import UserStatus, check_user_status
from schemas import TicketPayload
from zendesk_client import escalate_ticket, update_ticket

app = FastAPI(title="Rileo Cancel Bot")

# In-memory мьютекс: защита от параллельных вебхуков по одному тикету
# (обработка с отменой и верификацией занимает 15+ сек).
_processing: set[int] = set()
_lock = threading.Lock()


def process_ticket(payload: TicketPayload):
    ticket_id = payload.ticket_id
    print(f"🔄 Processing ticket #{ticket_id}")

    tags_str = str(payload.tags) if payload.tags else ""
    is_followup = "bot_started" in tags_str
    full_text = f"{payload.subject or ''}\n{payload.description or ''}".strip()

    # --- 5.0 Eligibility (проверяется на каждый заход пользователя) ---
    eligible, reason = checker.check(full_text, is_followup=is_followup)
    if not eligible:
        print(f"⛔ Ticket #{ticket_id} NOT eligible: {reason}")
        if settings.CO_PILOT_MODE:
            update_ticket(
                ticket_id,
                internal_note=f"🤖 [Co-pilot] Ticket is NOT eligible.\nReason: {reason}",
            )
        else:
            escalate_ticket(
                ticket_id, f"🤖 [Bot]: Ticket is NOT eligible.\nReason: {reason}"
            )
        return

    # --- 5.1 User Identification ---
    status, data = check_user_status(payload.requester_email, full_text)

    if status == UserStatus.FOUND:
        execute_cancel_flow(ticket_id, data)
        return

    if status == UserStatus.ALTERNATIVE_EMAIL_FOUND:
        note = f"alternative email + {data}"
        if settings.CO_PILOT_MODE:
            update_ticket(
                ticket_id,
                internal_note=f"🤖 [Co-pilot] Alternative Email Flow\n{note}",
            )
        else:
            escalate_ticket(ticket_id, note, extra_tags=["bot_alternative_email_found"])
        return

    # --- UserStatus.NOT_FOUND ---
    if settings.CO_PILOT_MODE:
        update_ticket(
            ticket_id,
            internal_note="🤖 [Co-pilot] User Identification Flow\nUser not found",
        )
    else:
        escalate_ticket(ticket_id, "User not found")


def _run(payload: TicketPayload):
    try:
        process_ticket(payload)
    except Exception as e:
        print(f"❌ Unhandled error on ticket #{payload.ticket_id}: {e}")
    finally:
        with _lock:
            _processing.discard(payload.ticket_id)
        print(f"🔓 Released ticket #{payload.ticket_id}")


@app.post("/webhook")
async def webhook(payload: TicketPayload, background_tasks: BackgroundTasks):
    tags_str = str(payload.tags) if payload.tags else ""
    if any(t in tags_str for t in ("bot_escalated", "bot_finished")):
        return {"status": "ignored", "reason": "already handled by bot"}

    with _lock:
        if payload.ticket_id in _processing:
            return {"status": "ignored", "reason": "already processing"}
        _processing.add(payload.ticket_id)

    background_tasks.add_task(_run, payload)
    return {"status": "accepted"}


@app.get("/health")
def health():
    return {"status": "ok", "co_pilot_mode": settings.CO_PILOT_MODE}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=True)
