from datetime import datetime, date
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from .extensions import db
from .models import QualityObjective, QualityAction, QualityRisk

quality_objectives_bp = Blueprint("quality_objectives", __name__, url_prefix="/obiettivi-qualita")


def owner_only():
    if not current_user.is_owner:
        abort(403)


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@quality_objectives_bp.route("/")
@login_required
def index():
    owner_only()
    anno_corrente = date.today().year
    anno = request.args.get("anno", type=int) or anno_corrente
    anni_disponibili = sorted({o.year for o in QualityObjective.query.all()} | {anno_corrente}, reverse=True)
    obiettivi = QualityObjective.query.filter_by(year=anno).order_by(QualityObjective.process, QualityObjective.indicator_name).all()
    rischi_contesto = QualityRisk.query.filter_by(objective_id=None, year=anno).order_by(QualityRisk.id.desc()).all()
    return render_template("quality_objectives/index.html", obiettivi=obiettivi, anno=anno,
                           anni_disponibili=anni_disponibili, oggi=date.today(), rischi_contesto=rischi_contesto)


@quality_objectives_bp.post("/nuovo")
@login_required
def create():
    owner_only()
    obiettivo = QualityObjective(
        year=request.form.get("year", type=int) or date.today().year,
        indicator_name=request.form.get("indicator_name", "").strip(),
        process=request.form.get("process", "").strip() or None,
        frequency=request.form.get("frequency", "").strip() or None,
        target_value=request.form.get("target_value", "").strip() or None,
        unit=request.form.get("unit", "").strip() or None,
        responsible=request.form.get("responsible", "").strip() or None,
        notes=request.form.get("notes", "").strip() or None,
        policy_alignment=request.form.get("policy_alignment", "").strip() or None,
    )
    if not obiettivo.indicator_name:
        flash("Serve almeno il nome dell'indicatore.", "error")
        return redirect(url_for("quality_objectives.index", anno=obiettivo.year))
    db.session.add(obiettivo)
    db.session.commit()
    flash("Obiettivo creato.", "success")
    return redirect(url_for("quality_objectives.detail", objective_id=obiettivo.id))


@quality_objectives_bp.route("/<int:objective_id>")
@login_required
def detail(objective_id):
    owner_only()
    obiettivo = db.get_or_404(QualityObjective, objective_id)
    return render_template("quality_objectives/detail.html", o=obiettivo, oggi=date.today())


@quality_objectives_bp.post("/<int:objective_id>/aggiorna")
@login_required
def update(objective_id):
    owner_only()
    o = db.get_or_404(QualityObjective, objective_id)
    o.status = request.form.get("status", o.status)
    o.responsible = request.form.get("responsible", "").strip() or None
    o.target_value = request.form.get("target_value", "").strip() or None
    o.q1_consuntivo = request.form.get("q1_consuntivo", "").strip() or None
    o.h1_consuntivo = request.form.get("h1_consuntivo", "").strip() or None
    o.ninemonths_consuntivo = request.form.get("ninemonths_consuntivo", "").strip() or None
    o.year_consuntivo = request.form.get("year_consuntivo", "").strip() or None
    o.year_analisi = request.form.get("year_analisi", "").strip() or None
    o.py_preventivo = request.form.get("py_preventivo", "").strip() or None
    o.py_consuntivo = request.form.get("py_consuntivo", "").strip() or None
    o.py_analisi = request.form.get("py_analisi", "").strip() or None
    o.notes = request.form.get("notes", "").strip() or None
    o.policy_alignment = request.form.get("policy_alignment", "").strip() or None
    db.session.commit()
    flash("Obiettivo aggiornato.", "success")
    return redirect(url_for("quality_objectives.detail", objective_id=o.id))


@quality_objectives_bp.post("/<int:objective_id>/elimina")
@login_required
def delete(objective_id):
    owner_only()
    o = db.get_or_404(QualityObjective, objective_id)
    db.session.delete(o)
    db.session.commit()
    flash("Obiettivo eliminato.", "success")
    return redirect(url_for("quality_objectives.index", anno=o.year))


@quality_objectives_bp.post("/<int:objective_id>/azioni")
@login_required
def add_action(objective_id):
    owner_only()
    o = db.get_or_404(QualityObjective, objective_id)
    descrizione = request.form.get("description", "").strip()
    if descrizione:
        db.session.add(QualityAction(
            objective_id=o.id, description=descrizione,
            responsible=request.form.get("responsible", "").strip() or None,
            due_date=_parse_date(request.form.get("due_date")),
        ))
        db.session.commit()
        flash("Azione aggiunta.", "success")
    return redirect(url_for("quality_objectives.detail", objective_id=o.id))


@quality_objectives_bp.post("/azioni/<int:action_id>/stato")
@login_required
def update_action(action_id):
    owner_only()
    a = db.get_or_404(QualityAction, action_id)
    a.status = request.form.get("status", a.status)
    db.session.commit()
    return redirect(url_for("quality_objectives.detail", objective_id=a.objective_id))


