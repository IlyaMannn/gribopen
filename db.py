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
    supplier_id INTEGER REFERENCES supplier(id),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS acceptance_grade (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    acceptance_id INTEGER NOT NULL REFERENCES acceptance(id) ON DELETE CASCADE,
    grade_id INTEGER NOT NULL REFERENCES grade(id),
    weight_kg REAL NOT NULL,
    price_per_kg REAL NOT NULL,
    total_amount REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS waste_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    season_id INTEGER NOT NULL REFERENCES season(id),
    grade_1_kg REAL NOT NULL DEFAULT 0,
    grade_2_kg REAL NOT NULL DEFAULT 0,
    grade_3_kg REAL NOT NULL DEFAULT 0,
    cleaned_grade_1_kg REAL NOT NULL DEFAULT 0,
    cleaned_grade_2_kg REAL NOT NULL DEFAULT 0,
    cleaned_grade_3_kg REAL NOT NULL DEFAULT 0,
    supplier_id INTEGER REFERENCES supplier(id),
    notes TEXT
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
    notes TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS drying_expense (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drying_run_id INTEGER NOT NULL REFERENCES drying_run(id) ON DELETE CASCADE,
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
    notes TEXT
);

CREATE TABLE IF NOT EXISTS sale_line (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL REFERENCES sale(id) ON DELETE CASCADE,
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

CREATE TABLE IF NOT EXISTS app_setting (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_acceptance_date ON acceptance(date);
CREATE INDEX IF NOT EXISTS idx_acceptance_season ON acceptance(season_id);
CREATE INDEX IF NOT EXISTS idx_acceptance_grade_acc ON acceptance_grade(acceptance_id);
CREATE INDEX IF NOT EXISTS idx_acceptance_grade_grade ON acceptance_grade(grade_id);
CREATE INDEX IF NOT EXISTS idx_drying_date ON drying_run(date);
CREATE INDEX IF NOT EXISTS idx_drying_expense_run ON drying_expense(drying_run_id);
CREATE INDEX IF NOT EXISTS idx_sale_date ON sale(date);
CREATE INDEX IF NOT EXISTS idx_sale_line_sale ON sale_line(sale_id);
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


def migrate_db():
    """Миграция существующей БД: добавляет новые колонки/таблицы если их нет."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    existing = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    cols = {}
    for t in existing:
        cols[t] = {r[1] for r in cur.execute(f"PRAGMA table_info({t})").fetchall()}
    # drying_run: добавить started_at, finished_at
    if "drying_run" in existing and "started_at" not in cols.get("drying_run", set()):
        cur.execute("ALTER TABLE drying_run ADD COLUMN started_at TEXT")
        cur.execute("ALTER TABLE drying_run ADD COLUMN finished_at TEXT")
    # sale: пересоздать (убрать grade_id, weight_kg, price_per_kg, total_amount)
    if "sale" in existing and "grade_id" in cols.get("sale", set()):
        cur.execute("CREATE TABLE IF NOT EXISTS sale_new (id INTEGER PRIMARY KEY AUTOINCREMENT, date DATE NOT NULL, season_id INTEGER NOT NULL REFERENCES season(id), buyer_id INTEGER REFERENCES buyer(id), notes TEXT)")
        cur.execute("INSERT INTO sale_new (id, date, season_id, buyer_id) SELECT id, date, season_id, buyer_id FROM sale")
        cur.execute("DROP TABLE sale")
        cur.execute("ALTER TABLE sale_new RENAME TO sale")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sale_date ON sale(date)")
    # drying_expense
    if "drying_expense" not in existing:
        cur.execute("""CREATE TABLE IF NOT EXISTS drying_expense (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drying_run_id INTEGER NOT NULL REFERENCES drying_run(id) ON DELETE CASCADE,
            cost_electricity REAL NOT NULL DEFAULT 0,
            cost_water REAL NOT NULL DEFAULT 0,
            cost_firewood REAL NOT NULL DEFAULT 0,
            cost_labor REAL NOT NULL DEFAULT 0,
            notes TEXT
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_drying_expense_run ON drying_expense(drying_run_id)")
    # sale_line
    if "sale_line" not in existing:
        cur.execute("""CREATE TABLE IF NOT EXISTS sale_line (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL REFERENCES sale(id) ON DELETE CASCADE,
            grade_id INTEGER NOT NULL REFERENCES grade(id),
            weight_kg REAL NOT NULL,
            price_per_kg REAL NOT NULL,
            total_amount REAL NOT NULL
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sale_line_sale ON sale_line(sale_id)")
    # app_setting
    if "app_setting" not in existing:
        cur.execute("CREATE TABLE IF NOT EXISTS app_setting (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    # waste_record: add cleaned columns
    if "waste_record" in existing and "cleaned_grade_1_kg" not in cols.get("waste_record", set()):
        cur.execute("ALTER TABLE waste_record ADD COLUMN cleaned_grade_1_kg REAL NOT NULL DEFAULT 0")
        cur.execute("ALTER TABLE waste_record ADD COLUMN cleaned_grade_2_kg REAL NOT NULL DEFAULT 0")
        cur.execute("ALTER TABLE waste_record ADD COLUMN cleaned_grade_3_kg REAL NOT NULL DEFAULT 0")
    conn.commit()
    conn.close()
