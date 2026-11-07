"""Laboratori ISO 56002 / 56001 nativi Flask.

Ispirati a funzionalità concettuali viste in OpenideaL, Gate Signal e ISO 9001 SDK.
Nessuna libreria dei progetti di terzi è importata o copiata. Le valutazioni sono
decisioni formative, non verifiche di conformità né approvazioni automatiche.
"""
import hmac
import secrets
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import (
    InnovationChallenge, InnovationChallengeIdea, InnovationCorrectiveAction,
    InnovationGateReview, InnovationIdea, InnovationProject,
)

innovation_lab_bp = Blueprint("innovation_lab", __name__, url_prefix="/innovazione/lab")

# Modello DIDATTICO autonomo: pesi fissi, scala 0-5, solidità della prova 0-3.
# Non corrisponde a punteggi prescritti dalla ISO 56001.
CRITERIA = (
    ("fit", "Coerenza con la strategia", 30),
    ("value", "Valore atteso per gli stakeholder", 30),
    ("feasibility", "Fattibilità tecnica e organizzativa", 25),
    ("finance", "Sostenibilità finanziaria", 15),
)
KINDS = {
    "non_conformita": "Non conformità del sistema (con requisito ed evidenza)",
    "miglioramento": "Opportunità di miglioramento",
    "apprendimento": "Esito sperimentale / lezione appresa (non automaticamente NC)",
}


def _owner():
    if not current_user.is_owner:
        abort(403)


def _token():
    if "_innovation_lab_csrf" not in session:
        session["_innovation_lab_csrf"] = secrets.token_urlsafe(24)
    return session["_innovation_lab_csrf"]


def _verify():
    sent = request.form.get("_csrf", "")
    if not sent or not hmac.compare_digest(sent, _token()):
        abort(400, "Modulo scaduto. Ricaricare la pagina.")


def _decimal(value):
    try:
        val = Decimal((value or "").replace(",", "."))
    except (ValueError, InvalidOperation):
        return None
    if not val.is_finite() or val < 0 or val > 1000000000:
        return None
    return val


def _date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _int_range(value, lo, hi):
    try:
        number = int(value)
    except (ValueError, TypeError):
        return None
    return number if lo <= number <= hi else None


def evaluate_criteria(rows, rationale, next_experiment, max_commitment, next_review):
    """Pure calculation: documented preference != proof != human approval.

    Each input dict: key, score 0-5, evidence 0-3, must_pass, threshold 0-5.
    """
    if not (rationale and next_experiment and max_commitment is not None and next_review):
        raise ValueError("Motivazione, prossimo esperimento, limite di spesa e data riesame sono obbligatori.")
    by_key = {r["key"]: r for r in rows}
    if len(rows) != len(CRITERIA) or len(by_key) != len(CRITERIA):
        raise ValueError("Tutti i criteri devono essere valutati.")
    score = 0.0
    coverage = 0.0
    blocks = []
    for key, label, weight in CRITERIA:
        r = by_key.get(key)
        if not r or type(r["score"]) is not int or not 0 <= r["score"] <= 5:
            raise ValueError("Punteggio non valido: " + label)
        if type(r["evidence"]) is not int or not 0 <= r["evidence"] <= 3:
            raise ValueError("Solidità dell'evidenza non valida: " + label)
        if type(r["threshold"]) is not int or not 0 <= r["threshold"] <= 5:
            raise ValueError("Soglia non valida: " + label)
        score += weight * r["score"] / 500
        coverage += weight * r["evidence"] / 300
        if r["must_pass"] and r["score"] < r["threshold"]:
            blocks.append(label)
    if blocks:
        recommendation = "stop_istruttoria"
    elif coverage < 0.50:
        recommendation = "integra_evidenze"
    elif score < 0.60:
        recommendation = "riprogetta"
    else:
        recommendation = "valutabile"
    return round(score, 3), round(coverage, 3), blocks, recommendation


@innovation_lab_bp.route("/")
@login_required
def index():
    _owner()
    sfide = InnovationChallenge.query.order_by(InnovationChallenge.created_at.desc()).all()
    progetti = InnovationProject.query.order_by(InnovationProject.created_at.desc()).all()
    recensioni = InnovationGateReview.query.order_by(InnovationGateReview.created_at.desc()).limit(12).all()
    azioni = InnovationCorrectiveAction.query.order_by(InnovationCorrectiveAction.created_at.desc()).all()
    by_horizon = Counter(p.horizon for p in progetti if p.status in ("attivo", "sospeso"))
    budget = sum(Decimal(str(p.budget or 0)) for p in progetti if p.status in ("attivo", "sospeso"))
    return render_template(
        "innovazione/lab.html", token=_token(), sfide=sfide, progetti=progetti,
        recensioni=recensioni, azioni=azioni, criteria=CRITERIA, kinds=KINDS,
        budget=budget, by_horizon=by_horizon,
    )


@innovation_lab_bp.post("/sfida")
@login_required
def crea_sfida():
    _owner(); _verify()
    title = request.form.get("title", "").strip()
    question = request.form.get("question", "").strip()
    goal = request.form.get("strategic_goal", "").strip()
    owner = request.form.get("owner", "").strip()
    if min(len(title), len(question), len(goal), len(owner)) < 5:
        flash("Completa titolo, domanda, obiettivo strategico e responsabile.", "error")
        return redirect(url_for(".index"))
    deadline = _date(request.form.get("deadline"))
    if request.form.get("deadline") and not deadline:
        abort(400)
    db.session.add(InnovationChallenge(title=title[:180], question=question[:1500],
        strategic_goal=goal[:250], owner=owner[:120], audience="dipendenti",
        deadline=deadline))
    db.session.commit()
    flash("Sfida di innovazione aperta.", "success")
    return redirect(url_for(".index"))


