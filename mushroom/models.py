"""РҐРµР»РїРµСЂС‹ РґР»СЏ СЂР°Р±РѕС‚С‹ СЃ Р‘Р”: Р·Р°РїСЂРѕСЃС‹ Рє СЃСѓС‰РЅРѕСЃС‚СЏРј."""
from datetime import date
from db import get_db


# --- Настройки ----------------------------------------------------------------

def get_setting(key, default=None):
    db = get_db()
    row = db.execute("SELECT value FROM app_setting WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key, value):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO app_setting (key, value) VALUES (?, ?)", (key, value))
    db.commit()


def get_all_settings():
    db = get_db()
    rows = db.execute("SELECT key, value FROM app_setting").fetchall()
    return {r["key"]: r["value"] for r in rows}


# --- РЎРµР·РѕРЅС‹ ------------------------------------------------------------------


# --- РЎРѕСЂС‚Р° --------------------------------------------------------------------

def list_grades() -> list[dict]:
    db = get_db()
    return [dict(r) for r in db.execute("SELECT * FROM grade ORDER BY sort_order")]




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

def add_acceptance(date_: str, season_id: int,
                   grades: list[tuple[int, float, float]],
                   supplier_id: int | None, notes: str | None) -> int:
    """Создать приёмку (header + lines).
    grades: [(grade_id, weight_kg, price_per_kg), ...] - только непустые (> 0)."""
    db = get_db()
    cur = db.execute("""
        INSERT INTO acceptance (date, season_id, supplier_id, notes)
        VALUES (?, ?, ?, ?)
    """, (date_, season_id, supplier_id or None, (notes or "").strip() or None))
    acceptance_id = cur.lastrowid
    for grade_id, w, p in grades:
        if w <= 0:
            continue
        total = round(float(w) * float(p), 2)
        db.execute("""
            INSERT INTO acceptance_grade
                (acceptance_id, grade_id, weight_kg, price_per_kg, total_amount)
            VALUES (?, ?, ?, ?, ?)
        """, (acceptance_id, int(grade_id), float(w), float(p), total))
    db.commit()
    return acceptance_id


def get_acceptance(acceptance_id: int) -> dict | None:
    """Вернуть header + список lines. None если не найдено."""
    db = get_db()
    row = db.execute("""
        SELECT a.*, s.name AS supplier_name
        FROM acceptance a
        LEFT JOIN supplier s ON s.id = a.supplier_id
        WHERE a.id = ?
    """, (acceptance_id,)).fetchone()
    if not row:
        return None
    rec = dict(row)
    rec["lines"] = [dict(r) for r in db.execute("""
        SELECT ag.*, g.display_name AS grade_name, g.sort_order
        FROM acceptance_grade ag
        JOIN grade g ON g.id = ag.grade_id
        WHERE ag.acceptance_id = ?
        ORDER BY g.sort_order
    """, (acceptance_id,))]
    return rec


def list_acceptance_for_date(date_: str, season_id: int) -> list[dict]:
    """Список приёмок (header-only) за дату, с подсчётом итогов по сортам."""
    db = get_db()
    rows = [dict(r) for r in db.execute("""
        SELECT a.id, a.date, a.season_id, a.supplier_id, a.notes,
               s.name AS supplier_name
        FROM acceptance a
        LEFT JOIN supplier s ON s.id = a.supplier_id
        WHERE a.date = ? AND a.season_id = ?
        ORDER BY a.id DESC
    """, (date_, season_id))]
    for r in rows:
        g_rows = db.execute("""
            SELECT ag.grade_id, ag.weight_kg, ag.price_per_kg, ag.total_amount,
                   g.display_name AS grade_name, g.sort_order
            FROM acceptance_grade ag
            JOIN grade g ON g.id = ag.grade_id
            WHERE ag.acceptance_id = ?
            ORDER BY g.sort_order
        """, (r["id"],)).fetchall()
        r["lines"] = [dict(gr) for gr in g_rows]
        r["total_kg"] = sum(gr["weight_kg"] for gr in g_rows)
        r["total_amount"] = sum(gr["total_amount"] for gr in g_rows)
    return rows




def update_acceptance(acceptance_id: int, date_: str,
                      grades: list[tuple[int, float, float]],
                      supplier_id: int | None, notes: str | None) -> None:
    """Полная перезапись: обновляем header, удаляем старые lines, вставляем новые."""
    db = get_db()
    db.execute("""
        UPDATE acceptance
        SET date = ?, supplier_id = ?, notes = ?
        WHERE id = ?
    """, (date_, supplier_id or None, (notes or "").strip() or None, acceptance_id))
    db.execute("DELETE FROM acceptance_grade WHERE acceptance_id = ?", (acceptance_id,))
    for grade_id, w, p in grades:
        if w <= 0:
            continue
        total = round(float(w) * float(p), 2)
        db.execute("""
            INSERT INTO acceptance_grade
                (acceptance_id, grade_id, weight_kg, price_per_kg, total_amount)
            VALUES (?, ?, ?, ?, ?)
        """, (acceptance_id, int(grade_id), float(w), float(p), total))
    db.commit()


def delete_acceptance(acceptance_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM acceptance WHERE id = ?", (acceptance_id,))
    db.commit()


# --- РћСЃС‚Р°С‚РєРё ------------------------------------------------------------------

def get_raw_stock(season_id: int) -> dict[int, float]:
    """Остатки сырья на складе (неочищенное): принято − очищено (мусор + в холодильник)."""
    db = get_db()
    out = {g["id"]: 0.0 for g in list_grades()}

    for r in db.execute("""
        SELECT ag.grade_id, COALESCE(SUM(ag.weight_kg), 0) AS kg
        FROM acceptance_grade ag
        JOIN acceptance a ON a.id = ag.acceptance_id
        WHERE a.season_id = ? GROUP BY ag.grade_id
    """, (season_id,)):
        out[r["grade_id"]] = float(r["kg"])

    waste = get_waste_total_season_by_grade(season_id)
    cleaned = get_cleaned_total_season_by_grade(season_id)
    for gid in (1, 2, 3):
        out[gid] -= waste.get(gid, 0.0) + cleaned.get(gid, 0.0)

    return out


def get_fridge_stock(season_id: int) -> dict[int, float]:
    """Остатки в холодильнике (очищенное): очищено − отправлено в сушку."""
    db = get_db()
    cleaned = get_cleaned_total_season_by_grade(season_id)
    out = {gid: cleaned.get(gid, 0.0) for gid in (1, 2, 3)}

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
        FROM sale s JOIN sale_line sl ON sl.sale_id = s.id WHERE s.season_id = ? GROUP BY sl.grade_id
    """, (season_id,)):
        out[r["grade_id"]] -= float(r["kg"])

    return out


def get_raw_stock_total_season(season_id: int) -> dict:
    """Суммы за сезон: принято кг и ₽ (по всем сортам и с разбивкой)."""
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(ag.weight_kg), 0) AS total_kg,
               COALESCE(SUM(ag.total_amount), 0) AS total_amount
        FROM acceptance_grade ag
        JOIN acceptance a ON a.id = ag.acceptance_id
        WHERE a.season_id = ?
    """, (season_id,)).fetchone()
    by_grade = {g["id"]: 0.0 for g in list_grades()}
    for r in db.execute("""
        SELECT ag.grade_id, COALESCE(SUM(ag.weight_kg), 0) AS kg
        FROM acceptance_grade ag
        JOIN acceptance a ON a.id = ag.acceptance_id
        WHERE a.season_id = ? GROUP BY ag.grade_id
    """, (season_id,)):
        by_grade[r["grade_id"]] = float(r["kg"])
    return {
        "by_grade_kg": by_grade,
        "total_kg": float(row["total_kg"] or 0),
        "total_amount": float(row["total_amount"] or 0),
    }


# --- РЎСѓС€РєР° --------------------------------------------------------------------

