-- ============================================================
-- StreamBot — Supabase SQL Schema
-- Run this in the Supabase SQL Editor to set up the database.
-- ============================================================

-- Users
CREATE TABLE IF NOT EXISTS users (
    id          BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT    NOT NULL UNIQUE,
    username    TEXT,
    language    TEXT      NOT NULL DEFAULT 'en',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users (telegram_id);

-- Categories
CREATE TABLE IF NOT EXISTS categories (
    id   BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE
);

-- Items
CREATE TABLE IF NOT EXISTS items (
    id          BIGSERIAL PRIMARY KEY,
    title       TEXT        NOT NULL,
    description TEXT,
    category_id BIGINT      NOT NULL REFERENCES categories (id) ON DELETE CASCADE,
    image       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_items_category_id ON items (category_id);
CREATE INDEX IF NOT EXISTS idx_items_title       ON items USING gin(to_tsvector('english', title));

-- Streams
CREATE TABLE IF NOT EXISTS streams (
    id         BIGSERIAL PRIMARY KEY,
    item_id    BIGINT      NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    url        TEXT        NOT NULL,
    quality    TEXT        NOT NULL DEFAULT 'HD',
    status     TEXT        NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_streams_item_id ON streams (item_id);

-- Favorites
CREATE TABLE IF NOT EXISTS favorites (
    id      BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    item_id BIGINT NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    UNIQUE (user_id, item_id)
);

-- History
CREATE TABLE IF NOT EXISTS history (
    id        BIGSERIAL PRIMARY KEY,
    user_id   BIGINT      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    item_id   BIGINT      NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    viewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_history_user_viewed ON history (user_id, viewed_at DESC);

-- ── Seed data (optional — remove in production) ──────────────
INSERT INTO categories (name, slug) VALUES
    ('Movies',  'movies'),
    ('Series',  'series'),
    ('Sports',  'sports'),
    ('Anime',   'anime'),
    ('Documentaries', 'documentaries')
ON CONFLICT (slug) DO NOTHING;
