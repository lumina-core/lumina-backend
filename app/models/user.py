from sqlmodel import Field, SQLModel
from datetime import datetime
from typing import Optional


class UserBase(SQLModel):
    name: str = Field(max_length=100)
    email: str = Field(unique=True, index=True, max_length=255)


class User(UserBase, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default=None)


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: int
    created_at: datetime