def add_drying_run(date_: str, season_id: int, raw_by_grade: dict, dry_by_grade: dict = None,
                   cost_electricity: float = 0, cost_water: float = 0,
                   cost_firewood: float = 0, cost_labor: float = 0, notes: str | None = None,
                   started_at: str | None = None) -> int:
    """Создать запись сушки. raw_by_grade/dry_by_grade: {grade_id: кг}."""
    if dry_by_grade is None:
        dry_by_grade = {}
    db = get_db()
    cur = db.execute("""
        INSERT INTO drying_run (
            date, season_id,
            raw_grade_1_kg, raw_grade_2_kg, raw_grade_3_kg,
            dry_grade_1_kg, dry_grade_2_kg, dry_grade_3_kg,
            cost_electricity, cost_water, cost_firewood, cost_labor, notes,
            started_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        started_at,
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
        SELECT d.*,
            COALESCE(de.cost_electricity, 0) AS de_electricity,
            COALESCE(de.cost_water, 0) AS de_water,
            COALESCE(de.cost_firewood, 0) AS de_firewood,
            COALESCE(de.cost_labor, 0) AS de_labor,
            COALESCE(de.cost_electricity + de.cost_water + de.cost_firewood + de.cost_labor, 0) AS de_total
        FROM drying_run d
        LEFT JOIN drying_expense de ON de.drying_run_id = d.id
        WHERE d.date = ? AND d.season_id = ?
        ORDER BY d.id DESC
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



def finish_drying(run_id, dry_by_grade):
    """Завершить сушку: заполнить dry_*_kg и finished_at."""
    db = get_db()
    from datetime import datetime
    d1 = dry_by_grade.get(1, 0.0)
    d2 = dry_by_grade.get(2, 0.0)
    d3 = dry_by_grade.get(3, 0.0)
    db.execute(
        """UPDATE drying_run
           SET dry_grade_1_kg = ?, dry_grade_2_kg = ?, dry_grade_3_kg = ?,
               finished_at = ?
           WHERE id = ?""",
        (d1, d2, d3, datetime.now().isoformat(timespec="seconds"), run_id),
    )
    db.commit()


def add_drying_expense(run_id, cost_electricity, cost_water, cost_firewood, cost_labor, notes=""):
    """Добавить расходы к записи сушки."""
    db = get_db()
    cur = db.execute(
        """INSERT INTO drying_expense
           (drying_run_id, cost_electricity, cost_water, cost_firewood, cost_labor, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (run_id, cost_electricity, cost_water, cost_firewood, cost_labor, notes),
    )
    db.commit()
    return cur.lastrowid


def get_drying_expenses(run_id):
    """Получить все расходы для записи сушки."""
    db = get_db()
    return [dict(r) for r in db.execute(
        "SELECT * FROM drying_expense WHERE drying_run_id = ? ORDER BY id", (run_id,)
    ).fetchall()]


def list_drying_runs_all(season_id):
    """Все записи сушки за сезон (для выбора в расходах)."""
    db = get_db()
    return [dict(r) for r in db.execute(
        """SELECT id, date,
                  (raw_grade_1_kg + raw_grade_2_kg + raw_grade_3_kg) AS total_raw,
                  (dry_grade_1_kg + dry_grade_2_kg + dry_grade_3_kg) AS total_dry,
                  started_at, finished_at
           FROM drying_run WHERE season_id = ? ORDER BY date DESC, id DESC""",
        (season_id,),
    ).fetchall()]
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

def list_acceptances_for_waste(season_id: int) -> list[dict]:
    db = get_db()
    acceptances = [dict(r) for r in db.execute("""
        SELECT a.id, a.date, a.supplier_id, s.name AS supplier_name
        FROM acceptance a
        LEFT JOIN supplier s ON s.id = a.supplier_id
        WHERE a.season_id = ?
        ORDER BY a.date DESC, a.id DESC
    """, (season_id,))]
    for acc in acceptances:
        acc["grades"] = {}
        for r in db.execute("""
            SELECT ag.grade_id, ag.weight_kg
            FROM acceptance_grade ag
            WHERE ag.acceptance_id = ?
        """, (acc["id"],)):
            acc["grades"][r["grade_id"]] = float(r["weight_kg"])
        acc["total_kg"] = sum(acc["grades"].values())
    return acceptances


def get_acceptance_remaining(acceptance_id: int, season_id: int) -> dict[int, float]:
    db = get_db()
    accepted = {1: 0.0, 2: 0.0, 3: 0.0}
    for r in db.execute("""
        SELECT ag.grade_id, ag.weight_kg
        FROM acceptance_grade ag
        WHERE ag.acceptance_id = ?
    """, (acceptance_id,)):
        accepted[r["grade_id"]] = float(r["weight_kg"])

    processed = {1: 0.0, 2: 0.0, 3: 0.0}
    for r in db.execute("""
        SELECT
            COALESCE(SUM(grade_1_kg + cleaned_grade_1_kg), 0) AS p1,
            COALESCE(SUM(grade_2_kg + cleaned_grade_2_kg), 0) AS p2,
            COALESCE(SUM(grade_3_kg + cleaned_grade_3_kg), 0) AS p3
        FROM waste_record WHERE acceptance_id = ?
    """, (acceptance_id,)):
        processed[1] = float(r["p1"])
        processed[2] = float(r["p2"])
        processed[3] = float(r["p3"])

    return {gid: max(0.0, accepted[gid] - processed[gid]) for gid in (1, 2, 3)}


def add_waste_record(date_: str, season_id: int,
                     kg_by_grade: dict[int, float],
                     cleaned_by_grade: dict[int, float] | None = None,
                     supplier_id: int | None = None,
                     acceptance_id: int | None = None,
                     notes: str | None = None) -> int:
    """Создать запись мусора с разбивкой по сортам. kg_by_grade = {1: kg, 2: kg, 3: kg}.
    cleaned_by_grade = {1: kg, 2: kg, 3: kg} — очищено, отправлено в холодильник."""
    if cleaned_by_grade is None:
        cleaned_by_grade = {1: 0, 2: 0, 3: 0}
    db = get_db()
    cur = db.execute("""
        INSERT INTO waste_record (date, season_id, grade_1_kg, grade_2_kg, grade_3_kg,
                                  cleaned_grade_1_kg, cleaned_grade_2_kg, cleaned_grade_3_kg,
                                  supplier_id, acceptance_id, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        date_, season_id,
        float(kg_by_grade.get(1, 0) or 0),
        float(kg_by_grade.get(2, 0) or 0),
        float(kg_by_grade.get(3, 0) or 0),
        float(cleaned_by_grade.get(1, 0) or 0),
        float(cleaned_by_grade.get(2, 0) or 0),
        float(cleaned_by_grade.get(3, 0) or 0),
        supplier_id or None,
        acceptance_id or None,
        (notes or "").strip() or None,
    ))
    db.commit()
    return cur.lastrowid


def update_waste_record(record_id: int, date_: str,
                        kg_by_grade: dict[int, float],
                        cleaned_by_grade: dict[int, float] | None = None,
                        supplier_id: int | None = None,
                        acceptance_id: int | None = None,
                        notes: str | None = None) -> None:
    if cleaned_by_grade is None:
        cleaned_by_grade = {1: 0, 2: 0, 3: 0}
    db = get_db()
    db.execute("""
        UPDATE waste_record
        SET date = ?, grade_1_kg = ?, grade_2_kg = ?, grade_3_kg = ?,
            cleaned_grade_1_kg = ?, cleaned_grade_2_kg = ?, cleaned_grade_3_kg = ?,
            supplier_id = ?, acceptance_id = ?, notes = ?
        WHERE id = ?
    """, (
        date_,
        float(kg_by_grade.get(1, 0) or 0),
        float(kg_by_grade.get(2, 0) or 0),
        float(kg_by_grade.get(3, 0) or 0),
        float(cleaned_by_grade.get(1, 0) or 0),
        float(cleaned_by_grade.get(2, 0) or 0),
        float(cleaned_by_grade.get(3, 0) or 0),
        supplier_id or None,
        acceptance_id or None,
        (notes or "").strip() or None,
        record_id,
    ))
    db.commit()


def get_waste_record(record_id: int) -> dict | None:
    db = get_db()
    row = db.execute("""
        SELECT w.*, s.name AS supplier_name
        FROM waste_record w
        LEFT JOIN supplier s ON s.id = w.supplier_id
        WHERE w.id = ?
    """, (record_id,)).fetchone()
    if not row:
        return None
    rec = dict(row)
    rec["total_kg"] = float(rec["grade_1_kg"] or 0) + float(rec["grade_2_kg"] or 0) + float(rec["grade_3_kg"] or 0)
    return rec


def list_waste_records_for_date(date_: str, season_id: int) -> list[dict]:
    db = get_db()
    rows = [dict(r) for r in db.execute("""
        SELECT w.*, s.name AS supplier_name
        FROM waste_record w
        LEFT JOIN supplier s ON s.id = w.supplier_id
        WHERE w.date = ? AND w.season_id = ?
        ORDER BY w.id DESC
    """, (date_, season_id))]
    for r in rows:
        r["total_kg"] = float(r["grade_1_kg"] or 0) + float(r["grade_2_kg"] or 0) + float(r["grade_3_kg"] or 0)
    return rows




def delete_waste_record(record_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM waste_record WHERE id = ?", (record_id,))
    db.commit()


def get_waste_total_season(season_id: int) -> float:
    """Общий мусор за сезон, кг."""
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(grade_1_kg + grade_2_kg + grade_3_kg), 0) AS kg
        FROM waste_record WHERE season_id = ?
    """, (season_id,)).fetchone()
    return float(row["kg"] or 0)


def get_waste_total_season_by_grade(season_id: int) -> dict[int, float]:
    """Мусор за сезон с разбивкой по сортам."""
    db = get_db()
    out = {1: 0.0, 2: 0.0, 3: 0.0}
    row = db.execute("""
        SELECT COALESCE(SUM(grade_1_kg), 0) AS g1,
               COALESCE(SUM(grade_2_kg), 0) AS g2,
               COALESCE(SUM(grade_3_kg), 0) AS g3
        FROM waste_record WHERE season_id = ?
    """, (season_id,)).fetchone()
    out[1] = float(row["g1"] or 0)
    out[2] = float(row["g2"] or 0)
    out[3] = float(row["g3"] or 0)
    return out


def get_cleaned_total_season_by_grade(season_id: int) -> dict[int, float]:
    """Очищено (в холодильник) за сезон с разбивкой по сортам."""
    db = get_db()
    out = {1: 0.0, 2: 0.0, 3: 0.0}
    row = db.execute("""
        SELECT COALESCE(SUM(cleaned_grade_1_kg), 0) AS c1,
               COALESCE(SUM(cleaned_grade_2_kg), 0) AS c2,
               COALESCE(SUM(cleaned_grade_3_kg), 0) AS c3
        FROM waste_record WHERE season_id = ?
    """, (season_id,)).fetchone()
    out[1] = float(row["c1"] or 0)
    out[2] = float(row["c2"] or 0)
    out[3] = float(row["c3"] or 0)
    return out


def get_accepted_kg_by_date(date_: str, season_id: int) -> float:
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(ag.weight_kg), 0) AS kg
        FROM acceptance_grade ag
        JOIN acceptance a ON a.id = ag.acceptance_id
        WHERE a.date = ? AND a.season_id = ?
    """, (date_, season_id)).fetchone()
    return float(row["kg"] or 0)


def get_waste_kg_by_date(date_: str, season_id: int) -> float:
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(grade_1_kg + grade_2_kg + grade_3_kg), 0) AS kg
        FROM waste_record WHERE date = ? AND season_id = ?
    """, (date_, season_id)).fetchone()
    return float(row["kg"] or 0)


