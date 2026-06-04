"""Сид начальных данных: пользователь admin/admin и 3 сорта гриба."""
from db import get_db
from auth import hash_password


def seed_if_empty():
    """Заполнить БД начальными данными, если она пустая. Идемпотентно."""
    db = get_db()

    # Пользователь
    if db.execute("SELECT COUNT(*) FROM user").fetchone()[0] == 0:
        db.execute(
            "INSERT INTO user (username, password_hash) VALUES (?, ?)",
            ("admin", hash_password("admin")),
        )

    # Сорта гриба: 1, 2, 3
    if db.execute("SELECT COUNT(*) FROM grade").fetchone()[0] == 0:
        for code, name, order in [
            ("1", "1 сорт", 1),
            ("2", "2 сорт", 2),
            ("3", "3 сорт", 3),
        ]:
            db.execute(
                "INSERT INTO grade (code, display_name, sort_order) VALUES (?, ?, ?)",
                (code, name, order),
            )

    db.commit()


def has_active_season() -> bool:
    db = get_db()
    row = db.execute("SELECT COUNT(*) FROM season WHERE is_active = 1").fetchone()
    return row[0] > 0


def get_active_season():
    db = get_db()
    return db.execute(
        "SELECT * FROM season WHERE is_active = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()


def create_season(name: str, start_date: str) -> int:
    """Создать новый активный сезон. Предыдущий активный закрывается."""
    db = get_db()
    db.execute("UPDATE season SET is_active = 0, end_date = ? WHERE is_active = 1", (start_date,))
    cur = db.execute(
        "INSERT INTO season (name, start_date, is_active) VALUES (?, ?, 1)",
        (name, start_date),
    )
    db.commit()
    return cur.lastrowid
