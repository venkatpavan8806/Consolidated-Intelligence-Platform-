import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.db.schema import init_db
from app.auth.rbac import seed_case_assignments

app = FastAPI(title="Consolidated Intelligence Platform", version="0.1.0")

# Set ALLOWED_ORIGINS (comma-separated) in production to the deployed
# frontend's exact origin(s), e.g. "https://your-app.vercel.app". Defaults
# to "*" for local/demo use. Auth is via a Bearer token header, not cookies,
# so allow_credentials stays False -- avoids the invalid wildcard-origin +
# credentials combination browsers reject.
_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
_allow_origins = ["*"] if _origins_env.strip() == "*" else [o.strip() for o in _origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.on_event("startup")
def on_startup():
    init_db(reset=False)
    seed_case_assignments()


@app.get("/api/health")
def health():
    return {"status": "ok"}
