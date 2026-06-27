from __future__ import annotations

from typing import Dict, Optional

# Translations dictionary — extend as needed
TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "en": {
        # General
        "welcome": "👋 Welcome, {name}!\n\nI help you find streaming links by category.",
        "welcome_back": "👋 Welcome back, {name}!",
        "choose_language": "🌐 Please choose your language:",
        "language_set": "✅ Language set to English.",
        "unknown_command": "❓ Unknown command. Use /start to begin.",
        "error_occurred": "⚠️ Something went wrong. Please try again.",
        "no_results": "😕 No results found.",
        "back": "◀️ Back",
        "cancel": "❌ Cancel",
        "confirm": "✅ Confirm",
        "next_page": "Next ▶️",
        "prev_page": "◀️ Prev",
        "page_info": "Page {current}/{total}",
        # Categories
        "select_category": "📂 Select a category:",
        "no_categories": "No categories available yet.",
        # Items
        "select_item": "🎬 Select an item:",
        "item_info": "🎬 *{title}*\n\n{description}",
        "no_items": "No items in this category yet.",
        # Streams
        "select_stream": "🔗 Available streams:",
        "no_streams": "No stream links available for this item.",
        "stream_link": "🔗 [{quality}] {url}",
        # Search
        "search_prompt": "🔍 Enter a title to search:",
        "search_results": "🔍 Search results for *{query}*:",
        "searching": "🔍 Searching...",
        # Favorites
        "favorites": "❤️ Your Favorites",
        "no_favorites": "You haven't saved any favorites yet.",
        "added_favorite": "❤️ Added to favorites!",
        "removed_favorite": "💔 Removed from favorites.",
        "already_favorite": "Already in your favorites.",
        # History
        "history": "🕘 Your History",
        "no_history": "No history yet.",
        "history_cleared": "🗑️ History cleared.",
        # Admin
        "admin_panel": "🛠 Admin Panel",
        "not_admin": "⛔ You don't have admin access.",
        "admin_add_category": "➕ Add Category",
        "admin_add_item": "➕ Add Item",
        "admin_add_stream": "➕ Add Stream",
        "admin_delete_stream": "🗑 Delete Stream",
        "admin_view_users": "👥 View Users",
        "admin_broadcast": "📢 Broadcast",
        "enter_category_name": "Enter the category name:",
        "enter_category_slug": "Enter the category slug (e.g. action-movies):",
        "category_added": "✅ Category '{name}' added.",
        "enter_item_title": "Enter the item title:",
        "enter_item_description": "Enter a short description:",
        "enter_item_image": "Enter an image URL (or skip with /skip):",
        "select_item_category": "Select the category for this item:",
        "item_added": "✅ Item '{title}' added.",
        "enter_stream_url": "Enter the stream URL:",
        "enter_stream_quality": "Enter quality label (e.g. 1080p, HD, SD):",
        "select_stream_item": "Select the item for this stream:",
        "stream_added": "✅ Stream link added.",
        "stream_deleted": "🗑 Stream deleted.",
        "select_stream_delete": "Select a stream to delete:",
        "users_count": "👥 Total users: {count}",
        "enter_broadcast": "Enter the broadcast message:",
        "broadcast_sent": "📢 Broadcast sent to {count} users.",
        "invalid_url": "❌ Invalid URL. Please enter a valid https:// link.",
        "skipped": "⏭ Skipped.",
    },
    "ru": {
        "welcome": "👋 Привет, {name}!\n\nЯ помогу найти ссылки на стримы по категориям.",
        "welcome_back": "👋 С возвращением, {name}!",
        "choose_language": "🌐 Выберите язык:",
        "language_set": "✅ Язык установлен: Русский.",
        "unknown_command": "❓ Неизвестная команда. Используйте /start.",
        "error_occurred": "⚠️ Что-то пошло не так. Попробуйте снова.",
        "no_results": "😕 Ничего не найдено.",
        "back": "◀️ Назад",
        "cancel": "❌ Отмена",
        "confirm": "✅ Подтвердить",
        "next_page": "Вперёд ▶️",
        "prev_page": "◀️ Назад",
        "page_info": "Страница {current}/{total}",
        "select_category": "📂 Выберите категорию:",
        "no_categories": "Категорий пока нет.",
        "select_item": "🎬 Выберите элемент:",
        "item_info": "🎬 *{title}*\n\n{description}",
        "no_items": "В этой категории пока нет элементов.",
        "select_stream": "🔗 Доступные стримы:",
        "no_streams": "Ссылок на стримы пока нет.",
        "stream_link": "🔗 [{quality}] {url}",
        "search_prompt": "🔍 Введите название для поиска:",
        "search_results": "🔍 Результаты поиска *{query}*:",
        "searching": "🔍 Ищу...",
        "favorites": "❤️ Избранное",
        "no_favorites": "Избранное пусто.",
        "added_favorite": "❤️ Добавлено в избранное!",
        "removed_favorite": "💔 Удалено из избранного.",
        "already_favorite": "Уже в избранном.",
        "history": "🕘 История",
        "no_history": "История пуста.",
        "history_cleared": "🗑️ История очищена.",
        "admin_panel": "🛠 Панель администратора",
        "not_admin": "⛔ У вас нет прав администратора.",
        "admin_add_category": "➕ Добавить категорию",
        "admin_add_item": "➕ Добавить элемент",
        "admin_add_stream": "➕ Добавить стрим",
        "admin_delete_stream": "🗑 Удалить стрим",
        "admin_view_users": "👥 Пользователи",
        "admin_broadcast": "📢 Рассылка",
        "enter_category_name": "Введите название категории:",
        "enter_category_slug": "Введите slug категории (например: action-movies):",
        "category_added": "✅ Категория '{name}' добавлена.",
        "enter_item_title": "Введите название элемента:",
        "enter_item_description": "Введите краткое описание:",
        "enter_item_image": "Введите URL изображения (или пропустите /skip):",
        "select_item_category": "Выберите категорию для этого элемента:",
        "item_added": "✅ Элемент '{title}' добавлен.",
        "enter_stream_url": "Введите URL стрима:",
        "enter_stream_quality": "Введите метку качества (например: 1080p, HD):",
        "select_stream_item": "Выберите элемент для этого стрима:",
        "stream_added": "✅ Ссылка на стрим добавлена.",
        "stream_deleted": "🗑 Стрим удалён.",
        "select_stream_delete": "Выберите стрим для удаления:",
        "users_count": "👥 Всего пользователей: {count}",
        "enter_broadcast": "Введите сообщение для рассылки:",
        "broadcast_sent": "📢 Рассылка отправлена {count} пользователям.",
        "invalid_url": "❌ Неверный URL. Введите корректную https:// ссылку.",
        "skipped": "⏭ Пропущено.",
    },
}

DEFAULT_LANG = "en"


def t(key: str, lang: Optional[str] = None, **kwargs: object) -> str:
    """Translate a key to the given language with optional format args."""
    lang = lang or DEFAULT_LANG
    translations = TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG])
    template = translations.get(key, TRANSLATIONS[DEFAULT_LANG].get(key, key))
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "🇬🇧 English",
    "ru": "🇷🇺 Русский",
}
