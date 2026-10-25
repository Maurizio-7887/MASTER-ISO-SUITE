"""Sistema di gestione dell'innovazione secondo la famiglia ISO 56000.

ISO 56001 (requisiti, certificabile) e ISO 56002 (linee guida) descrivono lo stesso
schema: contesto, leadership e strategia, pianificazione, supporto, processi di
innovazione, valutazione delle prestazioni, miglioramento. Qui diventano:

1) Strategia e politica dell'innovazione (§5, §6.2)
2) Opportunità e idee con valutazione a punteggio (§8.3.2)
3) Portafoglio progetti a fasi e gate (§8.3.3-8.3.6)
4) Indicatori del sistema (§9.1)
5) Autovalutazione di maturità per capitolo (§9.2-9.3, §10)
"""
from collections import Counter
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from .extensions import db
from .models import InnovationGate, InnovationIdea, InnovationMaturity, InnovationProject, InnovationStrategy

innovazione_bp = Blueprint("innovazione", __name__, url_prefix="/innovazione")

# Le fasi del processo di innovazione (ISO 56002 §8.3)
FASI = {
    1: ("Opportunità", "Identificare le opportunità: bisogni dei clienti, tecnologie, problemi del processo."),
    2: ("Concetto", "Creare il concetto: soluzione, valore atteso, ipotesi da verificare."),
    3: ("Validazione", "Validare il concetto con prove, prototipi, clienti pilota e caso economico."),
    4: ("Sviluppo", "Sviluppare la soluzione: progetto, investimento, formazione delle persone."),
    5: ("Implementazione", "Mettere in uso la soluzione e misurare il beneficio realizzato."),
    6: ("Chiuso", "Progetto concluso: risultati, lezioni apprese, proprietà intellettuale."),
}
DECISIONI = {"avanti": "Avanti alla fase successiva", "attesa": "In attesa (mancano evidenze)",
             "ripeti": "Ripeti la fase", "stop": "Stop: il progetto si ferma"}
FONTI = {"interna": "Persone dell'azienda", "cliente": "Cliente", "fornitore": "Fornitore",
         "universita": "Università / centro di ricerca", "bando": "Bando o finanziamento", "tecnologia": "Scouting tecnologico"}
TIPI = ["prodotto", "processo", "organizzativa", "modello di business"]
ORIZZONTI = {"incrementale": "Incrementale", "adiacente": "Adiacente", "radicale": "Radicale (breakthrough)"}
TECNOLOGIE = ["Automazione e robotica", "RFID e tracciabilità", "IoT e dati macchina", "Intelligenza artificiale",
              "Software gestionale", "Nuovi materiali", "Processo di saldatura", "Energia e sostenibilità", "Altro"]

