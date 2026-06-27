from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery

from app.database import queries
from app.database.models import User
from app.bot.keyboards import items_list_keyboard
from app.utils.i18n import t

router = Router(name="user_lists")


# ─────────────────────────── Favorites ────────────────────────

@router.callback_query(F.data == "menu:favorites")
async def cb_favorites(call: CallbackQuery, db_user: User | None) -> None:
    await call.answer()
    lang = db_user.language if db_user else "en"
    if not db_user:
        await call.message.edit_text(t("error_occurred", lang))
        return
    items = await queries.get_favorites(db_user.id)
    if not items:
        await call.message.edit_text(
            t("no_favorites", lang),
            reply_markup=items_list_keyboard([], back_data="menu:main", lang=lang),
        )
        return
    await call.message.edit_text(
        t("favorites", lang),
        reply_markup=items_list_keyboard(items, back_data="menu:main", lang=lang),
    )


@router.callback_query(F.data.startswith("fav:toggle:"))
async def cb_toggle_favorite(call: CallbackQuery, db_user: User | None) -> None:
    lang = db_user.language if db_user else "en"
    item_id = int(call.data.split(":")[2])
    if not db_user:
        await call.answer(t("error_occurred", lang))
        return
    already = await queries.is_favorite(db_user.id, item_id)
    if already:
        await queries.remove_favorite(db_user.id, item_id)
        await call.answer(t("removed_favorite", lang))
    else:
        await queries.add_favorite(db_user.id, item_id)
        await call.answer(t("added_favorite", lang))

    # Refresh the item detail keyboard
    from app.database import queries as q
    from app.bot.keyboards import item_detail_keyboard
    item = await q.get_item_by_id(item_id)
    if item:
        fav_now = not already
        await call.message.edit_reply_markup(
            reply_markup=item_detail_keyboard(item_id, fav_now, lang)
        )


# ─────────────────────────── History ──────────────────────────

@router.callback_query(F.data == "menu:history")
async def cb_history(call: CallbackQuery, db_user: User | None) -> None:
    await call.answer()
    lang = db_user.language if db_user else "en"
    if not db_user:
        await call.message.edit_text(t("error_occurred", lang))
        return
    items = await queries.get_history(db_user.id)
    if not items:
        await call.message.edit_text(
            t("no_history", lang),
            reply_markup=items_list_keyboard([], back_data="menu:main", lang=lang),
        )
        return
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    kb = items_list_keyboard(items, back_data="menu:main", lang=lang)
    # Append a "Clear history" button
    builder_rows = list(kb.inline_keyboard)
    from aiogram.types import InlineKeyboardMarkup
    clear_row = [InlineKeyboardButton(text="🗑 Clear History", callback_data="history:clear")]
    new_kb = InlineKeyboardMarkup(inline_keyboard=builder_rows[:-1] + [clear_row] + [builder_rows[-1]])
    await call.message.edit_text(t("history", lang), reply_markup=new_kb)


@router.callback_query(F.data == "history:clear")
async def cb_clear_history(call: CallbackQuery, db_user: User | None) -> None:
    lang = db_user.language if db_user else "en"
    if db_user:
        await queries.clear_history(db_user.id)
    await call.answer(t("history_cleared", lang))
    await call.message.edit_text(
        t("no_history", lang),
        reply_markup=items_list_keyboard([], back_data="menu:main", lang=lang),
    )
