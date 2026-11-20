"""Creates the first admin account (admins can't register through the API).
Safe to run many times: it does nothing if the admin already exists."""
import os

from sqlalchemy import select

import models  # noqa: F401  (so the tables are known)
from database import Base, SessionLocal, engine
from models import User
from security import hash_password

EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
PASSWORD = os.environ.get("ADMIN_PASSWORD", "AdminPass123")

Base.metadata.create_all(bind=engine)  # make sure the tables exist first

with SessionLocal() as db:
    if db.scalar(select(User.id).where(User.email == EMAIL)):
        print("Admin already exists")
    else:
        db.add(
            User(
                email=EMAIL,
                full_name="Administrator",
                hashed_password=hash_password(PASSWORD),
                role="admin",
            )
        )
        db.commit()
        print("Admin created")