def get_waste_kg_by_date_by_grade(date_: str, season_id: int) -> dict[int, float]:
    db = get_db()
    out = {1: 0.0, 2: 0.0, 3: 0.0}
    row = db.execute("""
        SELECT COALESCE(SUM(grade_1_kg), 0) AS g1,
               COALESCE(SUM(grade_2_kg), 0) AS g2,
               COALESCE(SUM(grade_3_kg), 0) AS g3
        FROM waste_record WHERE date = ? AND season_id = ?
    """, (date_, season_id)).fetchone()
    out[1] = float(row["g1"] or 0)
    out[2] = float(row["g2"] or 0)
    out[3] = float(row["g3"] or 0)
    return out


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
               (SELECT COUNT(*) FROM sale s JOIN sale_line sl ON sl.sale_id = s.id WHERE s.buyer_id = b.id) AS uses
        FROM buyer b
        ORDER BY b.name
    """)]




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


# --- Продажи (header + lines) ------------------------------------------------

def add_sale(date_, season_id, buyer_id, lines, notes=""):
    db = get_db()
    cur = db.execute(
        "INSERT INTO sale (date, season_id, buyer_id, notes) VALUES (?, ?, ?, ?)",
        (date_, season_id, buyer_id, notes),
    )
    sale_id = cur.lastrowid
    for grade_id, weight_kg, price_per_kg in lines:
        total = round(float(weight_kg) * float(price_per_kg), 2)
        db.execute(
            "INSERT INTO sale_line (sale_id, grade_id, weight_kg, price_per_kg, total_amount) VALUES (?, ?, ?, ?, ?)",
            (sale_id, grade_id, float(weight_kg), float(price_per_kg), total),
        )
    db.commit()
    return sale_id


def get_sale(sale_id):
    db = get_db()
    sale = db.execute(
        "SELECT s.*, b.name AS buyer_name FROM sale s LEFT JOIN buyer b ON b.id = s.buyer_id WHERE s.id = ?",
        (sale_id,),
    ).fetchone()
    if not sale:
        return None
    lines = [dict(r) for r in db.execute(
        "SELECT sl.*, g.display_name AS grade_name FROM sale_line sl JOIN grade g ON g.id = sl.grade_id WHERE sl.sale_id = ?",
        (sale_id,),
    ).fetchall()]
    total_kg = sum(l["weight_kg"] for l in lines)
    total_amount = sum(l["total_amount"] for l in lines)
    return {**dict(sale), "lines": lines, "total_kg": total_kg, "total_amount": total_amount}


def list_sales_for_date(date_, season_id):
    db = get_db()
    sales = [dict(r) for r in db.execute(
        "SELECT s.*, b.name AS buyer_name FROM sale s LEFT JOIN buyer b ON b.id = s.buyer_id WHERE s.date = ? AND s.season_id = ? ORDER BY s.id DESC",
        (date_, season_id),
    ).fetchall()]
    for s in sales:
        s_lines = [dict(r) for r in db.execute(
            "SELECT sl.*, g.display_name AS grade_name FROM sale_line sl JOIN grade g ON g.id = sl.grade_id WHERE sl.sale_id = ?",
            (s["id"],),
        ).fetchall()]
        s["lines"] = s_lines
        s["total_kg"] = sum(l["weight_kg"] for l in s_lines)
        s["total_amount"] = sum(l["total_amount"] for l in s_lines)
    return sales


def update_sale(sale_id, date_, season_id, buyer_id, lines, notes=""):
    db = get_db()
    db.execute(
        "UPDATE sale SET date = ?, season_id = ?, buyer_id = ?, notes = ? WHERE id = ?",
        (date_, season_id, buyer_id, notes, sale_id),
    )
    db.execute("DELETE FROM sale_line WHERE sale_id = ?", (sale_id,))
    for grade_id, weight_kg, price_per_kg in lines:
        total = round(float(weight_kg) * float(price_per_kg), 2)
        db.execute(
            "INSERT INTO sale_line (sale_id, grade_id, weight_kg, price_per_kg, total_amount) VALUES (?, ?, ?, ?, ?)",
            (sale_id, grade_id, float(weight_kg), float(price_per_kg), total),
        )
    db.commit()


def delete_sale(sale_id):
    db = get_db()
    db.execute("DELETE FROM sale WHERE id = ?", (sale_id,))
    db.commit()




def get_sales_total_season(season_id):
    db = get_db()
    row = db.execute(
        "SELECT COALESCE(SUM(sl.total_amount), 0) AS total, "
        "COALESCE(SUM(sl.weight_kg), 0) AS kg "
        "FROM sale s JOIN sale_line sl ON sl.sale_id = s.id "
        "WHERE s.season_id = ?",
        (season_id,),
    ).fetchone()
    by_grade = {g["id"]: 0.0 for g in list_grades()}
    for r in db.execute(
        "SELECT sl.grade_id, COALESCE(SUM(sl.weight_kg), 0) AS kg "
        "FROM sale s JOIN sale_line sl ON sl.sale_id = s.id "
        "WHERE s.season_id = ? GROUP BY sl.grade_id",
        (season_id,),
    ):
        by_grade[r["grade_id"]] = float(r["kg"])
    return {
        "total_amount": float(row["total"] or 0),
        "total_kg": float(row["kg"] or 0),
        "by_grade_kg": by_grade,
    }


def get_sales_kg_by_date(date_, season_id):
    db = get_db()
    row = db.execute(
        "SELECT COALESCE(SUM(sl.weight_kg), 0) AS kg, "
        "COALESCE(SUM(sl.total_amount), 0) AS amount "
        "FROM sale s JOIN sale_line sl ON sl.sale_id = s.id "
        "WHERE s.date = ? AND s.season_id = ?",
        (date_, season_id),
    ).fetchone()
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




def delete_expense(record_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM expense WHERE id = ?", (record_id,))
    db.commit()


def get_expenses_total_season(season_id: int) -> dict:
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expense WHERE season_id = ?
    """, (season_id,)).fetchone()
    drying = db.execute("""
        SELECT COALESCE(SUM(de.cost_electricity + de.cost_water + de.cost_firewood + de.cost_labor), 0) AS total
        FROM drying_expense de
        JOIN drying_run d ON d.id = de.drying_run_id
        WHERE d.season_id = ?
    """, (season_id,)).fetchone()
    total = float(row["total"] or 0) + float(drying["total"] or 0)
    by_category = {}
    for r in db.execute("""
        SELECT category, COALESCE(SUM(amount), 0) AS amount
        FROM expense WHERE season_id = ? GROUP BY category
    """, (season_id,)):
        by_category[r["category"]] = float(r["amount"])
    by_category["\u0421\u0443\u0448\u043a\u0430"] = float(drying["total"] or 0)
    return {"total": total, "by_category": by_category}


