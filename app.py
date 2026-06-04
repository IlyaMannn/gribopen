"""Flask-приложение: маршруты, маршрутизация, запуск."""
from datetime import date, datetime
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, abort,
)
from db import init_db, get_db, close_db
from auth import (
    login_user, logout_user, current_user, login_required,
    verify_password, change_password,
)
from seed import seed_if_empty, has_active_season, get_active_season, create_season
import models


app = Flask(__name__)
app.config["SECRET_KEY"] = "mushroom-local-dev-secret-change-me"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30  # 30 дней
app.config["JSON_AS_ASCII"] = False

# Инициализируем БД и сидируем данные при загрузке модуля,
# чтобы это работало и при запуске, и при импорте в тестах.
init_db()
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
    accepted_today_kg = sum(r["weight_kg"] for r in today_rows)
    accepted_today_amount = sum(r["total_amount"] for r in today_rows)
    today_drying = models.get_drying_kg_by_date(today, season_id)
    waste_today = models.get_waste_kg_by_date(today, season_id)
    waste_pct_today = (waste_today / accepted_today_kg * 100) if accepted_today_kg > 0 else 0.0
    today_sales = models.get_sales_kg_by_date(today, season_id)
    today_expenses = models.get_expenses_by_date(today, season_id)

    return render_template(
        "home.html",
        grades=grades,
        raw_stock=raw_stock,
        dry_stock=dry_stock,
        season_totals=season_totals,
        season_yield=season_yield,
        season_sales=season_sales,
        season_expenses=season_expenses,
        accepted_today_kg=accepted_today_kg,
        accepted_today_amount=accepted_today_amount,
        today_drying=today_drying,
        waste_today=waste_today,
        waste_pct_today=waste_pct_today,
        today_sales=today_sales,
        today_expenses=today_expenses,
        today=today,
    )


@app.route("/settings", methods=["GET"])
@login_required
def settings():
    return render_template("settings.html")


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

        added = 0
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
                models.add_acceptance(form_date, season_id, g["id"], w, p, supplier_id, notes)
                added += 1

        if added:
            flash(f"Сохранено записей: {added}", "ok")
        else:
            flash("Не введено ни одного значения веса", "err")
        return redirect(url_for("acceptance"))

    # GET
    selected_date = request.args.get("date") or today
    rows = models.list_acceptance_for_date(selected_date, season_id)
    latest_prices = models.latest_prices_dict(selected_date)
    raw_stock = models.get_raw_stock(season_id)

    return render_template(
        "acceptance.html",
        grades=grades,
        suppliers=suppliers,
        today=today,
        selected_date=selected_date,
        rows=rows,
        latest_prices=latest_prices,
        raw_stock=raw_stock,
    )


@app.route("/acceptance/<int:record_id>/delete", methods=["POST"])
@login_required
def acceptance_delete(record_id):
    models.delete_acceptance(record_id)
    flash("Запись удалена", "ok")
    return redirect(request.referrer or url_for("acceptance"))


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
    raw_stock = models.get_raw_stock(season_id)

    if request.method == "POST":
        form_date = request.form.get("date") or today
        raw_by_grade = {g["id"]: _parse_kg(request.form.get(f"raw_{g['id']}")) for g in grades}
        dry_by_grade = {g["id"]: _parse_kg(request.form.get(f"dry_{g['id']}")) for g in grades}
        cost_el = _parse_kg(request.form.get("cost_electricity"))
        cost_wt = _parse_kg(request.form.get("cost_water"))
        cost_fw = _parse_kg(request.form.get("cost_firewood"))
        cost_lb = _parse_kg(request.form.get("cost_labor"))
        notes = request.form.get("notes") or ""

        # Валидация: должен быть хотя бы один заполненный сорт
        total_raw = sum(raw_by_grade.values())
        total_dry = sum(dry_by_grade.values())
        if total_raw <= 0 and total_dry <= 0:
            flash("Не введено ни одного значения", "err")
            return redirect(url_for("drying"))

        # Валидация: нельзя загрузить больше сырья, чем есть на остатке
        over = []
        for g in grades:
            if raw_by_grade[g["id"]] > raw_stock[g["id"]] + 0.001:
                over.append(f"{g['display_name']}: {raw_by_grade[g['id']]:.2f} > остаток {raw_stock[g['id']]:.2f}")
        if over:
            flash("Недостаточно сырья: " + "; ".join(over), "err")
            return redirect(url_for("drying"))

        # Валидация: сухого не может быть больше сырья
        for g in grades:
            r = raw_by_grade[g["id"]]
            d = dry_by_grade[g["id"]]
            if d > r + 0.001:
                flash(f"{g['display_name']}: получено {d:.2f} кг > загружено {r:.2f} кг", "err")
                return redirect(url_for("drying"))

        models.add_drying_run(
            form_date, season_id,
            raw_by_grade, dry_by_grade,
            cost_el, cost_wt, cost_fw, cost_lb, notes,
        )
        flash("Запись сушки сохранена", "ok")
        return redirect(url_for("drying"))

    # GET
    selected_date = request.args.get("date") or today
    runs = models.list_drying_runs_for_date(selected_date, season_id)
    season_yield = models.get_drying_yield_season(season_id)
    return render_template(
        "drying.html",
        grades=grades,
        today=today,
        selected_date=selected_date,
        raw_stock=raw_stock,
        runs=runs,
        season_yield=season_yield,
    )


