"""Аутентификация: хеширование пароля, декоратор login_required, логин/логаут."""
from functools import wraps
from flask import session, redirect, url_for, request, flash
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db


def hash_password(plain: str) -> str:
    return generate_password_hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return check_password_hash(hashed, plain)


def login_user(user_id: int, username: str):
    """Установить сессию."""
    session.clear()
    session["user_id"] = user_id
    session["username"] = username
    session.permanent = True


def logout_user():
    session.clear()


def current_user():
    """Вернуть dict с данными текущего пользователя или None."""
    if "user_id" not in session:
        return None
    db = get_db()
    row = db.execute(
        "SELECT id, username FROM user WHERE id = ?", (session["user_id"],)
    ).fetchone()
    return dict(row) if row else None


def login_required(f):
    """Декоратор: требует залогиненного пользователя."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def change_password(user_id: int, old_password: str, new_password: str) -> str | None:
    """
    Сменить пароль. Возвращает None при успехе, иначе текст ошибки.
    """
    if not new_password or len(new_password) < 3:
        return "Новый пароль слишком короткий (минимум 3 символа)"
    db = get_db()
    row = db.execute(
        "SELECT password_hash FROM user WHERE id = ?", (user_id,)
    ).fetchone()
    if not row:
        return "Пользователь не найден"
    if not verify_password(old_password, row["password_hash"]):
        return "Текущий пароль введён неверно"
    db.execute(
        "UPDATE user SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user_id),
    )
    db.commit()
    return None