def get_expenses_by_date(date_: str, season_id: int) -> float:
    db = get_db()
    row = db.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM expense WHERE date = ? AND season_id = ?
    """, (date_, season_id)).fetchone()
    drying = db.execute("""
        SELECT COALESCE(SUM(de.cost_electricity + de.cost_water + de.cost_firewood + de.cost_labor), 0) AS total
        FROM drying_expense de
        JOIN drying_run d ON d.id = de.drying_run_id
        WHERE d.date = ? AND d.season_id = ?
    """, (date_, season_id)).fetchone()
    return float(row["total"] or 0) + float(drying["total"] or 0)


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


def _period_expr(group_by: str, date_col: str = "date") -> tuple[str, str]:
    """Вернуть (GROUP_BY_expr, SELECT_label_expr) для группировки по дню/неделе/месяцу."""
    if group_by == "week":
        expr = f"strftime('%Y-W%W', {date_col})"
    elif group_by == "month":
        expr = f"strftime('%Y-%m', {date_col})"
    else:
        expr = date_col
    return expr, expr


def pnl_by_period(season_id: int, date_from: str | None = None, date_to: str | None = None) -> dict:
    """P&L за период: выручка минус все расходы."""
    db = get_db()
    where_s, params_s = _date_filter("s", date_from, date_to)
    where_a, params_a = _date_filter("a", date_from, date_to)
    where_, params_all = _date_filter("", date_from, date_to)
    acc = db.execute(
        f"SELECT COALESCE(SUM(ag.weight_kg), 0) AS kg, COALESCE(SUM(ag.total_amount), 0) AS amount "
        f"FROM acceptance_grade ag JOIN acceptance a ON a.id = ag.acceptance_id"
        f" WHERE a.season_id = ?{where_a}",
        (season_id, *params_a)).fetchone()
    sales = db.execute(
        f"SELECT COALESCE(SUM(sl.weight_kg), 0) AS kg, COALESCE(SUM(sl.total_amount), 0) AS amount "
        f"FROM sale s JOIN sale_line sl ON sl.sale_id = s.id WHERE s.season_id = ?{where_s}",
        (season_id, *params_s)).fetchone()
    drying = db.execute(
        f"SELECT "
        f"COALESCE(SUM(d.raw_grade_1_kg + d.raw_grade_2_kg + d.raw_grade_3_kg), 0) AS raw, "
        f"COALESCE(SUM(d.dry_grade_1_kg + d.dry_grade_2_kg + d.dry_grade_3_kg), 0) AS dry, "
        f"COALESCE(SUM(COALESCE(de.cost_electricity, 0) + COALESCE(de.cost_water, 0) + "
        f"COALESCE(de.cost_firewood, 0) + COALESCE(de.cost_labor, 0)), 0) AS cost "
        f"FROM drying_run d LEFT JOIN drying_expense de ON de.drying_run_id = d.id "
        f"WHERE d.season_id = ?{where_}",
        (season_id, *params_all)).fetchone()
    waste = db.execute(
        f"SELECT COALESCE(SUM(grade_1_kg + grade_2_kg + grade_3_kg), 0) AS kg FROM waste_record WHERE season_id = ?{where_}",
        (season_id, *params_all)).fetchone()
    expenses = db.execute(
        f"SELECT COALESCE(SUM(amount), 0) AS total FROM expense WHERE season_id = ?{where_}",
        (season_id, *params_all)).fetchone()
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
               COALESCE(SUM(ag.weight_kg), 0) AS kg,
               COALESCE(SUM(ag.total_amount), 0) AS amount,
               COUNT(DISTINCT a.id) AS deliveries
        FROM acceptance a
        LEFT JOIN acceptance_grade ag ON ag.acceptance_id = a.id
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
               COALESCE(SUM(sl.weight_kg), 0) AS kg,
               COALESCE(SUM(sl.total_amount), 0) AS amount,
               COUNT(DISTINCT s.id) AS deals
        FROM sale s
        JOIN sale_line sl ON sl.sale_id = s.id
        LEFT JOIN buyer b ON b.id = s.buyer_id
        WHERE s.season_id = ?{where}
        GROUP BY COALESCE(b.id, 0)
        ORDER BY amount DESC
    """
    return [dict(r) for r in db.execute(sql, (season_id, *params)).fetchall()]


def daily_summary(season_id: int, date_from: str | None = None, date_to: str | None = None) -> list[dict]:
    """Сводка по дням. По одной строке на дату с движением, новые сверху."""
    db = get_db()
    where_a, params_a = _date_filter("a", date_from, date_to)
    where_s, params_s = _date_filter("s", date_from, date_to)
    where_, params_all = _date_filter("", date_from, date_to)
    acc = {r["date"]: r for r in db.execute(
        f"SELECT a.date AS date, COALESCE(SUM(ag.weight_kg), 0) AS kg, COALESCE(SUM(ag.total_amount), 0) AS amount "
        f"FROM acceptance a JOIN acceptance_grade ag ON ag.acceptance_id = a.id"
        f" WHERE a.season_id = ?{where_a} GROUP BY a.date",
        (season_id, *params_a))}
    dry = {r["date"]: r for r in db.execute(
        f"SELECT d.date, "
        f"COALESCE(SUM(d.raw_grade_1_kg + d.raw_grade_2_kg + d.raw_grade_3_kg), 0) AS raw, "
        f"COALESCE(SUM(d.dry_grade_1_kg + d.dry_grade_2_kg + d.dry_grade_3_kg), 0) AS dry, "
        f"COALESCE(SUM(COALESCE(de.cost_electricity, 0) + COALESCE(de.cost_water, 0) + "
        f"COALESCE(de.cost_firewood, 0) + COALESCE(de.cost_labor, 0)), 0) AS cost "
        f"FROM drying_run d LEFT JOIN drying_expense de ON de.drying_run_id = d.id "
        f"WHERE d.season_id = ?{where_} GROUP BY d.date", (season_id, *params_all))}
    waste = {r["date"]: r["kg"] for r in db.execute(
        f"SELECT date, COALESCE(SUM(grade_1_kg + grade_2_kg + grade_3_kg), 0) AS kg FROM waste_record WHERE season_id = ?{where_} "
        f"GROUP BY date", (season_id, *params_all))}
    sales = {r["date"]: r for r in db.execute(
        f"SELECT s.date, COALESCE(SUM(sl.weight_kg), 0) AS kg, COALESCE(SUM(sl.total_amount), 0) AS amount "
        f"FROM sale s JOIN sale_line sl ON sl.sale_id = s.id WHERE s.season_id = ?{where_s} GROUP BY s.date",
        (season_id, *params_s))}
    exp = {r["date"]: r["total"] for r in db.execute(
        f"SELECT date, COALESCE(SUM(amount), 0) AS total FROM expense WHERE season_id = ?{where_} "
        f"GROUP BY date", (season_id, *params_all))}
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



def get_cost_per_kg_dry(season_id: int, date_from: str | None = None,
                        date_to: str | None = None) -> dict:
    """Себестоимость 1 кг сухого: (приёмка₽ + сушка₽ + общие₽) / (продано_кг + сухой_остаток_кг)."""
    db = get_db()
    pnl = pnl_by_period(season_id, date_from, date_to)
    accepted_amount = pnl["accepted_amount"]
    drying_cost = pnl["drying_cost"]
    expenses = pnl["expenses_total"]
    total_invested = accepted_amount + drying_cost + expenses

    # Сухой остаток на дату окончания периода (или сейчас, если период не задан)
    end_date = date_to or date.today().isoformat()
    dry_kg_season = db.execute("""
        SELECT COALESCE(SUM(dry_grade_1_kg + dry_grade_2_kg + dry_grade_3_kg), 0)
        FROM drying_run WHERE season_id = ? AND date <= ?
    """, (season_id, end_date)).fetchone()[0]
    sold_kg = db.execute("""
        SELECT COALESCE(SUM(sl.weight_kg), 0) FROM sale s
        JOIN sale_line sl ON sl.sale_id = s.id
        WHERE s.season_id = ? AND s.date <= ?
    """, (season_id, end_date)).fetchone()[0]
    dry_stock = float(dry_kg_season or 0) - float(sold_kg or 0)
    if dry_stock < 0:
        dry_stock = 0.0
    sold_period = pnl["sales_kg"]
    total_dry = sold_period + dry_stock
    cost_per_kg = total_invested / total_dry if total_dry > 0 else 0.0

    # Себестоимость по сортам
    by_grade = get_cost_per_kg_dry_by_grade(season_id, date_from, date_to)

    return {
        "total_invested": total_invested,
        "accepted_amount": accepted_amount,
        "drying_cost": drying_cost,
        "expenses": expenses,
        "sold_kg": sold_period,
        "dry_stock_kg": dry_stock,
        "total_dry_kg": total_dry,
        "cost_per_kg": cost_per_kg,
        "by_grade": by_grade,
    }


