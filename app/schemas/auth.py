import re

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=6, max_length=72)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value):
            raise ValueError("email inválido")
        return value.strip().lower()

    @field_validator("name")
    @classmethod
    def non_blank_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("el nombre no puede estar vacío")
        return stripped


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserOut(BaseModel):
    id: str
    email: str
    name: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
