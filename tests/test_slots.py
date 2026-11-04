from datetime import timedelta, timezone

from tests.helpers import base_time, book, create_slot, make_user


def post_slots(client, doctor, start, end, **extra):
    return client.post(
        "/slots",
        json={"start_time": start.isoformat(), "end_time": end.isoformat(), **extra},
        headers=doctor["headers"],
    )


def test_window_is_split_into_slots(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    start = base_time()
    r = post_slots(client, doctor, start, start + timedelta(hours=2), slot_minutes=30)
    assert r.status_code == 201
    assert len(r.json()) == 4


def test_window_must_divide_evenly(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    start = base_time()
    assert post_slots(client, doctor, start, start + timedelta(minutes=50), slot_minutes=30).status_code == 400


def test_overlap_is_rejected_but_back_to_back_is_allowed(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    start = base_time()
    create_slot(client, doctor, start, 30)  # 09:00 - 09:30

    assert post_slots(client, doctor, start, start + timedelta(minutes=30)).status_code == 409  # identical
    assert post_slots(client, doctor, start + timedelta(minutes=15), start + timedelta(minutes=45)).status_code == 409  # partial
    assert post_slots(client, doctor, start + timedelta(minutes=30), start + timedelta(minutes=60)).status_code == 201  # touching


def test_two_doctors_can_have_the_same_time(client):
    d1 = make_user(client, "d1@example.com", "doctor")
    d2 = make_user(client, "d2@example.com", "doctor")
    create_slot(client, d1, base_time())
    create_slot(client, d2, base_time())


def test_past_slots_and_naive_times_are_rejected(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    past = base_time(-1)
    assert post_slots(client, doctor, past, past + timedelta(minutes=30)).status_code == 400
    r = client.post(
        "/slots",
        json={"start_time": "2099-01-01T09:00:00", "end_time": "2099-01-01T09:30:00"},  # no timezone
        headers=doctor["headers"],
    )
    assert r.status_code == 422


def test_different_timezone_offsets_mean_the_same_instant(client):
    from datetime import timezone as tz

    doctor = make_user(client, "doc@example.com", "doctor")
    start = base_time()
    india = start.astimezone(tz(timedelta(hours=5, minutes=30)))
    assert post_slots(client, doctor, india, india + timedelta(minutes=30)).status_code == 201
    # the same moment written in UTC must clash
    assert post_slots(client, doctor, start, start + timedelta(minutes=30)).status_code == 409


def test_patients_only_see_free_slots(client):
    doctor = make_user(client, "doc@example.com", "doctor")
    sam = make_user(client, "sam@example.com")
    taken = create_slot(client, doctor, base_time())
    create_slot(client, doctor, base_time() + timedelta(hours=1))
    book(client, sam, taken["id"])

    free = client.get(f"/doctors/{doctor['id']}/slots", headers=sam["headers"]).json()
    assert len(free) == 1
    assert free[0]["id"] != taken["id"]


def test_doctor_listing_can_filter_by_specialization(client):
    make_user(client, "c@example.com", "doctor", "Cardiology")
    make_user(client, "n@example.com", "doctor", "Neurology")
    sam = make_user(client, "sam@example.com")
    r = client.get("/doctors?specialization=neuro", headers=sam["headers"])
    assert [d["specialization"] for d in r.json()] == ["Neurology"]
