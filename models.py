"""РҐРµР»РїРµСЂС‹ РґР»СЏ СЂР°Р±РѕС‚С‹ СЃ Р‘Р”: Р·Р°РїСЂРѕСЃС‹ Рє СЃСѓС‰РЅРѕСЃС‚СЏРј."""
from datetime import date
from db import get_db


# --- РЎРµР·РѕРЅС‹ ------------------------------------------------------------------

def get_active_season_id() -> int | None:
    db = get_db()
    row = db.execute("SELECT id FROM season WHERE is_active = 1 ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"] if row else None


# --- РЎРѕСЂС‚Р° --------------------------------------------------------------------

def list_grades() -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("SELECT * FROM grade ORDER BY sort_order")]


def grade_by_id(grade_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM grade WHERE id = ?", (grade_id,)).fetchone()
    return dict(row) if row else None


# --- Р—Р°РєСѓРїРѕС‡РЅС‹Рµ С†РµРЅС‹ ----------------------------------------------------------

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
    """РџРѕСЃР»РµРґРЅСЏСЏ С†РµРЅР° РґР»СЏ СЃРѕСЂС‚Р°, РґРµР№СЃС‚РІСѓСЋС‰Р°СЏ РЅР° СѓРєР°Р·Р°РЅРЅСѓСЋ РґР°С‚Сѓ (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ вЂ” СЃРµРіРѕРґРЅСЏ)."""
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
    """{grade_id: С†РµРЅР°} РґР»СЏ РІСЃРµС… СЃРѕСЂС‚РѕРІ РЅР° РґР°С‚Сѓ."""
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


# --- РџРѕСЃС‚Р°РІС‰РёРєРё ---------------------------------------------------------------

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
    """РЈРґР°Р»РёС‚СЊ РїРѕСЃС‚Р°РІС‰РёРєР°. РЎРІСЏР·Р°РЅРЅС‹Рµ РїСЂРёС‘РјРєРё РїРѕР»СѓС‡Р°С‚ supplier_id = NULL.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ С‡РёСЃР»Рѕ Р·Р°С‚СЂРѕРЅСѓС‚С‹С… РїСЂРёС‘РјРѕРє (РґР»СЏ РёРЅС„РѕСЂРјР°С†РёРё)."""
    db = get_db()
    affected = db.execute(
        "SELECT COUNT(*) AS c FROM acceptance WHERE supplier_id = ?", (supplier_id,)
    ).fetchone()["c"]
    db.execute("UPDATE acceptance SET supplier_id = NULL WHERE supplier_id = ?", (supplier_id,))
    db.execute("DELETE FROM supplier WHERE id = ?", (supplier_id,))
    db.commit()
    return affected


# --- РџСЂРёС‘РјРєР° ------------------------------------------------------------------

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


# --- РћСЃС‚Р°С‚РєРё ------------------------------------------------------------------

def get_raw_stock(season_id: int) -> dict[int, float]:
    """РћСЃС‚Р°С‚РєРё СЃС‹СЂСЊСЏ РїРѕ СЃРѕСЂС‚Р°Рј: РїСЂРёРЅСЏС‚Рѕ в€’ РѕС‚РїСЂР°РІР»РµРЅРѕ РІ СЃСѓС€РєСѓ."""
    db = get_db()
    out = {g["id"]: 0.0 for g in list_grades()}

    for r in db.execute("""
        SELECT grade_id, COALESCE(SUM(weight_kg), 0) AS kg
        FROM acceptance WHERE season_id = ? GROUP BY grade_id
    """, (season_id,)):
        out[r["grade_id"]] = float(r["kg"])

    if out.get(1) or out.get(2) or out.get(3):
        r = db.execute("""
            SELECT
                COALESCE(SUM(raw_grade_1_kg), 0) AS r1,
                COALESCE(SUM(raw_grade_2_kg), 0) AS r2,
                COALESCE(SUM(raw_grade_3_kg), 0) AS r3
            FROM drying_run WHERE season_id = ?
        """, (season_id,)).fetchone()
        out[1] -= float(r["r1"])
        out[2] -= float(r["r2"])
        out[3] -= float(r["r3"])

    return out


def get_dry_stock(season_id: int) -> dict[int, float]:
    """РћСЃС‚Р°С‚РєРё СЃСѓС…РѕРіРѕ РїРѕ СЃРѕСЂС‚Р°Рј: РІС‹С…РѕРґ СЃСѓС€РєРё в€’ РїСЂРѕРґР°РЅРѕ."""
    db = get_db()
    out = {g["id"]: 0.0 for g in list_grades()}

    r = db.execute("""
        SELECT
            COALESCE(SUM(dry_grade_1_kg), 0) AS d1,
            COALESCE(SUM(dry_grade_2_kg), 0) AS d2,
            COALESCE(SUM(dry_grade_3_kg), 0) AS d3
        FROM drying_run WHERE season_id = ?
    """, (season_id,)).fetchone()
    out[1] += float(r["d1"])
    out[2] += float(r["d2"])
    out[3] += float(r["d3"])

    for r in db.execute("""
        SELECT grade_id, COALESCE(SUM(weight_kg), 0) AS kg
        FROM sale WHERE season_id = ? GROUP BY grade_id
    """, (season_id,)):
        out[r["grade_id"]] -= float(r["kg"])

    return out


def get_raw_stock_total_season(season_id: int) -> dict:
    """РЎСѓРјРјС‹ Р·Р° СЃРµР·РѕРЅ: РїСЂРёРЅСЏС‚Рѕ РєРі Рё в‚Ѕ."""
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


# --- РЎСѓС€РєР° --------------------------------------------------------------------

def add_drying_run(date_: str, season_id: int, raw_by_grade: dict, dry_by_grade: dict,
                   cost_electricity: float, cost_water: float,
                   cost_firewood: float, cost_labor: float, notes: str | None) -> int:
    """РЎРѕР·РґР°С‚СЊ Р·Р°РїРёСЃСЊ СЃСѓС€РєРё. raw_by_grade/dry_by_grade: {grade_id: РєРі}."""
    db = get_db()
    cur = db.execute("""
        INSERT INTO drying_run (
            date, season_id,
            raw_grade_1_kg, raw_grade_2_kg, raw_grade_3_kg,
            dry_grade_1_kg, dry_grade_2_kg, dry_grade_3_kg,
            cost_electricity, cost_water, cost_firewood, cost_labor, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        date_, season_id,
        float(raw_by_grade.get(1, 0) or 0),
        float(raw_by_grade.get(2, 0) or 0),
        float(raw_by_grade.get(3, 0) or 0),
        float(dry_by_grade.get(1, 0) or 0),
        float(dry_by_grade.get(2, 0) or 0),
        float(dry_by_grade.get(3, 0) or 0),
        float(cost_electricity or 0), float(cost_water or 0),
        float(cost_firewood or 0), float(cost_labor or 0),
        (notes or "").strip() or None,
    ))
    db.commit()
    return cur.lastrowid


def get_drying_run(run_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM drying_run WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_drying_runs_for_date(date_: str, season_id: int) -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT * FROM drying_run
        WHERE date = ? AND season_id = ?
        ORDER BY id DESC
    """, (date_, season_id))]


