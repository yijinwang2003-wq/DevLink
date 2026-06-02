from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChatRoomCreate(BaseModel):
    recipient_username: str = Field(min_length=3, max_length=50)


class ChatRoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_low_id: UUID
    user_high_id: UUID
    created_at: datetime
    updated_at: datetime


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    room_id: UUID
    sender_id: UUID
    content: str
    message_type: str
    created_at: datetime


class ChatMessageHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sender_id: UUID
    content: str
    message_type: str
    created_at: datetime


class ChatMessageEvent(BaseModel):
    type: str = "message"
    content: str
    sender_id: UUID
    timestamp: datetime