# Autovalutazione di maturità: capitoli e punti della norma, con la domanda guida
MATURITA = [
    ("4", "Contesto", [
        ("4.1", "Contesto dell'organizzazione", "Conosciamo tendenze di mercato, tecnologie e concorrenti che possono cambiare il nostro business?"),
        ("4.2", "Parti interessate", "Sappiamo cosa si aspettano clienti, persone, fornitori e territorio dall'innovazione?"),
        ("4.4", "Sistema di gestione", "L'innovazione ha un processo definito o succede per caso?")]),
    ("5", "Leadership", [
        ("5.1", "Impegno della direzione", "La direzione dedica tempo, risorse e attenzione all'innovazione?"),
        ("5.2", "Politica e visione", "Esiste una visione e una politica dell'innovazione comunicata a tutti?"),
        ("5.3", "Ruoli e responsabilità", "È chiaro chi coordina l'innovazione e chi decide ai gate?")]),
    ("6", "Pianificazione", [
        ("6.1", "Rischi e opportunità", "Valutiamo rischi e opportunità delle iniziative, accettando il rischio in modo consapevole?"),
        ("6.2", "Obiettivi di innovazione", "Abbiamo obiettivi di innovazione misurabili e collegati alla strategia?"),
        ("6.3", "Portafoglio", "Gestiamo un portafoglio equilibrato tra miglioramenti incrementali e progetti radicali?")]),
    ("7", "Supporto", [
        ("7.1", "Risorse", "Ci sono tempo, budget, spazi e partner dedicati all'innovazione?"),
        ("7.2", "Competenze", "Le persone hanno competenze di creatività, sperimentazione e gestione progetti?"),
        ("7.4", "Comunicazione", "Le idee circolano e i risultati vengono condivisi?"),
        ("7.6", "Strumenti e metodi", "Usiamo metodi come design thinking, lean startup, prototipazione rapida?"),
        ("7.7", "Proprietà intellettuale", "Proteggiamo e valorizziamo marchi, brevetti, know-how?")]),
    ("8", "Processi di innovazione", [
        ("8.3.2", "Identificare le opportunità", "Raccogliamo sistematicamente idee e segnali dall'interno e dall'esterno?"),
        ("8.3.3", "Creare i concetti", "Trasformiamo le idee in concetti chiari con valore atteso e ipotesi?"),
        ("8.3.4", "Validare i concetti", "Verifichiamo le ipotesi con prove e clienti prima di investire molto?"),
        ("8.3.5", "Sviluppare le soluzioni", "Sviluppiamo le soluzioni con tempi, costi e responsabilità sotto controllo?"),
        ("8.3.6", "Implementare le soluzioni", "Portiamo le soluzioni in produzione o sul mercato e ne misuriamo l'effetto?")]),
    ("9", "Valutazione", [
        ("9.1", "Indicatori", "Misuriamo idee, progetti, investimenti e benefici dell'innovazione?"),
        ("9.2", "Audit interno", "Verifichiamo periodicamente il sistema di gestione dell'innovazione?"),
        ("9.3", "Riesame della direzione", "La direzione riesamina portafoglio e risultati almeno una volta l'anno?")]),
    ("10", "Miglioramento", [
        ("10.1", "Miglioramento continuo", "Impariamo dai progetti fermati e dai successi, e cambiamo il modo di lavorare?")]),
]
LIVELLI = {0: "Assente", 1: "Iniziale", 2: "Ripetibile", 3: "Definito", 4: "Gestito con indicatori", 5: "Ottimizzato"}


def owner_only():
    if not current_user.is_owner:
        abort(403)


def _int(v, lo=None, hi=None):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    if lo is not None and n < lo or hi is not None and n > hi:
        return None
    return n


def _num(v):
    v = (v or "").strip().replace("€", "").replace(" ", "")
    if not v:
        return None
    if "," in v:
        v = v.replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def _data(v):
    try:
        return date.fromisoformat(v) if v else None
    except ValueError:
        return None


def _prossimo_codice(model, prefisso):
    anno = date.today().year
    n = model.query.filter(model.code.like(f"{prefisso}-{anno}-%")).count() + 1
    return f"{prefisso}-{anno}-{n:03d}"