@quality_objectives_bp.post("/<int:objective_id>/rischi")
@login_required
def add_risk(objective_id):
    owner_only()
    o = db.get_or_404(QualityObjective, objective_id)
    descrizione = request.form.get("description", "").strip()
    if descrizione:
        db.session.add(QualityRisk(
            objective_id=o.id,
            kind=request.form.get("kind", "rischio"),
            description=descrizione,
            probability=request.form.get("probability", type=int) or 1,
            impact=request.form.get("impact", type=int) or 1,
            mitigation=request.form.get("mitigation", "").strip() or None,
        ))
        db.session.commit()
        flash("Voce aggiunta al registro rischi.", "success")
    return redirect(url_for("quality_objectives.detail", objective_id=o.id))


@quality_objectives_bp.post("/rischi/<int:risk_id>/stato")
@login_required
def update_risk(risk_id):
    owner_only()
    r = db.get_or_404(QualityRisk, risk_id)
    r.status = request.form.get("status", r.status)
    r.mitigation = request.form.get("mitigation", r.mitigation)
    db.session.commit()
    if r.objective_id:
        return redirect(url_for("quality_objectives.detail", objective_id=r.objective_id))
    return redirect(url_for("quality_objectives.index", anno=r.year))


@quality_objectives_bp.post("/rischi-contesto/nuovo")
@login_required
def add_context_risk():
    """Rischio/opportunità NON legato a un obiettivo specifico (§4.1/§4.2 e
    §6.1): per i rischi di contesto o legati alle parti interessate che non
    minacciano un singolo KPI ma il sistema nel suo complesso."""
    owner_only()
    anno = request.form.get("year", type=int) or date.today().year
    descrizione = request.form.get("description", "").strip()
    if descrizione:
        db.session.add(QualityRisk(
            objective_id=None, year=anno,
            kind=request.form.get("kind", "rischio"),
            description=descrizione,
            probability=request.form.get("probability", type=int) or 1,
            impact=request.form.get("impact", type=int) or 1,
            mitigation=request.form.get("mitigation", "").strip() or None,
        ))
        db.session.commit()
        flash("Voce aggiunta al registro rischi di contesto.", "success")
    return redirect(url_for("quality_objectives.index", anno=anno))


# Elenco obiettivi cosi' come definiti nel Manuale della Qualita' (Cruscotto
# Obiettivi Qualita'): processo, indicatore, target, frequenza. Caricati una
# sola volta per l'anno corrente al momento del primo avvio dopo il deploy.
OBIETTIVI_DA_MANUALE = [
    ("Direzione", "Ore spese in miglioramento / Ore Direzione", "0,2", "Mensile", None),
    ("Direzione", "Obiettivi raggiunti / Obiettivi proposti", "1,0", "Annuale", None),
    ("Commerciale", "Capacità seminativa (n° offerte)", "≥ 10", "Mensile", None),
    ("Commerciale", "n° contratti / n° offerte", "0,8", "Mensile", None),
    ("Progettazione", "n° GANTT idonei e in tempo / n° GANTT", "1,0", "Mensile", None),
    ("Progettazione", "n° progetti esatti / n° progetti", "1,0", "Mensile", None),
    ("Produzione", "Zero difetti (= zero NC da produzione)", "0", "Mensile", None),
    ("Acquisti", "Zero difetti (= zero NC da fornitori)", "0", "Mensile", None),
    ("Acquisti", "n° NC / n° consegne (DDT)", "0", "Mensile", None),
    ("Risorse Umane", "Ore formazione / n° soci e dipendenti", "≥ 0,006", "Mensile", None),
    ("Altre Risorse", "Ore manutenzione / n° attrezzature", "~35", "Mensile", None),
    ("Altre Risorse", "n° NC per strumenti non tarati", "0", "Mensile", None),
    ("Miglioramento", "RAC + PM aperte", "≥ 2", "Mensile", None),
    ("Miglioramento", "Customer Satisfaction (media ponderata per cliente)", "≥ 8,6", "Annuale",
     "Media ponderata dei voti dei clienti chiave (storicamente: peso 0,6/0,3/0,1 sui tre clienti "
     "principali), calcolata automaticamente dal modulo Obiettivi. Ogni scostamento dal target genera "
     "una segnalazione che alimenta il processo di Miglioramento (§10)."),
]


def seed_objectives_from_manual(anno=None):
    from datetime import date as _date
    anno = anno or _date.today().year
    for processo, indicatore, target, frequenza, note in OBIETTIVI_DA_MANUALE:
        esiste = QualityObjective.query.filter_by(year=anno, process=processo, indicator_name=indicatore).first()
        if esiste:
            continue
        db.session.add(QualityObjective(
            year=anno, process=processo, indicator_name=indicatore,
            target_value=target, frequency=frequenza, notes=note,
        ))
    db.session.commit()
