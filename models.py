"""Хелперы для работы с БД: запросы к сущностям."""
from datetime import date
from db import get_db


# --- Сезоны ------------------------------------------------------------------

def get_active_season_id() -> int | None:
    db = get_db()
    row = db.execute("SELECT id FROM season WHERE is_active = 1 ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"] if row else None


# --- Сорта --------------------------------------------------------------------

def list_grades() -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("SELECT * FROM grade ORDER BY sort_order")]


def grade_by_id(grade_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM grade WHERE id = ?", (grade_id,)).fetchone()
    return dict(row) if row else None


# --- Закупочные цены ----------------------------------------------------------

def list_purchase_prices() -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT pp.id, pp.grade_id, pp.price_per_kg, pp.effective_from,
               g.display_name AS grade_name, g.sort_order
        FROM purchase_price pp
        JOIN grade g ON g.id = pp.grade_id
        ORDER BY pp.effective_from DESC, g.sort_order
    """)]


def latest_price_for_grade(grade_id: int, on_date: str | None = None) -> float | None:
    """Последняя цена для сорта, действующая на указанную дату (по умолчанию — сегодня)."""
    if on_date is None:
        on_date = date.today().isoformat()
    db = get_db()
    row = db.execute("""
        SELECT price_per_kg FROM purchase_price
        WHERE grade_id = ? AND effective_from <= ?
        ORDER BY effective_from DESC LIMIT 1
    """, (grade_id, on_date)).fetchone()
    return row["price_per_kg"] if row else None


def latest_prices_dict(on_date: str | None = None) -> dict[int, float]:
    """{grade_id: цена} для всех сортов на дату."""
    return {g["id"]: (latest_price_for_grade(g["id"], on_date) or 0)
            for g in list_grades()}


def add_purchase_price(grade_id: int, price_per_kg: float, effective_from: str) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO purchase_price (grade_id, price_per_kg, effective_from) VALUES (?, ?, ?)",
        (grade_id, price_per_kg, effective_from),
    )
    db.commit()
    return cur.lastrowid


def delete_purchase_price(price_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM purchase_price WHERE id = ?", (price_id,))
    db.commit()


# --- Поставщики ---------------------------------------------------------------

def list_suppliers() -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT s.*,
               (SELECT COUNT(*) FROM acceptance a WHERE a.supplier_id = s.id) AS uses
        FROM supplier s
        ORDER BY s.name
    """)]


def get_supplier(supplier_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM supplier WHERE id = ?", (supplier_id,)).fetchone()
    return dict(row) if row else None


def add_supplier(name: str, phone: str | None, notes: str | None) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO supplier (name, phone, notes) VALUES (?, ?, ?)",
        (name.strip(), (phone or "").strip() or None, (notes or "").strip() or None),
    )
    db.commit()
    return cur.lastrowid


def update_supplier(supplier_id: int, name: str, phone: str | None, notes: str | None) -> None:
    db = get_db()
    db.execute(
        "UPDATE supplier SET name = ?, phone = ?, notes = ? WHERE id = ?",
        (name.strip(), (phone or "").strip() or None, (notes or "").strip() or None, supplier_id),
    )
    db.commit()


def delete_supplier(supplier_id: int) -> int:
    """Удалить поставщика. Связанные приёмки получат supplier_id = NULL.
    Возвращает число затронутых приёмок (для информации)."""
    db = get_db()
    affected = db.execute(
        "SELECT COUNT(*) AS c FROM acceptance WHERE supplier_id = ?", (supplier_id,)
    ).fetchone()["c"]
    db.execute("UPDATE acceptance SET supplier_id = NULL WHERE supplier_id = ?", (supplier_id,))
    db.execute("DELETE FROM supplier WHERE id = ?", (supplier_id,))
    db.commit()
    return affected


# --- Приёмка ------------------------------------------------------------------