def indicatori(anno=None):
    """Indicatori del sistema di gestione dell'innovazione (ISO 56001 §9.1)."""
    anno = anno or date.today().year
    idee = InnovationIdea.query.all()
    idee_anno = [i for i in idee if i.submitted_at and i.submitted_at.year == anno]
    valutate = [i for i in idee_anno if i.priority is not None]
    progetti = InnovationProject.query.all()
    attivi = [p for p in progetti if p.status == "attivo"]
    chiusi = [p for p in progetti if p.status in ("chiuso_successo", "chiuso_stop")]
    successi = [p for p in chiusi if p.status == "chiuso_successo"]
    budget = sum(float(p.budget or 0) for p in attivi)
    speso = sum(float(p.spent or 0) for p in progetti)
    beneficio_atteso = sum(float(p.expected_benefit or 0) for p in attivi)
    beneficio_realizzato = sum(float(p.realized_benefit or 0) for p in progetti)
    per_fase = Counter(p.stage for p in attivi)
    per_orizzonte = Counter(p.horizon for p in attivi)
    per_tecnologia = Counter(p.technology or "—" for p in attivi)
    persone = {i.proposer for i in idee_anno if i.proposer}
    return {
        "anno": anno,
        "idee_anno": len(idee_anno),
        "idee_valutate_pct": round(100 * len(valutate) / len(idee_anno)) if idee_anno else 0,
        "idee_in_progetto": len([i for i in idee_anno if i.status == "progetto"]),
        "proponenti": len(persone),
        "progetti_attivi": len(attivi),
        "tasso_successo": round(100 * len(successi) / len(chiusi)) if chiusi else None,
        "budget_attivi": budget,
        "speso": speso,
        "beneficio_atteso": beneficio_atteso,
        "beneficio_realizzato": beneficio_realizzato,
        "rientro_anni": round(budget / beneficio_atteso, 1) if beneficio_atteso else None,
        "per_fase": [(FASI[f][0], per_fase.get(f, 0)) for f in range(1, 6)],
        "per_orizzonte": [(ORIZZONTI[k], per_orizzonte.get(k, 0)) for k in ORIZZONTI],
        "per_tecnologia": per_tecnologia.most_common(),
    }


@innovazione_bp.app_context_processor
def _costanti():
    return {"FASI_INNOVAZIONE": FASI}


# ------------------------------------------------------------------ cruscotto
@innovazione_bp.route("/")
@login_required
def index():
    owner_only()
    anno = request.args.get("anno", type=int) or date.today().year
    strategia = InnovationStrategy.query.filter_by(year=anno).first()
    ultima = InnovationMaturity.query.order_by(InnovationMaturity.assessed_at.desc()).first()
    return render_template("innovazione/index.html", k=indicatori(anno), strategia=strategia, ultima=ultima,
                           media=_media_maturita(ultima), anno=anno)


# ------------------------------------------------------------------ strategia
@innovazione_bp.route("/strategia", methods=["GET", "POST"])
@login_required
def strategia():
    owner_only()
    anno = request.values.get("anno", type=int) or date.today().year
    s = InnovationStrategy.query.filter_by(year=anno).first()
    if request.method == "POST":
        if s is None:
            s = InnovationStrategy(year=anno)
            db.session.add(s)
        for campo in ("vision", "policy", "focus_areas", "objectives"):
            setattr(s, campo, request.form.get(campo, "").strip() or None)
        s.budget = _num(request.form.get("budget"))
        db.session.commit()
        flash("Strategia dell'innovazione salvata.", "success")
        return redirect(url_for(".strategia", anno=anno))
    return render_template("innovazione/strategia.html", s=s, anno=anno)


# ------------------------------------------------------------------ idee
@innovazione_bp.route("/idee")
@login_required
def idee():
    stato = request.args.get("stato", "")
    q = InnovationIdea.query
    if stato:
        q = q.filter_by(status=stato)
    elenco = sorted(q.all(), key=lambda i: (i.priority is None, -(i.priority or 0), i.submitted_at), reverse=False)
    return render_template("innovazione/idee.html", idee=elenco, stato=stato, FONTI=FONTI, TIPI=TIPI, TECNOLOGIE=TECNOLOGIE)


@innovazione_bp.post("/idee/nuova")
@login_required
def nuova_idea():
    """Aperta a tutti gli utenti: chiunque in azienda può proporre un'idea."""
    titolo = request.form.get("title", "").strip()
    if not titolo:
        flash("Scrivi almeno il titolo dell'idea.", "error")
        return redirect(url_for(".idee"))
    i = InnovationIdea(code=_prossimo_codice(InnovationIdea, "ID"), title=titolo[:200],
                       description=request.form.get("description", "").strip() or None,
                       proposer=request.form.get("proposer", "").strip() or current_user.name,
                       source=request.form.get("source") if request.form.get("source") in FONTI else "interna",
                       kind=request.form.get("kind") if request.form.get("kind") in TIPI else "processo",
                       area=request.form.get("area", "").strip() or None,
                       technology=request.form.get("technology") or None)
    db.session.add(i)
    db.session.commit()
    flash(f"Idea {i.code} registrata. Grazie!", "success")
    return redirect(url_for(".idee"))