@app.route("/drying/<int:run_id>/delete", methods=["POST"])
@login_required
def drying_delete(run_id):
    models.delete_drying_run(run_id)
    flash("Запись сушки удалена", "ok")
    return redirect(request.referrer or url_for("drying"))


# --- Мусор --------------------------------------------------------------------

@app.route("/waste", methods=["GET", "POST"])
@login_required
def waste():
    season = get_active_season()
    if season is None:
        return redirect(url_for("first_run"))
    season_id = season["id"]
    today = date.today().isoformat()

    if request.method == "POST":
        form_date = request.form.get("date") or today
        w = _parse_kg(request.form.get("weight_kg"))
        if w <= 0:
            flash("Введите вес больше 0", "err")
            return redirect(url_for("waste"))
        models.add_waste_record(form_date, season_id, w)
        flash(f"Записан мусор: {w:.2f} кг", "ok")
        return redirect(url_for("waste"))

    # GET
    selected_date = request.args.get("date") or today
    rows = models.list_waste_records_for_date(selected_date, season_id)
    accepted_today = models.get_accepted_kg_by_date(selected_date, season_id)
    waste_today = models.get_waste_kg_by_date(selected_date, season_id)
    waste_pct = (waste_today / accepted_today * 100) if accepted_today > 0 else 0.0
    waste_total_season = models.get_waste_total_season(season_id)
    accepted_total_season = models.get_raw_stock_total_season(season_id)["total_kg"]
    waste_pct_season = (waste_total_season / accepted_total_season * 100) if accepted_total_season > 0 else 0.0

    return render_template(
        "waste.html",
        today=today,
        selected_date=selected_date,
        rows=rows,
        accepted_today=accepted_today,
        waste_today=waste_today,
        waste_pct=waste_pct,
        waste_total_season=waste_total_season,
        accepted_total_season=accepted_total_season,
        waste_pct_season=waste_pct_season,
    )


@app.route("/waste/<int:record_id>/delete", methods=["POST"])
@login_required
def waste_delete(record_id):
    models.delete_waste_record(record_id)
    flash("Запись удалена", "ok")
    return redirect(request.referrer or url_for("waste"))


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
        try:
            grade_id = int(request.form.get("grade_id") or 0)
        except ValueError:
            grade_id = 0
        w = _parse_kg(request.form.get("weight_kg"))
        p = _parse_kg(request.form.get("price_per_kg"))

        if grade_id <= 0 or w <= 0 or p < 0:
            flash("Заполните сорт, вес и цену", "err")
            return redirect(url_for("sales"))
        if w > dry_stock.get(grade_id, 0) + 0.001:
            gname = next((g["display_name"] for g in grades if g["id"] == grade_id), "?")
            flash(f"Недостаточно сухого {gname}: остаток {dry_stock.get(grade_id, 0):.2f} кг, продаёте {w:.2f}", "err")
            return redirect(url_for("sales"))

        models.add_sale(form_date, season_id, buyer_id, grade_id, w, p)
        flash(f"Продажа записана: {w:.2f} кг · {w*p:.2f} ₽", "ok")
        return redirect(url_for("sales"))

    # GET
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


# --- Заглушки остальных разделов ----------------------------------------------

PLACEHOLDERS = {
    "seasons": ("Сезоны", 5),
    "reports": ("Отчёты", 6),
}


@app.route("/seasons")
@login_required
def seasons():
    return render_template("placeholder.html", title=PLACEHOLDERS["seasons"][0],
                           stage=PLACEHOLDERS["seasons"][1])


@app.route("/reports")
@login_required
def reports():
    return render_template("placeholder.html", title=PLACEHOLDERS["reports"][0],
                           stage=PLACEHOLDERS["reports"][1])


# --- Запуск -------------------------------------------------------------------

def main():
    init_db()
    with app.app_context():
        seed_if_empty()
    print("=" * 60)
    print(" Учёт грибов — локальный запуск")
    print(" Откройте в браузере: http://127.0.0.1:5000")
    print(" С телефона в той же WiFi: http://<IP-этого-ПК>:5000")
    print(" Логин: admin   Пароль: admin")
    print("=" * 60)
    # debug=False чтобы не было reload-проблем; use_reloader=False
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
