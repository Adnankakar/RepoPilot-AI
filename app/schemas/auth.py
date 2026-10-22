from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.DEVELOPER


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID | str
    email: EmailStr
    role: UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"