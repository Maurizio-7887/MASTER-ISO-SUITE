"""Sistema di Gestione Qualità - moduli aggiuntivi:
1) Manutenzione (macchine, piano preventivo, registro interventi)
2) Formazione (corsi, partecipazioni per dipendente)
3) Tarature (registro dispositivi/strumenti e storico controlli)
4) Non conformità con modulo 8D (D1-D8)
5) Pianificazione e report delle verifiche ispettive (audit interni)
6) Riesame della Direzione

Il quinto modulo richiesto originariamente (miglioramento dei processi) usa
già il modulo "Obiettivi Qualità" esistente (QualityObjective/Action/Risk):
non è duplicato qui.

Le pagine di elenco/creazione/modifica sono riservate al proprietario
(owner_only). Le due registrazioni rapide da telefono - manutenzione e
formazione - sono invece aperte a chiunque sia loggato, perché è così che
venivano registrate anche nel programma precedente: dal telefono
dell'operatore, senza dover passare dal gestionale completo.
"""
from collections import OrderedDict
from datetime import datetime, date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import (Machine, MaintenancePlanItem, MaintenanceLog, TrainingCourse, TrainingAttendance,
                     CalibrationDevice, CalibrationRecord, NonConformity8D, AuditPlanItem,
                     ManagementReview, ManagementReviewActionItem, ManagementReviewSection,
                     ManagementReviewSectionAttachment, User, AuditReport, AuditReportFinding, AuditReportAttachment,
                     SourceDocument, TrainingSession, EmployeeTrainingGap, Qualification,
                     PolyvalenceMatrix, PolyvalenceColumn, PolyvalenceEntry, PolyvalenceEmployee, TrainingEmployee,
                     PianoFormazioneOverride)
from .audit_iso_clauses import PUNTI_ISO_9001

# I punti del Riesame della Direzione (formato del modulo di riesame): per ognuno
# l'ispettore vuole un'analisi della situazione (cosa va bene / cosa non va)
# e gli allegati a supporto. Una riga ManagementReviewSection per punto e per
# riesame viene creata automaticamente la prima volta che si apre il dettaglio.
SEZIONI_RIESAME = [
    ("risk_management", "Sistema Risk Management – Risk Based Thinking (linee di indirizzo e verifica dell'anno precedente)"),
    ("quality_policy", "Verifica Politica della Qualità"),
    ("improvement_dev", "Attività di sviluppo e miglioramento del Sistema Qualità"),
    ("internal_audit", "Sintesi dei risultati delle verifiche ispettive interne"),
    ("certification_audit", "Sintesi dei risultati delle verifiche ispettive degli Enti di Certificazione"),
    ("complaints", "Analisi reclami clienti / lavoratori / stakeholders e rilevazione soddisfazione clienti"),
    ("nonconformities", "Analisi delle non conformità riscontrate"),
    ("injuries", "Analisi infortuni"),
    ("training", "Formazione ed addestramento erogata"),
    ("suppliers", "Valutazione fornitori"),
    ("indicators", "Analisi adeguatezza indicatori Sistema Qualità"),
    ("previous_review", "Aspetti di riesami precedenti"),
]

# Corrispondenza col vecchio campo testo libero su ManagementReview (compilato
# prima dell'introduzione delle sezioni strutturate): serve solo per non
# perdere quanto già scritto, migrandolo una tantum in "cosa va bene" alla
# prima creazione della sezione.
_CAMPO_LEGACY_PER_SEZIONE = {
    "risk_management": "risk_management_notes",
    "quality_policy": "quality_policy_review",
    "improvement_dev": "improvement_development_notes",
    "internal_audit": "internal_audit_summary",
    "certification_audit": "certification_audit_summary",
    "complaints": "complaints_analysis",
    "nonconformities": "nonconformities_analysis",
    "injuries": "injuries_analysis",
    "training": "training_analysis",
    "suppliers": "suppliers_evaluation",
    "indicators": "indicators_adequacy",
    "previous_review": "previous_review_followup",
}


def _ensure_review_sections(review):
    """Crea le sezioni standard mancanti per questo riesame (idempotente:
    non tocca mai una sezione già esistente). Se il riesame ha ancora dati
    nel vecchio campo testo libero (compilati prima di questa funzionalità)
    li recupera in automatico come punto di partenza di 'cosa va bene'."""
    esistenti = {s.section_key for s in review.sections}
    mancanti = [(chiave, titolo) for chiave, titolo in SEZIONI_RIESAME if chiave not in esistenti]
    if not mancanti:
        return
    for i, (chiave, titolo) in enumerate(mancanti, start=len(esistenti) + 1):
        testo_legacy = getattr(review, _CAMPO_LEGACY_PER_SEZIONE.get(chiave, ""), None)
        db.session.add(ManagementReviewSection(review_id=review.id, section_key=chiave, title=titolo,
                                                sort_order=i, positives_text=testo_legacy))
    db.session.commit()

sgq_bp = Blueprint("sgq", __name__, url_prefix="/sistema-qualita")

# Etichette leggibili per il tipo di intervento di manutenzione (usate sia in
# fase di registrazione dal form che per la visualizzazione nel registro).
TIPO_MANUTENZIONE_LABEL = {
    "programmata": "Manutenzione programmata",
    "guasto": "Guasto",
    "straordinaria": "Straordinaria",
    "ispezione": "Ispezione",
}

# Reparti che, se presenti, vanno mostrati per primi e in quest'ordine; gli
# altri reparti trovati sui dati reali seguono in ordine alfabetico.
ORDINE_REPARTI_MANUTENZIONE = ["ESTERNO", "INTERNO"]

# Palette colori del sito (vedi variabili CSS in app.css) usata per accentare
# le card macchina in base alla categoria, senza dover assegnare colori a mano.
CATEGORY_COLOR_PALETTE = ["var(--cyan)", "var(--orange)", "var(--green)", "var(--navy-2)", "var(--red)"]


def colore_categoria(category):
    if not category:
        return "var(--muted)"
    idx = sum(ord(ch) for ch in category) % len(CATEGORY_COLOR_PALETTE)
    return CATEGORY_COLOR_PALETTE[idx]


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


