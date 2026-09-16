from typing import Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class DispositionRequest(BaseModel):
    disposition: str  # USEFUL | ALREADY_KNOWN | WRONG_PERSON
    notes: Optional[str] = None


class ReviewResolutionRequest(BaseModel):
    decision: str  # MERGE | KEEP_SEPARATE | ESCALATE
    notes: Optional[str] = None


class TamperDemoRequest(BaseModel):
    seq: int
    new_reason: str


class RestoreDemoRequest(BaseModel):
    seq: int
    original_reason: str
    original_payload_raw: str
