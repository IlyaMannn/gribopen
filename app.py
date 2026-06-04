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
    season_totals = models.get_raw_stock_total_season(season_id)

    # Итоги за сегодня
    today = date.today().isoformat()
    today_rows = models.list_acceptance_for_date(today, season_id)
    accepted_today_kg = sum(r["weight_kg"] for r in today_rows)
    accepted_today_amount = sum(r["total_amount"] for r in today_rows)

    return render_template(
        "home.html",
        grades=grades,
        raw_stock=raw_stock,
        season_totals=season_totals,
        accepted_today_kg=accepted_today_kg,
        accepted_today_amount=accepted_today_amount,
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
    return render_template(
        "directories.html",
        grades=grades,
        prices=prices,
        suppliers=suppliers,
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


# --- Заглушки остальных разделов ----------------------------------------------

PLACEHOLDERS = {
    "drying": ("Сушка", 3),
    "waste": ("Мусор и отходы", 3),
    "sales": ("Продажа", 4),
    "expenses": ("Расходы", 4),
    "seasons": ("Сезоны", 5),
    "reports": ("Отчёты", 6),
}


@app.route("/drying")
@login_required
def drying():
    return render_template("placeholder.html", title=PLACEHOLDERS["drying"][0],
                           stage=PLACEHOLDERS["drying"][1])


@app.route("/waste")
@login_required
def waste():
    return render_template("placeholder.html", title=PLACEHOLDERS["waste"][0],
                           stage=PLACEHOLDERS["waste"][1])


@app.route("/sales")
@login_required
def sales():
    return render_template("placeholder.html", title=PLACEHOLDERS["sales"][0],
                           stage=PLACEHOLDERS["sales"][1])


@app.route("/expenses")
@login_required
def expenses():
    return render_template("placeholder.html", title=PLACEHOLDERS["expenses"][0],
                           stage=PLACEHOLDERS["expenses"][1])


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
