from datetime import date
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from .extensions import db
from .models import VsmeIndicator
from .vsme_ai import genera_bozza_testo, BozzaAIError

vsme_bp = Blueprint("vsme", __name__, url_prefix="/vsme")


def owner_only():
    if not current_user.is_owner:
        abort(403)


# Registro standard degli indicatori del Modulo Base VSME ESRS (EFRAG, gennaio
# 2024), adattato a una PMI manifatturiera per rendicontazione volontaria.
# Struttura: (codice_modulo, nome_modulo, indicatore, unità, guida alla compilazione)
VSME_INDICATORI_BASE = [
    ("B1", "Criteri per la Redazione",
     "Forma giuridica e attività principale (settore)", None,
     "Denominazione, forma giuridica e settore/attività prevalente dell'impresa."),
    ("B1", "Criteri per la Redazione",
     "Sede legale e stabilimenti produttivi", None,
     "Elenco delle sedi/stabilimenti oggetto della rendicontazione."),
    ("B1", "Criteri per la Redazione",
     "Numero medio dipendenti nell'anno (ULA)", "n.",
     "Unità Lavorative Annue medie nel periodo di rendicontazione."),
    ("B1", "Criteri per la Redazione",
     "Perimetro di rendicontazione", None,
     "Indicare se il report copre la singola sede o è consolidato su più sedi/società."),
    ("B1", "Criteri per la Redazione",
     "Periodo e standard di rendicontazione", None,
     "Anno di riferimento e conferma dell'adozione dello Standard VSME ESRS - Modulo Base, su base volontaria."),

    ("B2", "Pratiche per la Transizione verso un'Economia più Sostenibile",
     "Policy o piano di transizione verso la sostenibilità", None,
     "Sì/No ed eventuale descrizione sintetica delle politiche adottate."),
    ("B2", "Pratiche per la Transizione verso un'Economia più Sostenibile",
     "Obiettivi di riduzione delle emissioni definiti", None,
     "Sì/No; se sì, indicare target e orizzonte temporale."),
    ("B2", "Pratiche per la Transizione verso un'Economia più Sostenibile",
     "Iniziative di sostenibilità pianificate nei prossimi 12 mesi", None,
     "Elenco sintetico delle azioni programmate."),

    ("B3", "Energia ed Emissioni di Gas a Effetto Serra",
     "Consumo totale di energia", "kWh/anno",
     "Somma dei consumi energetici annui (bollette elettriche + altri vettori convertiti in kWh)."),
    ("B3", "Energia ed Emissioni di Gas a Effetto Serra",
     "di cui da fonti fossili", "kWh/anno", "Quota parte del consumo totale da fonti non rinnovabili."),
    ("B3", "Energia ed Emissioni di Gas a Effetto Serra",
     "di cui da fonti rinnovabili", "kWh/anno",
     "Quota parte da fonti rinnovabili (da bolletta o da produzione propria, es. fotovoltaico)."),
    ("B3", "Energia ed Emissioni di Gas a Effetto Serra",
     "Percentuale di energia rinnovabile sul totale", "%", "Rinnovabile / consumo totale di energia."),
    ("B3", "Energia ed Emissioni di Gas a Effetto Serra",
     "Consumo di combustibili per riscaldamento", "litri o mc/anno",
     "Es. litri di gasolio o mc di gas metano consumati nell'anno."),
    ("B3", "Energia ed Emissioni di Gas a Effetto Serra",
     "Emissioni dirette di gas a effetto serra - Scope 1", "tCO2eq",
     "Emissioni da fonti controllate direttamente dall'impresa (es. combustione, mezzi aziendali)."),
    ("B3", "Energia ed Emissioni di Gas a Effetto Serra",
     "Emissioni indirette da energia acquistata - Scope 2", "tCO2eq",
     "Emissioni associate all'energia elettrica/termica acquistata."),
    ("B3", "Energia ed Emissioni di Gas a Effetto Serra",
     "Altre emissioni indirette - Scope 3 (se disponibili)", "tCO2eq",
     "Facoltativo: emissioni lungo la catena del valore, se calcolabili."),
    ("B3", "Energia ed Emissioni di Gas a Effetto Serra",
     "Intensità emissiva", "tCO2eq/€ fatturato", "Emissioni totali (Scope 1+2) rapportate al fatturato annuo."),

    ("B4", "Inquinamento di Aria, Acqua e Suolo",
     "Sostanze inquinanti emesse in aria", "tipologia e kg",
     "Elenco delle sostanze e quantità emesse, se soggette a monitoraggio/autorizzazione."),
    ("B4", "Inquinamento di Aria, Acqua e Suolo",
     "Sostanze inquinanti scaricate in acqua", "tipologia e kg", "Da autorizzazioni allo scarico, se presenti."),
    ("B4", "Inquinamento di Aria, Acqua e Suolo",
     "Sostanze inquinanti rilasciate nel suolo", "tipologia e kg", "Se pertinente all'attività svolta."),
    ("B4", "Inquinamento di Aria, Acqua e Suolo",
     "Autorizzazioni ambientali in essere", None, "Es. AUA, AIA o altre autorizzazioni ambientali rilevanti."),

    ("B5", "Biodiversità",
     "Siti in aree sensibili sotto il profilo della biodiversità", None,
     "Sì/No; distanza dalle aree protette più vicine."),
    ("B5", "Biodiversità",
     "Superficie totale dei siti", "mq", "Superficie complessiva degli stabilimenti."),
    ("B5", "Biodiversità",
     "Superficie impermeabilizzata", "mq", "Superficie coperta da edifici/piazzali non permeabili."),
    ("B5", "Biodiversità",
     "Iniziative di tutela/conservazione della biodiversità", None,
     "Es. aree verdi, piantumazioni, altre iniziative volontarie."),

    ("B6", "Acqua",
     "Livello di stress idrico dell'area", None,
     "Da strumenti pubblici (es. WRI Water Risk Atlas) per l'area in cui si trova lo stabilimento."),
    ("B6", "Acqua",
     "Prelievo idrico totale", "mc/anno", "Acqua prelevata da qualsiasi fonte entro i confini organizzativi."),
    ("B6", "Acqua",
     "Consumo idrico totale", "mc/anno", "Acqua prelevata e non restituita all'ambiente."),
    ("B6", "Acqua",
     "Percentuale di acqua riciclata/riutilizzata", "%", "Se applicabile al ciclo produttivo."),
    ("B6", "Acqua",
     "Scarichi idrici", "mc/anno", "Volume scaricato, se soggetto ad autorizzazione."),

    ("B7", "Uso delle Risorse, Economia Circolare e Gestione dei Rifiuti",
     "Materiali in ingresso per tipologia e peso", "kg/anno",
     "Es. kg di ferro, plastica, vernici, solventi acquistati nell'anno."),
    ("B7", "Uso delle Risorse, Economia Circolare e Gestione dei Rifiuti",
     "Percentuale di materiali riciclati in ingresso", "%", "Quota di materiale riciclato sul totale acquistato."),
    ("B7", "Uso delle Risorse, Economia Circolare e Gestione dei Rifiuti",
     "Percentuale di materiali/imballaggi da fonti certificate sostenibili", "%",
     "Es. materiali con certificazione FSC o equivalente."),
    ("B7", "Uso delle Risorse, Economia Circolare e Gestione dei Rifiuti",
     "Rifiuti totali generati", "kg o t/anno", "Totale rifiuti prodotti nell'anno, da registro/formulari."),
    ("B7", "Uso delle Risorse, Economia Circolare e Gestione dei Rifiuti",
     "di cui rifiuti pericolosi", "kg o t/anno", None),
    ("B7", "Uso delle Risorse, Economia Circolare e Gestione dei Rifiuti",
     "di cui rifiuti non pericolosi", "kg o t/anno", None),
    ("B7", "Uso delle Risorse, Economia Circolare e Gestione dei Rifiuti",
     "Percentuale di rifiuti avviati a riciclo/recupero", "%", "Quota di rifiuti non destinata a smaltimento."),

    ("B8", "Forza Lavoro - Caratteristiche Generali",
     "Numero totale dipendenti a fine periodo", "n.", "Testa di conteggio a fine anno."),
    ("B8", "Forza Lavoro - Caratteristiche Generali",
     "Suddivisione per genere", "n.", "Numero di dipendenti uomini/donne/altro."),
    ("B8", "Forza Lavoro - Caratteristiche Generali",
     "Suddivisione per tipo di contratto", "n.", "Determinato / indeterminato."),
    ("B8", "Forza Lavoro - Caratteristiche Generali",
     "Suddivisione per tipo di orario", "n.", "Tempo pieno / tempo parziale."),
    ("B8", "Forza Lavoro - Caratteristiche Generali",
     "Paese/i in cui opera la forza lavoro", None, "Rilevante se si opera in più paesi."),
    ("B8", "Forza Lavoro - Caratteristiche Generali",
     "Tasso di turnover del personale", "%", "Uscite nell'anno / organico medio."),

    ("B9", "Forza Lavoro - Salute e Sicurezza",
     "Numero di infortuni sul lavoro nel periodo", "n.", None),
    ("B9", "Forza Lavoro - Salute e Sicurezza",
     "Tasso di infortuni per 100 lavoratori equivalenti", "n.", "Standard EFRAG: infortuni x 100 / ULA."),
    ("B9", "Forza Lavoro - Salute e Sicurezza",
     "Numero di decessi per infortunio sul lavoro", "n.", None),
    ("B9", "Forza Lavoro - Salute e Sicurezza",
     "Giornate lavorative perse per infortuni/malattie professionali", "gg", None),

    ("B10", "Forza Lavoro - Retribuzione, Contrattazione Collettiva e Formazione",
     "Rapporto tra salario di ingresso e salario minimo applicabile", "rapporto",
     "Solo se rilevante rispetto al CCNL applicato."),
    ("B10", "Forza Lavoro - Retribuzione, Contrattazione Collettiva e Formazione",
     "Divario retributivo di genere (pay gap)", "%", None),
    ("B10", "Forza Lavoro - Retribuzione, Contrattazione Collettiva e Formazione",
     "Percentuale di dipendenti coperti da contrattazione collettiva", "%", None),
    ("B10", "Forza Lavoro - Retribuzione, Contrattazione Collettiva e Formazione",
     "Ore medie di formazione erogate per dipendente", "ore", None),
    ("B10", "Forza Lavoro - Retribuzione, Contrattazione Collettiva e Formazione",
     "Ore di formazione suddivise per genere/categoria", "ore", None),

    ("B11", "Lavoratori nella Catena del Valore, Comunità Interessate, Consumatori e Utilizzatori Finali",
     "Processo per identificare impatti sui lavoratori della catena di fornitura", None,
     "Sì/No; descrizione sintetica se presente."),
    ("B11", "Lavoratori nella Catena del Valore, Comunità Interessate, Consumatori e Utilizzatori Finali",
     "Segnalazioni/incidenti relativi a diritti umani nella catena del valore", "n.", None),
    ("B11", "Lavoratori nella Catena del Valore, Comunità Interessate, Consumatori e Utilizzatori Finali",
     "Iniziative di coinvolgimento della comunità locale", None,
     "Es. rapporti con scuole, enti locali, iniziative sul territorio."),
    ("B11", "Lavoratori nella Catena del Valore, Comunità Interessate, Consumatori e Utilizzatori Finali",
     "Iniziative rivolte a consumatori/utilizzatori finali", None, None),

    ("B12", "Condotta delle Imprese",
     "Policy anticorruzione adottata", None, "Sì/No."),
    ("B12", "Condotta delle Imprese",
     "Numero di condanne per corruzione attiva/passiva nel periodo", "n.", None),
    ("B12", "Condotta delle Imprese",
     "Importo delle ammende per violazioni anticorruzione", "€", None),
    ("B12", "Condotta delle Imprese",
     "Formazione anticorruzione erogata", "ore o n. persone", None),
]

