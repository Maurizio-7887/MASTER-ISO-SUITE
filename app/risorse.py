"""Risorse: gestione delle persone che accedono al programma (nome, PIN,
ruolo) - operatori e amministratori."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from .extensions import db
from .models import User

risorse_bp = Blueprint("risorse", __name__, url_prefix="/risorse")


def _owner_only():
    if not current_user.is_owner:
        abort(403)


@risorse_bp.route("/")
@login_required
def elenco():
    _owner_only()
    persone = User.query.order_by(User.active.desc(), User.role.desc(), User.name).all()
    return render_template("risorse/elenco.html", persone=persone)


@risorse_bp.post("/nuova")
@login_required
def nuova_persona():
    _owner_only()
    nome = request.form.get("name", "").strip()
    pin = request.form.get("pin", "").strip()
    ruolo = request.form.get("role", "operator").strip()
    if not nome or not pin:
        flash("Indica nome e PIN.", "error")
        return redirect(url_for("risorse.elenco"))
    if User.query.filter_by(pin=pin).first():
        flash(f"Il PIN \"{pin}\" è già usato da un'altra persona.", "error")
        return redirect(url_for("risorse.elenco"))
    db.session.add(User(name=nome, pin=pin, role=ruolo, active=True))
    db.session.commit()
    flash(f"{nome} aggiunto/a con PIN {pin}.", "success")
    return redirect(url_for("risorse.elenco"))


@risorse_bp.post("/<int:user_id>/modifica")
@login_required
def modifica_persona(user_id):
    _owner_only()
    persona = db.get_or_404(User, user_id)
    nome = request.form.get("name", "").strip()
    pin = request.form.get("pin", "").strip()
    ruolo = request.form.get("role", persona.role).strip()
    if not nome or not pin:
        flash("Indica nome e PIN.", "error")
        return redirect(url_for("risorse.elenco"))
    altro_con_stesso_pin = User.query.filter(User.pin == pin, User.id != persona.id).first()
    if altro_con_stesso_pin:
        flash(f"Il PIN \"{pin}\" è già usato da {altro_con_stesso_pin.name}.", "error")
        return redirect(url_for("risorse.elenco"))
    persona.name = nome
    persona.pin = pin
    persona.role = ruolo
    db.session.commit()
    flash(f"{persona.name} aggiornato/a.", "success")
    return redirect(url_for("risorse.elenco"))


@risorse_bp.post("/<int:user_id>/attiva-disattiva")
@login_required
def attiva_disattiva_persona(user_id):
    _owner_only()
    persona = db.get_or_404(User, user_id)
    if persona.id == current_user.id:
        flash("Non puoi disattivare il tuo stesso account.", "error")
        return redirect(url_for("risorse.elenco"))
    persona.active = not persona.active
    db.session.commit()
    flash(f"{persona.name} {'riattivato/a' if persona.active else 'disattivato/a'}.", "success")
    return redirect(url_for("risorse.elenco"))
