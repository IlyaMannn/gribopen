"""Подключение к SQLite и схема БД. Создаёт файл mushroom.db при первом запуске."""
import sqlite3
from pathlib import Path
from flask import g

DB_PATH = Path(__file__).parent / "mushroom.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS grade (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS season (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    is_active INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS purchase_price (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grade_id INTEGER NOT NULL REFERENCES grade(id),
    price_per_kg REAL NOT NULL,
    effective_from DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS acceptance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    season_id INTEGER NOT NULL REFERENCES season(id),
    grade_id INTEGER NOT NULL REFERENCES grade(id),
    weight_kg REAL NOT NULL,
    price_per_kg REAL NOT NULL,
    total_amount REAL NOT NULL,
    supplier_id INTEGER REFERENCES supplier(id),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS waste_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    season_id INTEGER NOT NULL REFERENCES season(id),
    weight_kg REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS drying_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    season_id INTEGER NOT NULL REFERENCES season(id),
    raw_grade_1_kg REAL NOT NULL DEFAULT 0,
    raw_grade_2_kg REAL NOT NULL DEFAULT 0,
    raw_grade_3_kg REAL NOT NULL DEFAULT 0,
    dry_grade_1_kg REAL NOT NULL DEFAULT 0,
    dry_grade_2_kg REAL NOT NULL DEFAULT 0,
    dry_grade_3_kg REAL NOT NULL DEFAULT 0,
    cost_electricity REAL NOT NULL DEFAULT 0,
    cost_water REAL NOT NULL DEFAULT 0,
    cost_firewood REAL NOT NULL DEFAULT 0,
    cost_labor REAL NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS buyer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS sale (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    season_id INTEGER NOT NULL REFERENCES season(id),
    buyer_id INTEGER REFERENCES buyer(id),
    grade_id INTEGER NOT NULL REFERENCES grade(id),
    weight_kg REAL NOT NULL,
    price_per_kg REAL NOT NULL,
    total_amount REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS expense (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    season_id INTEGER NOT NULL REFERENCES season(id),
    category TEXT NOT NULL,
    amount REAL NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_acceptance_date ON acceptance(date);
CREATE INDEX IF NOT EXISTS idx_acceptance_season ON acceptance(season_id);
CREATE INDEX IF NOT EXISTS idx_drying_date ON drying_run(date);
CREATE INDEX IF NOT EXISTS idx_sale_date ON sale(date);
CREATE INDEX IF NOT EXISTS idx_waste_date ON waste_record(date);
CREATE INDEX IF NOT EXISTS idx_expense_date ON expense(date);
"""


def get_db():
    """Получить соединение с БД для текущего запроса (Flask g)."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    """Закрыть соединение с БД в конце запроса."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Создать все таблицы (вызывается при старте приложения)."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
