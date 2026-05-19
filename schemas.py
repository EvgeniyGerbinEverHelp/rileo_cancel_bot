from typing import Optional, Union

from pydantic import BaseModel


class TicketPayload(BaseModel):
    """Полезная нагрузка вебхука Zendesk."""

    ticket_id: int
    subject: Optional[str] = ""
    description: str
    requester_email: str
    tags: Optional[Union[str, list]] = ""

    model_config = {
        "json_schema_extra": {
            "example": {
                "ticket_id": 105,
                "subject": "Cancel my subscription",
                "description": "Please cancel my subscription.",
                "requester_email": "client@example.com",
                "tags": ["new_request"],
            }
        }
    }
