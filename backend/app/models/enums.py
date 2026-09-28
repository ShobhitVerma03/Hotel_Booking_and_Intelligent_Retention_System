from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "customer"
    ADMIN = "admin"
    MANAGER = "manager"


class RoomStatus(StrEnum):
    AVAILABLE = "available"
    OUT_OF_SERVICE = "out_of_service"


class BookingStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class OfferStatus(StrEnum):
    DRAFT = "draft"
    PENDING_MANAGER = "pending_manager"
    AVAILABLE_TO_CUSTOMER = "available_to_customer"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class RetentionRequestStatus(StrEnum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class DecisionAction(StrEnum):
    APPROVE = "approve"
    MODIFY = "modify"
    REJECT = "reject"
