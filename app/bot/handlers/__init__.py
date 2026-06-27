from aiogram import Router

from app.bot.handlers import common, catalog, search, user_lists, admin


def get_main_router() -> Router:
    router = Router(name="main")
    router.include_router(common.router)
    router.include_router(catalog.router)
    router.include_router(search.router)
    router.include_router(user_lists.router)
    router.include_router(admin.router)
    return router
