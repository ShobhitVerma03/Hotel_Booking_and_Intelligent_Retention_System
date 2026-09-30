from sqlalchemy.orm import Session
from backend.app.models.entities import AuditLog
import logging

logger = logging.getLogger(__name__)


def log_event(db: Session, event_type: str, entity_type: str, entity_id: int | str, details: dict | None = None, actor_user_id: int | None = None) -> None:
    db.add(AuditLog(actor_user_id=actor_user_id, event_type=event_type, entity_type=entity_type, entity_id=str(entity_id), details=details))
    logger.info("audit event=%s entity=%s entity_id=%s actor_id=%s", event_type, entity_type, entity_id, actor_user_id)
