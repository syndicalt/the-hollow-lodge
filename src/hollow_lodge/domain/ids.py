from typing import NewType
from uuid import uuid4


EventId = NewType("EventId", str)
PlayerId = NewType("PlayerId", str)
CrewId = NewType("CrewId", str)
ActorId = NewType("ActorId", str)


def new_event_id() -> EventId:
    return EventId(f"evt_{uuid4().hex}")