def _parse_decimal(value):
    value = (value or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


@sgq_bp.route("/")
@login_required
def index():
    owner_only()
    oggi = date.today()
    nc_aperte = NonConformity8D.query.filter_by(status="aperta").order_by(NonConformity8D.opened_at.desc()).all()
    audit_pianificati = AuditPlanItem.query.filter_by(status="pianificata").order_by(AuditPlanItem.planned_date).limit(8).all()
    return render_template("sgq/index.html", oggi=oggi, nc_aperte=nc_aperte, audit_pianificati=audit_pianificati,
                           n_nc_aperte=len(nc_aperte))


# ============================================================ MANUTENZIONE ==

@sgq_bp.route("/manutenzione")
@login_required
def manutenzione():
    owner_only()
    macchine = Machine.query.order_by(Machine.active.desc(), Machine.area, Machine.name).all()

    macchine_per_reparto = OrderedDict()
    aree_presenti = sorted({m.area for m in macchine if m.area})
    aree_ordinate = [a for a in ORDINE_REPARTI_MANUTENZIONE if a in aree_presenti] + \
                     [a for a in aree_presenti if a not in ORDINE_REPARTI_MANUTENZIONE]
    for area in aree_ordinate:
        macchine_per_reparto[area] = [m for m in macchine if m.area == area]
    senza_reparto = [m for m in macchine if not m.area]
    if senza_reparto:
        macchine_per_reparto["SENZA REPARTO"] = senza_reparto

    categorie = sorted({m.category for m in macchine if m.category})

    # Tabella di piano (stile Excel): una riga per ogni voce di piano attiva,
    # con la settimana di scadenza e - pescati dagli interventi REALI
    # registrati nella pagina "Registro interventi" - se e quando quella
    # voce e' stata eseguita l'ultima volta e da chi (collegamento tramite
    # MaintenanceLog.plan_item_id, valorizzato quando l'operatore sceglie
    # "Voce di piano" in fase di registrazione).
    piano_item_ids = [p.id for m in macchine for p in m.plan_items if p.active]
    ultimo_log_per_piano = {}
    if piano_item_ids:
        log_collegati = (MaintenanceLog.query
                         .filter(MaintenanceLog.plan_item_id.in_(piano_item_ids))
                         .order_by(MaintenanceLog.performed_at.desc()).all())
        for l in log_collegati:
            if l.plan_item_id not in ultimo_log_per_piano:
                ultimo_log_per_piano[l.plan_item_id] = l  # il primo incontrato e' il piu' recente

    righe_piano = []
    for m in macchine:
        for p in m.plan_items:
            if not p.active:
                continue
            ultimo = ultimo_log_per_piano.get(p.id)
            if p.next_due:
                anno_sett, sett, _ = p.next_due.isocalendar()
                settimana_label = f"Sett. {sett}/{anno_sett}"
                scaduta = p.next_due < date.today()
            else:
                settimana_label = "Da programmare"
                scaduta = False
            righe_piano.append({
                "reparto": m.area or "SENZA REPARTO",
                "macchina": f"{m.code} — {m.name}",
                "machine_active": m.active,
                "intervento": p.intervention,
                "frequenza": p.frequency or "—",
                "settimana": settimana_label,
                "scadenza": p.next_due,
                "scaduta": scaduta,
                "eseguito": ultimo is not None,
                "esec_data": ultimo.performed_at.strftime("%d/%m/%Y") if ultimo else None,
                "esec_chi": (ultimo.operator.name if ultimo and ultimo.operator else None),
            })
    # scadenza piu' vicina in cima; le voci "da programmare" (senza data) in fondo
    righe_piano.sort(key=lambda r: (r["scadenza"] is None, r["scadenza"] or date.max, r["reparto"], r["macchina"]))

    return render_template("sgq/manutenzione.html", macchine=macchine, macchine_per_reparto=macchine_per_reparto,
                           categorie=categorie, righe_piano=righe_piano, oggi=date.today(),
                           colore_categoria=colore_categoria)


@sgq_bp.post("/manutenzione/macchine/nuova")
@login_required
def nuova_macchina():
    owner_only()
    code = request.form.get("code", "").strip()
    name = request.form.get("name", "").strip()
    if not code or not name:
        flash("Servono almeno codice e nome macchina.", "error")
        return redirect(url_for("sgq.manutenzione"))
    if Machine.query.filter_by(code=code).first():
        flash(f"Il codice macchina {code} esiste già.", "error")
        return redirect(url_for("sgq.manutenzione"))
    db.session.add(Machine(code=code, name=name, category=request.form.get("category", "").strip() or None,
                           area=request.form.get("area", "").strip() or None,
                           manufacturer=request.form.get("manufacturer", "").strip() or None,
                           responsible=request.form.get("responsible", "").strip() or None))
    db.session.commit()
    flash(f"Macchina {code} aggiunta.", "success")
    return redirect(url_for("sgq.manutenzione"))


@sgq_bp.post("/manutenzione/macchine/<int:machine_id>/salva")
@login_required
def salva_macchina(machine_id):
    owner_only()
    m = db.get_or_404(Machine, machine_id)
    m.name = request.form.get("name", m.name).strip()
    m.category = request.form.get("category", "").strip() or None
    m.area = request.form.get("area", "").strip() or None
    m.manufacturer = request.form.get("manufacturer", "").strip() or None
    m.responsible = request.form.get("responsible", "").strip() or None
    m.active = request.form.get("active") == "on"
    db.session.commit()
    flash("Macchina aggiornata.", "success")
    return redirect(url_for("sgq.manutenzione"))


@sgq_bp.post("/manutenzione/macchine/<int:machine_id>/elimina")
@login_required
def elimina_macchina(machine_id):
    owner_only()
    m = db.get_or_404(Machine, machine_id)
    codice = m.code
    db.session.delete(m)
    db.session.commit()
    flash(f"Macchina {codice} eliminata (con piano e registro interventi collegati).", "success")
    return redirect(url_for("sgq.manutenzione"))


@sgq_bp.post("/manutenzione/piano/<int:item_id>/elimina")
@login_required
def elimina_piano_manutenzione(item_id):
    owner_only()
    item = db.get_or_404(MaintenancePlanItem, item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Voce piano manutenzione eliminata.", "success")
    return redirect(url_for("sgq.manutenzione"))


@sgq_bp.post("/manutenzione/macchine/<int:machine_id>/piano/nuovo")
@login_required
def nuovo_piano_manutenzione(machine_id):
    owner_only()
    m = db.get_or_404(Machine, machine_id)
    intervento = request.form.get("intervention", "").strip()
    if not intervento:
        flash("Indica l'intervento previsto.", "error")
        return redirect(url_for("sgq.manutenzione"))
    db.session.add(MaintenancePlanItem(machine_id=m.id, intervention=intervento,
                                       frequency=request.form.get("frequency", "").strip() or None,
                                       next_due=_parse_date(request.form.get("next_due"))))
    db.session.commit()
    flash("Voce piano manutenzione aggiunta.", "success")
    return redirect(url_for("sgq.manutenzione"))


@sgq_bp.post("/manutenzione/piano/<int:item_id>/salva")
@login_required
def salva_piano_manutenzione(item_id):
    owner_only()
    item = db.get_or_404(MaintenancePlanItem, item_id)
    item.intervention = request.form.get("intervention", item.intervention).strip()
    item.frequency = request.form.get("frequency", "").strip() or None
    item.next_due = _parse_date(request.form.get("next_due"))
    item.active = request.form.get("active") == "on"
    db.session.commit()
    flash("Piano aggiornato.", "success")
    return redirect(url_for("sgq.manutenzione"))


@sgq_bp.route("/manutenzione/registro")
@login_required
def registro_manutenzione():
    owner_only()
    machine_id = request.args.get("macchina", type=int)
    query = MaintenanceLog.query
    if machine_id:
        query = query.filter_by(machine_id=machine_id)
    log = query.order_by(MaintenanceLog.performed_at.desc()).limit(300).all()
    macchine = Machine.query.order_by(Machine.name).all()
    return render_template("sgq/registro_manutenzione.html", log=log, macchine=macchine, machine_id=machine_id)


@sgq_bp.route("/manutenzione/registra", methods=["GET", "POST"])
@login_required
def registra_manutenzione():
    """Vista rapida da telefono/tablet: macchine raggruppate per reparto con
    ricerca e filtri, storico interventi per macchina e form di
    registrazione direttamente sulla card. Aperta a qualunque utente
    loggato, non solo al proprietario, com'era per la registrazione rapida."""
    if request.method == "GET":
        macchine = Machine.query.filter_by(active=True).order_by(Machine.area, Machine.name).all()

        macchine_per_reparto = OrderedDict()
        aree_presenti = sorted({m.area for m in macchine if m.area})
        aree_ordinate = [a for a in ORDINE_REPARTI_MANUTENZIONE if a in aree_presenti] + \
                         [a for a in aree_presenti if a not in ORDINE_REPARTI_MANUTENZIONE]
        for area in aree_ordinate:
            macchine_per_reparto[area] = [m for m in macchine if m.area == area]
        senza_reparto = [m for m in macchine if not m.area]
        if senza_reparto:
            macchine_per_reparto["SENZA REPARTO"] = senza_reparto

        categorie = sorted({m.category for m in macchine if m.category})

        machine_ids = [m.id for m in macchine]
        logs = (MaintenanceLog.query.filter(MaintenanceLog.machine_id.in_(machine_ids))
                .order_by(MaintenanceLog.performed_at.desc()).limit(500).all()) if machine_ids else []
        storico_json = [{
            "machine_id": l.machine_id,
            "macchina": f"{l.machine.code} — {l.machine.name}",
            "giorno": l.performed_at.strftime("%d/%m/%Y"),
            "chi": l.operator.name if l.operator else "—",
            "cosa": l.intervention,
            "tipo": TIPO_MANUTENZIONE_LABEL.get(l.kind, (l.kind or "").capitalize() or "—"),
            "ditta": l.external_company or "—",
            "ore": (f"{l.hours:g}" if l.hours is not None else "—"),
        } for l in logs]

        return render_template(
            "sgq/registra_manutenzione.html",
            macchine=macchine,
            macchine_per_reparto=macchine_per_reparto,
            categorie=categorie,
            storico_json=storico_json,
            tipi_intervento=TIPO_MANUTENZIONE_LABEL,
            oggi=date.today(),
            colore_categoria=colore_categoria,
        )

    machine_id = request.form.get("machine_id", type=int)
    macchina = db.session.get(Machine, machine_id) if machine_id else None
    intervento = request.form.get("intervention", "").strip()
    if not macchina or not intervento:
        flash("Scegli la macchina e indica l'intervento fatto.", "error")
        return redirect(url_for("sgq.registra_manutenzione"))
    performed_at = datetime.utcnow()
    data_scelta = _parse_date(request.form.get("data"))
    if data_scelta:
        performed_at = datetime.combine(data_scelta, performed_at.time())
    tipo = request.form.get("tipo", "straordinaria").strip() or "straordinaria"
    plan_item_id = request.form.get("plan_item_id", type=int)
    plan_item = None
    if plan_item_id:
        candidato = db.session.get(MaintenancePlanItem, plan_item_id)
        if candidato and candidato.machine_id == macchina.id:
            plan_item = candidato
    db.session.add(MaintenanceLog(
        machine_id=macchina.id, plan_item_id=(plan_item.id if plan_item else None), kind=tipo,
        intervention=intervento, operator_id=current_user.id,
        external_company=request.form.get("external_company", "").strip() or None,
        hours=_parse_decimal(request.form.get("hours")),
        notes=request.form.get("notes", "").strip() or None,
        performed_at=performed_at,
    ))
    db.session.commit()
    flash(f"Intervento registrato su {macchina.name}.", "success")
    return redirect(url_for("sgq.registra_manutenzione"))


# =============================================================== FORMAZIONE ==

@sgq_bp.route("/formazione")
@login_required
def formazione():
    owner_only()
    corsi = TrainingCourse.query.order_by(TrainingCourse.start_date.desc().nullslast()).all()
    persone = [("u", u.id, u.name) for u in User.query.filter_by(active=True).order_by(User.name).all()]
    persone += [("e", e.id, e.full_name) for e in TrainingEmployee.query.filter_by(active=True).order_by(TrainingEmployee.full_name).all()]
    return render_template("sgq/formazione.html", corsi=corsi, persone=persone, oggi=date.today())


@sgq_bp.route("/formazione/registro")
@login_required
def registro_formazione():
    """Registro corsi: vista con timeline, e la gestione completa (modifica,
    sessioni, partecipanti) dentro ogni scheda, dietro un 'Modifica'
    richiudibile - unico posto dove si gestisce un corso dopo averlo creato."""
    owner_only()
    oggi = date.today()
    corsi = TrainingCourse.query.order_by(TrainingCourse.start_date.desc().nullslast(), TrainingCourse.id.desc()).all()
    anni = sorted({c.start_date.year for c in corsi if c.start_date}, reverse=True)
    corsi_vista = []
    for c in corsi:
        eseguito = bool(c.end_date and c.end_date <= oggi)
        corsi_vista.append({
            "corso": c,
            "anno": c.start_date.year if c.start_date else None,
            "eseguito": eseguito,
            "allievi": [(a.user.name if a.user else a.employee.full_name, a.outcome) for a in c.attendances],
        })
    totale_ore = sum(float(c.hours) for c in corsi if c.hours)
    totale_partecipazioni = sum(len(cv["allievi"]) for cv in corsi_vista)
    persone = [("u", u.id, u.name) for u in User.query.filter_by(active=True).order_by(User.name).all()]
    persone += [("e", e.id, e.full_name) for e in TrainingEmployee.query.filter_by(active=True).order_by(TrainingEmployee.full_name).all()]
    return render_template("sgq/registro_formazione.html", corsi_vista=corsi_vista, anni=anni, oggi=oggi,
                           totale_ore=totale_ore, totale_partecipazioni=totale_partecipazioni, persone=persone)


@sgq_bp.post("/formazione/corsi/nuovo")
@login_required
def nuovo_corso():
    owner_only()
    titolo = request.form.get("title", "").strip()
    if not titolo:
        flash("Indica il titolo del corso.", "error")
        return redirect(url_for("sgq.formazione"))
    db.session.add(TrainingCourse(
        title=titolo, topic_area=request.form.get("topic_area", "").strip() or None,
        start_date=_parse_date(request.form.get("start_date")), end_date=_parse_date(request.form.get("end_date")),
        hours=_parse_decimal(request.form.get("hours")), teacher=request.form.get("teacher", "").strip() or None,
        notes=request.form.get("notes", "").strip() or None,
    ))
    db.session.commit()
    flash("Corso aggiunto.", "success")
    return redirect(url_for("sgq.formazione"))


@sgq_bp.post("/formazione/corsi/<int:course_id>/salva")
@login_required
def salva_corso(course_id):
    owner_only()
    c = db.get_or_404(TrainingCourse, course_id)
    c.title = request.form.get("title", c.title).strip()
    c.topic_area = request.form.get("topic_area", "").strip() or None
    c.start_date = _parse_date(request.form.get("start_date"))
    c.end_date = _parse_date(request.form.get("end_date"))
    c.hours = _parse_decimal(request.form.get("hours"))
    c.teacher = request.form.get("teacher", "").strip() or None
    c.notes = request.form.get("notes", "").strip() or None
    db.session.commit()
    flash("Corso aggiornato.", "success")
    return redirect(url_for("sgq.formazione"))


@sgq_bp.post("/formazione/corsi/<int:course_id>/elimina")
@login_required
def elimina_corso(course_id):
    owner_only()
    c = db.get_or_404(TrainingCourse, course_id)
    db.session.delete(c)
    db.session.commit()
    flash("Corso eliminato.", "success")
    return redirect(url_for("sgq.formazione"))


@sgq_bp.post("/formazione/corsi/<int:course_id>/partecipanti")
@login_required
def aggiungi_partecipante(course_id):
    owner_only()
    c = db.get_or_404(TrainingCourse, course_id)
    chiave = request.form.get("persona", "").strip()
    if not chiave:
        flash("Scegli una persona.", "error")
        return redirect(url_for("sgq.formazione"))
    user_id = int(chiave[1:]) if chiave.startswith("u") else None
    employee_id = int(chiave[1:]) if chiave.startswith("e") else None
    filtro = {"course_id": c.id, "user_id": user_id} if user_id else {"course_id": c.id, "employee_id": employee_id}
    if TrainingAttendance.query.filter_by(**filtro).first():
        flash("Questa persona è già registrata per questo corso.", "error")
        return redirect(url_for("sgq.formazione"))
    db.session.add(TrainingAttendance(course_id=c.id, user_id=user_id, employee_id=employee_id,
                                      outcome=request.form.get("outcome", "").strip() or None,
                                      notes=request.form.get("notes", "").strip() or None))
    db.session.commit()
    flash("Partecipante aggiunto.", "success")
    return redirect(url_for("sgq.formazione"))


@sgq_bp.post("/formazione/partecipazioni/<int:attendance_id>/salva")
@login_required
def salva_partecipazione(attendance_id):
    owner_only()
    a = db.get_or_404(TrainingAttendance, attendance_id)
    a.outcome = request.form.get("outcome", "").strip() or None
    a.notes = request.form.get("notes", "").strip() or None
    db.session.commit()
    flash("Partecipazione aggiornata.", "success")
    return redirect(url_for("sgq.formazione"))


@sgq_bp.post("/formazione/corsi/<int:course_id>/sessioni/nuova")
@login_required
def nuova_sessione_corso(course_id):
    owner_only()
    c = db.get_or_404(TrainingCourse, course_id)
    ultima = max([s.sequence for s in TrainingSession.query.filter_by(course_id=c.id).all()], default=0)
    db.session.add(TrainingSession(
        course_id=c.id, session_date=_parse_date(request.form.get("session_date")),
        hours=_parse_decimal(request.form.get("hours")), topic=request.form.get("topic", "").strip() or None,
        sequence=ultima + 1,
    ))
    db.session.commit()
    flash("Sessione aggiunta.", "success")
    return redirect(url_for("sgq.formazione"))


@sgq_bp.post("/formazione/sessioni/<int:session_id>/elimina")
@login_required
def elimina_sessione_corso(session_id):
    owner_only()
    s = db.get_or_404(TrainingSession, session_id)
    db.session.delete(s)
    db.session.commit()
    flash("Sessione eliminata.", "success")
    return redirect(url_for("sgq.formazione"))


@sgq_bp.route("/formazione/piano")
@login_required
def piano_formazione():
    """Piano formazione registro corsi per singola risorsa: una riga per
    persona (con o senza account di accesso), una colonna per area/argomento
    di corso (topic_area), con l'anno dell'ultimo corso concluso (eseguito)
    o il periodo dell'ultimo corso ancora in corso (pianificato) - calcolato
    dai corsi/partecipazioni gia' registrati."""
    owner_only()
    persone = [("u", u.id, u.name) for u in User.query.filter_by(active=True).order_by(User.name).all()]
    persone += [("e", e.id, e.full_name) for e in TrainingEmployee.query.filter_by(active=True).order_by(TrainingEmployee.full_name).all()]
    aree = sorted({c.topic_area for c in TrainingCourse.query.all() if c.topic_area})
    oggi = date.today()

    MESI_IT = {1:"GEN",2:"FEB",3:"MAR",4:"APR",5:"MAG",6:"GIU",7:"LUG",8:"AGO",9:"SET",10:"OTT",11:"NOV",12:"DIC"}
    matrice = {}  # "u<id>"/"e<id>" -> {area: {"testo":..., "eseguito": bool}}
    ore_totali_area = {a: 0 for a in aree}
    for corso in TrainingCourse.query.filter(TrainingCourse.topic_area.isnot(None)).all():
        eseguito = bool(corso.end_date and corso.end_date <= oggi)
        if corso.hours:
            ore_totali_area[corso.topic_area] = ore_totali_area.get(corso.topic_area, 0) + float(corso.hours)
        for partecipazione in corso.attendances:
            chiave = f"u{partecipazione.user_id}" if partecipazione.user_id else f"e{partecipazione.employee_id}"
            riga = matrice.setdefault(chiave, {})
            esistente = riga.get(corso.topic_area)
            # tiene il corso piu' recente per quell'area (per data fine/inizio)
            data_confronto = corso.end_date or corso.start_date
            if esistente and esistente.get("_data") and data_confronto and esistente["_data"] >= data_confronto:
                continue
            if corso.display_period:
                testo = corso.display_period
            elif eseguito:
                testo = str(corso.end_date.year)
            elif corso.start_date and corso.end_date:
                testo = f"{MESI_IT[corso.start_date.month]}-{MESI_IT[corso.end_date.month]} {corso.end_date.year}"
            elif corso.start_date:
                testo = f"{MESI_IT[corso.start_date.month]} {corso.start_date.year}"
            else:
                testo = "PIANIFICATO"
            riga[corso.topic_area] = {"testo": testo, "eseguito": eseguito, "_data": data_confronto}

    gap_notes = {}
    for g in EmployeeTrainingGap.query.all():
        chiave = f"u{g.user_id}" if g.user_id else f"e{g.employee_id}"
        gap_notes[chiave] = g.gap_note

    # Le correzioni manuali vincono sempre sul calcolo automatico.
    for over in PianoFormazioneOverride.query.all():
        chiave = f"u{over.user_id}" if over.user_id else f"e{over.employee_id}"
        riga = matrice.setdefault(chiave, {})
        if over.testo:
            riga[over.topic_area] = {"testo": over.testo, "eseguito": over.eseguito, "_data": None,
                                     "manuale": True, "data_iso": over.data.isoformat() if over.data else ""}
        elif over.topic_area in riga:
            del riga[over.topic_area]

    return render_template("sgq/piano_formazione.html", persone=persone, aree=aree, matrice=matrice,
                           ore_totali_area=ore_totali_area, gap_notes=gap_notes)


@sgq_bp.post("/formazione/piano/riga/<chiave>")
@login_required
def salva_riga_piano_formazione(chiave):
    owner_only()
    user_id = int(chiave[1:]) if chiave.startswith("u") else None
    employee_id = int(chiave[1:]) if chiave.startswith("e") else None

    gap_testo = request.form.get("gap_note", "").strip() or None
    filtro_gap = {"user_id": user_id} if user_id else {"employee_id": employee_id}
    gap = EmployeeTrainingGap.query.filter_by(**filtro_gap).first()
    if not gap:
        gap = EmployeeTrainingGap(gap_note=gap_testo, **filtro_gap)
        db.session.add(gap)
    else:
        gap.gap_note = gap_testo

    for chiave_campo, valore in request.form.items():
        if not chiave_campo.startswith("cella_"):
            continue
        area = chiave_campo[len("cella_"):]
        valore = (valore or "").strip()
        filtro = {"user_id": user_id, "topic_area": area} if user_id else {"employee_id": employee_id, "topic_area": area}
        over = PianoFormazioneOverride.query.filter_by(**filtro).first()
        if not valore:
            if over:
                db.session.delete(over)
            continue
        try:
            data_cella = datetime.strptime(valore, "%Y-%m-%d").date()
        except ValueError:
            continue
        eseguito = data_cella <= date.today()
        testo = str(data_cella.year) if eseguito else f"{data_cella.strftime('%d/%m/%Y')}"
        if not over:
            over = PianoFormazioneOverride(data=data_cella, testo=testo, eseguito=eseguito, **filtro)
            db.session.add(over)
        else:
            over.data = data_cella
            over.testo = testo
            over.eseguito = eseguito
    db.session.commit()
    flash("Riga aggiornata.", "success")
    return redirect(url_for("sgq.piano_formazione"))


@sgq_bp.post("/formazione/persone/nuova")
@login_required
def nuova_persona_formazione():
    owner_only()
    nome = request.form.get("full_name", "").strip()
    if not nome:
        flash("Indica il nome e cognome della persona.", "error")
        return redirect(url_for("sgq.piano_formazione"))
    if not TrainingEmployee.query.filter_by(full_name=nome).first():
        db.session.add(TrainingEmployee(full_name=nome))
        db.session.commit()
        flash(f"{nome} aggiunto al piano formazione.", "success")
    else:
        flash(f"{nome} è già presente.", "error")
    return redirect(url_for("sgq.piano_formazione"))


@sgq_bp.post("/formazione/dipendenti/<chiave>/gap")
@login_required
def salva_gap_formazione(chiave):
    owner_only()
    testo = request.form.get("gap_note", "").strip() or None
    if chiave.startswith("u"):
        user_id, employee_id = int(chiave[1:]), None
        gap = EmployeeTrainingGap.query.filter_by(user_id=user_id).first()
    else:
        user_id, employee_id = None, int(chiave[1:])
        gap = EmployeeTrainingGap.query.filter_by(employee_id=employee_id).first()
    if not gap:
        gap = EmployeeTrainingGap(user_id=user_id, employee_id=employee_id, gap_note=testo)
        db.session.add(gap)
    else:
        gap.gap_note = testo
    db.session.commit()
    return redirect(url_for("sgq.piano_formazione"))


# ==================================================== ATTESTATI E NOMINE ==

@sgq_bp.route("/formazione/attestati")
@login_required
def attestati():
    owner_only()
    oggi = date.today()
    elenco = Qualification.query.join(User).order_by(User.name, Qualification.issue_date.desc()).all()
    utenti = User.query.filter_by(active=True).order_by(User.name).all()
    return render_template("sgq/attestati.html", elenco=elenco, utenti=utenti, oggi=oggi)


@sgq_bp.post("/formazione/attestati/nuovo")
@login_required
def nuovo_attestato():
    owner_only()
    import os, uuid
    from flask import current_app
    from werkzeug.utils import secure_filename
    from .documents import ALLOWED, extract_text
    user_id = request.form.get("user_id", type=int)
    titolo = request.form.get("title", "").strip()
    if not user_id or not titolo:
        flash("Indica dipendente e titolo dell'attestato/nomina.", "error")
        return redirect(url_for("sgq.attestati"))
    documento_id = None
    file = request.files.get("documento")
    if file and file.filename:
        original = secure_filename(file.filename)
        ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
        if ext in ALLOWED:
            folder = current_app.config["UPLOAD_FOLDER"]
            os.makedirs(folder, exist_ok=True)
            stored = f"{uuid.uuid4().hex}.{ext}"
            path = os.path.join(folder, stored)
            file.save(path)
            utente = db.session.get(User, user_id)
            doc = SourceDocument(
                original_name=original, stored_name=stored, mime_type=file.mimetype,
                extracted_text=extract_text(path, ext), uploaded_by_id=current_user.id,
                category="Audit interno", document_title=f"{utente.name} — {titolo}", is_current=True,
            )
            db.session.add(doc)
            db.session.flush()
            documento_id = doc.id
        else:
            flash("Formato file non supportato, attestato salvato senza copia del documento.", "error")
    db.session.add(Qualification(
        user_id=user_id, kind=request.form.get("kind", "attestato"), title=titolo,
        reference_number=request.form.get("reference_number", "").strip() or None,
        issuing_body=request.form.get("issuing_body", "").strip() or None,
        issue_date=_parse_date(request.form.get("issue_date")), expiry_date=_parse_date(request.form.get("expiry_date")),
        notes=request.form.get("notes", "").strip() or None, document_id=documento_id,
    ))
    db.session.commit()
    flash("Attestato/nomina registrato.", "success")
    return redirect(url_for("sgq.attestati"))


@sgq_bp.post("/formazione/attestati/<int:qual_id>/elimina")
@login_required
def elimina_attestato(qual_id):
    owner_only()
    q = db.get_or_404(Qualification, qual_id)
    db.session.delete(q)
    db.session.commit()
    flash("Attestato/nomina eliminato.", "success")
    return redirect(url_for("sgq.attestati"))


# ================================================== MATRICE DI POLIVALENZA ==

@sgq_bp.route("/formazione/polivalenza")
@login_required
def polivalenza_elenco():
    owner_only()
    matrici = PolyvalenceMatrix.query.order_by(PolyvalenceMatrix.business_unit).all()
    return render_template("sgq/polivalenza_elenco.html", matrici=matrici)


@sgq_bp.post("/formazione/polivalenza/nuova")
@login_required
def nuova_matrice_polivalenza():
    owner_only()
    nome = request.form.get("business_unit", "").strip()
    if not nome:
        flash("Indica il nome della Business Unit.", "error")
        return redirect(url_for("sgq.polivalenza_elenco"))
    if PolyvalenceMatrix.query.filter_by(business_unit=nome).first():
        flash("Esiste già una matrice per questa Business Unit.", "error")
        return redirect(url_for("sgq.polivalenza_elenco"))
    m = PolyvalenceMatrix(business_unit=nome)
    db.session.add(m)
    db.session.commit()
    flash(f"Matrice creata per {nome}. Aggiungi ora le persone e le mansioni/postazioni.", "success")
    return redirect(url_for("sgq.polivalenza_dettaglio", matrix_id=m.id))


@sgq_bp.route("/formazione/polivalenza/<int:matrix_id>")
@login_required
def polivalenza_dettaglio(matrix_id):
    owner_only()
    matrice = db.get_or_404(PolyvalenceMatrix, matrix_id)
    valori = {(e.employee_id, e.column_id): e.level for e in matrice.entries}
    return render_template("sgq/polivalenza_dettaglio.html", matrice=matrice, valori=valori)


@sgq_bp.post("/formazione/polivalenza/<int:matrix_id>/colonna/nuova")
@login_required
def nuova_colonna_polivalenza(matrix_id):
    owner_only()
    m = db.get_or_404(PolyvalenceMatrix, matrix_id)
    etichetta = request.form.get("label", "").strip()
    if not etichetta:
        flash("Indica il nome della mansione/postazione.", "error")
        return redirect(url_for("sgq.polivalenza_dettaglio", matrix_id=m.id))
    ultima = max([c.sequence for c in m.columns], default=0)
    db.session.add(PolyvalenceColumn(matrix_id=m.id, group_label=request.form.get("group_label", "").strip() or None,
                                     label=etichetta, sequence=ultima + 1))
    db.session.commit()
    flash("Mansione/postazione aggiunta.", "success")
    return redirect(url_for("sgq.polivalenza_dettaglio", matrix_id=m.id))


@sgq_bp.post("/formazione/polivalenza/colonna/<int:column_id>/rinomina")
@login_required
def rinomina_colonna_polivalenza(column_id):
    owner_only()
    c = db.get_or_404(PolyvalenceColumn, column_id)
    c.label = request.form.get("label", c.label).strip() or c.label
    c.group_label = request.form.get("group_label", "").strip() or None
    db.session.commit()
    return redirect(url_for("sgq.polivalenza_dettaglio", matrix_id=c.matrix_id))


@sgq_bp.post("/formazione/polivalenza/colonna/<int:column_id>/elimina")
@login_required
def elimina_colonna_polivalenza(column_id):
    owner_only()
    c = db.get_or_404(PolyvalenceColumn, column_id)
    matrix_id = c.matrix_id
    PolyvalenceEntry.query.filter_by(column_id=c.id).delete()
    db.session.delete(c)
    db.session.commit()
    return redirect(url_for("sgq.polivalenza_dettaglio", matrix_id=matrix_id))


@sgq_bp.post("/formazione/polivalenza/<int:matrix_id>/persona/nuova")
@login_required
def nuova_persona_polivalenza(matrix_id):
    owner_only()
    m = db.get_or_404(PolyvalenceMatrix, matrix_id)
    nome = request.form.get("full_name", "").strip()
    if not nome:
        flash("Indica il nome e cognome della persona.", "error")
        return redirect(url_for("sgq.polivalenza_dettaglio", matrix_id=m.id))
    ultima = max([e.sequence for e in m.employees], default=0)
    db.session.add(PolyvalenceEmployee(matrix_id=m.id, full_name=nome, sequence=ultima + 1))
    db.session.commit()
    flash("Persona aggiunta.", "success")
    return redirect(url_for("sgq.polivalenza_dettaglio", matrix_id=m.id))


@sgq_bp.post("/formazione/polivalenza/persona/<int:employee_id>/rinomina")
@login_required
def rinomina_persona_polivalenza(employee_id):
    owner_only()
    e = db.get_or_404(PolyvalenceEmployee, employee_id)
    e.full_name = request.form.get("full_name", e.full_name).strip() or e.full_name
    db.session.commit()
    return redirect(url_for("sgq.polivalenza_dettaglio", matrix_id=e.matrix_id))


@sgq_bp.post("/formazione/polivalenza/persona/<int:employee_id>/elimina")
@login_required
def elimina_persona_polivalenza(employee_id):
    owner_only()
    e = db.get_or_404(PolyvalenceEmployee, employee_id)
    matrix_id = e.matrix_id
    PolyvalenceEntry.query.filter_by(employee_id=e.id).delete()
    db.session.delete(e)
    db.session.commit()
    return redirect(url_for("sgq.polivalenza_dettaglio", matrix_id=matrix_id))


@sgq_bp.post("/formazione/polivalenza/<int:matrix_id>/salva")
@login_required
def salva_matrice_polivalenza(matrix_id):
    owner_only()
    m = db.get_or_404(PolyvalenceMatrix, matrix_id)
    for chiave, valore in request.form.items():
        if not chiave.startswith("cella_"):
            continue
        _, employee_id, column_id = chiave.split("_")
        employee_id, column_id = int(employee_id), int(column_id)
        livello = int(valore) if valore.strip().isdigit() else 0
        voce = PolyvalenceEntry.query.filter_by(matrix_id=m.id, employee_id=employee_id, column_id=column_id).first()
        if voce:
            voce.level = livello
        elif livello:
            db.session.add(PolyvalenceEntry(matrix_id=m.id, employee_id=employee_id, column_id=column_id, level=livello))
    db.session.commit()
    flash("Matrice di polivalenza aggiornata.", "success")
    return redirect(url_for("sgq.polivalenza_dettaglio", matrix_id=m.id))


@sgq_bp.post("/formazione/polivalenza/<int:matrix_id>/elimina")
@login_required
def elimina_matrice_polivalenza(matrix_id):
    owner_only()
    m = db.get_or_404(PolyvalenceMatrix, matrix_id)
    db.session.delete(m)
    db.session.commit()
    flash("Matrice eliminata.", "success")
    return redirect(url_for("sgq.polivalenza_elenco"))


@sgq_bp.route("/formazione/registra", methods=["GET", "POST"])
@login_required
def registra_formazione():
    """Registrazione rapida da telefono, per il dipendente stesso o per chi
    lo affianca: scegli il corso e il proprio esito."""
    if request.method == "GET":
        corsi = TrainingCourse.query.order_by(TrainingCourse.start_date.desc().nullslast()).limit(30).all()
        return render_template("sgq/registra_formazione.html", corsi=corsi)
    course_id = request.form.get("course_id", type=int)
    corso = db.session.get(TrainingCourse, course_id) if course_id else None
    if not corso:
        flash("Scegli un corso.", "error")
        return redirect(url_for("sgq.registra_formazione"))
    esistente = TrainingAttendance.query.filter_by(course_id=corso.id, user_id=current_user.id).first()
    if esistente:
        esistente.outcome = request.form.get("outcome", "").strip() or esistente.outcome
        esistente.notes = request.form.get("notes", "").strip() or esistente.notes
    else:
        db.session.add(TrainingAttendance(course_id=corso.id, user_id=current_user.id,
                                          outcome=request.form.get("outcome", "").strip() or None,
                                          notes=request.form.get("notes", "").strip() or None))
    db.session.commit()
    flash(f"Formazione registrata per {corso.title}.", "success")
    return redirect(url_for("sgq.registra_formazione"))


# ================================================================ TARATURE ==

@sgq_bp.post("/formazione/partecipazioni/<int:attendance_id>/elimina")
@login_required
def elimina_partecipazione(attendance_id):
    owner_only()
    a = db.get_or_404(TrainingAttendance, attendance_id)
    db.session.delete(a)
    db.session.commit()
    flash("Partecipazione eliminata.", "success")
    return redirect(url_for("sgq.formazione"))


@sgq_bp.route("/tarature")
@login_required
def tarature():
    owner_only()
    dispositivi = CalibrationDevice.query.order_by(CalibrationDevice.active.desc(),
                                                    CalibrationDevice.next_due.isnot(None).desc(),
                                                    CalibrationDevice.next_due).all()
    return render_template("sgq/tarature.html", dispositivi=dispositivi, oggi=date.today())


@sgq_bp.post("/tarature/nuovo")
@login_required
def nuovo_dispositivo():
    owner_only()
    name = request.form.get("name", "").strip()
    if not name:
        flash("Indica la denominazione dello strumento.", "error")
        return redirect(url_for("sgq.tarature"))
    db.session.add(CalibrationDevice(
        sheet_number=request.form.get("sheet_number", "").strip() or None, name=name,
        code=request.form.get("code", "").strip() or None,
        assigned_to=request.form.get("assigned_to", "").strip() or None,
        frequency=request.form.get("frequency", "").strip() or None,
        last_check=_parse_date(request.form.get("last_check")),
        next_due=_parse_date(request.form.get("next_due")),
        supplier=request.form.get("supplier", "").strip() or None,
        notes=request.form.get("notes", "").strip() or None,
    ))
    db.session.commit()
    flash("Strumento aggiunto al registro tarature.", "success")
    return redirect(url_for("sgq.tarature"))


@sgq_bp.post("/tarature/<int:device_id>/salva")
@login_required
def salva_dispositivo(device_id):
    owner_only()
    d = db.get_or_404(CalibrationDevice, device_id)
    d.name = request.form.get("name", d.name).strip()
    d.sheet_number = request.form.get("sheet_number", "").strip() or None
    d.code = request.form.get("code", "").strip() or None
    d.assigned_to = request.form.get("assigned_to", "").strip() or None
    d.frequency = request.form.get("frequency", "").strip() or None
    d.last_check = _parse_date(request.form.get("last_check"))
    d.next_due = _parse_date(request.form.get("next_due"))
    d.supplier = request.form.get("supplier", "").strip() or None
    d.notes = request.form.get("notes", "").strip() or None
    d.active = request.form.get("active") == "on"
    db.session.commit()
    flash("Strumento aggiornato.", "success")
    return redirect(url_for("sgq.tarature"))


@sgq_bp.post("/tarature/<int:device_id>/elimina")
@login_required
def elimina_dispositivo(device_id):
    owner_only()
    d = db.get_or_404(CalibrationDevice, device_id)
    nome = d.name
    db.session.delete(d)
    db.session.commit()
    flash(f"Strumento {nome} eliminato (con storico controlli collegato).", "success")
    return redirect(url_for("sgq.tarature"))


@sgq_bp.post("/tarature/<int:device_id>/registra-controllo")
@login_required
def registra_controllo(device_id):
    owner_only()
    d = db.get_or_404(CalibrationDevice, device_id)
    checked = _parse_date(request.form.get("checked_at")) or date.today()
    next_due = _parse_date(request.form.get("next_due"))
    db.session.add(CalibrationRecord(device_id=d.id, checked_at=checked, next_due=next_due,
                                     outcome=request.form.get("outcome", "").strip() or None,
                                     responsible=request.form.get("responsible", "").strip() or None,
                                     notes=request.form.get("notes", "").strip() or None))
    d.last_check = checked
    if next_due:
        d.next_due = next_due
    db.session.commit()
    flash(f"Controllo registrato su {d.name}.", "success")
    return redirect(url_for("sgq.tarature"))


# ============================================================ NC - 8D ==

@sgq_bp.route("/non-conformita")
@login_required
def non_conformita():
    owner_only()
    stato = request.args.get("stato", "")
    query = NonConformity8D.query
    if stato:
        query = query.filter_by(status=stato)
    elenco = query.order_by(NonConformity8D.opened_at.desc()).all()
    return render_template("sgq/non_conformita.html", elenco=elenco, stato=stato)


@sgq_bp.post("/non-conformita/nuova")
@login_required
def nuova_nc():
    owner_only()
    descrizione = request.form.get("d2_description", "").strip()
    if not descrizione:
        flash("Indica almeno la descrizione del problema (D2).", "error")
        return redirect(url_for("sgq.non_conformita"))
    nc = NonConformity8D(
        number=request.form.get("number", "").strip() or None,
        opened_at=_parse_date(request.form.get("opened_at")) or date.today(),
        customer=request.form.get("customer", "").strip() or None,
        article_code=request.form.get("article_code", "").strip() or None,
        pieces=request.form.get("pieces", type=int),
        where_found=request.form.get("where_found", "").strip() or None,
        d2_description=descrizione,
        responsible=request.form.get("responsible", "").strip() or None,
    )
    db.session.add(nc)
    db.session.commit()
    flash(f"Non conformità {nc.number or nc.id} aperta.", "success")
    return redirect(url_for("sgq.dettaglio_nc", nc_id=nc.id))


@sgq_bp.route("/non-conformita/<int:nc_id>")
@login_required
def dettaglio_nc(nc_id):
    owner_only()
    nc = db.get_or_404(NonConformity8D, nc_id)
    return render_template("sgq/dettaglio_nc.html", nc=nc)


@sgq_bp.post("/non-conformita/<int:nc_id>/salva")
@login_required
def salva_nc(nc_id):
    owner_only()
    nc = db.get_or_404(NonConformity8D, nc_id)
    nc.number = request.form.get("number", "").strip() or None
    nc.customer = request.form.get("customer", "").strip() or None
    nc.article_code = request.form.get("article_code", "").strip() or None
    nc.pieces = request.form.get("pieces", type=int)
    nc.where_found = request.form.get("where_found", "").strip() or None
    nc.responsible = request.form.get("responsible", "").strip() or None
    nc.d1_team = request.form.get("d1_team", "").strip() or None
    nc.d2_description = request.form.get("d2_description", nc.d2_description).strip()
    nc.d3_containment = request.form.get("d3_containment", "").strip() or None
    nc.d4_root_cause = request.form.get("d4_root_cause", "").strip() or None
    nc.d5_corrective_actions = request.form.get("d5_corrective_actions", "").strip() or None
    nc.d5_date = _parse_date(request.form.get("d5_date"))
    nc.d6_verification = request.form.get("d6_verification", "").strip() or None
    nc.d6_date = _parse_date(request.form.get("d6_date"))
    nc.d7_extension = request.form.get("d7_extension", "").strip() or None
    nc.d8_notes = request.form.get("d8_notes", "").strip() or None
    db.session.commit()
    flash("Report 8D aggiornato.", "success")
    return redirect(url_for("sgq.dettaglio_nc", nc_id=nc.id))


@sgq_bp.post("/non-conformita/<int:nc_id>/chiudi")
@login_required
def chiudi_nc(nc_id):
    owner_only()
    nc = db.get_or_404(NonConformity8D, nc_id)
    if not nc.d5_corrective_actions or not nc.d6_verification:
        flash("Per chiudere servono almeno D5 (azioni correttive) e D6 (verifica efficacia).", "error")
        return redirect(url_for("sgq.dettaglio_nc", nc_id=nc.id))
    nc.status = "chiusa"
    nc.closed_at = date.today()
    db.session.commit()
    flash("Non conformità chiusa.", "success")
    return redirect(url_for("sgq.dettaglio_nc", nc_id=nc.id))


@sgq_bp.post("/non-conformita/<int:nc_id>/riapri")
@login_required
def riapri_nc(nc_id):
    owner_only()
    nc = db.get_or_404(NonConformity8D, nc_id)
    nc.status = "aperta"
    nc.closed_at = None
    db.session.commit()
    flash("Non conformità riaperta.", "success")
    return redirect(url_for("sgq.dettaglio_nc", nc_id=nc.id))


# =================================================================== AUDIT ==

AREE_STANDARD_AUDIT = [
    ("NC-RAC-PM", "RSGQ"), ("Piani e corsi di formazione", "DIR"), ("Obiettivi qualità", "DIR"),
    ("Gestione eco-finanziaria", "DIR"), ("Commerciale", "RCOMM"), ("Pianificazione e progettazione", "Rprod-RPROG"),
    ("Approvvigionamenti", "RACQ"), ("Montaggio e magazzino", "RPROD"), ("Manutenzioni", "RPROD"), ("Tarature", "RSGQ"),
]
SCOPO_STANDARD_AUDIT = ("1 - Verificare la corretta applicazione del SGQ: adeguatezza documentale; applicazione del SGQ; "
                        "correttezza e completezza delle registrazioni; verifica azioni per processi;\n"
                        "2 - Verifica efficacia ed efficacia del SGQ e dei processi, tramite gli indicatori, per verificare "
                        "l'audit di prestazione")


def seed_piano_audit(anno=None):
    """Pianifica le verifiche ispettive dell'anno sulle aree/processi standard
    del Piano degli Audit, pronte da confermare con data e auditor."""
    anno = anno or date.today().year
    if AuditPlanItem.query.filter_by(year=anno).first():
        return
    for area, responsabile in AREE_STANDARD_AUDIT:
        db.session.add(AuditPlanItem(year=anno, area_process=area, auditor=responsabile, scope=SCOPO_STANDARD_AUDIT))
    db.session.commit()


@sgq_bp.route("/audit")
@login_required
def audit():
    owner_only()
    anno_corrente = date.today().year
    anno = request.args.get("anno", type=int) or anno_corrente
    anni_disponibili = sorted({a.year for a in AuditPlanItem.query.all()} | {anno_corrente}, reverse=True)
    elenco = AuditPlanItem.query.filter_by(year=anno).order_by(AuditPlanItem.planned_date).all()
    aree_gia_pianificate = {a.area_process for a in elenco}
    aree_da_selezionare = [(area, resp) for area, resp in AREE_STANDARD_AUDIT if area not in aree_gia_pianificate]
    return render_template("sgq/audit.html", elenco=elenco, anno=anno, anni_disponibili=anni_disponibili,
                           oggi=date.today(), aree_da_selezionare=aree_da_selezionare)


@sgq_bp.post("/audit/pianifica-selezione")
@login_required
def pianifica_audit_selezione():
    owner_only()
    anno = request.form.get("year", type=int) or date.today().year
    aree_scelte = request.form.getlist("aree")
    mappa_responsabili = dict(AREE_STANDARD_AUDIT)
    già_presenti = {a.area_process for a in AuditPlanItem.query.filter_by(year=anno).all()}
    creati = 0
    for area in aree_scelte:
        if area in già_presenti or area not in mappa_responsabili:
            continue
        db.session.add(AuditPlanItem(year=anno, area_process=area, auditor=mappa_responsabili[area], scope=SCOPO_STANDARD_AUDIT))
        creati += 1
    db.session.commit()
    if creati:
        flash(f"{creati} verifiche pianificate per il {anno}, pronte da compilare.", "success")
    else:
        flash("Nessuna area selezionata.", "error")
    return redirect(url_for("sgq.audit", anno=anno))


@sgq_bp.post("/audit/nuovo")
@login_required
def nuovo_audit():
    owner_only()
    area = request.form.get("area_process", "").strip()
    if not area:
        flash("Indica l'area/processo da verificare.", "error")
        return redirect(url_for("sgq.audit"))
    db.session.add(AuditPlanItem(
        year=request.form.get("year", type=int) or date.today().year, area_process=area,
        planned_date=_parse_date(request.form.get("planned_date")), auditor=request.form.get("auditor", "").strip() or None,
        scope=request.form.get("scope", "").strip() or None,
    ))
    db.session.commit()
    flash("Verifica ispettiva pianificata.", "success")
    return redirect(url_for("sgq.audit", anno=request.form.get("year", type=int)))


@sgq_bp.post("/audit/<int:item_id>/salva")
@login_required
def salva_audit(item_id):
    owner_only()
    a = db.get_or_404(AuditPlanItem, item_id)
    a.area_process = request.form.get("area_process", a.area_process).strip()
    a.planned_date = _parse_date(request.form.get("planned_date"))
    a.actual_date = _parse_date(request.form.get("actual_date"))
    a.auditor = request.form.get("auditor", "").strip() or None
    a.scope = request.form.get("scope", "").strip() or None
    a.status = request.form.get("status", a.status)
    db.session.commit()
    flash("Verifica ispettiva aggiornata.", "success")
    return redirect(url_for("sgq.audit", anno=a.year))


# ==================================================== RAPPORTI DI AUDIT (VII) ==
# Rapporto di Audit strutturato per punti norma ISO 9001:2015, stesso formato
# storico PG-AUD-02: si compila online riga per riga (rilievo + azioni +
# allegati), poi si stampa nel formato noto.

@sgq_bp.route("/audit/rapporti")
@login_required
def audit_reports():
    owner_only()
    anno_corrente = date.today().year
    anno = request.args.get("anno", type=int) or anno_corrente
    anni_disponibili = sorted({r.year for r in AuditReport.query.all()} | {anno_corrente}, reverse=True)
    elenco = AuditReport.query.filter_by(year=anno).order_by(AuditReport.audit_dates).all()
    piano_anno = AuditPlanItem.query.filter_by(year=anno).all()
    return render_template("sgq/audit_reports.html", elenco=elenco, anno=anno,
                           anni_disponibili=anni_disponibili, piano_anno=piano_anno)


@sgq_bp.post("/audit/rapporti/nuovo")
@login_required
def nuovo_audit_report():
    owner_only()
    anno = request.form.get("year", type=int) or date.today().year
    report = AuditReport(
        year=anno, plan_item_id=request.form.get("plan_item_id", type=int) or None,
        audit_dates=request.form.get("audit_dates", "").strip() or None,
        team_lead=request.form.get("team_lead", "").strip() or None,
        team_members=request.form.get("team_members", "").strip() or None,
        status="bozza",
    )
    db.session.add(report)
    db.session.flush()
    for i, (sez, titolo, is_heading) in enumerate(PUNTI_ISO_9001, start=1):
        db.session.add(AuditReportFinding(report_id=report.id, sequence=i, sez=sez, iso_title=titolo, is_heading=is_heading))
    db.session.commit()
    flash(f"Nuovo Rapporto di Audit creato per il {anno}, con tutti i punti ISO 9001 pronti da compilare.", "success")
    return redirect(url_for("sgq.audit_report_detail", report_id=report.id))


@sgq_bp.route("/audit/rapporti/<int:report_id>")
@login_required
def audit_report_detail(report_id):
    owner_only()
    report = db.get_or_404(AuditReport, report_id)
    return render_template("sgq/audit_report_detail.html", report=report)


@sgq_bp.post("/audit/rapporti/<int:report_id>/salva")
@login_required
def salva_audit_report(report_id):
    owner_only()
    report = db.get_or_404(AuditReport, report_id)
    report.audit_dates = request.form.get("audit_dates", "").strip() or None
    report.team_lead = request.form.get("team_lead", "").strip() or None
    report.team_members = request.form.get("team_members", "").strip() or None
    report.status = request.form.get("status", report.status)
    db.session.commit()
    flash("Intestazione del rapporto aggiornata.", "success")
    return redirect(url_for("sgq.audit_report_detail", report_id=report.id))


@sgq_bp.post("/audit/rilievi/<int:finding_id>/salva")
@login_required
def salva_audit_finding(finding_id):
    owner_only()
    f = db.get_or_404(AuditReportFinding, finding_id)
    f.findings_text = request.form.get("findings_text", "").strip() or None
    f.actions_text = request.form.get("actions_text", "").strip() or None
    db.session.commit()
    return redirect(url_for("sgq.audit_report_detail", report_id=f.report_id) + f"#rilievo-{f.id}")


@sgq_bp.post("/audit/rilievi/<int:finding_id>/allegato")
@login_required
def carica_audit_allegato(finding_id):
    owner_only()
    import os, uuid
    from flask import current_app
    from werkzeug.utils import secure_filename
    from .documents import ALLOWED, extract_text
    f = db.get_or_404(AuditReportFinding, finding_id)
    file = request.files.get("allegato")
    if not file or not file.filename:
        flash("Seleziona un file da allegare.", "error")
        return redirect(url_for("sgq.audit_report_detail", report_id=f.report_id) + f"#rilievo-{f.id}")
    original = secure_filename(file.filename)
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED:
        flash("Formato non supportato.", "error")
        return redirect(url_for("sgq.audit_report_detail", report_id=f.report_id) + f"#rilievo-{f.id}")
    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(folder, stored)
    file.save(path)
    titolo = f"Audit {f.report.year} — {f.sez} — allegato"
    doc = SourceDocument(
        original_name=original, stored_name=stored, mime_type=file.mimetype,
        extracted_text=extract_text(path, ext), uploaded_by_id=current_user.id,
        category="Audit interno", document_title=titolo, is_current=True,
    )
    db.session.add(doc)
    db.session.flush()
    db.session.add(AuditReportAttachment(finding_id=f.id, document_id=doc.id, label=original))
    db.session.commit()
    flash("Allegato caricato.", "success")
    return redirect(url_for("sgq.audit_report_detail", report_id=f.report_id) + f"#rilievo-{f.id}")


@sgq_bp.post("/audit/allegati/<int:attachment_id>/elimina")
@login_required
def elimina_audit_allegato(attachment_id):
    owner_only()
    a = db.get_or_404(AuditReportAttachment, attachment_id)
    finding_id, report_id = a.finding_id, a.finding.report_id
    db.session.delete(a)
    db.session.commit()
    return redirect(url_for("sgq.audit_report_detail", report_id=report_id) + f"#rilievo-{finding_id}")


@sgq_bp.route("/audit/rapporti/<int:report_id>/stampa")
@login_required
def stampa_audit_report(report_id):
    owner_only()
    from .audit_report_print import genera_docx_rapporto_audit
    report = db.get_or_404(AuditReport, report_id)
    return genera_docx_rapporto_audit(report)


# ==================================================== RIESAME DELLA DIREZIONE ==

@sgq_bp.route("/riesame-direzione")
@login_required
def riesame_direzione():
    owner_only()
    elenco = ManagementReview.query.order_by(ManagementReview.review_date.desc()).all()
    return render_template("sgq/riesame_direzione.html", elenco=elenco, oggi=date.today())


@sgq_bp.post("/riesame-direzione/nuovo")
@login_required
def nuovo_riesame():
    owner_only()
    data_riesame = _parse_date(request.form.get("review_date")) or date.today()
    db.session.add(ManagementReview(review_date=data_riesame, reference_period=str(data_riesame.year - 1)))
    db.session.commit()
    nuovo = ManagementReview.query.order_by(ManagementReview.id.desc()).first()
    flash("Riesame della Direzione creato: compila gli ingressi/uscite.", "success")
    return redirect(url_for("sgq.dettaglio_riesame", review_id=nuovo.id))


@sgq_bp.route("/riesame-direzione/<int:review_id>")
@login_required
def dettaglio_riesame(review_id):
    owner_only()
    r = db.get_or_404(ManagementReview, review_id)
    _ensure_review_sections(r)
    from .riesame_stats import (dati_nc_per_anno, grafico_nc_per_mese, dati_audit_per_anno,
                                 grafico_audit_per_stato, dati_piani_miglioramento, png_a_base64)
    anno = int(r.reference_period) if (r.reference_period or "").isdigit() else r.review_date.year - 1
    dati_nc = dati_nc_per_anno(anno)
    dati_audit = dati_audit_per_anno(anno)
    grafici_per_sezione = {
        "nonconformities": png_a_base64(grafico_nc_per_mese(dati_nc)),
        "internal_audit": png_a_base64(grafico_audit_per_stato(dati_audit)),
    }
    return render_template("sgq/dettaglio_riesame.html", r=r, anno_dati=anno, dati_nc=dati_nc,
                           dati_audit=dati_audit, dati_piani=dati_piani_miglioramento(r),
                           grafici_per_sezione=grafici_per_sezione)


@sgq_bp.post("/riesame-direzione/<int:review_id>/salva")
@login_required
def salva_riesame(review_id):
    owner_only()
    r = db.get_or_404(ManagementReview, review_id)
    r.review_date = _parse_date(request.form.get("review_date")) or r.review_date
    r.participants = request.form.get("participants", "").strip() or None
    r.input_audit_results = request.form.get("input_audit_results", "").strip() or None
    r.input_customer_feedback = request.form.get("input_customer_feedback", "").strip() or None
    r.input_process_performance = request.form.get("input_process_performance", "").strip() or None
    r.input_nonconformities = request.form.get("input_nonconformities", "").strip() or None
    r.input_corrective_actions_status = request.form.get("input_corrective_actions_status", "").strip() or None
    r.input_objectives_status = request.form.get("input_objectives_status", "").strip() or None
    r.input_resources_adequacy = request.form.get("input_resources_adequacy", "").strip() or None
    r.input_risks_opportunities = request.form.get("input_risks_opportunities", "").strip() or None
    r.output_improvement_opportunities = request.form.get("output_improvement_opportunities", "").strip() or None
    r.output_system_changes = request.form.get("output_system_changes", "").strip() or None
    r.output_resource_needs = request.form.get("output_resource_needs", "").strip() or None
    r.notes = request.form.get("notes", "").strip() or None
    # --- Formato del modulo di riesame ---
    r.reference_period = request.form.get("reference_period", "").strip() or None
    r.participants = request.form.get("participants", "").strip() or None
    for campo in ("basis_audit_reports", "basis_certification_reports", "basis_previous_review_actions",
                  "basis_customer_feedback", "basis_corrective_actions_trend", "basis_preventive_actions_trend",
                  "basis_rac", "basis_context_analysis"):
        setattr(r, campo, request.form.get(campo) == "on")
    r.conclusions = request.form.get("conclusions", "").strip() or None
    r.signature_date = _parse_date(request.form.get("signature_date"))
    db.session.commit()
    flash("Riesame della Direzione salvato.", "success")
    return redirect(url_for("sgq.dettaglio_riesame", review_id=r.id))


@sgq_bp.post("/riesame-direzione/sezioni/<int:section_id>/salva")
@login_required
def salva_riesame_sezione(section_id):
    owner_only()
    s = db.get_or_404(ManagementReviewSection, section_id)
    s.positives_text = request.form.get("positives_text", "").strip() or None
    s.negatives_text = request.form.get("negatives_text", "").strip() or None
    db.session.commit()
    return redirect(url_for("sgq.dettaglio_riesame", review_id=s.review_id) + f"#sezione-{s.id}")


@sgq_bp.post("/riesame-direzione/sezioni/<int:section_id>/genera-bozza")
@login_required
def genera_bozza_riesame_sezione(section_id):
    owner_only()
    from flask import current_app
    from .riesame_ai import genera_bozza_sezione, dati_vivi_per_sezione, BozzaAIError
    s = db.get_or_404(ManagementReviewSection, section_id)
    try:
        dati_vivi = dati_vivi_per_sezione(s.section_key, s.review)
        positivo, negativo = genera_bozza_sezione(
            section=s, appunti_positivi=s.positives_text, appunti_negativi=s.negatives_text,
            ragione_sociale=current_app.config["RAGIONE_SOCIALE"], dati_vivi=dati_vivi,
        )
        if positivo:
            s.positives_text = positivo
        if negativo:
            s.negatives_text = negativo
        db.session.commit()
        flash("Bozza generata dall'AI: rileggila e correggila prima di considerarla definitiva.", "success")
    except BozzaAIError as exc:
        flash(str(exc), "error")
    return redirect(url_for("sgq.dettaglio_riesame", review_id=s.review_id) + f"#sezione-{s.id}")


@sgq_bp.post("/riesame-direzione/sezioni/<int:section_id>/allegato")
@login_required
def carica_riesame_allegato(section_id):
    owner_only()
    import os, uuid
    from flask import current_app
    from werkzeug.utils import secure_filename
    from .documents import ALLOWED, extract_text
    s = db.get_or_404(ManagementReviewSection, section_id)
    file = request.files.get("allegato")
    if not file or not file.filename:
        flash("Seleziona un file da allegare.", "error")
        return redirect(url_for("sgq.dettaglio_riesame", review_id=s.review_id) + f"#sezione-{s.id}")
    original = secure_filename(file.filename)
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED:
        flash("Formato non supportato.", "error")
        return redirect(url_for("sgq.dettaglio_riesame", review_id=s.review_id) + f"#sezione-{s.id}")
    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(folder, stored)
    file.save(path)
    titolo = f"Riesame Direzione {s.review.review_date.strftime('%d/%m/%Y')} — {s.title} — allegato"
    doc = SourceDocument(
        original_name=original, stored_name=stored, mime_type=file.mimetype,
        extracted_text=extract_text(path, ext), uploaded_by_id=current_user.id,
        category="Riesame Direzione", document_title=titolo, is_current=True,
    )
    db.session.add(doc)
    db.session.flush()
    db.session.add(ManagementReviewSectionAttachment(section_id=s.id, document_id=doc.id, label=original))
    db.session.commit()
    flash("Allegato caricato.", "success")
    return redirect(url_for("sgq.dettaglio_riesame", review_id=s.review_id) + f"#sezione-{s.id}")


@sgq_bp.post("/riesame-direzione/allegati/<int:attachment_id>/elimina")
@login_required
def elimina_riesame_allegato(attachment_id):
    owner_only()
    a = db.get_or_404(ManagementReviewSectionAttachment, attachment_id)
    section_id, review_id = a.section_id, a.section.review_id
    db.session.delete(a)
    db.session.commit()
    return redirect(url_for("sgq.dettaglio_riesame", review_id=review_id) + f"#sezione-{section_id}")


@sgq_bp.post("/riesame-direzione/<int:review_id>/piani/nuovo")
@login_required
def nuova_riesame_azione(review_id):
    owner_only()
    r = db.get_or_404(ManagementReview, review_id)
    kind = request.form.get("kind")
    if kind not in ("verifica_precedente", "nuova_proposta"):
        abort(400)
    ordine = len([i for i in r.action_items if i.kind == kind])
    db.session.add(ManagementReviewActionItem(review_id=r.id, kind=kind, sort_order=ordine))
    db.session.commit()
    return redirect(url_for("sgq.dettaglio_riesame", review_id=r.id) + "#piani")


@sgq_bp.post("/riesame-direzione/piani/<int:item_id>/salva")
@login_required
def salva_riesame_azione(item_id):
    owner_only()
    voce = db.get_or_404(ManagementReviewActionItem, item_id)
    voce.activity = request.form.get("activity", "").strip() or None
    voce.resources = request.form.get("resources", "").strip() or None
    voce.responsible = request.form.get("responsible", "").strip() or None
    voce.status_text = request.form.get("status_text", "").strip() or None
    db.session.commit()
    return redirect(url_for("sgq.dettaglio_riesame", review_id=voce.review_id) + "#piani")


@sgq_bp.post("/riesame-direzione/piani/<int:item_id>/elimina")
@login_required
def elimina_riesame_azione(item_id):
    owner_only()
    voce = db.get_or_404(ManagementReviewActionItem, item_id)
    review_id = voce.review_id
    db.session.delete(voce)
    db.session.commit()
    return redirect(url_for("sgq.dettaglio_riesame", review_id=review_id) + "#piani")


@sgq_bp.route("/riesame-direzione/<int:review_id>/stampa")
@login_required
def stampa_riesame(review_id):
    owner_only()
    from .riesame_print import genera_docx_riesame_direzione
    from .riesame_stats import dati_nc_per_anno, grafico_nc_per_mese, dati_audit_per_anno, grafico_audit_per_stato
    r = db.get_or_404(ManagementReview, review_id)
    _ensure_review_sections(r)
    anno = int(r.reference_period) if (r.reference_period or "").isdigit() else r.review_date.year - 1
    grafici_per_sezione = {
        "nonconformities": grafico_nc_per_mese(dati_nc_per_anno(anno)),
        "internal_audit": grafico_audit_per_stato(dati_audit_per_anno(anno)),
    }
    return genera_docx_riesame_direzione(r, grafici_per_sezione=grafici_per_sezione)
