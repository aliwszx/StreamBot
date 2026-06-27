from aiogram.fsm.state import State, StatesGroup


class SearchState(StatesGroup):
    waiting_for_query = State()


class AdminAddCategory(StatesGroup):
    name = State()
    slug = State()


class AdminAddItem(StatesGroup):
    title = State()
    description = State()
    image = State()
    category = State()


class AdminAddStream(StatesGroup):
    item = State()
    url = State()
    quality = State()


class AdminDeleteStream(StatesGroup):
    item = State()
    stream = State()


class AdminBroadcast(StatesGroup):
    message = State()


class AdminScrapeURL(StatesGroup):
    url = State()
    category = State()
