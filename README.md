# 🎬 StreamBot

A production-ready Telegram bot that collects and manages streaming links from external websites, presenting them to users via category browsing, full-text search, favourites, and watch history.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Bot framework | aiogram 3.x |
| Database | Supabase (PostgreSQL) |
| Deployment | Render (Docker Web Service) |
| Caching | In-process TTLCache |
| Scraping | aiohttp + BeautifulSoup4 |
| Logging | structlog |

---

## Project Structure

```
streambot/
├── app/
│   ├── main.py                  # Entrypoint (polling or webhook)
│   ├── config.py                # Pydantic-settings config
│   ├── bot/
│   │   ├── __init__.py          # Bot + Dispatcher factory
│   │   ├── handlers/
│   │   │   ├── common.py        # /start, language, main menu
│   │   │   ├── catalog.py       # Categories, items, streams
│   │   │   ├── search.py        # FSM search flow
│   │   │   ├── user_lists.py    # Favourites & history
│   │   │   └── admin.py         # Full admin panel
│   │   ├── keyboards/
│   │   │   └── inline.py        # All InlineKeyboardMarkup builders
│   │   ├── middlewares/
│   │   │   ├── user.py          # Auto-register + attach DB user
│   │   │   └── rate_limit.py    # Sliding-window rate limiter
│   │   └── states/
│   │       └── states.py        # All FSM state groups
│   ├── database/
│   │   ├── supabase.py          # AsyncClient singleton
│   │   ├── models.py            # Pydantic models
│   │   └── queries.py           # All async DB queries
│   ├── services/
│   │   ├── cache.py             # TTLCache helper
│   │   └── scraper/
│   │       ├── base.py          # Abstract BaseScraper
│   │       ├── site1.py         # Example scraper #1
│   │       ├── site2.py         # Example scraper #2
│   │       └── runner.py        # Orchestrator + Supabase persistence
│   └── utils/
│       ├── i18n.py              # Translation strings (EN + RU)
│       ├── validators.py        # URL validation
│       └── logging.py           # structlog setup
├── supabase_schema.sql          # Database schema + seed data
├── Dockerfile
├── render.yaml
├── requirements.txt
└── .env.example
```

---

## Quick Start (Local)

### 1. Clone & install

```bash
git clone https://github.com/yourorg/streambot.git
cd streambot
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your real values
```

| Variable | Description |
|---|---|
| `BOT_TOKEN` | BotFather token |
| `SUPABASE_URL` | Project URL from Supabase dashboard |
| `SUPABASE_KEY` | `service_role` key (or `anon` if RLS allows) |
| `ADMIN_IDS` | Comma-separated Telegram user IDs |
| `WEBHOOK_URL` | Leave empty for local polling mode |

### 3. Set up the database

1. Open your Supabase project → **SQL Editor**
2. Paste the contents of `supabase_schema.sql` and run it

### 4. Run the bot

```bash
python -m app.main
```

---

## Running Scrapers

The scraper system is modular. To run all registered scrapers and persist results:

```python
import asyncio
from app.services.scraper import run_all_scrapers

asyncio.run(run_all_scrapers())
```

To add a new scraper:

1. Create `app/services/scraper/mysite.py` extending `BaseScraper`
2. Implement the `scrape()` method with your site-specific selectors
3. Import and add it to the `SCRAPERS` list in `app/services/scraper/runner.py`

---

## Deployment on Render

### Option A — render.yaml (recommended)

1. Push to GitHub
2. In Render: **New → Blueprint** → connect your repo
3. Render reads `render.yaml` automatically
4. Set secret env vars in the Render dashboard (**Environment** tab)

### Option B — Manual Web Service

1. **New → Web Service** → Docker runtime
2. Set **Start Command**: *(auto-detected from Dockerfile)*
3. Add all environment variables from `.env.example`
4. Set `WEBHOOK_URL` to your Render service URL (e.g. `https://streambot.onrender.com`)

> **Note:** On the free plan Render sleeps after 15 min idle. Upgrade to **Starter** for always-on.

---

## Admin Commands

| Command | Description |
|---|---|
| `/admin` | Open the admin panel |

From the admin panel you can:
- **Add Category** — name + slug
- **Add Item** — title, description, image URL, category
- **Add Stream** — select item → paste URL → quality label
- **Delete Stream** — pick item → pick stream → delete
- **View Users** — total registered count
- **Broadcast** — send a message to all users

Admin access is controlled by the `ADMIN_IDS` environment variable.

---

## i18n / Localization

All user-facing strings live in `app/utils/i18n.py`. To add a new language:

1. Add a new key to `TRANSLATIONS` with all keys translated
2. Add the language code + label to `SUPPORTED_LANGUAGES`
3. The language picker in the bot will show it automatically

---

## Architecture Decisions

- **Webhook in production, polling locally** — the bot auto-detects based on `WEBHOOK_URL`
- **UserMiddleware** runs on every update, auto-registering new users and attaching the DB user object to handler `data`
- **FSM with MemoryStorage** — suitable for moderate traffic; swap for `RedisStorage` for multi-instance deployments
- **TTLCache** avoids hammering Supabase for repeated category/item lookups
- **Scrapers are isolated** — each site scraper only knows about `BaseScraper`; the runner handles DB persistence

---

## License

MIT
