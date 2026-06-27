from __future__ import annotations

import math

from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.database import queries
from app.database.models import User
from app.bot.keyboards import (
    categories_keyboard,
    items_keyboard,
    item_detail_keyboard,
    streams_keyboard,
)
from app.config import settings
from app.utils.i18n import t

router = Router(name="catalog")


@router.callback_query(F.data == "menu:categories")
async def cb_categories(call: CallbackQuery, db_user: User | None) -> None:
    await call.answer()
    lang = db_user.language if db_user else "en"
    cats = await queries.get_categories()
    if not cats:
        await call.message.edit_text(t("no_categories", lang))
        return
    await call.message.edit_text(
        t("select_category", lang),
        reply_markup=categories_keyboard(cats, lang),
    )


@router.callback_query(F.data.regexp(r"^cat:\d+:\d+$"))
async def cb_category_items(call: CallbackQuery, db_user: User | None) -> None:
    await call.answer()
    lang = db_user.language if db_user else "en"
    _, cat_id_str, page_str = call.data.split(":")
    cat_id, page = int(cat_id_str), int(page_str)
    per_page = settings.items_per_page

    total = await queries.count_items_by_category(cat_id)
    total_pages = max(1, math.ceil(total / per_page))
    items = await queries.get_items_by_category(cat_id, offset=page * per_page, limit=per_page)

    if not items:
        await call.message.edit_text(t("no_items", lang))
        return

    await call.message.edit_text(
        t("select_item", lang) + f"\n{t('page_info', lang, current=page+1, total=total_pages)}",
        reply_markup=items_keyboard(
            items, page, total_pages, source=f"cat:{cat_id}", lang=lang
        ),
    )


@router.callback_query(F.data.regexp(r"^page:.*:\d+$"))
async def cb_pagination(call: CallbackQuery, db_user: User | None) -> None:
    await call.answer()
    lang = db_user.language if db_user else "en"
    parts = call.data.split(":")
    # Format: page:<source_type>:<source_val>:<page>  OR page:search:<query>:<page>
    page = int(parts[-1])
    source = ":".join(parts[1:-1])   # e.g. "cat:3" or "search:batman"

    per_page = settings.items_per_page

    if source.startswith("cat:"):
        cat_id = int(source.split(":")[1])
        total = await queries.count_items_by_category(cat_id)
        total_pages = max(1, math.ceil(total / per_page))
        items = await queries.get_items_by_category(cat_id, offset=page * per_page, limit=per_page)
    else:  # search
        query = ":".join(source.split(":")[1:])
        total = await queries.count_search_results(query)
        total_pages = max(1, math.ceil(total / per_page))
        items = await queries.search_items(query, offset=page * per_page, limit=per_page)

    if not items:
        await call.message.edit_text(t("no_results", lang))
        return

    await call.message.edit_text(
        t("select_item", lang) + f"\n{t('page_info', lang, current=page+1, total=total_pages)}",
        reply_markup=items_keyboard(items, page, total_pages, source=source, lang=lang),
    )


@router.callback_query(F.data.regexp(r"^item:\d+$"))
async def cb_item_detail(call: CallbackQuery, db_user: User | None) -> None:
    await call.answer()
    lang = db_user.language if db_user else "en"
    item_id = int(call.data.split(":")[1])
    item = await queries.get_item_by_id(item_id)
    if not item:
        await call.message.edit_text(t("no_results", lang))
        return

    # Add to history
    if db_user:
        await queries.add_history(db_user.id, item_id)
        fav = await queries.is_favorite(db_user.id, item_id)
    else:
        fav = False

    text = t("item_info", lang, title=item.title, description=item.description or "")
    await call.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=item_detail_keyboard(item_id, fav, lang),
    )


@router.callback_query(F.data.regexp(r"^streams:\d+$"))
async def cb_streams(call: CallbackQuery, db_user: User | None) -> None:
    await call.answer()
    lang = db_user.language if db_user else "en"
    item_id = int(call.data.split(":")[1])
    streams = await queries.get_streams_by_item(item_id)
    if not streams:
        await call.message.edit_text(t("no_streams", lang))
        return
    # Fetch item title so the player page can display it
    item = await queries.get_item_by_id(item_id)
    item_title = item.title if item else ""
    await call.message.edit_text(
        t("select_stream", lang),
        reply_markup=streams_keyboard(streams, item_id, lang, item_title=item_title),
    )