def get_cost_per_kg_dry_by_grade(season_id: int, date_from: str | None = None,
                                  date_to: str | None = None) -> list[dict]:
    """Себестоимость 1 кг сухого по каждому сорту. Расходы на сушку/прочие распределяются пропорционально стоимости приёмки."""
    db = get_db()
    where_a, params_a = _date_filter("a", date_from, date_to)
    where_d, params_d = _date_filter("d", date_from, date_to)
    where_s, params_s = _date_filter("s", date_from, date_to)
    where_e, params_e = _date_filter("", date_from, date_to)

    # Принято по сортам
    accepted = {}
    for r in db.execute(f"""
        SELECT ag.grade_id,
            COALESCE(SUM(ag.weight_kg), 0) AS kg,
            COALESCE(SUM(ag.total_amount), 0) AS amount
        FROM acceptance a JOIN acceptance_grade ag ON ag.acceptance_id = a.id
        WHERE a.season_id = ?{where_a}
        GROUP BY ag.grade_id
    """, (season_id, *params_a)):
        accepted[r["grade_id"]] = {"kg": float(r["kg"] or 0), "amount": float(r["amount"] or 0)}

    total_accepted_amount = sum(v["amount"] for v in accepted.values())
    total_accepted_kg = sum(v["kg"] for v in accepted.values())

    # Высушено по сортам
    dried = {}
    for r in db.execute(f"""
        SELECT
            COALESCE(SUM(raw_grade_1_kg), 0) AS r1, COALESCE(SUM(raw_grade_2_kg), 0) AS r2,
            COALESCE(SUM(raw_grade_3_kg), 0) AS r3,
            COALESCE(SUM(dry_grade_1_kg), 0) AS d1, COALESCE(SUM(dry_grade_2_kg), 0) AS d2,
            COALESCE(SUM(dry_grade_3_kg), 0) AS d3
        FROM drying_run d WHERE d.season_id = ?{where_d}
    """, (season_id, *params_d)):
        dried = {1: float(r["d1"] or 0), 2: float(r["d2"] or 0), 3: float(r["d3"] or 0)}

    # Продано по сортам
    sold = {}
    for r in db.execute(f"""
        SELECT sl.grade_id, COALESCE(SUM(sl.weight_kg), 0) AS kg
        FROM sale s JOIN sale_line sl ON sl.sale_id = s.id
        WHERE s.season_id = ?{where_s}
        GROUP BY sl.grade_id
    """, (season_id, *params_s)):
        sold[r["grade_id"]] = float(r["kg"] or 0)

    # Итого сушка + прочие расходы
    drying_cost = db.execute(f"""
        SELECT COALESCE(SUM(COALESCE(de.cost_electricity, 0) + COALESCE(de.cost_water, 0) +
            COALESCE(de.cost_firewood, 0) + COALESCE(de.cost_labor, 0)), 0) AS cost
        FROM drying_run d LEFT JOIN drying_expense de ON de.drying_run_id = d.id
        WHERE d.season_id = ?{where_d}
    """, (season_id, *params_d)).fetchone()["cost"]
    other_cost = db.execute(f"""
        SELECT COALESCE(SUM(amount), 0) FROM expense WHERE season_id = ?{where_e}
    """, (season_id, *params_e)).fetchone()[0]
    shared_cost = float(drying_cost or 0) + float(other_cost or 0)

    grades = list_grades()
    rows = []
    for g in grades:
        gid = g["id"]
        acc = accepted.get(gid, {"kg": 0.0, "amount": 0.0})
        dry_kg = dried.get(gid, 0.0)
        sold_kg = sold.get(gid, 0.0)
        dry_stock = max(dry_kg - sold_kg, 0.0)

        # Пропорциональная доля по стоимости приёмки
        share = acc["amount"] / total_accepted_amount if total_accepted_amount > 0 else 0.0
        cost_share = shared_cost * share
        total_invested = acc["amount"] + cost_share
        total_output = sold_kg + dry_stock
        cost_per_kg = total_invested / total_output if total_output > 0 else 0.0

        rows.append({
            "grade_name": g["display_name"],
            "accepted_kg": acc["kg"],
            "accepted_amount": acc["amount"],
            "dry_kg": dry_kg,
            "sold_kg": sold_kg,
            "dry_stock_kg": dry_stock,
            "drying_share": shared_cost * share if share > 0 else 0.0,
            "total_invested": total_invested,
            "cost_per_kg": cost_per_kg,
        })

    # Итого строка
    total_row = {
        "grade_name": "Итого",
        "accepted_kg": total_accepted_kg,
        "accepted_amount": total_accepted_amount,
        "dry_kg": sum(dried.values()),
        "sold_kg": sum(sold.values()),
        "dry_stock_kg": max(sum(dried.values()) - sum(sold.values()), 0),
        "drying_share": shared_cost,
        "total_invested": total_accepted_amount + shared_cost,
        "cost_per_kg": (total_accepted_amount + shared_cost) / (sum(sold.values()) + max(sum(dried.values()) - sum(sold.values()), 0)) if (sum(sold.values()) + max(sum(dried.values()) - sum(sold.values()), 0)) > 0 else 0,
    }
    rows.append(total_row)
    return rows


def get_margin(season_id: int, date_from: str | None = None,
               date_to: str | None = None) -> dict:
    """Рентабельность: (выручка - все_расходы) / выручка × 100."""
    db = get_db()
    where_s, params_s = _date_filter("s", date_from, date_to)
    sales = db.execute(
        f"SELECT COALESCE(SUM(sl.total_amount), 0) AS amount "
        f"FROM sale s JOIN sale_line sl ON sl.sale_id = s.id WHERE s.season_id = ?{where_s}",
        (season_id, *params_s)).fetchone()
    revenue = float(sales["amount"] or 0)
    pnl = pnl_by_period(season_id, date_from, date_to)
    profit = pnl["profit"]
    margin_pct = (profit / revenue * 100) if revenue > 0 else 0.0
    return {
        "revenue": revenue,
        "total_cost": pnl["total_cost"],
        "profit": profit,
        "margin_pct": margin_pct,
    }



def get_grade_movement(season_id: int, date_from: str | None = None,
                       date_to: str | None = None) -> list[dict]:
    """Движение по сортам: принято, мусор, в сушку, выход, продано, остатки."""
    db = get_db()
    where_a, params_a = _date_filter("a", date_from, date_to)
    where_d, params_d = _date_filter("d", date_from, date_to)
    where_s, params_s = _date_filter("s", date_from, date_to)
    where_w, params_w = _date_filter("w", date_from, date_to)

    # Принято по сортам
    accepted = {1: 0.0, 2: 0.0, 3: 0.0}
    for r in db.execute(f"""
        SELECT ag.grade_id, COALESCE(SUM(ag.weight_kg), 0) AS kg
        FROM acceptance_grade ag JOIN acceptance a ON a.id = ag.acceptance_id
        WHERE a.season_id = ?{where_a}
        GROUP BY ag.grade_id
    """, (season_id, *params_a)):
        accepted[r["grade_id"]] = float(r["kg"] or 0)

    # В сушку (raw) и выход (dry) по сортам
    drying_raw = {1: 0.0, 2: 0.0, 3: 0.0}
    drying_dry = {1: 0.0, 2: 0.0, 3: 0.0}
    row = db.execute(f"""
        SELECT COALESCE(SUM(raw_grade_1_kg), 0) AS r1, COALESCE(SUM(raw_grade_2_kg), 0) AS r2,
               COALESCE(SUM(raw_grade_3_kg), 0) AS r3,
               COALESCE(SUM(dry_grade_1_kg), 0) AS d1, COALESCE(SUM(dry_grade_2_kg), 0) AS d2,
               COALESCE(SUM(dry_grade_3_kg), 0) AS d3
        FROM drying_run d WHERE d.season_id = ?{where_d}
    """, (season_id, *params_d)).fetchone()
    drying_raw = {1: float(row["r1"] or 0), 2: float(row["r2"] or 0), 3: float(row["r3"] or 0)}
    drying_dry = {1: float(row["d1"] or 0), 2: float(row["d2"] or 0), 3: float(row["d3"] or 0)}

    # Продано
    sold = {1: 0.0, 2: 0.0, 3: 0.0}
    for r in db.execute(f"""
        SELECT sl.grade_id, COALESCE(SUM(sl.weight_kg), 0) AS kg FROM sale s
        JOIN sale_line sl ON sl.sale_id = s.id WHERE s.season_id = ?{where_s} GROUP BY sl.grade_id
    """, (season_id, *params_s)):
        sold[r["grade_id"]] = float(r["kg"] or 0)

    # Мусор по сортам
    waste = {1: 0.0, 2: 0.0, 3: 0.0}
    row = db.execute(f"""
        SELECT COALESCE(SUM(grade_1_kg), 0) AS g1, COALESCE(SUM(grade_2_kg), 0) AS g2,
               COALESCE(SUM(grade_3_kg), 0) AS g3
        FROM waste_record w WHERE w.season_id = ?{where_w}
    """, (season_id, *params_w)).fetchone()
    waste = {1: float(row["g1"] or 0), 2: float(row["g2"] or 0), 3: float(row["g3"] or 0)}

    rows = []
    for g in list_grades():
        gid = g["id"]
        rows.append({
            "grade_id": gid,
            "grade_name": g["display_name"],
            "accepted_kg": accepted[gid],
            "waste_kg": waste[gid],
            "drying_raw_kg": drying_raw[gid],
            "drying_dry_kg": drying_dry[gid],
            "sold_kg": sold[gid],
            "raw_stock_kg": accepted[gid] - waste[gid] - drying_raw[gid],
            "dry_stock_kg": drying_dry[gid] - sold[gid],
        })
    return rows


