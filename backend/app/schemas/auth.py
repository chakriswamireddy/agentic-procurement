"""Pydantic schemas for authentication and user sessions."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=256, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=1, max_length=128)


class UserInfo(BaseModel):
    id: str
    email: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(default=1800, description="Token lifetime in seconds")
    user: UserInfo


class AuthenticatedUser(BaseModel):
    id: str
    email: str
    role: str
