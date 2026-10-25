"""Altri sistemi di gestione, con la stessa struttura per tutti:

- ISO 14001 — ambiente: aspetti e impatti ambientali, obblighi di conformità, emergenze
- ISO 45001 — salute e sicurezza: pericoli e rischi, requisiti legali, infortuni e quasi infortuni
- SA8000 — responsabilità sociale: rischi sociali, requisiti, segnalazioni e reclami

Per ogni norma: registro di valutazione (aspetti o rischi con probabilità × gravità),
registro degli obblighi con scadenze, registro degli eventi, autovalutazione per punto.
Si riempiono piano piano: la struttura è già quella che l'ispettore si aspetta.
"""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import ComplianceObligation, MgmtAssessment, MgmtEvent, MgmtRisk

sistemi_bp = Blueprint("sistemi", __name__, url_prefix="/sistemi")

_HLS_SUPPORTO = [("7.1", "Risorse"), ("7.2", "Competenza"), ("7.3", "Consapevolezza"), ("7.4", "Comunicazione"),
                 ("7.5", "Informazioni documentate")]

NORME = {
    "iso14001": {
        "sigla": "ISO 14001", "nome": "Ambiente", "icona": "🌿", "colore": "green",
        "intro": "Sistema di gestione ambientale: si conoscono gli aspetti ambientali dell'attività, si rispettano gli obblighi di legge e si migliora la prestazione ambientale.",
        "registro": "Aspetti e impatti ambientali", "voce": "Aspetto ambientale", "effetto": "Impatto",
        "condizioni": ["Normale", "Anomala", "Emergenza"],
        "eventi": ["Emergenza ambientale", "Sversamento", "Superamento limiti", "Reclamo ambientale", "Segnalazione"],
        "punti": [("4", "Contesto", [("4.1", "Contesto e condizioni ambientali"), ("4.2", "Parti interessate"), ("4.3", "Campo di applicazione")]),
                  ("5", "Leadership", [("5.1", "Leadership e impegno"), ("5.2", "Politica ambientale"), ("5.3", "Ruoli e responsabilità")]),
                  ("6", "Pianificazione", [("6.1.2", "Aspetti ambientali"), ("6.1.3", "Obblighi di conformità"), ("6.1.4", "Pianificazione delle azioni"), ("6.2", "Obiettivi ambientali")]),
                  ("7", "Supporto", _HLS_SUPPORTO),
                  ("8", "Attività operative", [("8.1", "Controllo operativo e ciclo di vita"), ("8.2", "Preparazione e risposta alle emergenze")]),
                  ("9", "Valutazione", [("9.1.1", "Monitoraggio e misurazione"), ("9.1.2", "Valutazione della conformità"), ("9.2", "Audit interno"), ("9.3", "Riesame della direzione")]),
                  ("10", "Miglioramento", [("10.2", "Non conformità e azioni correttive"), ("10.3", "Miglioramento continuo")])],
    },
    "iso45001": {
        "sigla": "ISO 45001", "nome": "Salute e sicurezza", "icona": "🦺", "colore": "coral",
        "intro": "Sistema di gestione per la salute e sicurezza sul lavoro: pericoli identificati, rischi valutati e ridotti con la gerarchia dei controlli, lavoratori consultati e coinvolti. Si integra con il DVR del D.Lgs. 81/08.",
        "registro": "Pericoli e valutazione dei rischi", "voce": "Pericolo", "effetto": "Danno possibile",
        "condizioni": ["Ordinaria", "Straordinaria", "Emergenza"],
        "eventi": ["Infortunio", "Quasi infortunio", "Malattia professionale", "Condizione pericolosa", "Emergenza"],
        "punti": [("4", "Contesto", [("4.1", "Contesto dell'organizzazione"), ("4.2", "Esigenze dei lavoratori e delle parti interessate"), ("4.3", "Campo di applicazione")]),
                  ("5", "Leadership", [("5.1", "Leadership e impegno"), ("5.2", "Politica SSL"), ("5.3", "Ruoli e responsabilità"), ("5.4", "Consultazione e partecipazione dei lavoratori")]),
                  ("6", "Pianificazione", [("6.1.2", "Identificazione dei pericoli e valutazione dei rischi"), ("6.1.3", "Requisiti legali"), ("6.2", "Obiettivi SSL")]),
                  ("7", "Supporto", _HLS_SUPPORTO),
                  ("8", "Attività operative", [("8.1.2", "Eliminare i pericoli e ridurre i rischi"), ("8.1.3", "Gestione del cambiamento"), ("8.1.4", "Appalti e fornitori"), ("8.2", "Emergenze")]),
                  ("9", "Valutazione", [("9.1", "Monitoraggio e misurazione"), ("9.1.2", "Valutazione della conformità"), ("9.2", "Audit interno"), ("9.3", "Riesame della direzione")]),
                  ("10", "Miglioramento", [("10.2", "Incidenti, non conformità e azioni correttive"), ("10.3", "Miglioramento continuo")])],
    },
    "sa8000": {
        "sigla": "SA8000", "nome": "Responsabilità sociale", "icona": "🤝", "colore": "purple",
        "intro": "Standard di responsabilità sociale: condizioni di lavoro dignitose in azienda e lungo la catena di fornitura, con un Social Performance Team che valuta i rischi e gestisce le segnalazioni.",
        "registro": "Valutazione dei rischi sociali", "voce": "Rischio sociale", "effetto": "Persone o requisito coinvolti",
        "condizioni": ["Interno", "Fornitori", "Appalti"],
        "eventi": ["Segnalazione anonima", "Reclamo dei lavoratori", "Reclamo esterno", "Non conformità fornitore", "Verifica esterna"],
        "punti": [("1-8", "Requisiti", [("1", "Lavoro infantile"), ("2", "Lavoro forzato o obbligato"), ("3", "Salute e sicurezza"),
                                        ("4", "Libertà di associazione e contrattazione collettiva"), ("5", "Discriminazione"),
                                        ("6", "Pratiche disciplinari"), ("7", "Orario di lavoro"), ("8", "Retribuzione")]),
                  ("9", "Sistema di gestione", [("9.1", "Politiche, procedure e registrazioni"), ("9.2", "Social Performance Team"),
                                                ("9.3", "Identificazione e valutazione dei rischi"), ("9.4", "Monitoraggio interno"),
                                                ("9.5", "Coinvolgimento interno e comunicazione"), ("9.6", "Gestione dei reclami"),
                                                ("9.7", "Verifica esterna e coinvolgimento delle parti interessate"), ("9.8", "Azioni correttive e preventive"),
                                                ("9.9", "Formazione e sviluppo delle capacità"), ("9.10", "Gestione di fornitori e appaltatori")])],
    },
}
LIVELLI = {0: "Non applicato", 1: "Iniziale", 2: "Parziale", 3: "Applicato", 4: "Applicato e misurato", 5: "Eccellente"}
STATI_OBBLIGO = {"conforme": "Conforme", "in_scadenza": "In scadenza", "da_verificare": "Da verificare", "non_conforme": "Non conforme"}