# Modulo Narrativo-PAT (Politiche, Azioni e Obiettivi) dello Standard VSME ESRS
# (EFRAG, gennaio 2024). Informative N1-N5: a differenza del Modulo Base, sono
# prevalentemente narrative — ogni riga rappresenta un punto di informativa da
# descrivere in testo libero nel campo valore/note.
VSME_INDICATORI_NARRATIVE = [
    ("N1", "Strategia: Modello Aziendale e Iniziative di Sostenibilità",
     "Modello di business e attività principale", None,
     "Descrizione sintetica del modello di business, dei prodotti/servizi offerti e dei mercati/clienti serviti."),
    ("N1", "Strategia: Modello Aziendale e Iniziative di Sostenibilità",
     "Iniziative di sostenibilità collegate al modello di business", None,
     "Iniziative in corso o pianificate che si riflettono nel modo in cui l'impresa opera."),

    ("N2", "Questioni Rilevanti di Sostenibilità",
     "Processo di identificazione dei temi materiali", None,
     "Come sono stati individuati i temi ambientali, sociali e di governance rilevanti per l'impresa."),
    ("N2", "Questioni Rilevanti di Sostenibilità",
     "Elenco dei temi materiali individuati", None,
     "Elenco sintetico dei temi ESG ritenuti rilevanti (es. sicurezza sul lavoro, gestione rifiuti, qualità di prodotto...)."),

    ("N3", "Gestione delle Questioni Rilevanti di Sostenibilità",
     "Politiche adottate per ciascun tema materiale", None,
     "Politiche, anche informali, con cui l'impresa affronta i temi materiali individuati in N2."),
    ("N3", "Gestione delle Questioni Rilevanti di Sostenibilità",
     "Azioni e obiettivi collegati", None,
     "Azioni concrete intraprese o pianificate, con eventuali obiettivi quantitativi e scadenze."),

    ("N4", "Principali Portatori di Interessi",
     "Mappatura degli stakeholder", None,
     "Elenco dei principali portatori di interesse (dipendenti, clienti, fornitori, comunità locale...)."),
    ("N4", "Principali Portatori di Interessi",
     "Modalità di coinvolgimento e comunicazione", None,
     "Come e con quale frequenza l'impresa dialoga con i propri stakeholder."),

    ("N5", "Governance: Responsabilità in Materia di Sostenibilità",
     "Struttura di governance e responsabilità assegnate", None,
     "Chi, nell'organizzazione, ha la responsabilità delle questioni di sostenibilità (es. Direzione, Responsabile Qualità)."),
    ("N5", "Governance: Responsabilità in Materia di Sostenibilità",
     "Sistemi di gestione e certificazioni adottate", None,
     "Es. ISO 9001, ISO 45001, ISO 14001 o altri sistemi/certificazioni in essere."),
    ("N5", "Governance: Responsabilità in Materia di Sostenibilità",
     "Compliance: azioni legali, sanzioni o non conformità significative nel periodo", None,
     "Dare atto dell'eventuale assenza (o presenza) di azioni legali, sanzioni ambientali/sociali o non conformità rilevanti nell'anno."),
]

