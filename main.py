from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import exists, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine, get_db
from models import Appointment, Slot, User
from schemas import (
    AppointmentOut,
    BookRequest,
    RegisterRequest,
    SlotCreate,
    SlotOut,
    TokenOut,
    UserBrief,
    UserOut,
)
from security import create_access_token, decode_token, hash_password, verify_password

MAX_SLOTS_PER_REQUEST = 48
PAYMENT_WINDOW_MINUTES = 15
EXPIRY_JOB_INTERVAL_SECONDS = 30
# Appointments in these statuses "hold" a slot
ACTIVE_STATUSES = ("pending_payment", "confirmed")


def expire_unpaid(db: Session) -> int:
    """Cancel every unpaid appointment whose payment deadline has passed.
    ONE atomic UPDATE, so it is safe even if two workers run it together."""
    now = datetime.now(timezone.utc)
    result = db.execute(
        update(Appointment)
        .where(Appointment.status == "pending_payment", Appointment.payment_deadline <= now)
        .values(status="cancelled", cancelled_at=now, cancel_reason="payment_timeout")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return result.rowcount


def expire_unpaid_job() -> None:
    """The scheduler calls this every EXPIRY_JOB_INTERVAL_SECONDS."""
    try:
        with SessionLocal() as db:
            cancelled = expire_unpaid(db)
        if cancelled:
            print(f"[scheduler] auto-cancelled {cancelled} unpaid appointment(s)")
    except Exception as e:  # never let the background thread die
        print(f"[scheduler] error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        expire_unpaid_job,
        "interval",
        seconds=EXPIRY_JOB_INTERVAL_SECONDS,
        id="expire_unpaid",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Clinic Appointment Booking API", lifespan=lifespan)
# Let the React website (running on port 5173) call this API from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = int(decode_token(token)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_roles(*roles: str):
    """Build a dependency that only lets the given roles through."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return checker


# ---------------------------------------------------------------- auth
@app.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower()

    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    if payload.role == "doctor" and not payload.specialization:
        raise HTTPException(422, "specialization is required for doctors")

    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        hashed_password=hash_password(payload.password),
        role=payload.role,
        specialization=payload.specialization if payload.role == "doctor" else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=TokenOut)
def login(
    form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    return TokenOut(access_token=create_access_token(user.id, user.role))


@app.get("/users/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# --------------------------------------------------------------- admin
@app.get("/admin/users", response_model=list[UserOut])
def list_users(
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    return db.scalars(select(User).order_by(User.id)).all()


@app.post("/admin/jobs/expire-unpaid")
def run_expiry_now(
    admin: User = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """Run the auto-cancel job by hand (it also runs on a schedule)."""
    return {"cancelled": expire_unpaid(db)}


# --------------------------------------------------------------- slots
@app.post("/slots", response_model=list[SlotOut], status_code=status.HTTP_201_CREATED)
def create_slots(
    payload: SlotCreate,
    doctor: User = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    """Define availability. Give slot_minutes to split a window into several slots."""
    start = payload.start_time.astimezone(timezone.utc)
    end = payload.end_time.astimezone(timezone.utc)

    if end <= start:
        raise HTTPException(400, "end_time must be after start_time")
    if start <= datetime.now(timezone.utc):
        raise HTTPException(400, "Slots must be in the future")

    if payload.slot_minutes is None:
        windows = [(start, end)]
    else:
        step = timedelta(minutes=payload.slot_minutes)
        if (end - start) % step:
            raise HTTPException(400, "Time window must be an exact multiple of slot_minutes")
        count = (end - start) // step
        if count > MAX_SLOTS_PER_REQUEST:
            raise HTTPException(400, f"At most {MAX_SLOTS_PER_REQUEST} slots per request")
        windows = [(start + i * step, start + (i + 1) * step) for i in range(count)]

    # Overlap rule: existing.start < new.end AND existing.end > new.start
    clash = db.scalar(
        select(Slot.id)
        .where(Slot.doctor_id == doctor.id, Slot.start_time < end, Slot.end_time > start)
        .limit(1)
    )
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Overlaps with an existing slot")

    slots = [Slot(doctor_id=doctor.id, start_time=s, end_time=e) for s, e in windows]
    db.add_all(slots)
    db.commit()
    return slots


@app.get("/slots/mine", response_model=list[SlotOut])
def my_slots(
    doctor: User = Depends(require_roles("doctor")),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(Slot).where(Slot.doctor_id == doctor.id).order_by(Slot.start_time)
    ).all()


# ------------------------------------------------------ browsing doctors
@app.get("/doctors", response_model=list[UserBrief])
def list_doctors(
    specialization: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = select(User).where(User.role == "doctor", User.is_active.is_(True))
    if specialization:
        q = q.where(User.specialization.ilike(f"%{specialization}%"))
    return db.scalars(q.order_by(User.full_name)).all()


@app.get("/doctors/{doctor_id}/slots", response_model=list[SlotOut])
def doctor_slots(
    doctor_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upcoming slots of one doctor that nobody has booked yet."""
    doctor = db.get(User, doctor_id)
    if doctor is None or doctor.role != "doctor":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doctor not found")

    is_booked = exists().where(
        Appointment.slot_id == Slot.id, Appointment.status.in_(ACTIVE_STATUSES)
    )
    return db.scalars(
        select(Slot)
        .where(
            Slot.doctor_id == doctor_id,
            Slot.start_time > datetime.now(timezone.utc),
            ~is_booked,
        )
        .order_by(Slot.start_time)
    ).all()


# -------------------------------------------------------- appointments
@app.post("/appointments", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def book_appointment(
    payload: BookRequest,
    patient: User = Depends(require_roles("patient")),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)

    # 1. Lock this slot's row: if two patients arrive together, the second
    #    waits here until the first one has finished.
    slot = db.scalar(select(Slot).where(Slot.id == payload.slot_id).with_for_update())
    if slot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Slot not found")
    if slot.start_time <= now:
        raise HTTPException(400, "Slot has already started")

    # 2. Lock this patient too, so they can't double-book themselves
    db.execute(select(User.id).where(User.id == patient.id).with_for_update())

    # 3. Is the slot already taken?
    taken = db.scalar(
        select(Appointment.id)
        .where(Appointment.slot_id == slot.id, Appointment.status.in_(ACTIVE_STATUSES))
        .limit(1)
    )
    if taken is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Slot is already booked")

    # 4. Does this patient already have something at the same time?
    clash = db.scalar(
        select(Appointment.id)
        .join(Slot, Slot.id == Appointment.slot_id)
        .where(
            Appointment.patient_id == patient.id,
            Appointment.status.in_(ACTIVE_STATUSES),
            Slot.start_time < slot.end_time,
            Slot.end_time > slot.start_time,
        )
        .limit(1)
    )
    if clash is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "You already have an appointment at this time"
        )

    # 5. Create it. The payment window can't extend past the appointment start.
    appointment = Appointment(
        slot_id=slot.id,
        patient_id=patient.id,
        doctor_id=slot.doctor_id,
        status="pending_payment",
        payment_deadline=min(now + timedelta(minutes=PAYMENT_WINDOW_MINUTES), slot.start_time),
    )
    db.add(appointment)
    try:
        db.commit()
    except IntegrityError:
        # The database's unique index caught a double-booking we somehow missed
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Slot is already booked") from None
    db.refresh(appointment)
    return appointment


@app.get("/appointments", response_model=list[AppointmentOut])
def list_appointments(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Patients see their own, doctors see theirs, admins see everything."""
    q = select(Appointment).join(Slot, Slot.id == Appointment.slot_id)
    if user.role == "patient":
        q = q.where(Appointment.patient_id == user.id)
    elif user.role == "doctor":
        q = q.where(Appointment.doctor_id == user.id)
    return db.scalars(q.order_by(Slot.start_time.desc())).unique().all()


def get_appointment_for_user(db: Session, appointment_id: int, user: User) -> Appointment:
    """Load an appointment, but only if this user is allowed to see it."""
    appointment = db.get(Appointment, appointment_id)
    allowed = appointment is not None and (
        user.role == "admin" or user.id in (appointment.patient_id, appointment.doctor_id)
    )
    if not allowed:  # 404, not 403: don't reveal that other people's IDs exist
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appointment not found")
    return appointment


@app.get("/appointments/{appointment_id}", response_model=AppointmentOut)
def get_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_appointment_for_user(db, appointment_id, user)


@app.post("/appointments/{appointment_id}/pay", response_model=AppointmentOut)
def pay_appointment(
    appointment_id: int,
    patient: User = Depends(require_roles("patient")),
    db: Session = Depends(get_db),
):
    """Mock payment. Later this is where a real provider (Stripe/Razorpay) plugs in."""
    appointment = get_appointment_for_user(db, appointment_id, patient)
    now = datetime.now(timezone.utc)

    # One conditional UPDATE: it only succeeds if the appointment is STILL unpaid
    # and the deadline has NOT passed. If the scheduler cancels it at the same
    # moment, exactly one of the two wins.
    result = db.execute(
        update(Appointment)
        .where(
            Appointment.id == appointment.id,
            Appointment.status == "pending_payment",
            Appointment.payment_deadline > now,
        )
        .values(status="confirmed", paid_at=now)
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This appointment is not awaiting payment (it may have expired)",
        )
    db.refresh(appointment)
    return appointment


@app.post("/appointments/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel_appointment(
    appointment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The patient, the doctor, or an admin can cancel. The slot becomes free again."""
    appointment = get_appointment_for_user(db, appointment_id, user)
    now = datetime.now(timezone.utc)

    if appointment.slot.start_time <= now:
        raise HTTPException(400, "This appointment has already started")

    result = db.execute(
        update(Appointment)
        .where(Appointment.id == appointment.id, Appointment.status.in_(ACTIVE_STATUSES))
        .values(status="cancelled", cancelled_at=now, cancel_reason=f"cancelled by {user.role}")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "This appointment can no longer be cancelled")
    db.refresh(appointment)
    return appointment


# ---------------------------------------------------------------- misc
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/hello/{name}")
def hello(name: str):
    return {"message": f"Hello, {name}"}