def owner_only():
    if not current_user.is_owner:
        abort(403)


def _norma(codice):
    if codice not in NORME:
        abort(404)
    return NORME[codice]


def _int(v, lo, hi):
    try:
        n = int(v)
        return n if lo <= n <= hi else None
    except (TypeError, ValueError):
        return None


def _data(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def livello_rischio(p, g):
    """Classe del rischio da probabilità × gravità (1-4 ciascuna)."""
    if not p or not g:
        return None, "—"
    r = p * g
    return r, ("alto" if r >= 9 else "medio" if r >= 4 else "basso")


def stato_obbligo(o, oggi=None):
    oggi = oggi or date.today()
    if o.status == "non_conforme":
        return "non_conforme"
    if o.due_date and o.due_date < oggi:
        return "non_conforme"
    if o.due_date and (o.due_date - oggi).days <= 30:
        return "in_scadenza"
    return o.status or "da_verificare"


def sintesi(codice):
    rischi = MgmtRisk.query.filter_by(standard=codice).all()
    obblighi = ComplianceObligation.query.filter_by(standard=codice).all()
    eventi = MgmtEvent.query.filter_by(standard=codice).all()
    ultima = MgmtAssessment.query.filter_by(standard=codice).order_by(MgmtAssessment.id.desc()).first()
    voti = [v for v in (ultima.scores or {}).values() if isinstance(v, int)] if ultima else []
    return {
        "rischi": len(rischi),
        "rischi_alti": sum(1 for r in rischi if livello_rischio(r.probability, r.severity)[1] == "alto" and r.status != "chiuso"),
        "obblighi": len(obblighi),
        "obblighi_critici": sum(1 for o in obblighi if stato_obbligo(o) in ("non_conforme", "in_scadenza")),
        "eventi_aperti": sum(1 for e in eventi if e.status == "aperto"),
        "eventi_anno": sum(1 for e in eventi if e.event_date and e.event_date.year == date.today().year),
        "maturita": round(sum(voti) / len(voti), 1) if voti else None,
    }


@sistemi_bp.app_context_processor
def _ctx():
    return {"NORME_SISTEMI": NORME}


@sistemi_bp.route("/<codice>")
@login_required
def norma(codice):
    owner_only()
    n = _norma(codice)
    rischi = sorted(MgmtRisk.query.filter_by(standard=codice).all(),
                    key=lambda r: -(livello_rischio(r.probability, r.severity)[0] or 0))
    obblighi = ComplianceObligation.query.filter_by(standard=codice).order_by(ComplianceObligation.due_date.is_(None), ComplianceObligation.due_date).all()
    eventi = MgmtEvent.query.filter_by(standard=codice).order_by(MgmtEvent.event_date.desc()).all()
    ultima = MgmtAssessment.query.filter_by(standard=codice).order_by(MgmtAssessment.id.desc()).first()
    return render_template("sistemi/norma.html", codice=codice, n=n, rischi=rischi, obblighi=obblighi, eventi=eventi,
                           ultima=ultima, s=sintesi(codice), LIVELLI=LIVELLI, STATI_OBBLIGO=STATI_OBBLIGO,
                           livello_rischio=livello_rischio, stato_obbligo=stato_obbligo, tab=request.args.get("tab", "rischi"))


@sistemi_bp.post("/<codice>/rischio")
@login_required
def salva_rischio(codice):
    owner_only()
    _norma(codice)
    rid = request.form.get("id", type=int)
    r = db.get_or_404(MgmtRisk, rid) if rid else MgmtRisk(standard=codice)
    if request.form.get("azione") == "elimina" and rid:
        db.session.delete(r)
    else:
        r.activity = request.form.get("activity", "").strip() or None
        r.item = request.form.get("item", "").strip() or "—"
        r.effect = request.form.get("effect", "").strip() or None
        r.condition = request.form.get("condition") or None
        r.probability = _int(request.form.get("probability"), 1, 4)
        r.severity = _int(request.form.get("severity"), 1, 4)
        r.controls = request.form.get("controls", "").strip() or None
        r.responsible = request.form.get("responsible", "").strip() or None
        r.status = request.form.get("status") or "aperto"
        db.session.add(r)
    db.session.commit()
    flash("Registro aggiornato.", "success")
    return redirect(url_for(".norma", codice=codice, tab="rischi"))


@sistemi_bp.post("/<codice>/obbligo")
@login_required
def salva_obbligo(codice):
    owner_only()
    _norma(codice)
    oid = request.form.get("id", type=int)
    o = db.get_or_404(ComplianceObligation, oid) if oid else ComplianceObligation(standard=codice)
    if request.form.get("azione") == "elimina" and oid:
        db.session.delete(o)
    else:
        o.source = request.form.get("source", "").strip() or None
        o.requirement = request.form.get("requirement", "").strip() or "—"
        o.due_date = _data(request.form.get("due_date"))
        o.responsible = request.form.get("responsible", "").strip() or None
        o.evidence = request.form.get("evidence", "").strip() or None
        o.status = request.form.get("status") if request.form.get("status") in STATI_OBBLIGO else "da_verificare"
        db.session.add(o)
    db.session.commit()
    flash("Obblighi aggiornati.", "success")
    return redirect(url_for(".norma", codice=codice, tab="obblighi"))


@sistemi_bp.post("/<codice>/evento")
@login_required
def salva_evento(codice):
    owner_only()
    _norma(codice)
    eid = request.form.get("id", type=int)
    e = db.get_or_404(MgmtEvent, eid) if eid else MgmtEvent(standard=codice)
    e.kind = request.form.get("kind") or None
    e.event_date = _data(request.form.get("event_date")) or date.today()
    e.description = request.form.get("description", "").strip() or "—"
    e.cause = request.form.get("cause", "").strip() or None
    e.action = request.form.get("action", "").strip() or None
    e.lost_days = _int(request.form.get("lost_days"), 0, 9999)
    e.status = "chiuso" if request.form.get("status") == "chiuso" else "aperto"
    db.session.add(e)
    db.session.commit()
    flash("Evento registrato.", "success")
    return redirect(url_for(".norma", codice=codice, tab="eventi"))


@sistemi_bp.post("/<codice>/autovalutazione")
@login_required
def salva_autovalutazione(codice):
    owner_only()
    n = _norma(codice)
    scores, notes = {}, {}
    for _, _, punti in n["punti"]:
        for cod, _ in punti:
            v = _int(request.form.get(f"s_{cod}"), 0, 5)
            if v is not None:
                scores[cod] = v
            t = request.form.get(f"n_{cod}", "").strip()
            if t:
                notes[cod] = t[:500]
    db.session.add(MgmtAssessment(standard=codice, scores=scores, notes=notes,
                                  assessor=request.form.get("assessor", "").strip() or current_user.name))
    db.session.commit()
    flash("Autovalutazione salvata.", "success")
    return redirect(url_for(".norma", codice=codice, tab="autovalutazione"))
