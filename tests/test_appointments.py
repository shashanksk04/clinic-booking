from datetime import timedelta

from sqlalchemy import update

from database import SessionLocal
from main import expire_unpaid
from models import Appointment
from tests.helpers import base_time, book, create_slot, make_admin, make_user


def set_deadline(appointment_id: int, delta: timedelta):
    """Time travel: move an appointment's payment deadline relative to now."""
    from datetime import datetime, timezone

    with SessionLocal() as db:
        db.execute(
            update(Appointment)
            .where(Appointment.id == appointment_id)
            .values(payment_deadline=datetime.now(timezone.utc) + delta)
        )
        db.commit()


def test_booking_starts_unpaid_and_shows_the_doctor(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    sam = make_user(client, "sam@example.com")
    slot = create_slot(client, doctor, base_time())
    r = book(client, sam, slot["id"])
    assert r.status_code == 201
    assert r.json()["status"] == "pending_payment"
    assert r.json()["doctor"]["id"] == doctor["id"]
    assert "email" not in r.json()["doctor"]  # privacy: no doctor email leaked


def test_second_patient_cannot_book_the_same_slot(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    sam = make_user(client, "sam@example.com")
    amy = make_user(client, "amy@example.com")
    slot = create_slot(client, doctor, base_time())
    assert book(client, sam, slot["id"]).status_code == 201
    assert book(client, amy, slot["id"]).status_code == 409
    assert book(client, sam, slot["id"]).status_code == 409  # not even the same person twice


def test_patient_cannot_be_in_two_places_at_once(client):
    d1 = make_user(client, "d1@example.com", "doctor")
    d2 = make_user(client, "d2@example.com", "doctor")
    sam = make_user(client, "sam@example.com")
    s1 = create_slot(client, d1, base_time(), 60)                         # 09:00-10:00
    s2 = create_slot(client, d2, base_time() + timedelta(minutes=30), 60)  # 09:30-10:30 overlaps
    s3 = create_slot(client, d1, base_time() + timedelta(minutes=60), 30)  # 10:00-10:30 back-to-back
    assert book(client, sam, s1["id"]).status_code == 201
    assert book(client, sam, s2["id"]).status_code == 409
    assert book(client, sam, s3["id"]).status_code == 201


def test_unknown_slot_is_404(client):
    sam = make_user(client, "sam@example.com")
    assert book(client, sam, 9999).status_code == 404


def test_pay_confirms_and_cannot_be_repeated(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    sam = make_user(client, "sam@example.com")
    appt = book(client, sam, create_slot(client, doctor, base_time())["id"]).json()

    r = client.post(f"/appointments/{appt['id']}/pay", headers=sam["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"
    assert r.json()["paid_at"] is not None
    assert client.post(f"/appointments/{appt['id']}/pay", headers=sam["headers"]).status_code == 409


def test_cancel_frees_the_slot_for_someone_else(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    sam = make_user(client, "sam@example.com")
    amy = make_user(client, "amy@example.com")
    slot = create_slot(client, doctor, base_time())
    appt = book(client, sam, slot["id"]).json()

    r = client.post(f"/appointments/{appt['id']}/cancel", headers=sam["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert r.json()["cancel_reason"] == "cancelled by patient"
    assert client.post(f"/appointments/{appt['id']}/cancel", headers=sam["headers"]).status_code == 409
    assert book(client, amy, slot["id"]).status_code == 201


def test_doctor_can_cancel_but_strangers_cannot_even_see_it(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    other_doc = make_user(client, "other@example.com", "doctor")
    sam = make_user(client, "sam@example.com")
    stranger = make_user(client, "stranger@example.com")
    admin = make_admin(client)
    appt = book(client, sam, create_slot(client, doctor, base_time())["id"]).json()
    url = f"/appointments/{appt['id']}"

    assert client.get(url, headers=stranger["headers"]).status_code == 404
    assert client.get(url, headers=other_doc["headers"]).status_code == 404
    assert client.post(url + "/pay", headers=stranger["headers"]).status_code == 404
    assert client.post(url + "/cancel", headers=stranger["headers"]).status_code == 404
    assert client.get(url, headers=admin["headers"]).status_code == 200
    r = client.post(url + "/cancel", headers=doctor["headers"])
    assert r.status_code == 200
    assert r.json()["cancel_reason"] == "cancelled by doctor"


def test_unpaid_appointments_expire_and_release_the_slot(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    sam = make_user(client, "sam@example.com")
    amy = make_user(client, "amy@example.com")
    slot = create_slot(client, doctor, base_time())
    appt = book(client, sam, slot["id"]).json()

    with SessionLocal() as db:
        assert expire_unpaid(db) == 0  # deadline is still in the future

    set_deadline(appt["id"], timedelta(minutes=-1))
    # Too late to pay, even though the job hasn't run yet
    assert client.post(f"/appointments/{appt['id']}/pay", headers=sam["headers"]).status_code == 409

    with SessionLocal() as db:
        assert expire_unpaid(db) == 1
        assert expire_unpaid(db) == 0  # running it again changes nothing

    got = client.get(f"/appointments/{appt['id']}", headers=sam["headers"]).json()
    assert got["status"] == "cancelled"
    assert got["cancel_reason"] == "payment_timeout"
    assert book(client, amy, slot["id"]).status_code == 201


def test_paid_appointments_never_expire(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    sam = make_user(client, "sam@example.com")
    appt = book(client, sam, create_slot(client, doctor, base_time())["id"]).json()
    client.post(f"/appointments/{appt['id']}/pay", headers=sam["headers"])
    set_deadline(appt["id"], timedelta(hours=-1))
    with SessionLocal() as db:
        assert expire_unpaid(db) == 0
    assert client.get(f"/appointments/{appt['id']}", headers=sam["headers"]).json()["status"] == "confirmed"


def test_each_role_sees_only_its_own_appointments(client):
    d1 = make_user(client, "d1@example.com", "doctor")
    d2 = make_user(client, "d2@example.com", "doctor")
    sam = make_user(client, "sam@example.com")
    amy = make_user(client, "amy@example.com")
    admin = make_admin(client)
    book(client, sam, create_slot(client, d1, base_time())["id"])
    book(client, amy, create_slot(client, d2, base_time())["id"])

    count = lambda user: len(client.get("/appointments", headers=user["headers"]).json())
    assert (count(sam), count(amy), count(d1), count(d2), count(admin)) == (1, 1, 1, 1, 2)


def test_admin_can_run_the_expiry_job_by_hand(client):
    admin = make_admin(client)
    r = client.post("/admin/jobs/expire-unpaid", headers=admin["headers"])
    assert r.status_code == 200
    assert r.json() == {"cancelled": 0}
