"""Generazione assistita da AI di bozze testuali per i punti del Riesame
della Direzione ("cosa va bene" / "cosa non va").

Stesso principio di sicurezza già usato per il VSME (vedi app/vsme_ai.py):
l'AI non inventa MAI fatti, numeri o giudizi sull'azienda. Riformula in un
testo scorrevole solo gli appunti puntati che la Direzione ha già scritto,
integrando eventuali dati reali già tracciati dal programma (es. numero di
non conformità aperte nell'anno). Se non ci sono appunti, la generazione
viene rifiutata: prima serve almeno qualche appunto da formalizzare.

La bozza generata resta SEMPRE da rileggere e correggere: non salva mai
automaticamente come definitiva.
"""
import json
import os
import urllib.error
import urllib.request

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM_PROMPT = (
    "Sei un assistente che aiuta la Direzione di una PMI manifatturiera italiana (settore "
    "carpenteria/saldatura) a redigere in bella forma un punto del Verbale di Riesame della "
    "Direzione (ISO 9001:2015 §9.3), nello stesso stile sobrio e diretto già usato in azienda. "
    "Scrivi in italiano, terza persona, frasi chiare, senza enfasi. "
    "REGOLA ASSOLUTA: non aggiungere MAI fatti, numeri, cause o giudizi che non ti sono stati "
    "esplicitamente forniti negli appunti dell'utente o nei 'dati reali dal programma'. Riformula "
    "e organizza solo ciò che ti viene fornito, non arricchirlo con contenuti plausibili ma non "
    "confermati. Se un aspetto tipico di questo punto non è coperto dagli appunti, non menzionarlo. "
    "Restituisci ESATTAMENTE due paragrafi, nell'ordine seguente, ciascuno introdotto dalla sua "
    "etichetta esatta su una riga a sé stante e nient'altro prima o dopo:\n"
    "COSA VA BENE:\n<paragrafo, o \"Nessun elemento positivo indicato.\" se gli appunti non ne parlano>\n"
    "COSA NON VA:\n<paragrafo, o \"Nessuna criticità indicata.\" se gli appunti non ne parlano>"
)


class BozzaAIError(Exception):
    pass


def _chiama_anthropic(messaggio_utente):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise BozzaAIError(
            "Variabile d'ambiente ANTHROPIC_API_KEY non configurata su Railway: "
            "serve una chiave API Anthropic per generare le bozze."
        )
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 600,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": messaggio_utente}],
    }
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        dettaglio = exc.read().decode("utf-8", errors="ignore")
        raise BozzaAIError(f"Errore dall'API Anthropic ({exc.code}): {dettaglio[:300]}")
    except urllib.error.URLError as exc:
        raise BozzaAIError(f"Impossibile contattare l'API Anthropic: {exc.reason}")
    blocchi_testo = [b.get("text", "") for b in body.get("content", []) if b.get("type") == "text"]
    testo = "\n".join(blocchi_testo).strip()
    if not testo:
        raise BozzaAIError("L'API ha risposto senza testo utilizzabile. Riprova.")
    return testo


def _dividi_positivo_negativo(testo):
    """Divide la risposta dell'AI in (cosa_va_bene, cosa_non_va) cercando le
    due etichette. Se il formato non torna, restituisce tutto come 'cosa va
    bene' per non perdere il testo generato."""
    marcatore_pos = "COSA VA BENE:"
    marcatore_neg = "COSA NON VA:"
    if marcatore_pos in testo and marcatore_neg in testo:
        prima, dopo = testo.split(marcatore_neg, 1)
        positivo = prima.split(marcatore_pos, 1)[-1].strip()
        negativo = dopo.strip()
        return positivo or None, negativo or None
    return testo.strip() or None, None


def genera_bozza_sezione(section, appunti_positivi, appunti_negativi, ragione_sociale, dati_vivi=None):
    """Genera una bozza di analisi (cosa va bene / cosa non va) per un punto
    del riesame, a partire dagli appunti già scritti dalla Direzione (in uno
    dei due campi, o entrambi) e dai dati reali del programma per quel punto."""
    appunti_positivi = (appunti_positivi or "").strip()
    appunti_negativi = (appunti_negativi or "").strip()
    if not appunti_positivi and not appunti_negativi:
        raise BozzaAIError(
            "Scrivi prima qualche appunto puntato (anche solo poche parole) in 'Cosa va bene' "
            "e/o 'Cosa non va': l'AI li riformula in un testo scorrevole, ma non deve inventare "
            "i contenuti da sola."
        )
    righe = [
        f"Azienda: {ragione_sociale}",
        f"Punto del riesame da redigere: {section.title}",
    ]
    if dati_vivi:
        righe.append(f"Dati reali già tracciati dal programma per questo punto: {dati_vivi}")
    if appunti_positivi:
        righe.append(f"Appunti della Direzione su cosa va bene:\n{appunti_positivi}")
    if appunti_negativi:
        righe.append(f"Appunti della Direzione su cosa non va / criticità:\n{appunti_negativi}")
    testo = _chiama_anthropic("\n\n".join(righe))
    return _dividi_positivo_negativo(testo)


# Per ogni punto del riesame, quali dati reali del programma passare
# all'AI come contesto (solo numeri già tracciati, mai stime).
def dati_vivi_per_sezione(section_key, review):
    from .riesame_stats import dati_nc_per_anno, dati_audit_per_anno
    anno = int(review.reference_period) if (review.reference_period or "").isdigit() else review.review_date.year - 1
    if section_key == "nonconformities":
        d = dati_nc_per_anno(anno)
        return (f"non conformità 8D aperte nel {anno}: {d['totale_anno']} (anno precedente: "
                f"{d['totale_anno_precedente']}), di cui chiuse {d['chiuse']} e ancora aperte {d['aperte']}.")
    if section_key == "internal_audit":
        d = dati_audit_per_anno(anno)
        return (f"verifiche ispettive interne pianificate nel {anno}: {d['totale']} "
                f"(eseguite {d['per_stato'].get('eseguita', 0)}, pianificate {d['per_stato'].get('pianificata', 0)}, "
                f"annullate {d['per_stato'].get('annullata', 0)}).")
    return None
