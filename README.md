# Clinic Appointment Booking System

A full-stack web app where **doctors publish time slots**, **patients book them**, and the system
guarantees **no double-booking**, **role-based access**, and **automatic cancellation of unpaid appointments**.

**Stack:** React + TypeScript (Vite) · FastAPI · PostgreSQL · SQLAlchemy 2.0 · JWT auth · APScheduler · pytest · Docker · GitHub Actions

```
Browser (React + TS, :5173)  ──HTTP/JSON──▶  FastAPI (:8000)  ──SQL──▶  PostgreSQL
                                               └─ background job: cancels unpaid bookings
```

## Features

- **Auth:** register / login with JWT, bcrypt-hashed passwords
- **Roles:** Patient, Doctor, Admin (enforced on the server, not just hidden in the UI)
- **Doctors** create availability, either one slot or a whole window split into equal slots; overlapping slots are rejected
- **Patients** browse doctors (filter by specialization), see only free slots, book, pay, cancel
- **No double-booking**, even when many people book the same slot at the same instant
- **Auto-cancel:** unpaid appointments are cancelled after 15 minutes by a background job and the slot is released
- **Admin** can list users and run the auto-cancel job manually

## Run it locally

**Requirements:** Python 3.12+, Node.js 20+, PostgreSQL 16+.

**1. Database** (in `psql`, as the `postgres` superuser):

```sql
CREATE USER clinic WITH PASSWORD 'clinic';
CREATE DATABASE clinic OWNER clinic;
CREATE DATABASE clinic_test OWNER clinic;   -- used by the automated tests
```

**2. Backend**

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash. macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python create_admin.py               # creates admin@example.com / AdminPass123
uvicorn main:app --reload            # API docs: http://localhost:8000/docs
```

**3. Frontend** (second terminal)

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

**Demo accounts:** register a doctor and a patient on the sign-up page, or use the admin above.

## Run it with Docker

Needs Docker Desktop. No secrets live in the repository, so create your own `.env` first:

```bash
cp .env.example .env     # then open .env and set your own values (see the comments inside)
docker compose up --build
```

Website: http://localhost:5173 · API docs: http://localhost:8000/docs · Admin: the `ADMIN_EMAIL` / `ADMIN_PASSWORD` from your `.env`

Stop any local servers first (they use the same ports). `docker compose down -v` stops everything and deletes the database volume.
What makes the containers safer is explained in [DEVOPS.md](DEVOPS.md).

## Tests and code quality

```bash
python -m pytest -v --cov --cov-fail-under=85    # 30 tests + coverage gate
ruff check .                                     # lint
pip-audit -r requirements.txt                    # known vulnerabilities in Python packages
```

The tests run against a separate `clinic_test` database (each test starts with empty tables).
They cover auth, roles, slot overlap rules, booking, payment, cancellation, auto-expiry, and concurrency.

## CI/CD pipeline

GitHub Actions runs on every push and pull request (`.github/workflows/ci.yml`):

| Stage | What it checks |
|---|---|
| backend | ruff lint, 30 tests against PostgreSQL, coverage of at least 85%, pip-audit |
| frontend | TypeScript type-check, production build, npm audit |
| docker | hadolint on both Dockerfiles, builds the images, starts the whole stack and smoke-tests it, Trivy image scan |
| publish | on `main` only: pushes the images to GitHub Container Registry |

Details, findings and the fixes they led to are in [DEVOPS.md](DEVOPS.md).

## How the important parts work

**Double-booking is prevented by the database, not just by code.**
The `appointments` table has a *partial unique index* on `slot_id` that only counts rows whose status is
`pending_payment` or `confirmed`. Whatever the application does, PostgreSQL will never hold two active
appointments for one slot. Cancelled and expired rows drop out of the index, so the slot can be booked again.
On top of that, booking locks the slot row (`SELECT ... FOR UPDATE`) so concurrent requests queue up and get a
clean `409 Conflict`. One test fires 10 simultaneous bookings at one slot and asserts exactly one succeeds;
another inserts rows directly (bypassing the API) to prove the index alone is enough.

**Overlapping time ranges.** Two ranges overlap when `a.start < b.end AND a.end > b.start`. Back-to-back
slots (09:00-09:30 then 09:30-10:00) are allowed. The same rule stops a doctor from publishing overlapping slots
and stops a patient from booking two appointments at the same time.

**Payment vs. auto-cancel race.** "Pay" and "expire" are each a single conditional `UPDATE`
(`... WHERE status = 'pending_payment' AND payment_deadline > now`). The database runs one first; the other
then matches zero rows. So an appointment can never be both paid and cancelled.

**Security details.** Passwords are bcrypt-hashed. Login returns the same error for an unknown email and a wrong
password. Role and active status are re-read from the database on every request, so disabling a user takes
effect immediately. Admins cannot self-register. Other people's appointments return `404`, not `403`, so IDs
are not leaked. All times are timezone-aware and stored in UTC.

## API overview

| Method | Path | Who | Purpose |
|---|---|---|---|
| POST | `/auth/register` | public | Register as patient or doctor |
| POST | `/auth/login` | public | Get a JWT |
| GET | `/users/me` | any | Current user |
| GET | `/doctors` | any | List doctors (`?specialization=`) |
| GET | `/doctors/{id}/slots` | any | A doctor's free upcoming slots |
| POST | `/slots` | doctor | Create a slot, or split a window with `slot_minutes` |
| GET | `/slots/mine` | doctor | My slots |
| POST | `/appointments` | patient | Book a slot (starts as `pending_payment`) |
| GET | `/appointments` | any | My appointments (admin: all) |
| GET | `/appointments/{id}` | participant / admin | One appointment |
| POST | `/appointments/{id}/pay` | patient | Mock payment, becomes `confirmed` |
| POST | `/appointments/{id}/cancel` | patient / doctor / admin | Cancel and free the slot |
| GET | `/admin/users` | admin | List all users |
| POST | `/admin/jobs/expire-unpaid` | admin | Run the auto-cancel job now |

Appointment lifecycle: `pending_payment → confirmed`, or `→ cancelled` (by a user, or automatically on timeout).

## Project structure

```
main.py  models.py  schemas.py  database.py  security.py   FastAPI backend
create_admin.py                                            creates the first admin
tests/                                                     pytest suite (30 tests)
frontend/src/                                              React + TypeScript app
  api.ts (all API calls)  types.ts  auth.tsx  pages/
```

## Limitations and next steps

- Payment is mocked. A real provider (Stripe / Razorpay) would call the same conditional update from a signed webhook.
- Tables are created with `create_all`; a real deployment would use Alembic migrations.
- The scheduler runs inside the API process. At larger scale it would move to a worker (Celery); the job is
  already idempotent, so running it from several places is safe.
- The JWT is stored in `localStorage` for simplicity; an `httpOnly` cookie would be safer in production.
- Not built yet: doctors marking appointments as completed, admin user disable/enable screens, email reminders.
