from __future__ import annotations

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from app.config import settings
from app.database import queries
from app.database.models import User
from app.bot.states import (
    AdminAddCategory, AdminAddItem, AdminAddStream,
    AdminDeleteStream, AdminBroadcast, AdminScrapeURL,
)
from app.bot.keyboards import (
    admin_panel_keyboard,
    admin_category_select_keyboard,
    admin_item_select_keyboard,
    admin_stream_select_keyboard,
)
from app.utils.i18n import t
from app.utils.validators import is_valid_url
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = Router(name="admin")


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_id_list


# ─────────────────────────── /admin ───────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, db_user: User | None) -> None:
    if not is_admin(message.from_user.id):
        await message.answer(t("not_admin"))
        return
    await message.answer(t("admin_panel"), reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin:cancel")
async def cb_admin_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer("Cancelled")
    await call.message.edit_text(t("admin_panel"), reply_markup=admin_panel_keyboard())


# ─────────────────────────── Add Category ─────────────────────

@router.callback_query(F.data == "admin:add_category")
async def cb_add_category_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer(t("not_admin"))
    await state.set_state(AdminAddCategory.name)
    await call.message.edit_text(t("enter_category_name"))


@router.message(AdminAddCategory.name)
async def admin_category_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminAddCategory.slug)
    await message.answer(t("enter_category_slug"))


@router.message(AdminAddCategory.slug)
async def admin_category_slug(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    slug = message.text.strip().lower().replace(" ", "-")
    cat = await queries.create_category(data["name"], slug)
    await state.clear()
    await message.answer(
        t("category_added", name=cat.name),
        reply_markup=admin_panel_keyboard(),
    )


# ─────────────────────────── Add Item (URL ilə) ───────────────
#
# Admin "➕ Film Əlavə Et (URL)" düyməsinə basdıqda:
# 1. sinekfilmizle.com URL-i soruşur
# 2. Film adı soruşur (və ya /skip deyib saytdan otomatik çəkməyə buraxır)
# 3. Kateqoriya seçir
# 4. Items DB-ə əlavə edilir; stream SAXLANMIR — hər izləmədə canlı tapılır
#

@router.callback_query(F.data == "admin:scrape_url")
async def cb_add_url_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer(t("not_admin"))
    await state.set_state(AdminScrapeURL.url)
    await call.message.edit_text(
        "🔗 <b>Film URL-i Əlavə Et</b>\n\n"
        "Aşağıdakı formatlardan birini göndərin:\n\n"
        "<b>1. sinekfilmizle.com URL-i:</b>\n"
        "<code>https://sinekfilmizle.com/yenilmez-undisputed-2002-izle/</code>\n\n"
        "<b>2. p2turk video ID-si</b> (saytda şəbəkə trafikindən görünür):\n"
        "<code>p2turk:Bno1xDl</code>\n\n"
        "Bot istifadəçi izləmək istədikdə m3u8-i <b>canlı</b> tapacaq.",
        parse_mode="HTML",
    )


@router.message(AdminScrapeURL.url)
async def admin_url_received(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    url = message.text.strip() if message.text else ""
    if not (url.startswith("http") or url.startswith("p2turk:")):
        await message.answer(
            "❌ Yanlış format.\n"
            "http/https URL və ya <code>p2turk:VIDEO_ID</code> formatında göndərin.",
            parse_mode="HTML",
        )
        return

    await state.update_data(url=url)
    await state.set_state(AdminScrapeURL.category)

    # Film adını saytdan otomatik çəkməyə çalış
    await message.answer("⏳ Saytdan film adı oxunur...")
    title = await _fetch_title(url)

    if title:
        await state.update_data(title=title)
        await message.answer(
            f"✅ Film adı tapıldı: <b>{title}</b>\n\n"
            "Dəyişdirmək istəyirsənsə yeni ad göndər, ya da /skip yaz.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "Film adı tapılmadı. Zəhmət olmasa əl ilə daxil edin:"
        )


@router.message(AdminScrapeURL.category)
async def admin_url_title_override(message: Message, state: FSMContext) -> None:
    """İstifadəçi film adını əl ilə daxil etdikdə və ya /skip yazdıqda."""
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip() if message.text else ""
    if text != "/skip":
        await state.update_data(title=text)

    data = await state.get_data()
    if not data.get("title"):
        await message.answer("❌ Film adı lazımdır. Zəhmət olmasa daxil edin:")
        return

    cats = await queries.get_categories()
    if not cats:
        await message.answer("❌ Kateqoriya yoxdur. Əvvəl kateqoriya əlavə edin.")
        await state.clear()
        return

    await message.answer(
        "📂 Hansı kateqoriyaya əlavə edim?",
        reply_markup=admin_category_select_keyboard(cats),
    )


@router.callback_query(F.data.startswith("adm_cat:"), AdminScrapeURL.category)
async def admin_url_save(call: CallbackQuery, state: FSMContext) -> None:
    """Kateqoriya seçildikdən sonra filmi DB-ə əlavə edir."""
    cat_id = int(call.data.split(":")[1])
    data = await state.get_data()
    url = data.get("url", "")
    title = data.get("title", "")

    await state.clear()

    # Eyni title varsa yenilə, yoxdursa əlavə et
    existing = await queries.search_items(title, limit=1)
    item_exists = [i for i in existing if i.title.lower() == title.lower()]

    if item_exists:
        item = item_exists[0]
        # source_url-i yenilə
        from app.database.supabase import get_client as _get_client
        db = await _get_client()
        await db.table("items").update({"source_url": url}).eq("id", item.id).execute()
        await call.message.edit_text(
            f"♻️ <b>Mövcud film yeniləndi!</b>\n\n"
            f"📌 Film: <b>{item.title}</b>\n"
            f"🔗 URL yeniləndi.\n\n"
            f"İstifadəçilər filmi izləmək istədikdə m3u8 canlı tapılacaq.",
            parse_mode="HTML",
            reply_markup=admin_panel_keyboard(),
        )
        return

    item = await queries.create_item(
        title=title,
        description="",
        category_id=cat_id,
        source_url=url,
    )

    await call.message.edit_text(
        f"✅ <b>Film əlavə edildi!</b>\n\n"
        f"📌 Ad: <b>{item.title}</b>\n"
        f"🔗 URL: <code>{url}</code>\n\n"
        f"İstifadəçilər izləmək istədikdə bot m3u8-i canlı tapacaq.",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(),
    )


# ─────────────────────────── Add Item (manual) ────────────────

@router.callback_query(F.data == "admin:add_item")
async def cb_add_item_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer(t("not_admin"))
    await state.set_state(AdminAddItem.title)
    await call.message.edit_text(t("enter_item_title"))


@router.message(AdminAddItem.title)
async def admin_item_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip())
    await state.set_state(AdminAddItem.description)
    await message.answer(t("enter_item_description"))


@router.message(AdminAddItem.description)
async def admin_item_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text.strip())
    await state.set_state(AdminAddItem.image)
    await message.answer(t("enter_item_image"))


