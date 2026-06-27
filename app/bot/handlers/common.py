from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.database.models import User
from app.database import queries
from app.bot.keyboards import language_keyboard, main_menu_keyboard
from app.utils.i18n import t

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User | None) -> None:
    if db_user is None:
        await message.answer("⚠️ Could not load your profile. Please try again.")
        return
    lang = db_user.language
    name = message.from_user.first_name or "there"
    await message.answer(
        t("welcome", lang, name=name),
        reply_markup=main_menu_keyboard(lang),
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(call: CallbackQuery, db_user: User | None) -> None:
    await call.answer()
    lang = db_user.language if db_user else "en"
    await call.message.edit_text(
        t("welcome_back", lang, name=call.from_user.first_name or "there"),
        reply_markup=main_menu_keyboard(lang),
    )


@router.callback_query(F.data == "menu:language")
async def cb_language_menu(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.edit_text(
        t("choose_language"),
        reply_markup=language_keyboard(),
    )


@router.callback_query(F.data.startswith("lang:"))
async def cb_set_language(call: CallbackQuery, db_user: User | None) -> None:
    lang = call.data.split(":")[1]
    await queries.update_user_language(call.from_user.id, lang)
    await call.answer(t("language_set", lang))
    await call.message.edit_text(
        t("welcome_back", lang, name=call.from_user.first_name or "there"),
        reply_markup=main_menu_keyboard(lang),
    )


@router.message(Command("help"))
async def cmd_help(message: Message, db_user: User | None) -> None:
    lang = db_user.language if db_user else "en"
    text = (
        "ℹ️ *StreamBot Help*\n\n"
        "• /start — Main menu\n"
        "• Browse categories to find stream links\n"
        "• Use 🔍 Search to find titles\n"
        "• ❤️ Save favourites for quick access\n"
        "• 🕘 View your history\n"
    )
    await message.answer(text, parse_mode="Markdown")