def get_supplier_efficiency(season_id: int, date_from: str | None = None,
                            date_to: str | None = None) -> list[dict]:
    """Эффективность поставщиков: принято/выплачено + % мусора по поставщику (если привязан)."""
    db = get_db()
    where_a, params_a = _date_filter("a", date_from, date_to)
    where_w, params_w = _date_filter("w", date_from, date_to)

    rows = []
    for r in db.execute(f"""
        SELECT s.id AS supplier_id, s.name AS supplier_name,
               COALESCE(SUM(ag.weight_kg), 0) AS kg,
               COALESCE(SUM(ag.total_amount), 0) AS amount,
               COUNT(DISTINCT a.id) AS deliveries
        FROM supplier s
        LEFT JOIN acceptance a ON a.supplier_id = s.id
        LEFT JOIN acceptance_grade ag ON ag.acceptance_id = a.id
        WHERE (a.season_id = ? OR a.id IS NULL){where_a}
        GROUP BY s.id
        HAVING COALESCE(SUM(ag.weight_kg), 0) > 0
        ORDER BY amount DESC
    """, (season_id, *params_a)).fetchall():
        sid = r["supplier_id"]
        waste_kg = db.execute(f"""
            SELECT COALESCE(SUM(grade_1_kg + grade_2_kg + grade_3_kg), 0) AS kg
            FROM waste_record w WHERE w.supplier_id = ?{where_w}
        """, (sid, *params_w)).fetchone()["kg"]
        waste_kg = float(waste_kg or 0)
        accepted_kg = float(r["kg"] or 0)
        waste_pct = (waste_kg / accepted_kg * 100) if accepted_kg > 0 else 0.0
        rows.append({
            "supplier_id": sid,
            "supplier_name": r["supplier_name"],
            "accepted_kg": accepted_kg,
            "paid_amount": float(r["amount"] or 0),
            "waste_kg": waste_kg,
            "waste_pct": waste_pct,
            "deliveries": r["deliveries"] or 0,
        })
    # Добавим "без поставщика"
    no_sup = db.execute(f"""
        SELECT COALESCE(SUM(ag.weight_kg), 0) AS kg,
               COALESCE(SUM(ag.total_amount), 0) AS amount,
               COUNT(DISTINCT a.id) AS deliveries
        FROM acceptance a
        LEFT JOIN acceptance_grade ag ON ag.acceptance_id = a.id
        WHERE a.season_id = ? AND a.supplier_id IS NULL{where_a}
    """, (season_id, *params_a)).fetchone()
    no_waste = db.execute(f"""
        SELECT COALESCE(SUM(grade_1_kg + grade_2_kg + grade_3_kg), 0) AS kg
        FROM waste_record w WHERE w.season_id = ? AND w.supplier_id IS NULL{where_w}
    """, (season_id, *params_w)).fetchone()["kg"]
    no_kg = float(no_sup["kg"] or 0)
    if no_kg > 0 or float(no_waste or 0) > 0:
        no_waste = float(no_waste or 0)
        rows.append({
            "supplier_id": None,
            "supplier_name": None,
            "accepted_kg": no_kg,
            "paid_amount": float(no_sup["amount"] or 0),
            "waste_kg": no_waste,
            "waste_pct": (no_waste / no_kg * 100) if no_kg > 0 else 0.0,
            "deliveries": no_sup["deliveries"] or 0,
        })
    return rows


def get_yield_trend(season_id: int, date_from: str | None = None,
                    date_to: str | None = None) -> list[dict]:
    """% выхода сушки по дням (с ненулевой сушкой)."""
    db = get_db()
    where, params = _date_filter("d", date_from, date_to)
    rows = []
    for r in db.execute(f"""
        SELECT date,
               COALESCE(SUM(raw_grade_1_kg + raw_grade_2_kg + raw_grade_3_kg), 0) AS raw,
               COALESCE(SUM(dry_grade_1_kg + dry_grade_2_kg + dry_grade_3_kg), 0) AS dry
        FROM drying_run d WHERE d.season_id = ?{where}
        GROUP BY date
        HAVING raw > 0
        ORDER BY date DESC
    """, (season_id, *params)):
        raw = float(r["raw"] or 0)
        dry = float(r["dry"] or 0)
        yield_pct = (dry / raw * 100) if raw > 0 else 0.0
        rows.append({
            "date": r["date"],
            "raw_kg": raw,
            "dry_kg": dry,
            "yield_pct": yield_pct,
        })
    return rows


def get_top_grades(season_id: int, date_from: str | None = None,
                   date_to: str | None = None) -> list[dict]:
    """Топ сортов по продажам: кг и ₽."""
    db = get_db()
    where, params = _date_filter("s", date_from, date_to)
    rows = []
    for r in db.execute(f"""
        SELECT g.id AS grade_id, g.display_name AS grade_name,
               COALESCE(SUM(sl.weight_kg), 0) AS kg,
               COALESCE(SUM(sl.total_amount), 0) AS amount,
               COUNT(DISTINCT s.id) AS deals
        FROM grade g
        LEFT JOIN sale_line sl ON sl.grade_id = g.id
        LEFT JOIN sale s ON s.id = sl.sale_id AND s.season_id = ?{where}
        GROUP BY g.id
        ORDER BY amount DESC
    """, (season_id, *params)):
        rows.append({
            "grade_id": r["grade_id"],
            "grade_name": r["grade_name"],
            "sold_kg": float(r["kg"] or 0),
            "revenue": float(r["amount"] or 0),
            "deals": r["deals"] or 0,
        })
    return rows


def get_cashflow(season_id: int, date_from: str | None = None,
                 date_to: str | None = None) -> list[dict]:
    """Cash flow по дням: приход (sales), отток (drying_cost + expense), нетто."""
    db = get_db()
    where_s, params_s = _date_filter("s", date_from, date_to)
    where_, params_all = _date_filter("", date_from, date_to)

    sales = {r["date"]: float(r["amount"] or 0) for r in db.execute(
        f"SELECT s.date, COALESCE(SUM(sl.total_amount), 0) AS amount FROM sale s JOIN sale_line sl ON sl.sale_id = s.id WHERE s.season_id = ?{where_s} GROUP BY s.date",
        (season_id, *params_s))}
    exp = {r["date"]: float(r["total"] or 0) for r in db.execute(
        f"SELECT date, COALESCE(SUM(amount), 0) AS total FROM expense WHERE season_id = ?{where_} GROUP BY date",
        (season_id, *params_all))}
    dry_cost = {}
    for r in db.execute(
        f"SELECT d.date, COALESCE(SUM(COALESCE(de.cost_electricity, 0) + COALESCE(de.cost_water, 0) + "
        f"COALESCE(de.cost_firewood, 0) + COALESCE(de.cost_labor, 0)), 0) AS cost "
        f"FROM drying_run d LEFT JOIN drying_expense de ON de.drying_run_id = d.id "
        f"WHERE d.season_id = ?{where_} GROUP BY d.date",
        (season_id, *params_all)):
        dry_cost[r["date"]] = float(r["cost"] or 0)

    all_dates = sorted(set(sales) | set(exp) | set(dry_cost), reverse=True)
    rows = []
    inflow_total = 0.0
    outflow_total = 0.0
    for d in all_dates:
        inflow = sales.get(d, 0.0)
        outflow = exp.get(d, 0.0) + dry_cost.get(d, 0.0)
        net = inflow - outflow
        inflow_total += inflow
        outflow_total += outflow
        rows.append({
            "date": d,
            "inflow": inflow,
            "outflow": outflow,
            "net": net,
        })
    return {
        "rows": rows,
        "inflow_total": inflow_total,
        "outflow_total": outflow_total,
        "net_total": inflow_total - outflow_total,
    }



# --- Новые отчёты (детализация) -----------------------------------------------