def list_drying_runs_for_season(season_id: int) -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT * FROM drying_run
        WHERE season_id = ?
        ORDER BY date DESC, id DESC
    """, (season_id,))]


def delete_drying_run(run_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM drying_run WHERE id = ?", (run_id,))
    db.commit()


def get_drying_yield_season(season_id: int) -> dict:
    """РЎСѓРјРјС‹ СЃСѓС€РєРё Р·Р° СЃРµР·РѕРЅ: kg РїРѕ СЃРѕСЂС‚Р°Рј (raw Рё dry), РѕР±С‰РёР№ РІС‹С…РѕРґ %, СЂР°СЃС…РѕРґС‹."""
    db = get_db()
    row = db.execute("""
        SELECT
            COALESCE(SUM(raw_grade_1_kg), 0) AS r1,
            COALESCE(SUM(raw_grade_2_kg), 0) AS r2,
            COALESCE(SUM(raw_grade_3_kg), 0) AS r3,
            COALESCE(SUM(dry_grade_1_kg), 0) AS d1,
            COALESCE(SUM(dry_grade_2_kg), 0) AS d2,
            COALESCE(SUM(dry_grade_3_kg), 0) AS d3,
            COALESCE(SUM(cost_electricity), 0) AS ce,
            COALESCE(SUM(cost_water), 0) AS cw,
            COALESCE(SUM(cost_firewood), 0) AS cf,
            COALESCE(SUM(cost_labor), 0) AS cl
        FROM drying_run WHERE season_id = ?
    """, (season_id,)).fetchone()
    raw = {1: float(row["r1"]), 2: float(row["r2"]), 3: float(row["r3"])}
    dry = {1: float(row["d1"]), 2: float(row["d2"]), 3: float(row["d3"])}
    total_raw = sum(raw.values())
    total_dry = sum(dry.values())
    yield_pct = (total_dry / total_raw * 100) if total_raw > 0 else 0.0
    yield_by_grade = {}
    for gid in (1, 2, 3):
        r = raw[gid]; d = dry[gid]
        yield_by_grade[gid] = (d / r * 100) if r > 0 else 0.0
    costs = {
        "electricity": float(row["ce"]),
        "water": float(row["cw"]),
        "firewood": float(row["cf"]),
        "labor": float(row["cl"]),
    }
    costs["total"] = sum(costs.values())
    return {
        "raw": raw, "dry": dry,
        "total_raw": total_raw, "total_dry": total_dry,
        "yield_pct": yield_pct, "yield_by_grade": yield_by_grade,
        "costs": costs,
    }


# --- РњСѓСЃРѕСЂ --------------------------------------------------------------------

def add_waste_record(date_: str, season_id: int, weight_kg: float) -> int:
    db = get_db()
    cur = db.execute("""
        INSERT INTO waste_record (date, season_id, weight_kg)
        VALUES (?, ?, ?)
    """, (date_, season_id, float(weight_kg)))
    db.commit()
    return cur.lastrowid


def list_waste_records_for_date(date_: str, season_id: int) -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT * FROM waste_record
        WHERE date = ? AND season_id = ?
        ORDER BY id DESC
    """, (date_, season_id))]


