"""Allegato al Bilancio - Relazione sulla Sostenibilità VSME ESRS.

Genera una vista stampabile, strutturata come lo Standard VSME ESRS (EFRAG,
gennaio 2024) nella sua versione completa (Opzione D: Modulo Base + Modulo
Narrativo-PAT + Modulo Partner Commerciali), popolata SOLO con:
  1) i valori compilati a mano nel Registro Indicatori VSME (VsmeIndicator);
  2) dati già tracciati automaticamente dal programma (controlli qualità,
     obiettivi, rischi, ore di lavoro registrate).
Nessun dato o testo di terzi: le sezioni non compilate restano segnalate
come "da compilare" invece di essere indovinate o inventate.
"""
from collections import defaultdict
from datetime import date, datetime
import re

from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required

from .extensions import db
from .models import (VsmeIndicator, NonConformity8D, QualityObjective, QualityRisk,
                      TrainingCourse, User)
from .vsme import _moduli_ordinati, modulo_pillar, seed_vsme_indicators

vsme_report_bp = Blueprint("vsme_report", __name__, url_prefix="/vsme/allegato")


def owner_only():
    if not current_user.is_owner:
        abort(403)


ESITO_LABEL = {"conforme": "NC chiuse", "non_conforme": "Non conforme", "da_verificare": "NC aperte"}
STATO_OBIETTIVO_LABEL = {"raggiunto": "Raggiunto", "non_raggiunto": "Non raggiunto", "in_corso": "In corso"}
STATO_RISCHIO_LABEL = {"aperto": "Aperto", "mitigato": "Mitigato", "chiuso": "Chiuso"}
LIVELLO_RISCHIO_LABEL = {"alto": "Alto", "medio": "Medio", "basso": "Basso"}


def _dati_qualita_governance(anno):
    """Indicatori di processo realmente tracciati dal programma per l'anno
    di rendicontazione: controlli qualità, obiettivi, rischi, ore registrate.
    Servono da supporto oggettivo alle informative N3/N5/BP5/BP8 del modulo
    narrativo, e non sostituiscono la compilazione manuale del registro."""
    inizio = datetime(anno, 1, 1)
    fine = datetime(anno + 1, 1, 1)

    # Non conformità dell'anno (registro 8D): aperte e chiuse
    ncs = (NonConformity8D.query
           .filter(NonConformity8D.opened_at >= inizio.date(), NonConformity8D.opened_at < fine.date())
           .all())
    esiti = defaultdict(int)
    for c in ncs:
        esiti["da_verificare" if c.status == "aperta" else "conforme"] += 1
    controlli_totali = len(ncs)
    controlli_non_conformi = esiti.get("da_verificare", 0)

    obiettivi = QualityObjective.query.filter_by(year=anno).all()
    obiettivi_stato = defaultdict(int)
    for o in obiettivi:
        obiettivi_stato[o.status] += 1

    rischi = (QualityRisk.query
              .filter(QualityRisk.created_at >= inizio, QualityRisk.created_at < fine)
              .all())
    rischi_livello = defaultdict(int)
    rischi_stato = defaultdict(int)
    for r in rischi:
        rischi_livello[r.livello] += 1
        rischi_stato[r.status] += 1

    # Formazione erogata nell'anno: ore dei corsi e persone coinvolte
    corsi = (TrainingCourse.query
             .filter(TrainingCourse.start_date >= inizio.date(), TrainingCourse.start_date < fine.date())
             .all())
    ore_totali = round(sum(float(c.hours or 0) for c in corsi), 1)
    operatori_coinvolti = len({(a.user_id, a.employee_id) for c in corsi for a in c.attendances})

    dipendenti_attivi = User.query.filter_by(active=True).count()

    return {
        "controlli_totali": controlli_totali,
        "controlli_non_conformi": controlli_non_conformi,
        "controlli_per_esito": {ESITO_LABEL.get(k, k): v for k, v in esiti.items()},
        "obiettivi_totali": len(obiettivi),
        "obiettivi_per_stato": {STATO_OBIETTIVO_LABEL.get(k, k): v for k, v in obiettivi_stato.items()},
        "rischi_totali": len(rischi),
        "rischi_per_livello": {LIVELLO_RISCHIO_LABEL.get(k, k): v for k, v in rischi_livello.items()},
        "rischi_per_stato": {STATO_RISCHIO_LABEL.get(k, k): v for k, v in rischi_stato.items()},
        "ore_registrate": ore_totali,
        "operatori_coinvolti": operatori_coinvolti,
        "dipendenti_attivi": dipendenti_attivi,
    }


