from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from ..models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def safe_next(value):
    return value if value and value.startswith("/") and not value.startswith("//") else None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = safe_next(request.values.get("next"))
    if current_user.is_authenticated:
        return redirect(next_url or (url_for("home")))
    if request.method == "POST":
        user = User.query.filter_by(pin=request.form.get("pin", ""), active=True).first()
        if user:
            login_user(user)
            return redirect(next_url or (url_for("home")))
        flash("PIN non riconosciuto.", "error")
    return render_template("auth/login.html", next_url=next_url)


@auth_bp.post("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
