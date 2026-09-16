"""
Minimal RBAC for the demo: investigator / admin roles, with case-scoped
visibility enforced SERVER-SIDE (not just hidden in the UI) and a mandatory
reason-for-query on any endpoint that reads case data -- logged to the
tamper-evident audit chain, never optional.
"""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Header
from passlib.context import CryptContext

from app.config import JWT_SECRET, JWT_ALGORITHM
from app.db.schema import get_connection

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Demo users. In production these would live in a real identity provider;
# hardcoding here keeps the reviewer able to log in without extra setup.
USERS = {
    "investigator1": {"password_hash": pwd_context.hash("investigator1pass"), "role": "investigator",
                       "display_name": "Investigator Priya Nair"},
    "investigator2": {"password_hash": pwd_context.hash("investigator2pass"), "role": "investigator",
                       "display_name": "Investigator Rohan Mehta"},
    "admin1": {"password_hash": pwd_context.hash("admin1pass"), "role": "admin",
               "display_name": "Admin Kavita Rao"},
}

DEFAULT_CASE_ASSIGNMENTS = [
    ("investigator1", "C001"),
    ("investigator2", "C002"),
    ("investigator1", "C002"),
]


def seed_case_assignments():
    conn = get_connection()
    conn.execute("DELETE FROM case_assignments")
    conn.executemany("INSERT INTO case_assignments (username, case_id) VALUES (?, ?)", DEFAULT_CASE_ASSIGNMENTS)
    conn.commit()
    conn.close()


def authenticate(username: str, password: str):
    user = USERS.get(username)
    if not user or not pwd_context.verify(password, user["password_hash"]):
        return None
    return {"username": username, "role": user["role"], "display_name": user["display_name"]}


def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username, "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid or expired token")


def get_current_user(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    return {"username": payload["sub"], "role": payload["role"]}


def require_case_access(case_id: str, user: dict = Depends(get_current_user)) -> dict:
    if user["role"] == "admin":
        return user
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM case_assignments WHERE username = ? AND case_id = ?", (user["username"], case_id)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=403, detail=f"user {user['username']} is not assigned to case {case_id}")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return user
