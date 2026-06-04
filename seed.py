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
    """Создать новый активный сезон. Предыдущий активный закрывается (мягко)."""
    db = get_db()
    db.execute("UPDATE season SET is_active = 0, end_date = ? WHERE is_active = 1", (start_date,))
    cur = db.execute(
        "INSERT INTO season (name, start_date, is_active) VALUES (?, ?, 1)",
        (name, start_date),
    )
    db.commit()
    return cur.lastrowid


def list_seasons() -> list[dict]:
    """Все сезоны, новые сверху."""
    db = get_db()
    return [dict(r) for r in db.execute(
        "SELECT * FROM season ORDER BY start_date DESC, id DESC"
    ).fetchall()]


def get_season(season_id: int):
    db = get_db()
    return db.execute("SELECT * FROM season WHERE id = ?", (season_id,)).fetchone()


def set_active_season(season_id: int) -> int:
    """Сделать сезон активным. Текущий активный закрывается (мягко):
    его end_date заполняется сегодняшней датой, если ещё не задана.
    Возвращает id бывшего активного (0, если не было)."""
    from datetime import date
    db = get_db()
    cur = db.execute("SELECT id, end_date FROM season WHERE is_active = 1").fetchone()
    old_id = cur["id"] if cur else 0
    if old_id and old_id != season_id:
        # Закрываем бывший активный
        if not cur["end_date"]:
            db.execute(
                "UPDATE season SET is_active = 0, end_date = ? WHERE id = ?",
                (date.today().isoformat(), old_id),
            )
        else:
            db.execute("UPDATE season SET is_active = 0 WHERE id = ?", (old_id,))
    # Активируем новый
    db.execute("UPDATE season SET is_active = 0 WHERE id != ?", (season_id,))
    db.execute("UPDATE season SET is_active = 1 WHERE id = ?", (season_id,))
    db.commit()
    return old_id


def rename_season(season_id: int, name: str) -> None:
    db = get_db()
    db.execute("UPDATE season SET name = ? WHERE id = ?", (name.strip(), season_id))
    db.commit()


def get_season_stats(season_id: int) -> dict:
    """Сводка по сезону: сколько приняли/высушили/продали/потратили."""
    db = get_db()
    accepted = db.execute(
        "SELECT COALESCE(SUM(weight_kg), 0) AS kg, "
        "COALESCE(SUM(total_amount), 0) AS amount "
        "FROM acceptance WHERE season_id = ?", (season_id,)
    ).fetchone()
    dried = db.execute(
        "SELECT "
        "COALESCE(SUM(raw_grade_1_kg + raw_grade_2_kg + raw_grade_3_kg), 0) AS raw, "
        "COALESCE(SUM(dry_grade_1_kg + dry_grade_2_kg + dry_grade_3_kg), 0) AS dry "
        "FROM drying_run WHERE season_id = ?", (season_id,)
    ).fetchone()
    sales = db.execute(
        "SELECT COALESCE(SUM(weight_kg), 0) AS kg, "
        "COALESCE(SUM(total_amount), 0) AS amount "
        "FROM sale WHERE season_id = ?", (season_id,)
    ).fetchone()
    drying_cost = db.execute(
        "SELECT COALESCE(SUM(COALESCE(cost_electricity, 0) + COALESCE(cost_water, 0) + "
        "COALESCE(cost_firewood, 0) + COALESCE(cost_labor, 0)), 0) AS total "
        "FROM drying_run WHERE season_id = ?", (season_id,)
    ).fetchone()
    waste = db.execute(
        "SELECT COALESCE(SUM(weight_kg), 0) AS kg FROM waste_record WHERE season_id = ?",
        (season_id,)
    ).fetchone()
    expenses = db.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM expense WHERE season_id = ?",
        (season_id,)
    ).fetchone()
    return {
        "accepted_kg": float(accepted["kg"] or 0),
        "accepted_amount": float(accepted["amount"] or 0),
        "dried_raw_kg": float(dried["raw"] or 0),
        "dried_dry_kg": float(dried["dry"] or 0),
        "sales_kg": float(sales["kg"] or 0),
        "sales_amount": float(sales["amount"] or 0),
        "drying_cost": float(drying_cost["total"] or 0),
        "waste_kg": float(waste["kg"] or 0),
        "expenses_total": float(expenses["total"] or 0),
    }