@router.message(AdminAddItem.image)
async def admin_item_image(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""
    if text == "/skip":
        await state.update_data(image=None)
        await message.answer(t("skipped"))
    elif is_valid_url(text):
        await state.update_data(image=text)
    else:
        await message.answer(t("invalid_url"))
        return
    cats = await queries.get_categories()
    await state.set_state(AdminAddItem.category)
    await message.answer(
        t("select_item_category"),
        reply_markup=admin_category_select_keyboard(cats),
    )


@router.callback_query(F.data.startswith("adm_cat:"), AdminAddItem.category)
async def admin_item_category(call: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(call.data.split(":")[1])
    data = await state.get_data()
    item = await queries.create_item(
        title=data["title"],
        description=data.get("description", ""),
        category_id=cat_id,
        image=data.get("image"),
    )
    await state.clear()
    await call.message.edit_text(
        t("item_added", title=item.title),
        reply_markup=admin_panel_keyboard(),
    )


# ─────────────────────────── Add Stream (manual) ──────────────

@router.callback_query(F.data == "admin:add_stream")
async def cb_add_stream_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer(t("not_admin"))
    cats = await queries.get_categories()
    await state.set_state(AdminAddStream.item)
    await call.message.edit_text(
        t("select_stream_item"),
        reply_markup=admin_category_select_keyboard(cats),
    )


@router.callback_query(F.data.startswith("adm_cat:"), AdminAddStream.item)
async def admin_stream_pick_category(call: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(call.data.split(":")[1])
    items = await queries.get_items_by_category(cat_id, limit=50)
    await call.message.edit_text(
        "Select item:",
        reply_markup=admin_item_select_keyboard(items),
    )


@router.callback_query(F.data.startswith("adm_item:"), AdminAddStream.item)
async def admin_stream_pick_item(call: CallbackQuery, state: FSMContext) -> None:
    item_id = int(call.data.split(":")[1])
    await state.update_data(item_id=item_id)
    await state.set_state(AdminAddStream.url)
    await call.message.edit_text(t("enter_stream_url"))


@router.message(AdminAddStream.url)
async def admin_stream_url(message: Message, state: FSMContext) -> None:
    url = message.text.strip() if message.text else ""
    if not is_valid_url(url):
        await message.answer(t("invalid_url"))
        return
    await state.update_data(url=url)
    await state.set_state(AdminAddStream.quality)
    await message.answer(t("enter_stream_quality"))


@router.message(AdminAddStream.quality)
async def admin_stream_quality(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await queries.create_stream(
        item_id=data["item_id"],
        url=data["url"],
        quality=message.text.strip(),
    )
    await state.clear()
    await message.answer(t("stream_added"), reply_markup=admin_panel_keyboard())


# ─────────────────────────── Delete Stream ────────────────────

@router.callback_query(F.data == "admin:delete_stream")
async def cb_delete_stream_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer(t("not_admin"))
    cats = await queries.get_categories()
    await state.set_state(AdminDeleteStream.item)
    await call.message.edit_text(
        "Select category:",
        reply_markup=admin_category_select_keyboard(cats),
    )


@router.callback_query(F.data.startswith("adm_cat:"), AdminDeleteStream.item)
async def admin_delete_pick_category(call: CallbackQuery, state: FSMContext) -> None:
    cat_id = int(call.data.split(":")[1])
    items = await queries.get_items_by_category(cat_id, limit=50)
    await call.message.edit_text("Select item:", reply_markup=admin_item_select_keyboard(items))


@router.callback_query(F.data.startswith("adm_item:"), AdminDeleteStream.item)
async def admin_delete_pick_item(call: CallbackQuery, state: FSMContext) -> None:
    item_id = int(call.data.split(":")[1])
    streams = await queries.get_streams_by_item(item_id)
    await state.set_state(AdminDeleteStream.stream)
    await call.message.edit_text(
        t("select_stream_delete"),
        reply_markup=admin_stream_select_keyboard(streams),
    )


@router.callback_query(F.data.startswith("adm_stream:"), AdminDeleteStream.stream)
async def admin_delete_stream(call: CallbackQuery, state: FSMContext) -> None:
    stream_id = int(call.data.split(":")[1])
    await queries.delete_stream(stream_id)
    await state.clear()
    await call.message.edit_text(t("stream_deleted"), reply_markup=admin_panel_keyboard())


# ─────────────────────────── View Users ───────────────────────

@router.callback_query(F.data == "admin:users")
async def cb_admin_users(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer(t("not_admin"))
    count = await queries.count_users()
    await call.message.edit_text(
        t("users_count", count=count),
        reply_markup=admin_panel_keyboard(),
    )


# ─────────────────────────── Broadcast ────────────────────────

@router.callback_query(F.data == "admin:broadcast")
async def cb_broadcast_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer(t("not_admin"))
    await state.set_state(AdminBroadcast.message)
    await call.message.edit_text(t("enter_broadcast"))


@router.message(AdminBroadcast.message)
async def admin_broadcast_send(message: Message, state: FSMContext) -> None:
    from aiogram import Bot
    bot: Bot = message.bot
    users = await queries.get_all_users()
    sent = 0
    for user in users:
        try:
            await bot.send_message(user.telegram_id, message.text)
            sent += 1
        except Exception as exc:
            logger.warning("Broadcast failed for user", user_id=user.telegram_id, error=str(exc))
    await state.clear()
    await message.answer(t("broadcast_sent", count=sent), reply_markup=admin_panel_keyboard())


# ─────────────────────────── Helpers ──────────────────────────

async def _fetch_title(url: str) -> str:
    """sinekfilmizle.com səhifəsindən film adını oxuyur."""
    import aiohttp
    from bs4 import BeautifulSoup
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "tr-TR,tr;q=0.9",
        "Accept-Encoding": "gzip, deflate",
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                html = await resp.text(errors="replace")
        soup = BeautifulSoup(html, "lxml")
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            return og["content"].strip()
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
    except Exception as exc:
        logger.warning("Title fetch failed", url=url, error=str(exc))
    return ""
