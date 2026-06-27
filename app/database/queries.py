from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any

from app.database.supabase import get_client
from app.database.models import User, Category, Item, Stream, Favorite, HistoryEntry
from app.utils.logging import get_logger

logger = get_logger(__name__)


# ─────────────────────────── Users ────────────────────────────

async def get_or_create_user(telegram_id: int, username: Optional[str]) -> User:
    db = await get_client()
    res = await db.table("users").select("*").eq("telegram_id", telegram_id).limit(1).execute()
    if res.data:
        return User(**res.data[0])
    now = datetime.utcnow().isoformat()
    insert = {
        "telegram_id": telegram_id,
        "username": username,
        "language": "en",
        "created_at": now,
    }
    res = await db.table("users").insert(insert).execute()
    return User(**res.data[0])


async def update_user_language(telegram_id: int, language: str) -> None:
    db = await get_client()
    await db.table("users").update({"language": language}).eq("telegram_id", telegram_id).execute()


async def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
    db = await get_client()
    res = await db.table("users").select("*").eq("telegram_id", telegram_id).limit(1).execute()
    return User(**res.data[0]) if res.data else None


async def get_all_users() -> List[User]:
    db = await get_client()
    res = await db.table("users").select("*").execute()
    return [User(**row) for row in res.data]


async def count_users() -> int:
    db = await get_client()
    res = await db.table("users").select("id", count="exact").execute()
    return res.count or 0


# ─────────────────────────── Categories ───────────────────────

async def get_categories() -> List[Category]:
    db = await get_client()
    res = await db.table("categories").select("*").order("name").execute()
    return [Category(**row) for row in res.data]


async def get_category_by_id(category_id: int) -> Optional[Category]:
    db = await get_client()
    res = await db.table("categories").select("*").eq("id", category_id).limit(1).execute()
    return Category(**res.data[0]) if res.data else None


async def create_category(name: str, slug: str) -> Category:
    db = await get_client()
    res = await db.table("categories").insert({"name": name, "slug": slug}).execute()
    return Category(**res.data[0])


# ─────────────────────────── Items ────────────────────────────

async def get_items_by_category(
    category_id: int, offset: int = 0, limit: int = 5
) -> List[Item]:
    db = await get_client()
    res = (
        await db.table("items")
        .select("*")
        .eq("category_id", category_id)
        .order("title")
        .range(offset, offset + limit - 1)
        .execute()
    )
    return [Item(**row) for row in res.data]


async def count_items_by_category(category_id: int) -> int:
    db = await get_client()
    res = await db.table("items").select("id", count="exact").eq("category_id", category_id).execute()
    return res.count or 0


async def get_item_by_id(item_id: int) -> Optional[Item]:
    db = await get_client()
    res = await db.table("items").select("*").eq("id", item_id).limit(1).execute()
    return Item(**res.data[0]) if res.data else None


async def search_items(query: str, offset: int = 0, limit: int = 5) -> List[Item]:
    db = await get_client()
    res = (
        await db.table("items")
        .select("*")
        .ilike("title", f"%{query}%")
        .order("title")
        .range(offset, offset + limit - 1)
        .execute()
    )
    return [Item(**row) for row in res.data]


async def count_search_results(query: str) -> int:
    db = await get_client()
    res = await db.table("items").select("id", count="exact").ilike("title", f"%{query}%").execute()
    return res.count or 0


async def create_item(
    title: str,
    description: str,
    category_id: int,
    image: Optional[str] = None,
) -> Item:
    db = await get_client()
    now = datetime.utcnow().isoformat()
    res = await db.table("items").insert(
        {
            "title": title,
            "description": description,
            "category_id": category_id,
            "image": image,
            "created_at": now,
        }
    ).execute()
    return Item(**res.data[0])


# ─────────────────────────── Streams ──────────────────────────

async def get_streams_by_item(item_id: int) -> List[Stream]:
    db = await get_client()
    res = (
        await db.table("streams")
        .select("*")
        .eq("item_id", item_id)
        .eq("status", "active")
        .order("quality")
        .execute()
    )
    return [Stream(**row) for row in res.data]


async def create_stream(item_id: int, url: str, quality: str) -> Stream:
    db = await get_client()
    now = datetime.utcnow().isoformat()
    res = await db.table("streams").insert(
        {
            "item_id": item_id,
            "url": url,
            "quality": quality,
            "status": "active",
            "created_at": now,
        }
    ).execute()
    return Stream(**res.data[0])


async def delete_stream(stream_id: int) -> None:
    db = await get_client()
    await db.table("streams").delete().eq("id", stream_id).execute()


async def delete_streams_by_item(item_id: int) -> None:
    """Remove all existing streams for an item (used before re-scraping,
    so stale/expired URLs don't linger alongside the fresh ones)."""
    db = await get_client()
    await db.table("streams").delete().eq("item_id", item_id).execute()


# ─────────────────────────── Favorites ────────────────────────

async def get_favorites(user_id: int) -> List[Item]:
    db = await get_client()
    fav_res = await db.table("favorites").select("item_id").eq("user_id", user_id).execute()
    item_ids = [f["item_id"] for f in fav_res.data]
    if not item_ids:
        return []
    res = await db.table("items").select("*").in_("id", item_ids).execute()
    return [Item(**row) for row in res.data]


async def is_favorite(user_id: int, item_id: int) -> bool:
    db = await get_client()
    res = (
        await db.table("favorites")
        .select("id")
        .eq("user_id", user_id)
        .eq("item_id", item_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


async def add_favorite(user_id: int, item_id: int) -> None:
    db = await get_client()
    if not await is_favorite(user_id, item_id):
        await db.table("favorites").insert({"user_id": user_id, "item_id": item_id}).execute()


async def remove_favorite(user_id: int, item_id: int) -> None:
    db = await get_client()
    await db.table("favorites").delete().eq("user_id", user_id).eq("item_id", item_id).execute()


# ─────────────────────────── History ──────────────────────────

async def add_history(user_id: int, item_id: int) -> None:
    db = await get_client()
    now = datetime.utcnow().isoformat()
    # Upsert: if the row already exists update viewed_at
    await db.table("history").upsert(
        {"user_id": user_id, "item_id": item_id, "viewed_at": now},
        on_conflict="user_id,item_id",
    ).execute()


async def get_history(user_id: int, limit: int = 20) -> List[Item]:
    db = await get_client()
    hist_res = (
        await db.table("history")
        .select("item_id, viewed_at")
        .eq("user_id", user_id)
        .order("viewed_at", desc=True)
        .limit(limit)
        .execute()
    )
    item_ids = [h["item_id"] for h in hist_res.data]
    if not item_ids:
        return []
    res = await db.table("items").select("*").in_("id", item_ids).execute()
    # Preserve order
    item_map = {item["id"]: Item(**item) for item in res.data}
    return [item_map[iid] for iid in item_ids if iid in item_map]


async def clear_history(user_id: int) -> None:
    db = await get_client()
    await db.table("history").delete().eq("user_id", user_id).execute()