def list_waste_records_for_season(season_id: int) -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT * FROM waste_record
        WHERE season_id = ?
        ORDER BY date DESC, id DESC
    """, (season_id,))]


def delete_waste_record(record_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM waste_record WHERE id = ?", (record_id,))
    db.commit()


def get_waste_total_season(season_id: int) -> float:
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(weight_kg), 0) AS kg
        FROM waste_record WHERE season_id = ?
    """, (season_id,)).fetchone()
    return float(row["kg"])


def get_accepted_kg_by_date(date_: str, season_id: int) -> float:
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(weight_kg), 0) AS kg
        FROM acceptance WHERE date = ? AND season_id = ?
    """, (date_, season_id)).fetchone()
    return float(row["kg"])


def get_waste_kg_by_date(date_: str, season_id: int) -> float:
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(weight_kg), 0) AS kg
        FROM waste_record WHERE date = ? AND season_id = ?
    """, (date_, season_id)).fetchone()
    return float(row["kg"])


def get_drying_kg_by_date(date_: str, season_id: int) -> dict:
    """РЎСѓРјРјС‹ СЃСѓС€РєРё Р·Р° РґРµРЅСЊ: Р·Р°РіСЂСѓР¶РµРЅРѕ Рё РїРѕР»СѓС‡РµРЅРѕ (raw Рё dry)."""
    db = get_db()
    row = db.execute("""
        SELECT
            COALESCE(SUM(raw_grade_1_kg + raw_grade_2_kg + raw_grade_3_kg), 0) AS raw_total,
            COALESCE(SUM(dry_grade_1_kg + dry_grade_2_kg + dry_grade_3_kg), 0) AS dry_total
        FROM drying_run WHERE date = ? AND season_id = ?
    """, (date_, season_id)).fetchone()
    return {"raw": float(row["raw_total"]), "dry": float(row["dry_total"])}