# Modulo Partner Commerciali (BP) dello Standard VSME ESRS (EFRAG, gennaio
# 2024). Informative BP1-BP11: destinate principalmente a investitori,
# finanziatori e partner della catena del valore.
VSME_INDICATORI_BP = [
    ("BP1", "Ricavi in Alcuni Settori",
     "Presenza in settori sensibili", None,
     "Dare atto se l'impresa opera in settori quali armi controverse, tabacco, combustibili fossili, sostanze chimiche controverse."),

    ("BP2", "Indice di Diversità di Genere negli Organi di Governance",
     "Composizione per genere dell'organo di governance", "%",
     "Percentuale di componenti donne sul totale dell'organo amministrativo/di governance."),
    ("BP2", "Indice di Diversità di Genere negli Organi di Governance",
     "Fasce di età rappresentate", None, None),

    ("BP3", "Obiettivo di Riduzione delle Emissioni di Gas a Effetto Serra",
     "Obiettivo di riduzione emissioni Scope 1/2 definito", None,
     "Sì/No; se sì, indicare percentuale di riduzione target e anno di riferimento."),

    ("BP4", "Piano di Transizione per la Mitigazione dei Cambiamenti Climatici",
     "Iniziative e leve di decarbonizzazione", None,
     "Elenco sintetico delle iniziative (efficienza energetica, fonti rinnovabili, mobilità, ecc.)."),

    ("BP5", "Rischi Fisici da Cambiamento Climatico",
     "Valutazione dei rischi fisici climatici rilevanti", None,
     "Es. rischio idrogeologico, eventi meteo estremi, in relazione alla sede/stabilimento."),

    ("BP6", "Indice Rifiuti Pericolosi e/o Radioattivi",
     "Quantità di rifiuti pericolosi e/o radioattivi", "kg o t/anno",
     "Quota di rifiuti pericolosi/radioattivi sul totale dei rifiuti prodotti (vedi anche B7)."),

    ("BP7", "Allineamento con gli Strumenti Riconosciuti a Livello Internazionale",
     "Allineamento con Principi Guida ONU / Dichiarazione ILO / Linee Guida OCSE", None,
     "Sì/No; descrizione sintetica se presente un impegno formale."),

    ("BP8", "Processi per Monitorare la Conformità e Meccanismi per Affrontare le Violazioni",
     "Processi di monitoraggio conformità e canali di segnalazione", None,
     "Es. audit interni/esterni, procedure di reclamo, canali di whistleblowing."),

    ("BP9", "Violazione delle Linee Guida OCSE o dei Principi Guida ONU (forza lavoro)",
     "Violazioni registrate nel periodo", None,
     "Dare atto dell'eventuale assenza (o presenza) di violazioni relative alla forza lavoro nel periodo di rendicontazione."),

    ("BP10", "Equilibrio tra Vita Professionale e Vita Privata",
     "Percentuale di dipendenti con diritto al congedo familiare", "%", None),
    ("BP10", "Equilibrio tra Vita Professionale e Vita Privata",
     "Percentuale di dipendenti che ne ha usufruito", "%", None),

    ("BP11", "Numero di Apprendisti",
     "Numero di apprendisti nel periodo di rendicontazione", "n.", None),
]


