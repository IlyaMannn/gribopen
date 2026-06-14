"""Flask-приложение: маршруты, маршрутизация, запуск."""
from datetime import date, datetime, timedelta
import csv
import io
import os
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort, Response,
)
from db import init_db, migrate_db, get_db, close_db
from auth import (
    login_user, logout_user, current_user, login_required,
    verify_password, change_password,
)
from seed import seed_if_empty, has_active_season, get_active_season, create_season, list_seasons, get_season, set_active_season, rename_season, update_season, delete_season, get_season_stats
import models


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "mushroom-local-dev-secret-change-me")
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30  # 30 дней
app.config["JSON_AS_ASCII"] = False

# Инициализируем БД и сидируем данные при загрузке модуля,
# чтобы это работало и при запуске, и при импорте в тестах.
init_db()
migrate_db()
with app.app_context():
    seed_if_empty()


@app.teardown_appcontext
def teardown(exception):
    close_db()


# --- Фильтры шаблонов --------------------------------------------------------

@app.template_filter("money")
def fmt_money(value) -> str:
    """Формат 1 234,56 ₽"""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} \u20bd"


@app.template_filter("kg")
def fmt_kg(value) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} кг"


@app.template_filter("pct")
def fmt_pct(value) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{v:.1f} %".replace(".", ",")


@app.template_filter("dmy")
def fmt_dmy(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return value
    return value.strftime("%d.%m.%Y")


@app.context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "active_season": dict(get_active_season()) if has_active_season() else None,
        "today_iso": date.today().isoformat(),
    }


# --- Маршруты ----------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user() is not None:
        return redirect(url_for("home"))

    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        db = get_db()
        row = db.execute(
            "SELECT id, username, password_hash FROM user WHERE username = ?",
            (username,),
        ).fetchone()
        if row and verify_password(password, row["password_hash"]):
            login_user(row["id"], row["username"])
            nxt = request.args.get("next") or url_for("home")
            return redirect(nxt)
        error = "Неверный логин или пароль"

    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/first-run", methods=["GET", "POST"])
@login_required
def first_run():
    """Мастер первого запуска: создание первого сезона."""
    if has_active_season():
        return redirect(url_for("home"))

    error = None
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        start_date = request.form.get("start_date") or date.today().isoformat()
        if not name:
            error = "Введите название сезона"
        else:
            create_season(name, start_date)
            flash(f"Сезон «{name}» создан", "ok")
            return redirect(url_for("home"))

    return render_template(
        "first_run.html",
        error=error,
        today=date.today().isoformat(),
    )