# --- РџРѕРєСѓРїР°С‚РµР»Рё ---------------------------------------------------------------

def list_buyers() -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT b.*,
               (SELECT COUNT(*) FROM sale s WHERE s.buyer_id = b.id) AS uses
        FROM buyer b
        ORDER BY b.name
    """)]


def get_buyer(buyer_id: int) -> dict | None:
    db = get_db()
    row = db.execute("SELECT * FROM buyer WHERE id = ?", (buyer_id,)).fetchone()
    return dict(row) if row else None


def add_buyer(name: str, phone: str | None, notes: str | None) -> int:
    db = get_db()
    cur = db.execute(
        "INSERT INTO buyer (name, phone, notes) VALUES (?, ?, ?)",
        (name.strip(), (phone or "").strip() or None, (notes or "").strip() or None),
    )
    db.commit()
    return cur.lastrowid


def update_buyer(buyer_id: int, name: str, phone: str | None, notes: str | None) -> None:
    db = get_db()
    db.execute(
        "UPDATE buyer SET name = ?, phone = ?, notes = ? WHERE id = ?",
        (name.strip(), (phone or "").strip() or None, (notes or "").strip() or None, buyer_id),
    )
    db.commit()


def delete_buyer(buyer_id: int) -> int:
    """РЈРґР°Р»РёС‚СЊ РїРѕРєСѓРїР°С‚РµР»СЏ. РЎРІСЏР·Р°РЅРЅС‹Рµ РїСЂРѕРґР°Р¶Рё РїРѕР»СѓС‡Р°С‚ buyer_id = NULL.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ С‡РёСЃР»Рѕ Р·Р°С‚СЂРѕРЅСѓС‚С‹С… РїСЂРѕРґР°Р¶ (РґР»СЏ РёРЅС„РѕСЂРјР°С†РёРё)."""
    db = get_db()
    affected = db.execute(
        "SELECT COUNT(*) AS c FROM sale WHERE buyer_id = ?", (buyer_id,)
    ).fetchone()["c"]
    db.execute("UPDATE sale SET buyer_id = NULL WHERE buyer_id = ?", (buyer_id,))
    db.execute("DELETE FROM buyer WHERE id = ?", (buyer_id,))
    db.commit()
    return affected


# --- РџСЂРѕРґР°Р¶Рё ------------------------------------------------------------------

def add_sale(date_: str, season_id: int, buyer_id: int | None, grade_id: int,
             weight_kg: float, price_per_kg: float) -> int:
    total = round(float(weight_kg) * float(price_per_kg), 2)
    db = get_db()
    cur = db.execute("""
        INSERT INTO sale
            (date, season_id, buyer_id, grade_id, weight_kg, price_per_kg, total_amount)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (date_, season_id, buyer_id or None, grade_id,
          float(weight_kg), float(price_per_kg), total))
    db.commit()
    return cur.lastrowid


def get_sale(sale_id: int) -> dict | None:
    db = get_db()
    row = db.execute("""
        SELECT s.*, g.display_name AS grade_name, b.name AS buyer_name
        FROM sale s
        JOIN grade g ON g.id = s.grade_id
        LEFT JOIN buyer b ON b.id = s.buyer_id
        WHERE s.id = ?
    """, (sale_id,)).fetchone()
    return dict(row) if row else None