@innovation_lab_bp.post("/sfida/<int:challenge_id>/idea")
@login_required
def associa_idea(challenge_id):
    """Collegare un'idea esistente al challenge senza ri-copiare la proposta."""
    _owner(); _verify()
    ch = db.get_or_404(InnovationChallenge, challenge_id)
    idea_id = _int_range(request.form.get("idea_id"), 1, 100000000)
    idea = db.session.get(InnovationIdea, idea_id) if idea_id else None
    if ch.status != "aperta" or not idea or InnovationChallengeIdea.query.filter_by(idea_id=idea.id).first():
        flash("Idea non trovata, sfida chiusa o idea già associata.", "error")
        return redirect(url_for(".index"))
    db.session.add(InnovationChallengeIdea(challenge_id=ch.id, idea_id=idea.id))
    db.session.commit()
    flash("Idea collegata alla sfida.", "success")
    return redirect(url_for(".index"))


@innovation_lab_bp.route("/gate/<int:project_id>", methods=["GET", "POST"])
@login_required
def valuta_gate(project_id):
    _owner()
    project = db.get_or_404(InnovationProject, project_id)
    if request.method == "POST":
        _verify()
        rows = []
        for key, name, weight in CRITERIA:
            score = _int_range(request.form.get("score_" + key), 0, 5)
            evidence = _int_range(request.form.get("evidence_" + key), 0, 3)
            threshold = _int_range(request.form.get("threshold_" + key), 0, 5)
            if score is None or evidence is None or threshold is None:
                abort(400, "Scoring, prove o soglie non valide.")
            rows.append(dict(key=key, score=score, evidence=evidence,
                threshold=threshold, must_pass=request.form.get("must_" + key) == "on",
                source=request.form.get("source_" + key, "").strip()[:400]))
        limit = _decimal(request.form.get("max_commitment"))
        next_date = _date(request.form.get("next_review"))
        rationale = request.form.get("rationale", "").strip()[:1500]
        experiment = request.form.get("next_experiment", "").strip()[:1000]
        if len(rationale) < 20 or len(experiment) < 20:
            flash("Motiva la decisione e descrivi il prossimo esperimento in almeno 20 caratteri.", "error")
            return redirect(url_for(".valuta_gate", project_id=project_id))
        if limit is None or not next_date:
            abort(400, "Limite economico o data di riesame non validi.")
        if any(row["evidence"] and not row["source"] for row in rows):
            flash("Ogni evidenza con punteggio positivo richiede una fonte o un limite documentato.", "error")
            return redirect(url_for(".valuta_gate", project_id=project_id))
        score, coverage, blocks, recommendation = evaluate_criteria(rows, rationale, experiment, limit, next_date)
        db.session.add(InnovationGateReview(
            project_id=project.id, stage=project.stage, assessor=current_user.name,
            criteria=rows, score=score, evidence_coverage=coverage,
            hard_blocks=blocks, recommendation=recommendation, rationale=rationale,
            next_experiment=experiment, max_commitment=limit, next_review=next_date,
        ))
        db.session.commit()
        flash("Analisi del gate salvata: la decisione operativa rimane al responsabile.", "success")
        return redirect(url_for(".valuta_gate", project_id=project.id))
    reports = InnovationGateReview.query.filter_by(project_id=project.id).order_by(InnovationGateReview.id.desc()).all()
    return render_template("innovazione/gate_review.html", project=project, reports=reports,
                           criteria=CRITERIA, token=_token())


@innovation_lab_bp.post("/azione")
@login_required
def nuova_azione():
    _owner(); _verify()
    kind = request.form.get("kind", "")
    issue = request.form.get("issue", "").strip()
    cause = request.form.get("cause", "").strip()
    action = request.form.get("action", "").strip()
    source = request.form.get("source", "").strip()
    owner = request.form.get("owner", "").strip()
    due_date = _date(request.form.get("due_date"))
    if kind not in KINDS or min(map(len, (issue, cause, action, source, owner))) < 8 or not due_date:
        flash("Indica tipo, origine, descrizione, causa, attività, responsabile e scadenza.", "error")
        return redirect(url_for(".index"))
    db.session.add(InnovationCorrectiveAction(kind=kind, issue=issue[:1500],
        cause=cause[:1000], action=action[:1000], source=source[:150],
        owner=owner[:120], due_date=due_date))
    db.session.commit()
    flash("Azione registrata.", "success")
    return redirect(url_for(".index"))


@innovation_lab_bp.post("/azione/<int:action_id>/chiudi")
@login_required
def chiudi_azione(action_id):
    _owner(); _verify()
    entry = db.get_or_404(InnovationCorrectiveAction, action_id)
    effectiveness = request.form.get("effectiveness", "").strip()
    if len(effectiveness) < 20:
        flash("Per chiudere l'azione occorre una verifica di efficacia descrittiva.", "error")
        return redirect(url_for(".index"))
    if entry.status != "aperta":
        abort(400)
    entry.status = "chiusa_verificata"
    entry.effectiveness = effectiveness[:1500]
    db.session.commit()
    flash("Azione chiusa con evidenza di efficacia.", "success")
    return redirect(url_for(".index"))