@app.route("/")
@login_required
def home():
    """Главная: остатки, итоги дня, быстрые действия."""
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    season_id = season["id"]
    grades = models.list_grades()
    raw_stock = models.get_raw_stock(season_id)
    dry_stock = models.get_dry_stock(season_id)
    season_totals = models.get_raw_stock_total_season(season_id)
    season_yield = models.get_drying_yield_season(season_id)
    season_sales = models.get_sales_total_season(season_id)
    season_expenses = models.get_expenses_total_season(season_id)

    # Итоги за сегодня
    today = date.today().isoformat()
    today_rows = models.list_acceptance_for_date(today, season_id)
    accepted_today_kg = sum(r["total_kg"] for r in today_rows)
    accepted_today_amount = sum(r["total_amount"] for r in today_rows)
    today_drying = models.get_drying_kg_by_date(today, season_id)
    waste_today = models.get_waste_kg_by_date(today, season_id)
    waste_pct_today = (waste_today / accepted_today_kg * 100) if accepted_today_kg > 0 else 0.0
    today_sales = models.get_sales_kg_by_date(today, season_id)
    today_expenses = models.get_expenses_by_date(today, season_id)
    fridge_stock = models.get_fridge_stock(season_id)
    cost = models.get_cost_per_kg_dry(season_id)
    margin = models.get_margin(season_id)

    # Notifications
    settings = models.get_all_settings()
    fridge_notify_min = float(settings.get("fridge_notify_min", "450"))
    fridge_notify_max = float(settings.get("fridge_notify_max", "500"))
    min_drying_load = float(settings.get("min_drying_load", "100"))
    total_fridge = sum(fridge_stock.values())
    notifications = []
    if total_fridge >= fridge_notify_max:
        notifications.append({"type": "danger", "text": f"Холодильник заполнен! {total_fridge:.1f} кг"})
    elif total_fridge >= fridge_notify_min:
        notifications.append({"type": "warning", "text": f"Холодильник: {total_fridge:.1f} кг. Пора загрузить сушилку."})
    if 0 < total_fridge < min_drying_load:
        need = min_drying_load - total_fridge
        notifications.append({"type": "info", "text": f"Для запуска сушилки нужно минимум {min_drying_load:.0f} кг. Сейчас {total_fridge:.1f} кг. Нужно ещё закупить {need:.1f} кг."})
    # Drying ready notifications (started_at + 12h)
    from datetime import datetime
    now = datetime.now()
    for r in models.list_drying_runs_all(season_id):
        if r.get("started_at") and not r.get("finished_at"):
            try:
                started = datetime.fromisoformat(r["started_at"])
                hours = (now - started).total_seconds() / 3600
                if hours >= 12:
                    notifications.append({"type": "success", "text": f"Сушка #{r['id']} готова! Прошло {hours:.0f}ч с момента загрузки."})
            except (ValueError, TypeError):
                pass

    return render_template(
        "home.html",
        grades=grades,
        raw_stock=raw_stock,
        dry_stock=dry_stock,
        fridge_stock=fridge_stock,
        accepted_today_kg=accepted_today_kg,
        accepted_today_amount=accepted_today_amount,
        today_drying=today_drying,
        waste_today=waste_today,
        waste_pct_today=waste_pct_today,
        today_sales=today_sales,
        today_expenses=today_expenses,
        today=today,
        notifications=notifications,
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        # Save notification thresholds
        for key in ("fridge_notify_min", "fridge_notify_max", "min_drying_load"):
            val = request.form.get(key, "").strip()
            if val:
                models.set_setting(key, val)
        flash("Настройки сохранены", "ok")
        return redirect(url_for("settings"))
    return render_template("settings.html",
                           settings=models.get_all_settings())


@app.route("/settings/password", methods=["POST"])
@login_required
def settings_change_password():
    user = current_user()
    old = request.form.get("old_password") or ""
    new = request.form.get("new_password") or ""
    new2 = request.form.get("new_password2") or ""
    if new != new2:
        flash("Новые пароли не совпадают", "err")
        return redirect(url_for("settings"))
    err = change_password(user["id"], old, new)
    if err:
        flash(err, "err")
    else:
        flash("Пароль изменён", "ok")
    return redirect(url_for("settings"))


# --- Приёмка ------------------------------------------------------------------

@app.route("/acceptance", methods=["GET", "POST"])
@login_required
def acceptance():
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    season_id = season["id"]
    grades = models.list_grades()
    suppliers = models.list_suppliers()
    today = date.today().isoformat()

    if request.method == "POST":
        form_date = request.form.get("date") or today
        supplier_id_raw = request.form.get("supplier_id") or ""
        supplier_id = int(supplier_id_raw) if supplier_id_raw.isdigit() else None
        notes = request.form.get("notes") or ""

        grades_input = []
        for g in grades:
            w_raw = request.form.get(f"weight_{g['id']}") or ""
            p_raw = request.form.get(f"price_{g['id']}") or ""
            try:
                w = float(w_raw.replace(",", ".")) if w_raw.strip() else 0
            except ValueError:
                w = 0
            try:
                p = float(p_raw.replace(",", ".")) if p_raw.strip() else 0
            except ValueError:
                p = 0
            if w > 0 and p >= 0:
                grades_input.append((g["id"], w, p))

        if grades_input:
            models.add_acceptance(form_date, season_id, grades_input, supplier_id, notes)
            flash(f"Приёмка сохранена: {len(grades_input)} сорт(ов)", "ok")
        else:
            flash("Не введено ни одного значения веса", "err")
        return redirect(url_for("acceptance", date=form_date))

    # GET
    selected_date = request.args.get("date") or today
    rows = models.list_acceptance_for_date(selected_date, season_id)
    latest_prices = models.latest_prices_dict(selected_date)
    raw_stock = models.get_raw_stock(season_id)
    fridge_stock = models.get_fridge_stock(season_id)

    return render_template(
        "acceptance.html",
        grades=grades,
        suppliers=suppliers,
        today=today,
        selected_date=selected_date,
        rows=rows,
        latest_prices=latest_prices,
        raw_stock=raw_stock,
        fridge_stock=fridge_stock,
    )


@app.route("/acceptance/<int:acceptance_id>/edit", methods=["GET", "POST"])
@login_required
def acceptance_edit(acceptance_id):
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    rec = models.get_acceptance(acceptance_id)
    if rec is None:
        flash("Запись не найдена", "err")
        return redirect(url_for("acceptance"))

    grades = models.list_grades()
    suppliers = models.list_suppliers()
    today = date.today().isoformat()

    if request.method == "POST":
        form_date = request.form.get("date") or rec["date"]
        supplier_id_raw = request.form.get("supplier_id") or ""
        supplier_id = int(supplier_id_raw) if supplier_id_raw.isdigit() else None
        notes = request.form.get("notes") or ""

        grades_input = []
        for g in grades:
            w_raw = request.form.get(f"weight_{g['id']}") or ""
            p_raw = request.form.get(f"price_{g['id']}") or ""
            try:
                w = float(w_raw.replace(",", ".")) if w_raw.strip() else 0
            except ValueError:
                w = 0
            try:
                p = float(p_raw.replace(",", ".")) if p_raw.strip() else 0
            except ValueError:
                p = 0
            if w > 0 and p >= 0:
                grades_input.append((g["id"], w, p))

        models.update_acceptance(acceptance_id, form_date, grades_input, supplier_id, notes)
        flash("Приёмка обновлена", "ok")
        return redirect(url_for("acceptance", date=form_date))

    latest_prices = models.latest_prices_dict(rec["date"])
    return render_template(
        "acceptance_edit.html",
        rec=rec,
        grades=grades,
        suppliers=suppliers,
        latest_prices=latest_prices,
        today=today,
    )


@app.route("/acceptance/<int:acceptance_id>/delete", methods=["POST"])
@login_required
def acceptance_delete(acceptance_id):
    rec = models.get_acceptance(acceptance_id)
    if rec is None:
        flash("Запись не найдена", "err")
        return redirect(url_for("acceptance"))
    models.delete_acceptance(acceptance_id)
    flash("Запись удалена", "ok")
    return redirect(url_for("acceptance", date=rec["date"]))


@app.route("/acceptance/quick-supplier", methods=["POST"])
@login_required
def acceptance_quick_supplier():
    """Быстрое создание поставщика прямо с приёмки. Возврат на /acceptance?date=..."""
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    notes = (request.form.get("supplier_notes") or "").strip()
    if not name:
        flash("Имя поставщика обязательно", "err")
        return redirect(request.referrer or url_for("acceptance"))
    new_id = models.add_supplier(name, phone, notes)
    flash(f"Поставщик «{name}» добавлен", "ok")
    target_date = request.form.get("date") or date.today().isoformat()
    return redirect(url_for("acceptance", date=target_date) + f"&new_supplier={new_id}")


# --- Справочники --------------------------------------------------------------

@app.route("/directories", methods=["GET"])
@login_required
def directories():
    grades = models.list_grades()
    prices = models.list_purchase_prices()
    suppliers = models.list_suppliers()
    buyers = models.list_buyers()
    return render_template(
        "directories.html",
        grades=grades,
        prices=prices,
        suppliers=suppliers,
        buyers=buyers,
        today=date.today().isoformat(),
    )


@app.route("/directories/purchase-prices", methods=["POST"])
@login_required
def directories_add_price():
    try:
        grade_id = int(request.form.get("grade_id") or 0)
        price = float((request.form.get("price_per_kg") or "0").replace(",", "."))
        eff = request.form.get("effective_from") or date.today().isoformat()
    except ValueError:
        flash("Некорректные значения", "err")
        return redirect(url_for("directories"))
    if price < 0 or grade_id <= 0:
        flash("Цена и сорт должны быть заданы", "err")
        return redirect(url_for("directories"))
    models.add_purchase_price(grade_id, price, eff)
    flash("Цена добавлена", "ok")
    return redirect(url_for("directories") + "#prices")


@app.route("/directories/purchase-prices/<int:price_id>/delete", methods=["POST"])
@login_required
def directories_delete_price(price_id):
    models.delete_purchase_price(price_id)
    flash("Запись цены удалена", "ok")
    return redirect(url_for("directories") + "#prices")


@app.route("/directories/suppliers", methods=["POST"])
@login_required
def directories_add_supplier():
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    if not name:
        flash("Имя поставщика обязательно", "err")
        return redirect(url_for("directories") + "#suppliers")
    models.add_supplier(name, phone, notes)
    flash(f"Поставщик «{name}» добавлен", "ok")
    return redirect(url_for("directories") + "#suppliers")


@app.route("/directories/suppliers/<int:supplier_id>/edit", methods=["POST"])
@login_required
def directories_edit_supplier(supplier_id):
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    if not name:
        flash("Имя поставщика обязательно", "err")
        return redirect(url_for("directories") + "#suppliers")
    models.update_supplier(supplier_id, name, phone, notes)
    flash("Поставщик обновлён", "ok")
    return redirect(url_for("directories") + "#suppliers")


@app.route("/directories/suppliers/<int:supplier_id>/delete", methods=["POST"])
@login_required
def directories_delete_supplier(supplier_id):
    affected = models.delete_supplier(supplier_id)
    if affected:
        flash(f"Поставщик удалён. У {affected} записей приёмки поставщик снят.", "ok")
    else:
        flash("Поставщик удалён", "ok")
    return redirect(url_for("directories") + "#suppliers")


# --- Покупатели ----------------------------------------------------------------

@app.route("/directories/buyers", methods=["POST"])
@login_required
def directories_add_buyer():
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    if not name:
        flash("Имя покупателя обязательно", "err")
        return redirect(url_for("directories") + "#buyers")
    models.add_buyer(name, phone, notes)
    flash(f"Покупатель «{name}» добавлен", "ok")
    return redirect(url_for("directories") + "#buyers")


@app.route("/directories/buyers/<int:buyer_id>/edit", methods=["POST"])
@login_required
def directories_edit_buyer(buyer_id):
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    if not name:
        flash("Имя покупателя обязательно", "err")
        return redirect(url_for("directories") + "#buyers")
    models.update_buyer(buyer_id, name, phone, notes)
    flash("Покупатель обновлён", "ok")
    return redirect(url_for("directories") + "#buyers")


@app.route("/directories/buyers/<int:buyer_id>/delete", methods=["POST"])
@login_required
def directories_delete_buyer(buyer_id):
    affected = models.delete_buyer(buyer_id)
    if affected:
        flash(f"Покупатель удалён. У {affected} продаж покупатель снят.", "ok")
    else:
        flash("Покупатель удалён", "ok")
    return redirect(url_for("directories") + "#buyers")


# --- Сушка --------------------------------------------------------------------

def _parse_kg(value: str) -> float:
    if not value:
        return 0.0
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return 0.0


@app.route("/drying", methods=["GET", "POST"])
@login_required
def drying():
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    season_id = season["id"]
    grades = models.list_grades()
    today = date.today().isoformat()
    fridge_stock = models.get_fridge_stock(season_id)

    if request.method == "POST":
        form_date = request.form.get("date") or today
        raw_by_grade = {g["id"]: _parse_kg(request.form.get(f"raw_{g['id']}")) for g in grades}
        notes = request.form.get("notes") or ""
        total_raw = sum(raw_by_grade.values())
        if total_raw <= 0:
            flash("Не введено ни одного значения загрузки", "err")
            return redirect(url_for("drying"))
        over = []
        for g in grades:
            if raw_by_grade[g["id"]] > fridge_stock[g["id"]] + 0.001:
                over.append(f"{g['display_name']}: {raw_by_grade[g['id']]:.2f} > остаток {fridge_stock[g['id']]:.2f}")
        if over:
            flash("Недостаточно сырья: " + "; ".join(over), "err")
            return redirect(url_for("drying"))
        from datetime import datetime
        now = datetime.now().isoformat(timespec="seconds")
        models.add_drying_run(form_date, season_id, raw_by_grade, notes=notes, started_at=now)
        flash("Сушка запущена", "ok")
        return redirect(url_for("drying"))

    selected_date = request.args.get("date") or today
    runs = models.list_drying_runs_for_date(selected_date, season_id)
    # Mark status
    for r in runs:
        if r.get("finished_at"):
            r["status"] = "done"
        elif r.get("started_at"):
            r["status"] = "drying"
        else:
            r["status"] = "queued"
    season_yield = models.get_drying_yield_season(season_id)
    return render_template(
        "drying.html",
        grades=grades,
        today=today,
        selected_date=selected_date,
        fridge_stock=fridge_stock,
        runs=runs,
        season_yield=season_yield,
    )


@app.route("/drying/<int:run_id>/finish", methods=["GET", "POST"])
@login_required
def drying_finish(run_id):
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    grades = models.list_grades()
    run = models.get_drying_run(run_id)
    if not run:
        flash("Запись сушки не найдена", "err")
        return redirect(url_for("drying"))
    exps = models.get_drying_expenses(run_id)
    exp_total = {
        "cost_electricity": sum(e["cost_electricity"] for e in exps),
        "cost_water": sum(e["cost_water"] for e in exps),
        "cost_firewood": sum(e["cost_firewood"] for e in exps),
        "cost_labor": sum(e["cost_labor"] for e in exps),
    }
    if request.method == "POST":
        dry_by_grade = {g["id"]: _parse_kg(request.form.get(f"dry_{g['id']}")) for g in grades}
        for g in grades:
            r = run.get(f"raw_grade_{g['id']}_kg", 0)
            d = dry_by_grade[g["id"]]
            if d > r + 0.001:
                flash(f"{g['display_name']}: получено {d:.2f} кг > загружено {r:.2f} кг", "err")
                return redirect(url_for("drying_finish", run_id=run_id))
        models.finish_drying(run_id, dry_by_grade)
        cost_el = _parse_kg(request.form.get("cost_electricity"))
        cost_wt = _parse_kg(request.form.get("cost_water"))
        cost_fw = _parse_kg(request.form.get("cost_firewood"))
        cost_lb = _parse_kg(request.form.get("cost_labor"))
        expense_notes = request.form.get("expense_notes") or ""
        has_expense = cost_el > 0 or cost_wt > 0 or cost_fw > 0 or cost_lb > 0
        if has_expense:
            models.add_drying_expense(run_id, cost_el, cost_wt, cost_fw, cost_lb, expense_notes)
        flash("Сушка завершена", "ok")
        return redirect(url_for("drying"))
    return render_template("drying_finish.html", run=run, grades=grades, exp_total=exp_total)


@app.route("/drying/<int:run_id>/delete", methods=["POST"])
@login_required
def drying_delete(run_id):
    models.delete_drying_run(run_id)
    flash("Запись сушки удалена", "ok")
    return redirect(request.referrer or url_for("drying"))


@app.route("/drying-expenses", methods=["GET", "POST"])
@login_required
def drying_expenses():
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    season_id = season["id"]
    runs = models.list_drying_runs_all(season_id)
    if request.method == "POST":
        run_id_raw = request.form.get("run_id") or ""
        if not run_id_raw.isdigit():
            flash("Выберите запись сушки", "err")
            return redirect(url_for("drying_expenses"))
        run_id = int(run_id_raw)
        cost_el = _parse_kg(request.form.get("cost_electricity"))
        cost_wt = _parse_kg(request.form.get("cost_water"))
        cost_fw = _parse_kg(request.form.get("cost_firewood"))
        cost_lb = _parse_kg(request.form.get("cost_labor"))
        notes = request.form.get("notes") or ""
        models.add_drying_expense(run_id, cost_el, cost_wt, cost_fw, cost_lb, notes)
        flash("Расходы на сушку сохранены", "ok")
        return redirect(url_for("drying_expenses"))
    # GET: show expenses per run
    expenses_by_run = {}
    for r in runs:
        exps = models.get_drying_expenses(r["id"])
        total = sum(e["cost_electricity"] + e["cost_water"] + e["cost_firewood"] + e["cost_labor"] for e in exps)
        expenses_by_run[r["id"]] = {"expenses": exps, "total": total}
    return render_template("drying_expenses.html", runs=runs, expenses_by_run=expenses_by_run)


# --- Мусор --------------------------------------------------------------------

@app.route("/waste", methods=["GET", "POST"])
@login_required
def waste():
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    season_id = season["id"]
    today = date.today().isoformat()
    grades = models.list_grades()

    if request.method == "POST":
        form_date = request.form.get("date") or today
        acceptance_id_raw = request.form.get("acceptance_id") or ""
        acceptance_id = int(acceptance_id_raw) if acceptance_id_raw.isdigit() else None

        kg_by_grade = {}
        cleaned_by_grade = {}
        total = 0.0

        if acceptance_id:
            remaining = models.get_acceptance_remaining(acceptance_id, season_id)
            over = []
            for g in grades:
                w = _parse_kg(request.form.get(f"weight_{g['id']}"))
                if w < 0:
                    w = 0
                r = remaining.get(g["id"], 0.0)
                if w > r + 0.001:
                    over.append(f"{g['display_name']}: мусор {w:.2f} > остаток {r:.2f}")
                kg_by_grade[g["id"]] = w
                cleaned_by_grade[g["id"]] = max(0.0, r - w)
                total += w
            if over:
                flash("Нельзя ввести больше мусора, чем принято: " + "; ".join(over), "err")
                return redirect(url_for("waste", date=form_date))
            acc = models.get_acceptance(acceptance_id)
            supplier_id = acc["supplier_id"] if acc else None
        else:
            for g in grades:
                w = _parse_kg(request.form.get(f"weight_{g['id']}"))
                c = _parse_kg(request.form.get(f"cleaned_{g['id']}"))
                if w < 0:
                    w = 0
                if c < 0:
                    c = 0
                kg_by_grade[g["id"]] = w
                cleaned_by_grade[g["id"]] = c
                total += w
            supplier_id = None

        notes = request.form.get("notes") or ""
        total_cleaned = sum(cleaned_by_grade.values())
        models.add_waste_record(form_date, season_id, kg_by_grade, cleaned_by_grade, supplier_id, acceptance_id, notes)
        flash(f"Записано: мусор {total:.2f} кг, в холодильник {total_cleaned:.2f} кг", "ok")
        return redirect(url_for("waste", date=form_date))

    # GET
    selected_date = request.args.get("date") or today
    rows = models.list_waste_records_for_date(selected_date, season_id)
    accepted_today = models.get_accepted_kg_by_date(selected_date, season_id)
    waste_today = models.get_waste_kg_by_date(selected_date, season_id)
    waste_by_grade_today = models.get_waste_kg_by_date_by_grade(selected_date, season_id)
    waste_pct = (waste_today / accepted_today * 100) if accepted_today > 0 else 0.0
    waste_total_season = models.get_waste_total_season(season_id)
    waste_by_grade_season = models.get_waste_total_season_by_grade(season_id)
    accepted_total_season = models.get_raw_stock_total_season(season_id)["total_kg"]
    waste_pct_season = (waste_total_season / accepted_total_season * 100) if accepted_total_season > 0 else 0.0
    acceptances = models.list_acceptances_for_waste(season_id)

    return render_template(
        "waste.html",
        today=today,
        selected_date=selected_date,
        rows=rows,
        grades=grades,
        acceptances=acceptances,
        accepted_today=accepted_today,
        waste_today=waste_today,
        waste_by_grade_today=waste_by_grade_today,
        waste_pct=waste_pct,
        waste_total_season=waste_total_season,
        waste_by_grade_season=waste_by_grade_season,
        accepted_total_season=accepted_total_season,
        waste_pct_season=waste_pct_season,
    )


@app.route("/waste/<int:record_id>/edit", methods=["GET", "POST"])
@login_required
def waste_edit(record_id):
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    rec = models.get_waste_record(record_id)
    if rec is None:
        flash("Запись не найдена", "err")
        return redirect(url_for("waste"))
    season_id = season["id"]
    grades = models.list_grades()
    acceptances = models.list_acceptances_for_waste(season_id)
    today = date.today().isoformat()

    if request.method == "POST":
        form_date = request.form.get("date") or rec["date"]
        acceptance_id_raw = request.form.get("acceptance_id") or ""
        acceptance_id = int(acceptance_id_raw) if acceptance_id_raw.isdigit() else None

        kg_by_grade = {}
        cleaned_by_grade = {}

        if acceptance_id:
            remaining = models.get_acceptance_remaining(acceptance_id, season_id)
            over = []
            for g in grades:
                w = _parse_kg(request.form.get(f"weight_{g['id']}"))
                if w < 0:
                    w = 0
                r = remaining.get(g["id"], 0.0)
                if w > r + 0.001:
                    over.append(f"{g['display_name']}: мусор {w:.2f} > остаток {r:.2f}")
                kg_by_grade[g["id"]] = w
                cleaned_by_grade[g["id"]] = max(0.0, r - w)
            if over:
                flash("Нельзя ввести больше мусора, чем принято: " + "; ".join(over), "err")
                return redirect(url_for("waste", date=rec["date"]))
            acc = models.get_acceptance(acceptance_id)
            supplier_id = acc["supplier_id"] if acc else None
        else:
            for g in grades:
                w = _parse_kg(request.form.get(f"weight_{g['id']}"))
                c = _parse_kg(request.form.get(f"cleaned_{g['id']}"))
                if w < 0:
                    w = 0
                if c < 0:
                    c = 0
                kg_by_grade[g["id"]] = w
                cleaned_by_grade[g["id"]] = c
            supplier_id_raw = request.form.get("supplier_id") or ""
            supplier_id = int(supplier_id_raw) if supplier_id_raw.isdigit() else None

        notes = request.form.get("notes") or ""
        models.update_waste_record(record_id, form_date, kg_by_grade, cleaned_by_grade, supplier_id, acceptance_id, notes)
        flash("Запись мусора обновлена", "ok")
        return redirect(url_for("waste", date=form_date))

    return render_template(
        "waste_edit.html",
        rec=rec,
        grades=grades,
        acceptances=acceptances,
        today=today,
    )


@app.route("/waste/<int:record_id>/delete", methods=["POST"])
@login_required
def waste_delete(record_id):
    rec = models.get_waste_record(record_id)
    if rec is None:
        flash("Запись не найдена", "err")
        return redirect(url_for("waste"))
    models.delete_waste_record(record_id)
    flash("Запись удалена", "ok")
    return redirect(url_for("waste", date=rec["date"]))


# --- Продажи -------------------------------------------------------------------

@app.route("/sales", methods=["GET", "POST"])
@login_required
def sales():
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    season_id = season["id"]
    grades = models.list_grades()
    buyers = models.list_buyers()
    today = date.today().isoformat()
    dry_stock = models.get_dry_stock(season_id)

    if request.method == "POST":
        form_date = request.form.get("date") or today
        buyer_id_raw = request.form.get("buyer_id") or ""
        buyer_id = int(buyer_id_raw) if buyer_id_raw.isdigit() else None
        notes = request.form.get("notes") or ""
        lines = []
        for g in grades:
            w = _parse_kg(request.form.get(f"weight_{g['id']}"))
            p = _parse_kg(request.form.get(f"price_{g['id']}"))
            if w > 0 and p >= 0:
                lines.append((g["id"], w, p))
        if not lines:
            flash("Не введено ни одного значения веса", "err")
            return redirect(url_for("sales"))
        # Validate stock
        for gid, w, p in lines:
            if w > dry_stock.get(gid, 0) + 0.001:
                gname = next((g["display_name"] for g in grades if g["id"] == gid), "?")
                flash(f"Недостаточно сухого {gname}: остаток {dry_stock.get(gid, 0):.2f} кг, продаёте {w:.2f}", "err")
                return redirect(url_for("sales"))
        models.add_sale(form_date, season_id, buyer_id, lines, notes)
        flash(f"Продажа сохранена: {len(lines)} сорт(ов)", "ok")
        return redirect(url_for("sales"))

    selected_date = request.args.get("date") or today
    rows = models.list_sales_for_date(selected_date, season_id)
    season_sales = models.get_sales_total_season(season_id)
    return render_template(
        "sales.html",
        grades=grades,
        buyers=buyers,
        today=today,
        selected_date=selected_date,
        dry_stock=dry_stock,
        rows=rows,
        season_sales=season_sales,
    )


@app.route("/sales/<int:sale_id>/edit", methods=["GET", "POST"])
@login_required
def sales_edit(sale_id):
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    season_id = season["id"]
    grades = models.list_grades()
    buyers = models.list_buyers()
    rec = models.get_sale(sale_id)
    if not rec:
        flash("Продажа не найдена", "err")
        return redirect(url_for("sales"))
    if request.method == "POST":
        form_date = request.form.get("date") or rec["date"]
        buyer_id_raw = request.form.get("buyer_id") or ""
        buyer_id = int(buyer_id_raw) if buyer_id_raw.isdigit() else None
        notes = request.form.get("notes") or ""
        lines = []
        for g in grades:
            w = _parse_kg(request.form.get(f"weight_{g['id']}"))
            p = _parse_kg(request.form.get(f"price_{g['id']}"))
            if w > 0 and p >= 0:
                lines.append((g["id"], w, p))
        if not lines:
            flash("Не введено ни одного значения веса", "err")
            return redirect(url_for("sales_edit", sale_id=sale_id))
        models.update_sale(sale_id, form_date, season_id, buyer_id, lines, notes)
        flash("Продажа обновлена", "ok")
        return redirect(url_for("sales"))
    return render_template("sales_edit.html", rec=rec, grades=grades, buyers=buyers)


@app.route("/sales/<int:sale_id>/delete", methods=["POST"])
@login_required
def sales_delete(sale_id):
    models.delete_sale(sale_id)
    flash("Продажа удалена", "ok")
    return redirect(request.referrer or url_for("sales"))


# --- Расходы (общие) -----------------------------------------------------------

@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    season_id = season["id"]
    today = date.today().isoformat()

    if request.method == "POST":
        form_date = request.form.get("date") or today
        category = (request.form.get("category") or "").strip()
        amount = _parse_kg(request.form.get("amount"))
        notes = request.form.get("notes") or ""
        if not category or amount <= 0:
            flash("Заполните категорию и сумму (> 0)", "err")
            return redirect(url_for("expenses"))
        models.add_expense(form_date, season_id, category, amount, notes)
        flash(f"Расход записан: {category} · {amount:.2f} ₽", "ok")
        return redirect(url_for("expenses"))

    # GET
    selected_date = request.args.get("date") or today
    rows = models.list_expenses_for_date(selected_date, season_id)
    season_expenses = models.get_expenses_total_season(season_id)
    return render_template(
        "expenses.html",
        today=today,
        selected_date=selected_date,
        rows=rows,
        season_expenses=season_expenses,
    )


@app.route("/expenses/<int:expense_id>/delete", methods=["POST"])
@login_required
def expenses_delete(expense_id):
    models.delete_expense(expense_id)
    flash("Расход удалён", "ok")
    return redirect(request.referrer or url_for("expenses"))


# --- Сезоны --------------------------------------------------------------------

@app.route("/seasons", methods=["GET", "POST"])
@login_required
def seasons():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        start_date = request.form.get("start_date") or date.today().isoformat()
        if not name:
            flash("Название сезона обязательно", "err")
            return redirect(url_for("seasons"))
        new_id = create_season(name, start_date)
        flash(f"Сезон «{name}» создан и активирован", "ok")
        return redirect(url_for("seasons"))

    rows = list_seasons()
    # Считаем статистику по каждому сезону
    seasons_data = []
    for s in rows:
        stats = get_season_stats(s["id"])
        seasons_data.append({**dict(s), "stats": stats})
    return render_template("seasons.html", seasons=seasons_data, today=date.today().isoformat())


@app.route("/seasons/<int:season_id>/activate", methods=["POST"])
@login_required
def seasons_activate(season_id):
    s = get_season(season_id)
    if s is None:
        flash("Сезон не найден", "err")
        return redirect(url_for("seasons"))
    if s["is_active"]:
        flash("Этот сезон уже активен", "ok")
        return redirect(url_for("seasons"))
    old_id = set_active_season(season_id)
    flash(f"Активен сезон «{s['name']}»", "ok")
    return redirect(url_for("seasons"))


@app.route("/seasons/<int:season_id>/rename", methods=["POST"])
@login_required
def seasons_rename(season_id):
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Название не может быть пустым", "err")
        return redirect(url_for("seasons"))
    rename_season(season_id, name)
    flash("Сезон переименован", "ok")
    return redirect(url_for("seasons"))


@app.route("/seasons/<int:season_id>/edit", methods=["GET", "POST"])
@login_required
def seasons_edit(season_id):
    s = get_season(season_id)
    if s is None:
        flash("Сезон не найден", "err")
        return redirect(url_for("seasons"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        start_date = request.form.get("start_date") or s["start_date"]
        end_date_raw = request.form.get("end_date") or ""
        end_date = end_date_raw or None
        if not name:
            flash("Название не может быть пустым", "err")
            return redirect(url_for("seasons_edit", season_id=season_id))
        update_season(season_id, name, start_date, end_date)
        flash("Сезон обновлён", "ok")
        return redirect(url_for("seasons"))
    return render_template("seasons_edit.html", s=s, today=date.today().isoformat())


@app.route("/seasons/<int:season_id>/delete", methods=["POST"])
@login_required
def seasons_delete(season_id):
    s = get_season(season_id)
    if s is None:
        flash("Сезон не найден", "err")
        return redirect(url_for("seasons"))
    if s["is_active"]:
        flash("Нельзя удалить активный сезон. Сначала активируйте другой.", "err")
        return redirect(url_for("seasons"))
    affected = delete_season(season_id)
    if affected:
        flash(f"Сезон «{s['name']}» удалён. Затронуто связанных записей: {affected}.", "ok")
    else:
        flash(f"Сезон «{s['name']}» удалён", "ok")
    return redirect(url_for("seasons"))


# --- Отчёты --------------------------------------------------------------------

@app.route("/reports")
@login_required
def reports():
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    season_id = season["id"]
    today = date.today()

    # Пресеты: season, today, yesterday, week, month, all
    preset = request.args.get("preset", "season")
    date_from = request.args.get("date_from", "").strip() or None
    date_to = request.args.get("date_to", "").strip() or None

    if not date_from and not date_to:
        if preset == "today":
            date_from = date_to = today.isoformat()
        elif preset == "yesterday":
            y = today - timedelta(days=1)
            date_from = date_to = y.isoformat()
        elif preset == "week":
            date_from = (today - timedelta(days=6)).isoformat()
            date_to = today.isoformat()
        elif preset == "month":
            date_from = today.replace(day=1).isoformat()
            date_to = today.isoformat()
        elif preset == "season":
            date_from = season["start_date"]
            date_to = season["end_date"] or today.isoformat()
        # else: all time (both None)

    group_by = request.args.get("group_by", "day")
    if group_by not in ("day", "week", "month"):
        group_by = "day"
    active_tab = request.args.get("tab", "cost")

    pnl = models.pnl_by_period(season_id, date_from, date_to)
    suppliers = models.supplier_summary(season_id, date_from, date_to)
    buyers = models.buyer_summary(season_id, date_from, date_to)
    daily = models.daily_summary(season_id, date_from, date_to)
    cost = models.get_cost_per_kg_dry(season_id, date_from, date_to)
    margin = models.get_margin(season_id, date_from, date_to)
    movement = models.get_grade_movement(season_id, date_from, date_to)
    supp_eff = models.get_supplier_efficiency(season_id, date_from, date_to)
    yield_trend = models.get_yield_trend(season_id, date_from, date_to)
    top_grades = models.get_top_grades(season_id, date_from, date_to)
    cashflow = models.get_cashflow(season_id, date_from, date_to)
    expenses_detail = models.get_expenses_detail(season_id, date_from, date_to, group_by)
    sales_detail = models.get_sales_detail(season_id, date_from, date_to, group_by)
    production = models.get_production_summary(season_id, date_from, date_to, group_by)
    profitability = models.get_profitability_by_grade(season_id, date_from, date_to, group_by)
    product_profit = models.get_product_profitability(season_id, date_from, date_to, group_by)
    price_trend = models.get_acceptance_price_trend(season_id, date_from, date_to, group_by)
    drying_runs = models.list_drying_runs_for_season(season_id)

    return render_template(
        "reports.html",
        active_tab=active_tab,
        pnl=pnl,
        suppliers=suppliers,
        buyers=buyers,
        daily=daily,
        cost=cost,
        margin=margin,
        movement=movement,
        supp_eff=supp_eff,
        yield_trend=yield_trend,
        top_grades=top_grades,
        cashflow=cashflow,
        expenses_detail=expenses_detail,
        sales_detail=sales_detail,
        production=production,
        profitability=profitability,
        product_profit=product_profit,
        price_trend=price_trend,
        drying_runs=drying_runs,
        group_by=group_by,
        preset=preset,
        date_from=date_from or "",
        date_to=date_to or "",
        season=season,
    )


@app.route("/reports/export.csv")
@login_required
def reports_export_csv():
    """Экспорт отчёта в CSV. Параметр ?section=suppliers|buyers|daily|pnl."""
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    season_id = season["id"]
    preset = request.args.get("preset", "season")
    date_from = request.args.get("date_from", "").strip() or None
    date_to = request.args.get("date_to", "").strip() or None
    if not date_from and not date_to:
        if preset == "today":
            d = date.today()
            date_from = date_to = d.isoformat()
        elif preset == "yesterday":
            d = date.today() - timedelta(days=1)
            date_from = date_to = d.isoformat()
        elif preset == "week":
            date_from = (date.today() - timedelta(days=6)).isoformat()
            date_to = date.today().isoformat()
        elif preset == "month":
            date_from = date.today().replace(day=1).isoformat()
            date_to = date.today().isoformat()
        elif preset == "season":
            date_from = season["start_date"]
            date_to = season["end_date"] or date.today().isoformat()

    section = request.args.get("section", "daily")
    buf = io.StringIO()
    # BOM для корректного открытия в Excel на Windows
    buf.write("\ufeff")
    writer = csv.writer(buf, delimiter=";")

    if section == "pnl":
        pnl = models.pnl_by_period(season_id, date_from, date_to)
        writer.writerow(["Показатель", "Значение"])
        writer.writerow(["Период", f"{date_from or 'с начала'} — {date_to or 'сейчас'}"])
        writer.writerow(["Принято, кг", f"{pnl['accepted_kg']:.2f}"])
        writer.writerow(["Принято, ₽", f"{pnl['accepted_amount']:.2f}"])
        writer.writerow(["Загружено в сушку, кг", f"{pnl['dried_raw_kg']:.2f}"])
        writer.writerow(["Получено сухого, кг", f"{pnl['dried_dry_kg']:.2f}"])
        writer.writerow(["Расходы на сушку, ₽", f"{pnl['drying_cost']:.2f}"])
        writer.writerow(["Мусор, кг", f"{pnl['waste_kg']:.2f}"])
        writer.writerow(["Продано, кг", f"{pnl['sales_kg']:.2f}"])
        writer.writerow(["Выручка, ₽", f"{pnl['revenue']:.2f}"])
        writer.writerow(["Общие расходы, ₽", f"{pnl['expenses_total']:.2f}"])
        writer.writerow(["Всего расходов, ₽", f"{pnl['total_cost']:.2f}"])
        writer.writerow(["Прибыль, ₽", f"{pnl['profit']:.2f}"])
        fname = "pnl.csv"
    elif section == "suppliers":
        suppliers = models.supplier_summary(season_id, date_from, date_to)
        writer.writerow(["Поставщик", "Записей", "Кг", "Сумма, ₽"])
        for s in suppliers:
            writer.writerow([s["supplier_name"] or "(без имени)", s["deliveries"],
                             f"{s['kg']:.2f}", f"{s['amount']:.2f}"])
        fname = "suppliers.csv"
    elif section == "buyers":
        buyers = models.buyer_summary(season_id, date_from, date_to)
        writer.writerow(["Покупатель", "Сделок", "Кг", "Выручка, ₽"])
        for b in buyers:
            writer.writerow([b["buyer_name"] or "(без имени)", b["deals"],
                             f"{b['kg']:.2f}", f"{b['amount']:.2f}"])
        fname = "buyers.csv"
    elif section == "daily":
        daily = models.daily_summary(season_id, date_from, date_to)
        writer.writerow(["Дата", "Принято кг", "Принято ₽", "В сушку кг", "Получено сух кг",
                         "Расходы сушка ₽", "Мусор кг", "Продано кг", "Выручка ₽",
                         "Общие расходы ₽", "Прибыль ₽"])
        for d in daily:
            writer.writerow([d["date"],
                             f"{d['accepted_kg']:.2f}", f"{d['accepted_amount']:.2f}",
                             f"{d['dried_raw_kg']:.2f}", f"{d['dried_dry_kg']:.2f}",
                             f"{d['drying_cost']:.2f}", f"{d['waste_kg']:.2f}",
                             f"{d['sales_kg']:.2f}", f"{d['revenue']:.2f}",
                             f"{d['expenses_total']:.2f}", f"{d['profit']:.2f}"])
        fname = "daily.csv"
    elif section == "costs":
        cost = models.get_cost_per_kg_dry(season_id, date_from, date_to)
        writer.writerow(["Показатель", "Значение"])
        writer.writerow(["Вложено в приёмку, ₽", f"{cost['accepted_amount']:.2f}"])
        writer.writerow(["Расходы на сушку, ₽", f"{cost['drying_cost']:.2f}"])
        writer.writerow(["Общие расходы, ₽", f"{cost['expenses']:.2f}"])
        writer.writerow(["Всего вложено, ₽", f"{cost['total_invested']:.2f}"])
        writer.writerow(["Продано, кг", f"{cost['sold_kg']:.2f}"])
        writer.writerow(["Сухой остаток, кг", f"{cost['dry_stock_kg']:.2f}"])
        writer.writerow(["Себестоимость 1 кг сухого, ₽", f"{cost['cost_per_kg']:.2f}"])
        fname = "costs.csv"
    elif section == "margin":
        m = models.get_margin(season_id, date_from, date_to)
        writer.writerow(["Показатель", "Значение"])
        writer.writerow(["Выручка, ₽", f"{m['revenue']:.2f}"])
        writer.writerow(["Всего расходов, ₽", f"{m['total_cost']:.2f}"])
        writer.writerow(["Прибыль, ₽", f"{m['profit']:.2f}"])
        writer.writerow(["Рентабельность, %", f"{m['margin_pct']:.2f}"])
        fname = "margin.csv"
    elif section == "movement":
        m = models.get_grade_movement(season_id, date_from, date_to)
        writer.writerow(["Сорт", "Принято кг", "Мусор кг", "В сушку кг", "Выход кг",
                         "Продано кг", "Сырьё остаток кг", "Сухой остаток кг"])
        for r in m:
            writer.writerow([r["grade_name"], f"{r['accepted_kg']:.2f}",
                             f"{r['waste_kg']:.2f}", f"{r['drying_raw_kg']:.2f}",
                             f"{r['drying_dry_kg']:.2f}", f"{r['sold_kg']:.2f}",
                             f"{r['raw_stock_kg']:.2f}", f"{r['dry_stock_kg']:.2f}"])
        fname = "movement.csv"
    elif section == "suppliers_eff":
        se = models.get_supplier_efficiency(season_id, date_from, date_to)
        writer.writerow(["Поставщик", "Принято кг", "Выплачено ₽", "Мусор кг", "% мусора", "Записей"])
        for r in se:
            writer.writerow([r["supplier_name"] or "(без имени)",
                             f"{r['accepted_kg']:.2f}", f"{r['paid_amount']:.2f}",
                             f"{r['waste_kg']:.2f}", f"{r['waste_pct']:.2f}", r["deliveries"]])
        fname = "suppliers_eff.csv"
    elif section == "yield":
        y = models.get_yield_trend(season_id, date_from, date_to)
        writer.writerow(["Дата", "Загружено кг", "Получено кг", "Выход %"])
        for r in y:
            writer.writerow([r["date"], f"{r['raw_kg']:.2f}",
                             f"{r['dry_kg']:.2f}", f"{r['yield_pct']:.2f}"])
        fname = "yield.csv"
    elif section == "top":
        t = models.get_top_grades(season_id, date_from, date_to)
        writer.writerow(["Сорт", "Продано кг", "Выручка ₽", "Сделок"])
        for r in t:
            writer.writerow([r["grade_name"], f"{r['sold_kg']:.2f}",
                             f"{r['revenue']:.2f}", r["deals"]])
        fname = "top.csv"
    elif section == "cashflow":
        cf = models.get_cashflow(season_id, date_from, date_to)
        writer.writerow(["Дата", "Приход ₽", "Отток ₽", "Нетто ₽"])
        for r in cf["rows"]:
            writer.writerow([r["date"], f"{r['inflow']:.2f}",
                             f"{r['outflow']:.2f}", f"{r['net']:.2f}"])
        writer.writerow([])
        writer.writerow(["ИТОГО", f"{cf['inflow_total']:.2f}",
                         f"{cf['outflow_total']:.2f}", f"{cf['net_total']:.2f}"])
        fname = "cashflow.csv"

    data = buf.getvalue()
    season_name = season["name"].replace(" ", "_")
    stamp = date.today().isoformat()
    return Response(
        data,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "Content-Language": "ru",
        },
    )


# --- Запуск -------------------------------------------------------------------

def main():
    init_db()
    with app.app_context():
        seed_if_empty()
    print("=" * 60)
    print(" Учёт грибов — локальный запуск")
    print(" Откройте в браузере: http://127.0.0.1:5000")
    print(" С телефона в той же WiFi: http://<IP-этого-ПК>:5000")
    print("=" * 60)
    # debug=False чтобы не было reload-проблем; use_reloader=False
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


# --- Кастомные ошибки ---------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


if __name__ == "__main__":
    main()