def seed_vsme_indicators(anno=None):
    """Precarica il registro standard (Base + Narrativo-PAT + Partner Commerciali)
    per l'anno indicato, se non già presente. Non tocca mai i valori già
    compilati: aggiunge solo le voci mancanti."""
    anno = anno or date.today().year
    tutte_le_voci = VSME_INDICATORI_BASE + VSME_INDICATORI_NARRATIVE + VSME_INDICATORI_BP
    for posizione, (codice, nome_modulo, indicatore, unita, guida) in enumerate(tutte_le_voci, start=1):
        esiste = VsmeIndicator.query.filter_by(year=anno, module_code=codice, indicator_name=indicatore).first()
        if esiste:
            continue
        db.session.add(VsmeIndicator(
            year=anno, module_code=codice, module_name=nome_modulo, indicator_name=indicatore,
            unit=unita, description=guida, sort_order=posizione,
        ))
    db.session.commit()


def _moduli_ordinati():
    """Elenco ordinato (B1..B12, N1..N5, BP1..BP11) dei codici/nomi modulo,
    dedotto dai registri standard."""
    visti = []
    for codice, nome, *_ in VSME_INDICATORI_BASE + VSME_INDICATORI_NARRATIVE + VSME_INDICATORI_BP:
        if codice not in [c for c, _ in visti]:
            visti.append((codice, nome))
    return visti