def get_expenses_detail(season_id: int, date_from: str | None = None,
                        date_to: str | None = None, group_by: str = "day") -> dict:
    """Детализация расходов: общие + сушка, сгруппированные по периоду."""
    db = get_db()
    where, params = _date_filter("", date_from, date_to)
    pexpr, _ = _period_expr(group_by)

    general = {}
    for r in db.execute(f"""
        SELECT {pexpr} AS period, category, COALESCE(SUM(amount), 0) AS amount
        FROM expense WHERE season_id = ?{where}
        GROUP BY period, category ORDER BY period
    """, (season_id, *params)):
        per = r["period"]
        if per not in general:
            general[per] = {"rows": [], "total": 0.0}
        general[per]["rows"].append({"source": "Общие", "category": r["category"], "amount": float(r["amount"])})
        general[per]["total"] += float(r["amount"])

    drying = {}
    pexpr_d, _ = _period_expr(group_by, "d.date")
    for r in db.execute(f"""
        SELECT {pexpr_d} AS period,
            COALESCE(SUM(de.cost_electricity), 0) AS electricity,
            COALESCE(SUM(de.cost_water), 0) AS water,
            COALESCE(SUM(de.cost_firewood), 0) AS firewood,
            COALESCE(SUM(de.cost_labor), 0) AS labor
        FROM drying_run d
        JOIN drying_expense de ON de.drying_run_id = d.id
        WHERE d.season_id = ?{where}
        GROUP BY period ORDER BY period
    """, (season_id, *params)):
        per = r["period"]
        total = float(r["electricity"] + r["water"] + r["firewood"] + r["labor"])
        if total <= 0:
            continue
        if per not in drying:
            drying[per] = {"rows": [], "total": 0.0}
        for cat, val in [("Свет", float(r["electricity"])), ("Вода", float(r["water"])),
                         ("Дрова", float(r["firewood"])), ("Зарплата", float(r["labor"]))]:
            if val > 0:
                drying[per]["rows"].append({"source": "Сушка", "category": cat, "amount": val})
        drying[per]["total"] += total

    # Acceptance (приёмка грибов)
    acceptance = {}
    pexpr_a, _ = _period_expr(group_by, "a.date")
    where_a, params_a = _date_filter("a", date_from, date_to)
    for r in db.execute(f"""
        SELECT {pexpr_a} AS period,
            COALESCE(SUM(ag.total_amount), 0) AS amount
        FROM acceptance a
        JOIN acceptance_grade ag ON ag.acceptance_id = a.id
        WHERE a.season_id = ?{where_a}
        GROUP BY period ORDER BY period
    """, (season_id, *params_a)):
        per = r["period"]
        amt = float(r["amount"] or 0)
        if amt > 0:
            if per not in acceptance:
                acceptance[per] = {"rows": [], "total": 0.0}
            acceptance[per]["rows"].append({"source": "Приёмка", "category": "Грибы", "amount": amt})
            acceptance[per]["total"] += amt

    all_periods = sorted(set(list(general.keys()) + list(drying.keys()) + list(acceptance.keys())))
    rows = []
    total = 0.0
    by_source = {"Приёмка": 0.0, "Общие": 0.0, "Сушка": 0.0}
    for per in all_periods:
        a = acceptance.get(per, {"rows": [], "total": 0.0})
        g = general.get(per, {"rows": [], "total": 0.0})
        d = drying.get(per, {"rows": [], "total": 0.0})
        for row in a["rows"] + g["rows"] + d["rows"]:
            rows.append({"period": per, **row})
            by_source[row["source"]] = by_source.get(row["source"], 0.0) + row["amount"]
        total += a["total"] + g["total"] + d["total"]
    return {"rows": rows, "total": total, "by_source": by_source}


def get_sales_detail(season_id: int, date_from: str | None = None,
                     date_to: str | None = None, group_by: str = "day") -> dict:
    """Детализация продаж: покупатель, кг, сумма, ср.цена по периодам."""
    db = get_db()
    where_s, params_s = _date_filter("s", date_from, date_to)
    pexpr, _ = _period_expr(group_by, "s.date")
    rows = []
    total_kg = 0.0
    total_amount = 0.0
    for r in db.execute(f"""
        SELECT {pexpr} AS period, b.name AS buyer_name,
            COALESCE(SUM(sl.weight_kg), 0) AS kg,
            COALESCE(SUM(sl.total_amount), 0) AS amount
        FROM sale s
        JOIN sale_line sl ON sl.sale_id = s.id
        LEFT JOIN buyer b ON b.id = s.buyer_id
        WHERE s.season_id = ?{where_s}
        GROUP BY period, b.name
        ORDER BY period
    """, (season_id, *params_s)):
        kg = float(r["kg"] or 0)
        amt = float(r["amount"] or 0)
        avg = amt / kg if kg > 0 else 0.0
        rows.append({"period": r["period"], "buyer": r["buyer_name"] or "—",
                      "kg": kg, "amount": amt, "avg_price": avg})
        total_kg += kg
        total_amount += amt
    return {"rows": rows, "total_kg": total_kg, "total_amount": total_amount}


def get_production_summary(season_id: int, date_from: str | None = None,
                           date_to: str | None = None, group_by: str = "day") -> list[dict]:
    """Производство: принято/мусор/сухой/% выхода по периодам."""
    db = get_db()
    where_a, params_a = _date_filter("a", date_from, date_to)
    where_d, params_d = _date_filter("d", date_from, date_to)
    where_w, params_w = _date_filter("w", date_from, date_to)
    pexpr_a, _ = _period_expr(group_by, "a.date")
    pexpr_d, _ = _period_expr(group_by, "d.date")
    pexpr_w, _ = _period_expr(group_by, "w.date")

    accepted = {}
    for r in db.execute(f"""
        SELECT {pexpr_a} AS period, COALESCE(SUM(ag.weight_kg), 0) AS kg
        FROM acceptance a JOIN acceptance_grade ag ON ag.acceptance_id = a.id
        WHERE a.season_id = ?{where_a}
        GROUP BY period
    """, (season_id, *params_a)):
        accepted[r["period"]] = float(r["kg"] or 0)

    waste = {}
    for r in db.execute(f"""
        SELECT {pexpr_w} AS period, COALESCE(SUM(grade_1_kg + grade_2_kg + grade_3_kg), 0) AS kg
        FROM waste_record w WHERE w.season_id = ?{where_w}
        GROUP BY period
    """, (season_id, *params_w)):
        waste[r["period"]] = float(r["kg"] or 0)

    dried = {}
    for r in db.execute(f"""
        SELECT {pexpr_d} AS period,
            COALESCE(SUM(dry_grade_1_kg + dry_grade_2_kg + dry_grade_3_kg), 0) AS kg
        FROM drying_run d WHERE d.season_id = ?{where_d}
        GROUP BY period
    """, (season_id, *params_d)):
        dried[r["period"]] = float(r["kg"] or 0)

    all_periods = sorted(set(list(accepted.keys()) + list(waste.keys()) + list(dried.keys())))
    rows = []
    for per in all_periods:
        a = accepted.get(per, 0.0)
        w = waste.get(per, 0.0)
        d = dried.get(per, 0.0)
        clean = a - w
        yield_pct = (d / clean * 100) if clean > 0 else 0.0
        waste_pct = (w / a * 100) if a > 0 else 0.0
        rows.append({"period": per, "accepted_kg": a, "waste_kg": w,
                      "cleaned_kg": clean, "dried_kg": d, "waste_pct": waste_pct, "yield_pct": yield_pct})
    return rows


def get_profitability_by_grade(season_id: int, date_from: str | None = None,
                               date_to: str | None = None, group_by: str = "day") -> list[dict]:
    """Рентабельность по сортам: выручка, затраты, прибыль, маржа."""
    db = get_db()
    where_s, params_s = _date_filter("s", date_from, date_to)
    where_a, params_a = _date_filter("a", date_from, date_to)
    where_d, params_d = _date_filter("d", date_from, date_to)
    where_e, params_e = _date_filter("", date_from, date_to)
    pexpr_s, _ = _period_expr(group_by, "s.date")
    pexpr_a, _ = _period_expr(group_by, "a.date")
    pexpr_d, _ = _period_expr(group_by, "d.date")
    pexpr_e, _ = _period_expr(group_by, "date")

    # Выручка по периоду и сорту
    revenue = {}
    for r in db.execute(f"""
        SELECT {pexpr_s} AS period, sl.grade_id,
            COALESCE(SUM(sl.weight_kg), 0) AS kg,
            COALESCE(SUM(sl.total_amount), 0) AS amount
        FROM sale s JOIN sale_line sl ON sl.sale_id = s.id
        WHERE s.season_id = ?{where_s}
        GROUP BY period, sl.grade_id
    """, (season_id, *params_s)):
        key = (r["period"], r["grade_id"])
        revenue[key] = {"kg": float(r["kg"] or 0), "amount": float(r["amount"] or 0)}

    # Затраты по периоду и сорту (приёмка)
    cost_raw = {}
    for r in db.execute(f"""
        SELECT {pexpr_a} AS period, ag.grade_id,
            COALESCE(SUM(ag.weight_kg), 0) AS kg,
            COALESCE(SUM(ag.total_amount), 0) AS amount
        FROM acceptance a JOIN acceptance_grade ag ON ag.acceptance_id = a.id
        WHERE a.season_id = ?{where_a}
        GROUP BY period, ag.grade_id
    """, (season_id, *params_a)):
        key = (r["period"], r["grade_id"])
        cost_raw[key] = {"kg": float(r["kg"] or 0), "amount": float(r["amount"] or 0)}

    # Итого расходы на сушку по периоду
    drying_cost = {}
    for r in db.execute(f"""
        SELECT {pexpr_d} AS period,
            COALESCE(SUM(COALESCE(de.cost_electricity, 0) + COALESCE(de.cost_water, 0) +
            COALESCE(de.cost_firewood, 0) + COALESCE(de.cost_labor, 0)), 0) AS cost
        FROM drying_run d
        LEFT JOIN drying_expense de ON de.drying_run_id = d.id
        WHERE d.season_id = ?{where_d}
        GROUP BY period
    """, (season_id, *params_d)):
        drying_cost[r["period"]] = float(r["cost"] or 0)

    # Итого прочие расходы по периоду
    other_cost = {}
    for r in db.execute(f"""
        SELECT {pexpr_e} AS period, COALESCE(SUM(amount), 0) AS cost
        FROM expense WHERE season_id = ?{where_e}
        GROUP BY period
    """, (season_id, *params_e)):
        other_cost[r["period"]] = float(r["cost"] or 0)

    # Итого стоимость приёмки за период (для пропорционального распределения)
    total_value_by_period = {}
    for key, val in cost_raw.items():
        per = key[0]
        total_value_by_period[per] = total_value_by_period.get(per, 0.0) + val["amount"]

    grades = list_grades()
    all_keys = sorted(set(list(revenue.keys()) + list(cost_raw.keys())))
    rows = []
    for key in all_keys:
        per, gid = key
        rev = revenue.get(key, {"kg": 0.0, "amount": 0.0})
        c = cost_raw.get(key, {"kg": 0.0, "amount": 0.0})
        # Пропорциональная доля сушки и прочих расходов
        period_total_value = total_value_by_period.get(per, 0.0)
        share = c["amount"] / period_total_value if period_total_value > 0 else 0.0
        d_cost = drying_cost.get(per, 0.0) * share
        o_cost = other_cost.get(per, 0.0) * share
        total_cost = c["amount"] + d_cost + o_cost
        profit = rev["amount"] - total_cost
        margin = (profit / rev["amount"] * 100) if rev["amount"] > 0 else 0.0
        gname = next((g["display_name"] for g in grades if g["id"] == gid), str(gid))
        rows.append({
            "period": per, "grade_name": gname,
            "sold_kg": rev["kg"], "revenue": rev["amount"],
            "accepted_kg": c["kg"], "cost_raw": c["amount"],
            "cost_drying": d_cost, "cost_other": o_cost,
            "total_cost": total_cost, "profit": profit, "margin_pct": margin,
        })
    return rows


