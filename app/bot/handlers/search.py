from __future__ import annotations

import math

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.bot.states import SearchState
from app.database import queries
from app.database.models import User
from app.bot.keyboards import items_keyboard
from app.config import settings
from app.utils.i18n import t

router = Router(name="search")


@router.callback_query(F.data == "menu:search")
async def cb_search_start(call: CallbackQuery, state: FSMContext, db_user: User | None) -> None:
    await call.answer()
    lang = db_user.language if db_user else "en"
    await state.set_state(SearchState.waiting_for_query)
    await call.message.edit_text(t("search_prompt", lang))


@router.message(SearchState.waiting_for_query)
async def handle_search_query(message: Message, state: FSMContext, db_user: User | None) -> None:
    lang = db_user.language if db_user else "en"
    query = message.text.strip() if message.text else ""
    if not query:
        await message.answer(t("search_prompt", lang))
        return

    await state.clear()
    per_page = settings.items_per_page
    total = await queries.count_search_results(query)
    total_pages = max(1, math.ceil(total / per_page))
    items = await queries.search_items(query, offset=0, limit=per_page)

    if not items:
        await message.answer(t("no_results", lang))
        return

    await message.answer(
        t("search_results", lang, query=query)
        + f"\n{t('page_info', lang, current=1, total=total_pages)}",
        parse_mode="Markdown",
        reply_markup=items_keyboard(items, 0, total_pages, source=f"search:{query}", lang=lang),
    )