def list_sales_for_date(date_: str, season_id: int) -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT s.*, g.display_name AS grade_name, g.sort_order,
               b.name AS buyer_name
        FROM sale s
        JOIN grade g ON g.id = s.grade_id
        LEFT JOIN buyer b ON b.id = s.buyer_id
        WHERE s.date = ? AND s.season_id = ?
        ORDER BY s.id DESC
    """, (date_, season_id))]


def list_sales_for_season(season_id: int) -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT s.*, g.display_name AS grade_name, g.sort_order,
               b.name AS buyer_name
        FROM sale s
        JOIN grade g ON g.id = s.grade_id
        LEFT JOIN buyer b ON b.id = s.buyer_id
        WHERE s.season_id = ?
        ORDER BY s.date DESC, s.id DESC
    """, (season_id,))]


def delete_sale(sale_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM sale WHERE id = ?", (sale_id,))
    db.commit()


def get_sales_total_season(season_id: int) -> dict:
    """РџСЂРѕРґР°Р¶Рё Р·Р° СЃРµР·РѕРЅ: РѕР±С‰Р°СЏ РІС‹СЂСѓС‡РєР°, РїРѕ СЃРѕСЂС‚Р°Рј."""
    db = get_db()
    row = db.execute("""
        SELECT
            COALESCE(SUM(total_amount), 0) AS total,
            COALESCE(SUM(weight_kg), 0) AS kg
        FROM sale WHERE season_id = ?
    """, (season_id,)).fetchone()
    by_grade = {g["id"]: 0.0 for g in list_grades()}
    for r in db.execute("""
        SELECT grade_id, COALESCE(SUM(weight_kg), 0) AS kg
        FROM sale WHERE season_id = ? GROUP BY grade_id
    """, (season_id,)):
        by_grade[r["grade_id"]] = float(r["kg"])
    return {
        "total_amount": float(row["total"] or 0),
        "total_kg": float(row["kg"] or 0),
        "by_grade_kg": by_grade,
    }


def get_sales_kg_by_date(date_: str, season_id: int) -> dict:
    """РџСЂРѕРґР°РЅРѕ Р·Р° РґРµРЅСЊ: РєРі Рё в‚Ѕ."""
    db = get_db()
    row = db.execute("""
        SELECT
            COALESCE(SUM(weight_kg), 0) AS kg,
            COALESCE(SUM(total_amount), 0) AS amount
        FROM sale WHERE date = ? AND season_id = ?
    """, (date_, season_id)).fetchone()
    return {"kg": float(row["kg"]), "amount": float(row["amount"])}


# --- Р Р°СЃС…РѕРґС‹ (РѕР±С‰РёРµ, РЅРµ СЃСѓС€РєР°) ------------------------------------------------

def add_expense(date_: str, season_id: int, category: str, amount: float, notes: str | None) -> int:
    db = get_db()
    cur = db.execute("""
        INSERT INTO expense (date, season_id, category, amount, notes)
        VALUES (?, ?, ?, ?, ?)
    """, (date_, season_id, category.strip(), float(amount), (notes or "").strip() or None))
    db.commit()
    return cur.lastrowid


def list_expenses_for_date(date_: str, season_id: int) -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT * FROM expense
        WHERE date = ? AND season_id = ?
        ORDER BY id DESC
    """, (date_, season_id))]


def list_expenses_for_season(season_id: int) -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("""
        SELECT * FROM expense
        WHERE season_id = ?
        ORDER BY date DESC, id DESC
    """, (season_id,))]


def delete_expense(record_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM expense WHERE id = ?", (record_id,))
    db.commit()


def get_expenses_total_season(season_id: int) -> dict:
    """Р Р°СЃС…РѕРґС‹ Р·Р° СЃРµР·РѕРЅ: РѕР±С‰Р°СЏ СЃСѓРјРјР° Рё РїРѕ РєР°С‚РµРіРѕСЂРёСЏРј."""
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expense WHERE season_id = ?
    """, (season_id,)).fetchone()
    by_category = {}
    for r in db.execute("""
        SELECT category, COALESCE(SUM(amount), 0) AS amount
        FROM expense WHERE season_id = ? GROUP BY category
    """, (season_id,)):
        by_category[r["category"]] = float(r["amount"])
    return {"total": float(row["total"] or 0), "by_category": by_category}


