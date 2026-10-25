"""Statistiche e grafici per il Riesame della Direzione, calcolati dai dati
GIA' tracciati dal programma (non conformità 8D, verifiche ispettive
interne, piani di miglioramento) — nessun numero è stimato o inventato,
sono conteggi reali sul database.

I grafici sono immagini PNG (matplotlib, backend 'Agg' non interattivo):
si possono mostrare inline nella pagina del riesame (base64) e incollare
nel verbale stampato (.docx)."""
import base64
import io
from calendar import month_abbr

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .models import NonConformity8D, AuditPlanItem, ManagementReviewActionItem

MESI_IT = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]


def _figura_a_png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def png_a_base64(png_bytes):
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def dati_nc_per_anno(anno):
    """Conteggio reale delle non conformità 8D aperte in un anno, mese per
    mese, più il totale dell'anno precedente per il confronto."""
    nc_anno = NonConformity8D.query.filter(
        NonConformity8D.opened_at >= f"{anno}-01-01", NonConformity8D.opened_at <= f"{anno}-12-31").all()
    per_mese = [0] * 12
    for nc in nc_anno:
        per_mese[nc.opened_at.month - 1] += 1
    totale_anno_prec = NonConformity8D.query.filter(
        NonConformity8D.opened_at >= f"{anno - 1}-01-01", NonConformity8D.opened_at <= f"{anno - 1}-12-31").count()
    return {
        "anno": anno,
        "per_mese": per_mese,
        "totale_anno": len(nc_anno),
        "totale_anno_precedente": totale_anno_prec,
        "chiuse": sum(1 for nc in nc_anno if nc.status == "chiusa"),
        "aperte": sum(1 for nc in nc_anno if nc.status == "aperta"),
    }


def grafico_nc_per_mese(dati):
    """Grafico a barre delle NC aperte mese per mese nell'anno di riferimento."""
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.bar(MESI_IT, dati["per_mese"], color="#4472C4")
    ax.set_title(f"Non conformità 8D aperte per mese — {dati['anno']}")
    ax.set_ylabel("N° NC")
    ax.set_yticks(range(0, max(dati["per_mese"] + [1]) + 2))
    fig.tight_layout()
    return _figura_a_png(fig)


def dati_audit_per_anno(anno):
    """Conteggio reale delle verifiche ispettive interne pianificate per
    anno, per stato (pianificata/eseguita/annullata)."""
    voci = AuditPlanItem.query.filter_by(year=anno).all()
    conteggi = {"pianificata": 0, "eseguita": 0, "annullata": 0}
    for v in voci:
        conteggi[v.status] = conteggi.get(v.status, 0) + 1
    return {"anno": anno, "totale": len(voci), "per_stato": conteggi}


def grafico_audit_per_stato(dati):
    fig, ax = plt.subplots(figsize=(5, 3))
    etichette = ["Pianificata", "Eseguita", "Annullata"]
    valori = [dati["per_stato"].get("pianificata", 0), dati["per_stato"].get("eseguita", 0),
              dati["per_stato"].get("annullata", 0)]
    colori = ["#ED7D31", "#70AD47", "#A6A6A6"]
    ax.bar(etichette, valori, color=colori)
    ax.set_title(f"Verifiche ispettive interne — stato {dati['anno']}")
    ax.set_ylabel("N° aree")
    ax.set_yticks(range(0, max(valori + [1]) + 2))
    fig.tight_layout()
    return _figura_a_png(fig)


def dati_piani_miglioramento(review):
    """Conteggio reale delle righe già inserite nelle due tabelle dei piani
    di miglioramento di questo riesame."""
    precedenti = [i for i in review.action_items if i.kind == "verifica_precedente"]
    nuovi = [i for i in review.action_items if i.kind == "nuova_proposta"]
    return {"verifica_precedente": len(precedenti), "nuova_proposta": len(nuovi)}
