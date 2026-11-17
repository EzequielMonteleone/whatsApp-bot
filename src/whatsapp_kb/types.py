from dataclasses import dataclass


@dataclass(frozen=True)
class Outcome:
    text: str
    handed_off: bool
    cached: bool = False
    skipped: bool = False


@dataclass(frozen=True)
class Hit:
    id: str
    path: str
    text: str
    distance: float


@dataclass(frozen=True)
class PendingItem:
    id: int
    sender: str
    question: str
    created_at: str


@dataclass(frozen=True)
class Inbound:
    sender: str
    message_id: str
    phone_number_id: str
    kind: str
    text: str