def _estrai_numero(testo):
    """Estrae il primo numero da un testo compilato a mano (es. '12,5 tCO2eq'
    -> 12.5). Ritorna None se non trova nulla di numerico: nessun valore
    viene mai indovinato."""
    if not testo:
        return None
    m = re.search(r"[-+]?\d+(?:[.,]\d+)?", str(testo))
    if not m:
        return None
    return float(m.group(0).replace(",", "."))


def _grafici_da_valori_compilati(indicatori):
    """Costruisce grafici a partire da indicatori del Modulo Base compilati
    a mano con un valore numerico, quando pertinenti a un confronto (Scope
    1/2/3, rifiuti pericolosi/non pericolosi). Un grafico compare solo se
    TUTTI i valori che lo compongono sono stati compilati con un numero."""
    per_nome = {i.indicator_name: i.value for i in indicatori}

    grafici = {}

    s1 = _estrai_numero(per_nome.get("Emissioni dirette di gas a effetto serra - Scope 1"))
    s2 = _estrai_numero(per_nome.get("Emissioni indirette da energia acquistata - Scope 2"))
    s3 = _estrai_numero(per_nome.get("Altre emissioni indirette - Scope 3 (se disponibili)"))
    valori_scope = [(l, v) for l, v in (("Scope 1", s1), ("Scope 2", s2), ("Scope 3", s3)) if v is not None]
    if len(valori_scope) >= 2:
        grafici["emissioni_scope"] = {
            "labels": [l for l, _ in valori_scope], "data": [v for _, v in valori_scope], "unita": "tCO2eq",
        }

    rp = _estrai_numero(per_nome.get("di cui rifiuti pericolosi"))
    rnp = _estrai_numero(per_nome.get("di cui rifiuti non pericolosi"))
    if rp is not None and rnp is not None:
        grafici["rifiuti"] = {
            "labels": ["Rifiuti pericolosi", "Rifiuti non pericolosi"], "data": [rp, rnp], "unita": "kg o t/anno",
        }

    return grafici


@vsme_report_bp.route("/<int:anno>")
@login_required
def allegato(anno):
    owner_only()
    seed_vsme_indicators(anno)  # idempotente: aggiunge solo le voci mancanti, non tocca quelle compilate
    indicatori = VsmeIndicator.query.filter_by(year=anno).order_by(VsmeIndicator.sort_order).all()

    moduli = []
    for codice, nome in _moduli_ordinati():
        voci = [i for i in indicatori if i.module_code == codice]
        moduli.append({
            "codice": codice, "nome": nome, "pillar": modulo_pillar(codice),
            "voci": voci, "totale": len(voci),
            "completati": len([v for v in voci if v.status != "da_compilare"]),
        })

    moduli_base = [m for m in moduli if m["pillar"] == "Base"]
    moduli_narrativi = [m for m in moduli if m["pillar"] == "Narrativo-PAT"]
    moduli_bp = [m for m in moduli if m["pillar"] == "Partner Commerciali"]

    totale_voci = len(indicatori)
    totale_completati = len([i for i in indicatori if i.status != "da_compilare"])

    dati_vivi = _dati_qualita_governance(anno)
    grafici_manuali = _grafici_da_valori_compilati(indicatori)

    return render_template(
        "vsme_report/allegato.html",
        anno=anno, data_generazione=date.today(),
        moduli_base=moduli_base, moduli_narrativi=moduli_narrativi, moduli_bp=moduli_bp,
        moduli_tutti=moduli,
        totale_voci=totale_voci, totale_completati=totale_completati,
        dati_vivi=dati_vivi, grafici_manuali=grafici_manuali,
    )