@innovazione_bp.post("/idee/<int:idea_id>/valuta")
@login_required
def valuta_idea(idea_id):
    owner_only()
    i = db.get_or_404(InnovationIdea, idea_id)
    for campo in ("score_value", "score_feasibility", "score_fit", "score_risk"):
        setattr(i, campo, _int(request.form.get(campo), 1, 5))
    i.evaluation_notes = request.form.get("evaluation_notes", "").strip() or None
    nuovo = request.form.get("status")
    if nuovo in ("proposta", "in_valutazione", "approvata", "scartata"):
        i.status = nuovo
    elif i.priority is not None and i.status == "proposta":
        i.status = "in_valutazione"
    db.session.commit()
    flash(f"Valutazione dell'idea {i.code} salvata" + (f": priorità {i.priority}." if i.priority else "."), "success")
    return redirect(url_for(".idee"))


@innovazione_bp.post("/idee/<int:idea_id>/progetto")
@login_required
def idea_in_progetto(idea_id):
    owner_only()
    i = db.get_or_404(InnovationIdea, idea_id)
    if i.project_id:
        return redirect(url_for(".progetto", project_id=i.project_id))
    p = InnovationProject(code=_prossimo_codice(InnovationProject, "PI"), title=i.title, objective=i.description,
                          kind=i.kind, technology=i.technology, stage=2, start_date=date.today(),
                          responsible=current_user.name)
    db.session.add(p)
    db.session.flush()
    db.session.add(InnovationGate(project_id=p.id, from_stage=1, to_stage=2, decision="avanti",
                                  decided_by=current_user.name,
                                  evidence=f"Idea {i.code} approvata, priorità {i.priority or '—'}."))
    i.status, i.project_id = "progetto", p.id
    db.session.commit()
    flash(f"Progetto {p.code} aperto dall'idea {i.code}.", "success")
    return redirect(url_for(".progetto", project_id=p.id))


# ------------------------------------------------------------------ progetti
@innovazione_bp.route("/progetti")
@login_required
def progetti():
    owner_only()
    tutti = InnovationProject.query.order_by(InnovationProject.status, InnovationProject.stage.desc()).all()
    colonne = {f: [p for p in tutti if p.status in ("attivo", "sospeso") and p.stage == f] for f in range(1, 6)}
    chiusi = [p for p in tutti if p.status.startswith("chiuso")]
    return render_template("innovazione/progetti.html", colonne=colonne, chiusi=chiusi, ORIZZONTI=ORIZZONTI,
                           TIPI=TIPI, TECNOLOGIE=TECNOLOGIE)


@innovazione_bp.post("/progetti/nuovo")
@login_required
def nuovo_progetto():
    owner_only()
    titolo = request.form.get("title", "").strip()
    if not titolo:
        flash("Indica il titolo del progetto.", "error")
        return redirect(url_for(".progetti"))
    p = InnovationProject(code=_prossimo_codice(InnovationProject, "PI"), title=titolo[:200], start_date=date.today(),
                          horizon=request.form.get("horizon") if request.form.get("horizon") in ORIZZONTI else "incrementale",
                          kind=request.form.get("kind") if request.form.get("kind") in TIPI else "processo",
                          technology=request.form.get("technology") or None, responsible=current_user.name)
    db.session.add(p)
    db.session.commit()
    return redirect(url_for(".progetto", project_id=p.id))