def get_acceptance_price_trend(season_id: int, date_from: str | None = None,
                               date_to: str | None = None, group_by: str = "month") -> list[dict]:
    """Динамика средней цены приёмки по периодам и сортам."""
    db = get_db()
    where, params = _date_filter("a", date_from, date_to)
    pexpr, _ = _period_expr(group_by, "a.date")
    rows = []
    for r in db.execute(f"""
        SELECT {pexpr} AS period, g.display_name AS grade_name,
            COALESCE(SUM(ag.weight_kg), 0) AS kg,
            COALESCE(SUM(ag.total_amount), 0) AS amount,
            MIN(ag.price_per_kg) AS min_price,
            MAX(ag.price_per_kg) AS max_price
        FROM acceptance a
        JOIN acceptance_grade ag ON ag.acceptance_id = a.id
        JOIN grade g ON g.id = ag.grade_id
        WHERE a.season_id = ?{where}
        GROUP BY period, g.display_name
        ORDER BY period, g.sort_order
    """, (season_id, *params)):
        kg = float(r["kg"] or 0)
        amt = float(r["amount"] or 0)
        avg = amt / kg if kg > 0 else 0.0
        rows.append({
            "period": r["period"],
            "grade_name": r["grade_name"],
            "avg_price": avg,
            "min_price": float(r["min_price"] or 0),
            "max_price": float(r["max_price"] or 0),
            "kg": kg,
        })
    return rows



def get_product_profitability(season_id: int, date_from: str | None = None,
                              date_to: str | None = None, group_by: str = "day") -> list[dict]:
    """Рентабельность продукции: (выручка - себестоимость_продаж) / себестоимость_продаж * 100%."""
    db = get_db()
    where_s, params_s = _date_filter("s", date_from, date_to)
    where_a, params_a = _date_filter("a", date_from, date_to)
    where_d, params_d = _date_filter("d", date_from, date_to)
    where_e, params_e = _date_filter("", date_from, date_to)
    pexpr_s, _ = _period_expr(group_by, "s.date")
    pexpr_a, _ = _period_expr(group_by, "a.date")
    pexpr_d, _ = _period_expr(group_by, "d.date")
    pexpr_e, _ = _period_expr(group_by, "date")

    # Выручка по периоду и сорту
    revenue = {}
    for r in db.execute(f"""
        SELECT {pexpr_s} AS period, sl.grade_id,
            COALESCE(SUM(sl.weight_kg), 0) AS kg,
            COALESCE(SUM(sl.total_amount), 0) AS amount
        FROM sale s JOIN sale_line sl ON sl.sale_id = s.id
        WHERE s.season_id = ?{where_s}
        GROUP BY period, sl.grade_id
    """, (season_id, *params_s)):
        key = (r["period"], r["grade_id"])
        revenue[key] = {"kg": float(r["kg"] or 0), "amount": float(r["amount"] or 0)}

    # Приёмка по периоду и сорту (стоимость и кг)
    accepted = {}
    for r in db.execute(f"""
        SELECT {pexpr_a} AS period, ag.grade_id,
            COALESCE(SUM(ag.weight_kg), 0) AS kg,
            COALESCE(SUM(ag.total_amount), 0) AS amount
        FROM acceptance a JOIN acceptance_grade ag ON ag.acceptance_id = a.id
        WHERE a.season_id = ?{where_a}
        GROUP BY period, ag.grade_id
    """, (season_id, *params_a)):
        key = (r["period"], r["grade_id"])
        accepted[key] = {"kg": float(r["kg"] or 0), "amount": float(r["amount"] or 0)}

    # Сухой выход по периоду и сорту
    dried = {}
    for r in db.execute(f"""
        SELECT {pexpr_d} AS period,
            COALESCE(SUM(dry_grade_1_kg), 0) AS d1,
            COALESCE(SUM(dry_grade_2_kg), 0) AS d2,
            COALESCE(SUM(dry_grade_3_kg), 0) AS d3
        FROM drying_run d WHERE d.season_id = ?{where_d}
        GROUP BY period
    """, (season_id, *params_d)):
        per = r["period"]
        for gid, col in [(1, "d1"), (2, "d2"), (3, "d3")]:
            dried[(per, gid)] = float(r[col] or 0)

    # Итого расходы на сушку по периоду
    drying_cost = {}
    for r in db.execute(f"""
        SELECT {pexpr_d} AS period,
            COALESCE(SUM(COALESCE(de.cost_electricity, 0) + COALESCE(de.cost_water, 0) +
            COALESCE(de.cost_firewood, 0) + COALESCE(de.cost_labor, 0)), 0) AS cost
        FROM drying_run d
        LEFT JOIN drying_expense de ON de.drying_run_id = d.id
        WHERE d.season_id = ?{where_d}
        GROUP BY period
    """, (season_id, *params_d)):
        drying_cost[r["period"]] = float(r["cost"] or 0)

    # Итого прочие расходы по периоду
    other_cost = {}
    for r in db.execute(f"""
        SELECT {pexpr_e} AS period, COALESCE(SUM(amount), 0) AS cost
        FROM expense WHERE season_id = ?{where_e}
        GROUP BY period
    """, (season_id, *params_e)):
        other_cost[r["period"]] = float(r["cost"] or 0)

    # Итого стоимость приёмки за период (для пропорционального распределения)
    total_value_by_period = {}
    for key, val in accepted.items():
        per = key[0]
        total_value_by_period[per] = total_value_by_period.get(per, 0.0) + val["amount"]

    grades = list_grades()
    all_keys = sorted(set(list(revenue.keys()) + list(accepted.keys())))
    rows = []
    for key in all_keys:
        per, gid = key
        rev = revenue.get(key, {"kg": 0.0, "amount": 0.0})
        acc = accepted.get(key, {"kg": 0.0, "amount": 0.0})
        dry_kg = dried.get(key, 0.0)
        sold_kg = rev["kg"]

        # Пропорциональная доля сушки и прочих расходов
        period_total_value = total_value_by_period.get(per, 0.0)
        share = acc["amount"] / period_total_value if period_total_value > 0 else 0.0
        drying_share = drying_cost.get(per, 0.0) * share
        other_share = other_cost.get(per, 0.0) * share

        # Себестоимость продукции сорта
        total_grade_cost = acc["amount"] + drying_share + other_share
        cogs_per_kg = total_grade_cost / dry_kg if dry_kg > 0 else 0.0
        cogs_sold = sold_kg * cogs_per_kg

        # Рентабельность продукции
        profit = rev["amount"] - cogs_sold
        margin_pct = (profit / cogs_sold * 100) if cogs_sold > 0 else 0.0

        gname = next((g["display_name"] for g in grades if g["id"] == gid), str(gid))
        rows.append({
            "period": per, "grade_name": gname,
            "sold_kg": sold_kg, "revenue": rev["amount"],
            "cogs_per_kg": cogs_per_kg, "cogs_sold": cogs_sold,
            "profit": profit, "margin_pct": margin_pct,
        })
    return rows