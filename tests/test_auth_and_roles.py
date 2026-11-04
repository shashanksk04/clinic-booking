from database import SessionLocal
from models import User
from sqlalchemy import select
from tests.helpers import PASSWORD, base_time, create_slot, login, make_admin, make_user


def test_register_login_and_me(client):
    sam = make_user(client, "sam@example.com")
    r = client.get("/users/me", headers=sam["headers"])
    assert r.status_code == 200
    assert r.json()["email"] == "sam@example.com"
    assert "password" not in r.text


def test_password_is_stored_hashed(client):
    make_user(client, "sam@example.com")
    with SessionLocal() as db:
        stored = db.scalar(select(User.hashed_password).where(User.email == "sam@example.com"))
    assert stored != PASSWORD
    assert stored.startswith("$2b$")


def test_duplicate_email_rejected_ignoring_case(client):
    make_user(client, "sam@example.com")
    r = client.post("/auth/register", json={"email": "SAM@example.com", "password": PASSWORD, "full_name": "x"})
    assert r.status_code == 409


def test_nobody_can_register_as_admin(client):
    r = client.post(
        "/auth/register",
        json={"email": "evil@example.com", "password": PASSWORD, "full_name": "x", "role": "admin"},
    )
    assert r.status_code == 422


def test_doctor_needs_specialization(client):
    r = client.post(
        "/auth/register",
        json={"email": "d@example.com", "password": PASSWORD, "full_name": "x", "role": "doctor"},
    )
    assert r.status_code == 422


def test_short_password_rejected(client):
    r = client.post("/auth/register", json={"email": "a@example.com", "password": "abc", "full_name": "x"})
    assert r.status_code == 422


def test_wrong_password_and_unknown_user_give_the_same_error(client):
    make_user(client, "sam@example.com")
    r1 = client.post("/auth/login", data={"username": "sam@example.com", "password": "wrong-wrong"})
    r2 = client.post("/auth/login", data={"username": "ghost@example.com", "password": "wrong-wrong"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_protected_routes_need_a_valid_token(client):
    assert client.get("/users/me").status_code == 401
    assert client.get("/users/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_roles_are_enforced(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    patient = make_user(client, "pat@example.com")
    admin = make_admin(client)
    slot = create_slot(client, doctor, base_time())

    body = {"start_time": base_time(3).isoformat(), "end_time": base_time(3).replace(hour=10).isoformat()}
    assert client.post("/slots", json=body, headers=patient["headers"]).status_code == 403
    assert client.post("/appointments", json={"slot_id": slot["id"]}, headers=doctor["headers"]).status_code == 403
    assert client.get("/admin/users", headers=patient["headers"]).status_code == 403
    assert client.get("/admin/users", headers=doctor["headers"]).status_code == 403
    assert client.get("/admin/users", headers=admin["headers"]).status_code == 200
    assert client.post("/admin/jobs/expire-unpaid", headers=patient["headers"]).status_code == 403