@innovazione_bp.route("/progetti/<int:project_id>", methods=["GET", "POST"])
@login_required
def progetto(project_id):
    owner_only()
    p = db.get_or_404(InnovationProject, project_id)
    if request.method == "POST":
        for campo in ("title", "objective", "responsible", "team", "funding", "ip_notes", "lessons"):
            setattr(p, campo, (request.form.get(campo) or "").strip() or None)
        p.title = p.title or "Progetto senza titolo"
        if request.form.get("kind") in TIPI:
            p.kind = request.form.get("kind")
        if request.form.get("horizon") in ORIZZONTI:
            p.horizon = request.form.get("horizon")
        p.technology = request.form.get("technology") or None
        for campo in ("start_date", "target_date"):
            setattr(p, campo, _data(request.form.get(campo)))
        for campo in ("budget", "spent", "expected_benefit", "realized_benefit"):
            setattr(p, campo, _num(request.form.get(campo)))
        db.session.commit()
        flash("Progetto aggiornato.", "success")
        return redirect(url_for(".progetto", project_id=p.id))
    return render_template("innovazione/progetto.html", p=p, DECISIONI=DECISIONI, ORIZZONTI=ORIZZONTI, TIPI=TIPI,
                           TECNOLOGIE=TECNOLOGIE)


@innovazione_bp.post("/progetti/<int:project_id>/gate")
@login_required
def gate(project_id):
    owner_only()
    p = db.get_or_404(InnovationProject, project_id)
    decisione = request.form.get("decision")
    if decisione not in DECISIONI or p.status.startswith("chiuso"):
        abort(400)
    da = p.stage
    if decisione == "avanti":
        p.stage = min(6, p.stage + 1)
        p.status = "attivo"
        if p.stage == 6:
            p.status, p.end_date = "chiuso_successo", date.today()
    elif decisione == "attesa":
        p.status = "sospeso"
    elif decisione == "ripeti":
        p.status = "attivo"
    elif decisione == "stop":
        p.status, p.end_date = "chiuso_stop", date.today()
    db.session.add(InnovationGate(project_id=p.id, from_stage=da, to_stage=p.stage, decision=decisione,
                                  decided_by=request.form.get("decided_by", "").strip() or current_user.name,
                                  evidence=request.form.get("evidence", "").strip() or None))
    db.session.commit()
    flash(f"Gate registrato: {DECISIONI[decisione]}.", "success")
    return redirect(url_for(".progetto", project_id=p.id))


# ------------------------------------------------------------------ maturità
def _media_maturita(m):
    if not m or not m.scores:
        return None
    voti = [v for v in m.scores.values() if isinstance(v, int)]
    return round(sum(voti) / len(voti), 1) if voti else None


def medie_capitoli(m):
    out = []
    for cap, nome, punti in MATURITA:
        voti = [m.scores.get(cod) for cod, *_ in punti if isinstance(m.scores.get(cod), int)] if m else []
        out.append((cap, nome, round(sum(voti) / len(voti), 1) if voti else 0))
    return out


@innovazione_bp.route("/maturita", methods=["GET", "POST"])
@login_required
def maturita():
    owner_only()
    if request.method == "POST":
        scores, notes = {}, {}
        for _, _, punti in MATURITA:
            for cod, *_ in punti:
                v = _int(request.form.get(f"s_{cod}"), 0, 5)
                if v is not None:
                    scores[cod] = v
                n = request.form.get(f"n_{cod}", "").strip()
                if n:
                    notes[cod] = n[:500]
        m = InnovationMaturity(assessor=request.form.get("assessor", "").strip() or current_user.name,
                               scores=scores, notes=notes, summary=request.form.get("summary", "").strip() or None)
        db.session.add(m)
        db.session.commit()
        flash(f"Autovalutazione salvata: maturità media {_media_maturita(m)} su 5.", "success")
        return redirect(url_for(".maturita"))
    storico = InnovationMaturity.query.order_by(InnovationMaturity.assessed_at.desc(), InnovationMaturity.id.desc()).all()
    ultima = storico[0] if storico else None
    precedente = storico[1] if len(storico) > 1 else None
    return render_template("innovazione/maturita.html", MATURITA=MATURITA, LIVELLI=LIVELLI, ultima=ultima,
                           precedente=precedente, storico=storico, capitoli=medie_capitoli(ultima),
                           capitoli_prec=medie_capitoli(precedente) if precedente else None, media=_media_maturita(ultima),
                           media_fn=_media_maturita)
