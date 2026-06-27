from __future__ import annotations

import math
import json
import urllib.parse
from typing import List

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.database.models import Category, Item, Stream
from app.utils.i18n import t, SUPPORTED_LANGUAGES
from app.config import settings


# ─────────────────────────── Language ─────────────────────────

def language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, label in SUPPORTED_LANGUAGES.items():
        builder.button(text=label, callback_data=f"lang:{code}")
    builder.adjust(2)
    return builder.as_markup()


# ─────────────────────────── Main menu ────────────────────────

def main_menu_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📂 Categories", callback_data="menu:categories")
    builder.button(text="🔍 Search", callback_data="menu:search")
    builder.button(text="❤️ Favorites", callback_data="menu:favorites")
    builder.button(text="🕘 History", callback_data="menu:history")
    builder.button(text="🌐 Language", callback_data="menu:language")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


# ─────────────────────────── Categories ───────────────────────

def categories_keyboard(categories: List[Category], lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name, callback_data=f"cat:{cat.id}:0")
    builder.button(text=t("back", lang), callback_data="menu:main")
    builder.adjust(2)
    return builder.as_markup()


# ─────────────────────────── Items ────────────────────────────

def items_keyboard(
    items: List[Item],
    current_page: int,
    total_pages: int,
    source: str,      # "cat:{id}" or "search:{query}"
    lang: str = "en",
) -> InlineKeyboardMarkup:
    per_page = settings.items_per_page
    builder = InlineKeyboardBuilder()
    for item in items:
        builder.button(text=item.title, callback_data=f"item:{item.id}")
    builder.adjust(1)

    # Pagination row
    nav: List[InlineKeyboardButton] = []
    if current_page > 0:
        nav.append(
            InlineKeyboardButton(
                text=t("prev_page", lang),
                callback_data=f"page:{source}:{current_page - 1}",
            )
        )
    if current_page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                text=t("next_page", lang),
                callback_data=f"page:{source}:{current_page + 1}",
            )
        )
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text=t("back", lang), callback_data="menu:categories"))
    return builder.as_markup()


# ─────────────────────────── Item detail ──────────────────────

def item_detail_keyboard(
    item_id: int,
    is_favorite: bool,
    lang: str = "en",
    back_data: str = "menu:categories",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Streams", callback_data=f"streams:{item_id}")
    fav_text = "💔 Remove Favorite" if is_favorite else "❤️ Add Favorite"
    builder.button(text=fav_text, callback_data=f"fav:toggle:{item_id}")
    builder.button(text=t("back", lang), callback_data=back_data)
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────── Streams ──────────────────────────

def streams_keyboard(
    streams: List[Stream], item_id: int, lang: str = "en", item_title: str = ""
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    base_url = (settings.webapp_base_url or "").rstrip("/")

    if base_url:
        # Build a single "▶ Videoya bax" WebApp button that opens the player
        # and passes all streams as JSON so the user can switch quality inside the app.
        streams_data = [{"url": s.url, "quality": s.quality} for s in streams]
        encoded_streams = urllib.parse.quote(json.dumps(streams_data))
        encoded_title   = urllib.parse.quote(item_title or "Video")

        # Use the first stream as the default; the player lets user switch
        first = streams[0] if streams else None
        player_url = (
            f"{base_url}/player"
            f"?title={encoded_title}"
            f"&streams={encoded_streams}"
        )
        if first:
            player_url += (
                f"&url={urllib.parse.quote(first.url)}"
                f"&quality={urllib.parse.quote(first.quality)}"
            )

        builder.button(
            text="▶️ Videoya bax",
            web_app=WebAppInfo(url=player_url),
        )
    else:
        # Fallback: direct URL buttons (original behaviour) when webapp_base_url not set
        for s in streams:
            builder.button(text=f"[{s.quality}] 🔗", url=s.url)

    builder.row(InlineKeyboardButton(text=t("back", lang), callback_data=f"item:{item_id}"))
    builder.adjust(1)
    return builder.as_markup()


def live_streams_keyboard(
    streams: list,   # List[ResolvedStream] from resolver
    item_id: int,
    lang: str = "en",
    item_title: str = "",
) -> InlineKeyboardMarkup:
    """
    Canlı resolver-dən gələn ResolvedStream-lər üçün keyboard.
    """
    builder = InlineKeyboardBuilder()
    base_url = (settings.webapp_base_url or "").rstrip("/")

    if base_url and streams:
        streams_data = [
            {
                "url": s.url,
                "quality": s.quality,
                **({"audioUrl": s.audio_url} if getattr(s, "audio_url", None) else {}),
            }
            for s in streams
        ]
        encoded_streams = urllib.parse.quote(json.dumps(streams_data))
        encoded_title = urllib.parse.quote(item_title or "Video")
        first = streams[0]
        player_url = (
            f"{base_url}/player"
            f"?title={encoded_title}"
            f"&streams={encoded_streams}"
            f"&url={urllib.parse.quote(first.url)}"
            f"&quality={urllib.parse.quote(first.quality)}"
        )
        builder.button(
            text="▶️ Videoya bax",
            web_app=WebAppInfo(url=player_url),
        )
    else:
        for s in streams:
            builder.button(text=f"[{s.quality}] 🔗", url=s.url)

    builder.row(InlineKeyboardButton(text=t("back", lang), callback_data=f"item:{item_id}"))
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────── Favorites / History ──────────────

def items_list_keyboard(
    items: List[Item], prefix: str = "item", back_data: str = "menu:main", lang: str = "en"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        builder.button(text=item.title, callback_data=f"{prefix}:{item.id}")
    builder.row(InlineKeyboardButton(text=t("back", lang), callback_data=back_data))
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────── Admin ────────────────────────────

def admin_panel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Add Category", callback_data="admin:add_category")
    builder.button(text="➕ Add Item", callback_data="admin:add_item")
    builder.button(text="➕ Add Stream", callback_data="admin:add_stream")
    builder.button(text="🗑 Delete Stream", callback_data="admin:delete_stream")
    builder.button(text="🔗 Film URL Əlavə Et", callback_data="admin:scrape_url")
    builder.button(text="👥 Users", callback_data="admin:users")
    builder.button(text="📢 Broadcast", callback_data="admin:broadcast")
    builder.adjust(2)
    return builder.as_markup()


def admin_category_select_keyboard(categories: List[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.name, callback_data=f"adm_cat:{cat.id}")
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:cancel"))
    builder.adjust(2)
    return builder.as_markup()


def admin_item_select_keyboard(items: List[Item]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in items:
        builder.button(text=item.title[:40], callback_data=f"adm_item:{item.id}")
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:cancel"))
    builder.adjust(1)
    return builder.as_markup()


def admin_stream_select_keyboard(streams: List[Stream]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in streams:
        builder.button(text=f"[{s.quality}] {s.url[:40]}", callback_data=f"adm_stream:{s.id}")
    builder.row(InlineKeyboardButton(text="❌ Cancel", callback_data="admin:cancel"))
    builder.adjust(1)
    return builder.as_markup()
