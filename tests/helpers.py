from datetime import datetime, timedelta, timezone

from database import SessionLocal
from models import User
from security import hash_password

PASSWORD = "Password123"


def make_user(client, email: str, role: str = "patient", specialization: str = "Cardiology") -> dict:
    """Register through the API, log in, and return {'headers': ..., 'id': ...}."""
    body = {"email": email, "password": PASSWORD, "full_name": email.split("@")[0], "role": role}
    if role == "doctor":
        body["specialization"] = specialization
    r = client.post("/auth/register", json=body)
    assert r.status_code == 201, r.text
    return {"headers": login(client, email), "id": r.json()["id"]}


def login(client, email: str) -> dict:
    r = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def make_admin(client, email: str = "admin@example.com") -> dict:
    """Admins can't register through the API, so insert directly."""
    with SessionLocal() as db:
        user = User(email=email, full_name="Admin", hashed_password=hash_password(PASSWORD), role="admin")
        db.add(user)
        db.commit()
        user_id = user.id
    return {"headers": login(client, email), "id": user_id}


def base_time(days: int = 2) -> datetime:
    """09:00 UTC, a few days from now (slots must be in the future)."""
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )


def create_slot(client, doctor: dict, start: datetime, minutes: int = 30) -> dict:
    r = client.post(
        "/slots",
        json={"start_time": start.isoformat(), "end_time": (start + timedelta(minutes=minutes)).isoformat()},
        headers=doctor["headers"],
    )
    assert r.status_code == 201, r.text
    return r.json()[0]


def book(client, patient: dict, slot_id: int):
    return client.post("/appointments", json={"slot_id": slot_id}, headers=patient["headers"])
