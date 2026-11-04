from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)
    full_name: str = Field(min_length=1, max_length=120)
    role: Literal["patient", "doctor"] = "patient"
    specialization: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: str
    specialization: str | None
    is_active: bool
    created_at: datetime


class UserBrief(BaseModel):
    """A safe, short view of a user (no email) for showing inside other objects."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    specialization: str | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SlotCreate(BaseModel):
    start_time: AwareDatetime
    end_time: AwareDatetime
    slot_minutes: int | None = Field(default=None, ge=5, le=240)


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    start_time: datetime
    end_time: datetime


class BookRequest(BaseModel):
    slot_id: int


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    slot: SlotOut
    patient: UserBrief
    doctor: UserBrief
    payment_deadline: datetime
    paid_at: datetime | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    created_at: datetime