def modulo_pillar(codice):
    """Raggruppamento in Pillar dello Standard VSME ESRS: Modulo Base (B1-B12),
    Modulo Narrativo-PAT (N1-N5), Modulo Partner Commerciali (BP1-BP11)."""
    if codice.startswith("BP"):
        return "Partner Commerciali"
    if codice.startswith("N"):
        return "Narrativo-PAT"
    return "Base"


# Testi guida mostrati nell'interfaccia per spiegare, in modo che sia chiaro
# anche a chi non conosce lo standard, quali informative sono il nucleo
# volontario minimo (Modulo Base) e quali sono invece approfondimenti da
# compilare SOLO se richiesti da un soggetto terzo (banca, investitore,
# grande cliente/capogruppo soggetta a CSRD che chiede dati alla filiera).
PILLAR_INFO = {
    "Base": {
        "badge": "SEMPRE",
        "titolo": "Modulo Base — nucleo minimo dello Standard VSME",
        "nota": ("È la parte dello Standard VSME ESRS che ogni impresa che adotta la "
                 "rendicontazione volontaria compila comunque: dati quantitativi essenziali "
                 "su ambiente, personale e condotta d'impresa (informative B1-B12)."),
    },
    "Narrativo-PAT": {
        "badge": "SOLO SU RICHIESTA",
        "titolo": "Approfondimento facoltativo — Politiche, Azioni e Obiettivi (N1-N5)",
        "nota": ("Da compilare solo se richiesto da una banca, un finanziatore o un grande "
                 "cliente/capogruppo che necessita di maggior dettaglio narrativo su "
                 "strategia, temi materiali, politiche e governance della sostenibilità. "
                 "Non è richiesto per la sola dichiarazione volontaria di base."),
    },
    "Partner Commerciali": {
        "badge": "SOLO SU RICHIESTA",
        "titolo": "Approfondimento facoltativo — Dati per Partner Commerciali (BP1-BP11)",
        "nota": ("Da compilare solo se richiesto da banche, investitori o grandi clienti "
                 "della filiera (tipicamente una capogruppo soggetta a CSRD che deve "
                 "raccogliere dati ESG dai propri fornitori, o un istituto di credito per "
                 "un finanziamento sostenibile). Non è richiesto per la sola dichiarazione "
                 "volontaria di base."),
    },
}


