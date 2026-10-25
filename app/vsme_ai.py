"""Generazione assistita da AI di bozze testuali per gli indicatori narrativi
del Registro VSME (moduli N1-N5, BP1-BP11 e le voci non numeriche del Modulo
Base).

Principio di sicurezza: l'AI non inventa MAI fatti sull'azienda (politiche,
certificazioni, governance, iniziative...). Riformula in un testo scorrevole
e professionale solo gli appunti che la Direzione ha già scritto nel campo
"Note" dell'indicatore, integrando eventuali numeri già tracciati dal
programma (dati_vivi). Se le note sono vuote, la generazione viene rifiutata
con un messaggio esplicito: prima servono almeno alcuni appunti puntati da
formalizzare.

La bozza generata resta SEMPRE in stato "da_compilare": la validazione e il
passaggio a "completato" restano una scelta esplicita della Direzione dopo
aver riletto il testo.
"""
import json
import os
import urllib.error
import urllib.request

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
ANTHROPIC_VERSION = "2023-06-01"

SYSTEM_PROMPT = (
    "Sei un assistente che aiuta l'ufficio qualità di una PMI manifatturiera italiana "
    "a redigere in bella forma un paragrafo per la Relazione sulla Sostenibilità VSME ESRS "
    "(standard EFRAG). Scrivi in italiano, tono professionale e sobrio, terza persona "
    "singolare o plurale societario, frasi chiare e non enfatiche. "
    "REGOLA ASSOLUTA: non aggiungere MAI fatti, numeri, politiche, certificazioni o "
    "iniziative che non ti sono stati esplicitamente forniti negli appunti dell'utente o "
    "nei dati indicati come 'dati reali dal programma'. Il tuo compito è solo riformulare "
    "e organizzare in un testo scorrevole ciò che ti viene fornito, non arricchirlo con "
    "contenuti plausibili ma non confermati. Se un aspetto tipico di questa informativa "
    "non è coperto dagli appunti forniti, non menzionarlo. Lunghezza: 60-150 parole. "
    "Restituisci solo il paragrafo finale, senza titoli, elenchi puntati o premesse."
)


class BozzaAIError(Exception):
    pass


def genera_bozza_testo(indicator, appunti, ragione_sociale, sede_legale, dati_vivi=None):
    """Genera una bozza di paragrafo a partire dagli appunti della Direzione.
    Solleva BozzaAIError con un messaggio parlante se la chiave API non è
    configurata, se gli appunti sono vuoti o se la chiamata fallisce."""
    if not appunti or not appunti.strip():
        raise BozzaAIError(
            "Scrivi prima qualche appunto/punto elenco nel campo Note: l'AI li riformula "
            "in un paragrafo, ma non deve inventare i contenuti da sola."
        )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise BozzaAIError(
            "Variabile d'ambiente ANTHROPIC_API_KEY non configurata su Railway: "
            "serve una chiave API Anthropic per generare le bozze."
        )

    righe_contesto = [
        f"Azienda: {ragione_sociale}",
        f"Sede: {sede_legale}",
        f"Modulo VSME: {indicator.module_code} — {indicator.module_name}",
        f"Informativa da redigere: {indicator.indicator_name}",
    ]
    if indicator.description:
        righe_contesto.append(f"Guida alla compilazione di questa informativa: {indicator.description}")
    if dati_vivi:
        righe_contesto.append(
            "Dati reali già tracciati dal programma (usali solo se pertinenti a questa "
            f"informativa, non forzarli): dipendenti attivi {dati_vivi.get('dipendenti_attivi')}, "
            f"ore di lavoro registrate nell'anno {dati_vivi.get('ore_registrate')}, "
            f"controlli qualità eseguiti {dati_vivi.get('controlli_totali')} "
            f"(non conformi {dati_vivi.get('controlli_non_conformi')})."
        )
    righe_contesto.append(f"Appunti della Direzione da riformulare in un paragrafo:\n{appunti.strip()}")

    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 500,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": "\n".join(righe_contesto)}],
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
