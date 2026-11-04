"""The most important tests: many people grabbing the SAME slot at the SAME moment."""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from database import SessionLocal
from main import app
from models import Appointment
from tests.helpers import base_time, book, create_slot, make_user

PEOPLE = 10


def test_only_one_of_many_simultaneous_bookings_wins(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    slot = create_slot(client, doctor, base_time())
    patients = [make_user(client, f"p{i}@example.com") for i in range(PEOPLE)]

    barrier = threading.Barrier(PEOPLE)  # everyone fires at the same instant

    def attempt(patient):
        own_client = TestClient(app)
        barrier.wait()
        return book(own_client, patient, slot["id"]).status_code

    with ThreadPoolExecutor(max_workers=PEOPLE) as pool:
        results = list(pool.map(attempt, patients))

    assert results.count(201) == 1, results
    assert results.count(409) == PEOPLE - 1, results

    with SessionLocal() as db:
        active = db.scalar(
            select(func.count()).select_from(Appointment).where(
                Appointment.slot_id == slot["id"],
                Appointment.status.in_(["pending_payment", "confirmed"]),
            )
        )
    assert active == 1


def test_database_blocks_double_booking_even_if_the_code_is_bypassed(client):
    """Insert rows directly, skipping every check in main.py. The index must still say no."""
    from datetime import datetime, timezone

    doctor = make_user(client, "doc@example.com", "doctor")
    sam = make_user(client, "sam@example.com")
    amy = make_user(client, "amy@example.com")
    slot = create_slot(client, doctor, base_time())

    def raw(patient_id):
        return Appointment(
            slot_id=slot["id"], patient_id=patient_id, doctor_id=doctor["id"],
            status="confirmed", payment_deadline=datetime.now(timezone.utc),
        )

    with SessionLocal() as db:
        db.add(raw(sam["id"]))
        db.commit()
    with SessionLocal() as db:
        db.add(raw(amy["id"]))
        with pytest.raises(IntegrityError):
            db.commit()