def _moduli_per_pillar(indicatori):
    """Costruisce l'elenco dei moduli con voci e progressi, suddiviso nei tre
    pillar (Base / Narrativo-PAT / Partner Commerciali), nell'ordine dello
    standard. Usato sia dal registro di lavoro sia dall'estratto pubblicabile."""
    moduli = []
    for codice, nome in _moduli_ordinati():
        voci = [i for i in indicatori if i.module_code == codice]
        completati = len([v for v in voci if v.status != "da_compilare"])
        moduli.append({
            "codice": codice, "nome": nome, "pillar": modulo_pillar(codice),
            "voci": voci, "totale": len(voci), "completati": completati,
        })
    moduli_base = [m for m in moduli if m["pillar"] == "Base"]
    moduli_narrativi = [m for m in moduli if m["pillar"] == "Narrativo-PAT"]
    moduli_bp = [m for m in moduli if m["pillar"] == "Partner Commerciali"]
    return moduli, moduli_base, moduli_narrativi, moduli_bp


def _totali(moduli):
    voci = [v for m in moduli for v in m["voci"]]
    return len(voci), len([v for v in voci if v.status != "da_compilare"])


@vsme_bp.route("/")
@login_required
def index():
    owner_only()
    anno_corrente = date.today().year
    anno = request.args.get("anno", type=int) or anno_corrente
    anni_disponibili = sorted({i.year for i in VsmeIndicator.query.all()} | {anno_corrente}, reverse=True)
    seed_vsme_indicators(anno)  # idempotente: aggiunge solo le voci mancanti, non tocca quelle compilate
    indicatori = VsmeIndicator.query.filter_by(year=anno).order_by(VsmeIndicator.sort_order).all()
    moduli, moduli_base, moduli_narrativi, moduli_bp = _moduli_per_pillar(indicatori)
    totale_base, completati_base = _totali(moduli_base)
    totale_facoltativi, completati_facoltativi = _totali(moduli_narrativi + moduli_bp)
    totale_voci = len(indicatori)
    totale_completati = len([i for i in indicatori if i.status != "da_compilare"])
    return render_template(
        "vsme/index.html", moduli=moduli, anno=anno, anni_disponibili=anni_disponibili,
        moduli_base=moduli_base, moduli_narrativi=moduli_narrativi, moduli_bp=moduli_bp,
        pillar_info=PILLAR_INFO,
        totale_base=totale_base, completati_base=completati_base,
        totale_facoltativi=totale_facoltativi, completati_facoltativi=completati_facoltativi,
        totale_voci=totale_voci, totale_completati=totale_completati,
    )