def add_acceptance(date_: str, season_id: int, grade_id: int, weight_kg: float,
                   price_per_kg: float, supplier_id: int | None, notes: str | None) -> int:
    total = round(float(weight_kg) * float(price_per_kg), 2)
    db = get_db()
    cur = db.execute("""
        INSERT INTO acceptance
            (date, season_id, grade_id, weight_kg, price_per_kg, total_amount, supplier_id, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (date_, season_id, grade_id, float(weight_kg), float(price_per_kg), total,
          supplier_id or None, (notes or "").strip() or None))
    db.commit()
    return cur.lastrowid


def get_acceptance(record_id: int) -> dict | None:
    db = get_db()
    row = db.execute("""
        SELECT a.*, g.display_name AS grade_name, s.name AS supplier_name
        FROM acceptance a
        JOIN grade g ON g.id = a.grade_id
        LEFT JOIN supplier s ON s.id = a.supplier_id
        WHERE a.id = ?
    """, (record_id,)).fetchone()
    return dict(row) if row else None


def list_acceptance_for_date(date_: str, season_id: int) -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT a.*, g.display_name AS grade_name, g.sort_order,
               s.name AS supplier_name
        FROM acceptance a
        JOIN grade g ON g.id = a.grade_id
        LEFT JOIN supplier s ON s.id = a.supplier_id
        WHERE a.date = ? AND a.season_id = ?
        ORDER BY a.created_rowid DESC, g.sort_order
    """.replace("a.created_rowid", "a.id"), (date_, season_id))]


def list_acceptance_for_season(season_id: int) -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT a.*, g.display_name AS grade_name, g.sort_order,
               s.name AS supplier_name
        FROM acceptance a
        JOIN grade g ON g.id = a.grade_id
        LEFT JOIN supplier s ON s.id = a.supplier_id
        WHERE a.season_id = ?
        ORDER BY a.date DESC, a.id DESC
    """, (season_id,))]


def update_acceptance(record_id: int, date_: str, weight_kg: float,
                      price_per_kg: float, supplier_id: int | None, notes: str | None) -> None:
    total = round(float(weight_kg) * float(price_per_kg), 2)
    db = get_db()
    db.execute("""
        UPDATE acceptance
        SET date = ?, weight_kg = ?, price_per_kg = ?, total_amount = ?,
            supplier_id = ?, notes = ?
        WHERE id = ?
    """, (date_, float(weight_kg), float(price_per_kg), total,
          supplier_id or None, (notes or "").strip() or None, record_id))
    db.commit()


def delete_acceptance(record_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM acceptance WHERE id = ?", (record_id,))
    db.commit()


# --- Остатки ------------------------------------------------------------------

def get_raw_stock(season_id: int) -> dict[int, float]:
    """Остатки сырья по сортам: {grade_id: кг}. Сейчас = SUM(приёмка) -
    SUM(отправлено в сушку), но сушка появится в Этапе 3."""
    db = get_db()
    rows = db.execute("""
        SELECT grade_id, COALESCE(SUM(weight_kg), 0) AS kg
        FROM acceptance WHERE season_id = ?
        GROUP BY grade_id
    """, (season_id,)).fetchall()
    out = {g["id"]: 0.0 for g in list_grades()}
    for r in rows:
        out[r["grade_id"]] = float(r["kg"])
    return out


def get_raw_stock_total_season(season_id: int) -> dict:
    """Сумма и общий вес по сортам за сезон + всего."""
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(weight_kg), 0) AS total_kg,
               COALESCE(SUM(total_amount), 0) AS total_amount
        FROM acceptance WHERE season_id = ?
    """, (season_id,)).fetchone()
    by_grade = {g["id"]: 0.0 for g in list_grades()}
    for r in db.execute("""
        SELECT grade_id, COALESCE(SUM(weight_kg), 0) AS kg
        FROM acceptance WHERE season_id = ? GROUP BY grade_id
    """, (season_id,)):
        by_grade[r["grade_id"]] = float(r["kg"])
    return {
        "by_grade_kg": by_grade,
        "total_kg": float(row["total_kg"] or 0),
        "total_amount": float(row["total_amount"] or 0),
    }