def get_expenses_by_date(date_: str, season_id: int) -> float:
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expense WHERE date = ? AND season_id = ?
    """, (date_, season_id)).fetchone()
    return float(row["total"] or 0)


# --- Отчёты -------------------------------------------------------------------

def _date_filter(table_alias: str, date_from: str | None, date_to: str | None) -> tuple[str, list]:
    """Построить фрагмент WHERE и список параметров для фильтра по дате."""
    col = f"{table_alias}.date" if table_alias else "date"
    parts = []
    params = []
    if date_from:
        parts.append(f"{col} >= ?")
        params.append(date_from)
    if date_to:
        parts.append(f"{col} <= ?")
        params.append(date_to)
    if parts:
        return " AND " + " AND ".join(parts), params
    return "", []


def pnl_by_period(season_id: int, date_from: str | None = None, date_to: str | None = None) -> dict:
    """P&L за период: выручка минус все расходы."""
    db = get_db()
    where, params = _date_filter("", date_from, date_to)
    where = " WHERE season_id = ?" + where
    acc = db.execute(
        f"SELECT COALESCE(SUM(weight_kg), 0) AS kg, COALESCE(SUM(total_amount), 0) AS amount "
        f"FROM acceptance{where}", (season_id, *params)).fetchone()
    sales = db.execute(
        f"SELECT COALESCE(SUM(weight_kg), 0) AS kg, COALESCE(SUM(total_amount), 0) AS amount "
        f"FROM sale{where}", (season_id, *params)).fetchone()
    drying = db.execute(
        f"SELECT "
        f"COALESCE(SUM(raw_grade_1_kg + raw_grade_2_kg + raw_grade_3_kg), 0) AS raw, "
        f"COALESCE(SUM(dry_grade_1_kg + dry_grade_2_kg + dry_grade_3_kg), 0) AS dry, "
        f"COALESCE(SUM(COALESCE(cost_electricity, 0) + COALESCE(cost_water, 0) + "
        f"COALESCE(cost_firewood, 0) + COALESCE(cost_labor, 0)), 0) AS cost "
        f"FROM drying_run{where}", (season_id, *params)).fetchone()
    waste = db.execute(
        f"SELECT COALESCE(SUM(weight_kg), 0) AS kg FROM waste_record{where}",
        (season_id, *params)).fetchone()
    expenses = db.execute(
        f"SELECT COALESCE(SUM(amount), 0) AS total FROM expense{where}",
        (season_id, *params)).fetchone()
    revenue = float(sales["amount"] or 0)
    total_cost = float(expenses["total"] or 0) + float(drying["cost"] or 0)
    return {
        "accepted_kg": float(acc["kg"] or 0),
        "accepted_amount": float(acc["amount"] or 0),
        "dried_raw_kg": float(drying["raw"] or 0),
        "dried_dry_kg": float(drying["dry"] or 0),
        "drying_cost": float(drying["cost"] or 0),
        "waste_kg": float(waste["kg"] or 0),
        "sales_kg": float(sales["kg"] or 0),
        "revenue": revenue,
        "expenses_total": float(expenses["total"] or 0),
        "total_cost": total_cost,
        "profit": revenue - total_cost,
    }


def supplier_summary(season_id: int, date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """Сводка по поставщикам. Без поставщика - отдельной строкой."""
    db = get_db()
    where, params = _date_filter("a", date_from, date_to)
    sql = f"""
        SELECT s.id AS supplier_id, s.name AS supplier_name,
               COALESCE(SUM(a.weight_kg), 0) AS kg,
               COALESCE(SUM(a.total_amount), 0) AS amount,
               COUNT(a.id) AS deliveries
        FROM acceptance a
        LEFT JOIN supplier s ON s.id = a.supplier_id
        WHERE a.season_id = ?{where}
        GROUP BY COALESCE(s.id, 0)
        ORDER BY amount DESC
    """
    return [dict(r) for r in db.execute(sql, (season_id, *params)).fetchall()]


def buyer_summary(season_id: int, date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """Сводка по покупателям. Без покупателя - отдельной строкой."""
    db = get_db()
    where, params = _date_filter("s", date_from, date_to)
    sql = f"""
        SELECT b.id AS buyer_id, b.name AS buyer_name,
               COALESCE(SUM(s.weight_kg), 0) AS kg,
               COALESCE(SUM(s.total_amount), 0) AS amount,
               COUNT(s.id) AS deals
        FROM sale s
        LEFT JOIN buyer b ON b.id = s.buyer_id
        WHERE s.season_id = ?{where}
        GROUP BY COALESCE(b.id, 0)
        ORDER BY amount DESC
    """
    return [dict(r) for r in db.execute(sql, (season_id, *params)).fetchall()]


def daily_summary(season_id: int, date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """Сводка по дням. По одной строке на дату с движением, новые сверху."""
    db = get_db()
    where, params = _date_filter("", date_from, date_to)
    where = " WHERE season_id = ?" + where
    acc = {r["date"]: r for r in db.execute(
        f"SELECT date, COALESCE(SUM(weight_kg), 0) AS kg, COALESCE(SUM(total_amount), 0) AS amount "
        f"FROM acceptance{where} GROUP BY date", (season_id, *params))}
    dry = {r["date"]: r for r in db.execute(
        f"SELECT date, "
        f"COALESCE(SUM(raw_grade_1_kg + raw_grade_2_kg + raw_grade_3_kg), 0) AS raw, "
        f"COALESCE(SUM(dry_grade_1_kg + dry_grade_2_kg + dry_grade_3_kg), 0) AS dry, "
        f"COALESCE(SUM(COALESCE(cost_electricity, 0) + COALESCE(cost_water, 0) + "
        f"COALESCE(cost_firewood, 0) + COALESCE(cost_labor, 0)), 0) AS cost "
        f"FROM drying_run{where} GROUP BY date", (season_id, *params))}
    waste = {r["date"]: r["kg"] for r in db.execute(
        f"SELECT date, COALESCE(SUM(weight_kg), 0) AS kg FROM waste_record{where} "
        f"GROUP BY date", (season_id, *params))}
    sales = {r["date"]: r for r in db.execute(
        f"SELECT date, COALESCE(SUM(weight_kg), 0) AS kg, COALESCE(SUM(total_amount), 0) AS amount "
        f"FROM sale{where} GROUP BY date", (season_id, *params))}
    exp = {r["date"]: r["total"] for r in db.execute(
        f"SELECT date, COALESCE(SUM(amount), 0) AS total FROM expense{where} "
        f"GROUP BY date", (season_id, *params))}
    all_dates = sorted(set(acc) | set(dry) | set(waste) | set(sales) | set(exp), reverse=True)
    rows = []
    for d in all_dates:
        a = acc.get(d, {"kg": 0, "amount": 0})
        dr = dry.get(d, {"raw": 0, "dry": 0, "cost": 0})
        s = sales.get(d, {"kg": 0, "amount": 0})
        e = exp.get(d, 0)
        revenue = float(s["amount"] or 0)
        cost = float(e or 0) + float(dr["cost"] or 0)
        rows.append({
            "date": d,
            "accepted_kg": float(a["kg"] or 0),
            "accepted_amount": float(a["amount"] or 0),
            "dried_raw_kg": float(dr["raw"] or 0),
            "dried_dry_kg": float(dr["dry"] or 0),
            "drying_cost": float(dr["cost"] or 0),
            "waste_kg": float(waste.get(d, 0) or 0),
            "sales_kg": float(s["kg"] or 0),
            "revenue": revenue,
            "expenses_total": float(e or 0),
            "profit": revenue - cost,
        })
    return rows