@vsme_bp.post("/nuovo-anno")
@login_required
def nuovo_anno():
    owner_only()
    anno = request.form.get("anno", type=int) or date.today().year
    seed_vsme_indicators(anno)
    flash(f"Registro indicatori VSME predisposto per l'anno {anno}.", "success")
    return redirect(url_for("vsme.index", anno=anno))


@vsme_bp.post("/<int:indicator_id>/aggiorna")
@login_required
def aggiorna(indicator_id):
    owner_only()
    i = db.get_or_404(VsmeIndicator, indicator_id)
    i.value = request.form.get("value", "").strip() or None
    i.notes = request.form.get("notes", "").strip() or None
    stato = request.form.get("status", i.status)
    if stato in ("da_compilare", "completato", "non_applicabile"):
        i.status = stato
    i.publish_on_site = request.form.get("publish_on_site") == "on"
    db.session.commit()
    return redirect(url_for("vsme.index", anno=i.year, _anchor=f"ind-{i.id}"))


@vsme_bp.post("/<int:indicator_id>/genera-bozza")
@login_required
def genera_bozza(indicator_id):
    owner_only()
    i = db.get_or_404(VsmeIndicator, indicator_id)
    from flask import current_app
    from .vsme_report import _dati_qualita_governance
    try:
        dati_vivi = _dati_qualita_governance(i.year)
        bozza = genera_bozza_testo(
            indicator=i, appunti=i.notes,
            ragione_sociale=current_app.config["RAGIONE_SOCIALE"],
            sede_legale=current_app.config["SEDE_LEGALE"],
            dati_vivi=dati_vivi,
        )
        i.value = bozza
        db.session.commit()
        flash("Bozza generata dall'AI: rileggila e correggila prima di segnarla come completata.", "success")
    except BozzaAIError as exc:
        flash(str(exc), "error")
    return redirect(url_for("vsme.index", anno=i.year, _anchor=f"ind-{i.id}"))


@vsme_bp.route("/anno/<int:anno>/pubblica")
@login_required
def pubblica(anno):
    """Vista di sola lettura, in formato 'pronto per il sito', dei soli
    indicatori compilati e marcati come pubblicabili."""
    owner_only()
    indicatori = (VsmeIndicator.query.filter_by(year=anno, publish_on_site=True)
                  .filter(VsmeIndicator.status == "completato")
                  .order_by(VsmeIndicator.sort_order).all())
    moduli, moduli_base, moduli_narrativi, moduli_bp = _moduli_per_pillar(indicatori)
    # Nell'estratto pubblicabile mostriamo solo i moduli che hanno almeno una voce
    moduli_base = [m for m in moduli_base if m["voci"]]
    moduli_narrativi = [m for m in moduli_narrativi if m["voci"]]
    moduli_bp = [m for m in moduli_bp if m["voci"]]
    return render_template(
        "vsme/pubblica.html", anno=anno, pillar_info=PILLAR_INFO,
        moduli_base=moduli_base, moduli_narrativi=moduli_narrativi, moduli_bp=moduli_bp,
    )
