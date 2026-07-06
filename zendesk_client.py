import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import settings

BASE_URL = f"https://{settings.ZD_SUBDOMAIN}.zendesk.com/api/v2"
_TRANSIENT = (429, 500, 502, 503, 504)

_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3,
            backoff_factor=2,
            status_forcelist=list(_TRANSIENT),
            allowed_methods=["GET"],
        )
    ),
)


def _auth():
    return (f"{settings.ZD_EMAIL}/token", settings.ZD_TOKEN)


def _tags_request(method: str, url: str, tags: list, max_retries: int = 3):
    """PUT/DELETE на /tags.json с ретраями. Tag-операции идемпотентны, повтор безопасен.
    Бросает исключение, если все попытки провалились."""
    last_exc = None
    for attempt in range(max_retries):
        try:
            if method == "put":
                res = _session.put(url, json={"tags": tags}, auth=_auth())
            else:
                res = _session.delete(url, json={"tags": tags}, auth=_auth())
            res.raise_for_status()
            return
        except requests.exceptions.RequestException as e:
            last_exc = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and status not in _TRANSIENT:
                raise
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    if last_exc:
        raise last_exc


def update_ticket(
    ticket_id: int,
    tags_to_add: list | None = None,
    tags_to_remove: list | None = None,
    internal_note: str | None = None,
    public_reply: str | None = None,
    assignee: str | None = None,  # None | "remove"
    ticket_status: str | None = None,
    group_id: str | None = None,
    custom_fields: list | None = None,
):
    """Обновляет тикет в Zendesk: комментарий, статус, assignee, группа, поля, теги."""
    url = f"{BASE_URL}/tickets/{ticket_id}.json"
    headers = {"Content-Type": "application/json", "Connection": "close"}
    ticket: dict = {}

    bot_agent = settings.BOT_AGENT_ID

    if public_reply:
        ticket["comment"] = {"html_body": public_reply, "public": True}
        if bot_agent:
            # Ответ клиенту публикуется от имени агента-бота.
            ticket["comment"]["author_id"] = bot_agent
        if assignee != "remove":
            if bot_agent:
                ticket["assignee_id"] = bot_agent
            else:
                ticket["assignee_email"] = settings.ZD_EMAIL
            ticket["status"] = ticket_status or "pending"
    elif internal_note:
        ticket["comment"] = {"body": internal_note, "public": False}
        if bot_agent:
            ticket["comment"]["author_id"] = bot_agent

    if assignee == "remove":
        # Эскалация: снять назначение на бота, оставить тикет видимым агентам.
        ticket["assignee_id"] = None
        ticket["status"] = "open"
    elif ticket_status and "status" not in ticket:
        ticket["status"] = ticket_status

    if group_id:
        ticket["group_id"] = int(group_id)
    if custom_fields:
        ticket["custom_fields"] = custom_fields

    try:
        if ticket:
            res = _session.put(
                url, json={"ticket": ticket}, auth=_auth(), headers=headers
            )
            res.raise_for_status()
            print(
                f"✅ Ticket #{ticket_id} updated "
                f"(status={ticket.get('status', 'unchanged')})"
            )

        if tags_to_add:
            _tags_request("put", f"{BASE_URL}/tickets/{ticket_id}/tags.json", tags_to_add)
        if tags_to_remove:
            _tags_request(
                "delete", f"{BASE_URL}/tickets/{ticket_id}/tags.json", tags_to_remove
            )
    except requests.exceptions.RequestException as e:
        print(f"❌ Error updating ticket #{ticket_id}: {e}")
        resp = getattr(e, "response", None)
        if resp is not None:
            print(f"   Response: {resp.text}")
        raise


def escalate_ticket(ticket_id: int, internal_note: str, extra_tags: list | None = None):
    """Эскалация на агента (поведение тега bot_escalated по BRD):
    статус Open, снять Assignee, добавить internal note и теги."""
    tags = ["bot_started", "bot_escalated"]
    for t in extra_tags or []:
        if t not in tags:
            tags.append(t)
    update_ticket(
        ticket_id,
        tags_to_add=tags,
        internal_note=internal_note,
        assignee="remove",
        group_id=settings.GROUP_ID or None,
    )
