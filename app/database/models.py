from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, HttpUrl


class User(BaseModel):
    id: int
    telegram_id: int
    username: Optional[str] = None
    language: str = "en"
    created_at: datetime

    class Config:
        from_attributes = True


class Category(BaseModel):
    id: int
    name: str
    slug: str

    class Config:
        from_attributes = True


class Item(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    category_id: int
    image: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class Stream(BaseModel):
    id: int
    item_id: int
    url: str
    quality: str
    status: str = "active"
    created_at: datetime

    class Config:
        from_attributes = True


class Favorite(BaseModel):
    id: int
    user_id: int
    item_id: int

    class Config:
        from_attributes = True


class HistoryEntry(BaseModel):
    id: int
    user_id: int
    item_id: int
    viewed_at: datetime

    class Config:
        from_attributes = True
