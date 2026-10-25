"""Dati dimostrativi di un'azienda simulata: ACME Saldature Srl.

Carpenteria metallica e saldatura conto terzi, 28 addetti: saldatura robotizzata e
manuale, puntatura, taglio laser, piegatura. Persone, clienti, fornitori e numeri sono
inventati e servono a esercitazioni, corsi e dimostrazioni. Il caricamento è
idempotente: parte solo se l'archivio è vuoto.
"""
from datetime import date, datetime, timedelta

from .extensions import db
from .models import (AuditPlanItem, AuditReport, AuditReportFinding, CalibrationDevice, CalibrationRecord,
                     InnovationGate, InnovationIdea, InnovationMaturity, InnovationProject, InnovationStrategy,
                     Machine, MaintenanceLog, MaintenancePlanItem, ManagementReview, ManagementReviewActionItem,
                     NonConformity8D, PolyvalenceColumn, PolyvalenceEmployee, PolyvalenceEntry, PolyvalenceMatrix,
                     Qualification, QualityAction, QualityObjective, QualityRisk, TrainingAttendance, TrainingCourse,
                     TrainingEmployee, User)

UTENTI = [("Laura Bianchi · Direzione", "9999", "owner"), ("Paolo Neri · Responsabile qualità", "1111", "owner"),
          ("Marco Rossi · Saldatore", "1234", "operator"), ("Giulia Verdi · Controllo qualità", "2345", "operator"),
          ("Luca Marini · Manutentore", "3456", "operator")]
REPARTO = ["Andrea Conti", "Sara Gallo", "Davide Moretti", "Elena Riva", "Karim Haddad", "Ion Popescu",
           "Matteo Greco", "Chiara Fontana"]


def carica_demo():
    if User.query.first():
        return
    oggi = date.today()
    anno = oggi.year
    d = lambda giorni: oggi + timedelta(days=giorni)  # noqa: E731

    utenti = []
    for nome, pin, ruolo in UTENTI:
        u = User(name=nome, pin=pin, role=ruolo)
        db.session.add(u)
        utenti.append(u)
    persone = [TrainingEmployee(full_name=n) for n in REPARTO]
    db.session.add_all(persone)
    db.session.flush()

    # ---------------------------------------------------------------- macchine e manutenzione (§7.1.3)
    macchine = [("RB-01", "Robot di saldatura MIG/MAG cella 1", "Robot", "Saldatura robot"),
                ("RB-02", "Robot di saldatura MIG/MAG cella 2", "Robot", "Saldatura robot"),
                ("PT-01", "Saldopuntatrice a colonna 100 kVA", "Saldopuntatrice", "Puntatura"),
                ("LS-01", "Taglio laser fibra 6 kW", "Taglio", "Taglio lamiera"),
                ("PG-01", "Pressa piegatrice 170 t", "Piegatura", "Piegatura"),
                ("SM-01", "Saldatrice manuale TIG", "Saldatrice", "Saldatura manuale")]
    for i, (cod, nome, cat, area) in enumerate(macchine):
        m = Machine(code=cod, name=nome, category=cat, area=area, manufacturer="Costruttore Esempio",
                    responsible="Luca Marini")
        db.session.add(m)
        db.session.flush()
        p1 = MaintenancePlanItem(machine_id=m.id, intervention="Pulizia ugelli, controllo cavi e masse",
                                 frequency="Settimanale", next_due=d(3 + i))
        p2 = MaintenancePlanItem(machine_id=m.id, intervention="Verifica parametri e calibrazione TCP/elettrodi",
                                 frequency="Semestrale", next_due=d(-5 if i == 2 else 40 + 10 * i))
        db.session.add_all([p1, p2])
        db.session.flush()
        db.session.add(MaintenanceLog(machine_id=m.id, plan_item_id=p1.id, kind="programmata",
                                      intervention=p1.intervention, operator_id=utenti[4].id, hours=1,
                                      performed_at=datetime.combine(d(-4), datetime.min.time())))
        if i == 0:
            db.session.add(MaintenanceLog(machine_id=m.id, kind="straordinaria", intervention="Sostituzione guaina filo e rullini trainafilo",
                                          operator_id=utenti[4].id, hours=2.5, notes="Fermo macchina 3 ore",
                                          performed_at=datetime.combine(d(-20), datetime.min.time())))

    # ---------------------------------------------------------------- tarature (§7.1.5)
    strumenti = [("01", "Calibro digitale 0-200 mm", "CD-200-01", "Annuale", -300, 65, "0,01 mm"),
                 ("02", "Micrometro centesimale 0-25 mm", "MC-25-01", "Annuale", -380, -15, "0,01 mm"),
                 ("03", "Calibro per saldature (gauge cordoni)", "GS-01", "Biennale", -200, 530, "0,5 mm"),
                 ("04", "Pinza amperometrica per verifica parametri", "PA-01", "Annuale", -100, 265, "± 1,5%"),
                 ("05", "Spessimetro a ultrasuoni", "UT-01", "Annuale", -350, 15, "0,1 mm")]
    for sch, nome, cod, freq, ult, pros, tol in strumenti:
        dev = CalibrationDevice(sheet_number=sch, name=nome, code=cod, assigned_to="Controllo qualità", frequency=freq,
                                last_check=d(ult), next_due=d(pros), resolution_tolerance=tol, supplier="Laboratorio Metrologico Demo")
        db.session.add(dev)
        db.session.flush()
        db.session.add(CalibrationRecord(device_id=dev.id, checked_at=d(ult), next_due=d(pros), outcome="conforme",
                                         responsible="Giulia Verdi", notes="Certificato di taratura con riferibilità"))

    # ---------------------------------------------------------------- formazione e qualifiche (§7.2)
    corsi = [("Formazione generale e specifica sicurezza (rischio alto)", "Sicurezza", -150, 16, "RSPP esterno"),
             ("Carrelli elevatori: abilitazione", "Muletti", -90, 12, "Ente formativo Demo"),
             ("Qualifica saldatori ISO 9606-1: preparazione e prova", "Saldatura", -60, 24, "Coordinatore di saldatura"),
             ("Consapevolezza ISO 9001 e gestione delle non conformità", "Qualità", -30, 4, "Responsabile qualità"),
             ("Lettura del disegno e simboli di saldatura ISO 2553", "Tecnica", 20, 8, "Ufficio tecnico")]
    for j, (tit, area, giorni, ore, doc) in enumerate(corsi):
        c = TrainingCourse(title=tit, topic_area=area, start_date=d(giorni), end_date=d(giorni + 1), hours=ore, teacher=doc)
        db.session.add(c)
        db.session.flush()
        if giorni < 0:
            for p in persone[j:j + 5]:
                db.session.add(TrainingAttendance(course_id=c.id, employee_id=p.id, outcome="superato"))
            db.session.add(TrainingAttendance(course_id=c.id, user_id=utenti[2].id, outcome="superato"))
    db.session.add_all([
        Qualification(user_id=utenti[2].id, kind="attestato", title="Qualifica saldatore ISO 9606-1 135 P BW FM1 S t10",
                      reference_number="QS-0001", issuing_body="Ente di certificazione Demo", issue_date=d(-55), expiry_date=d(675)),
        Qualification(user_id=utenti[1].id, kind="nomina", title="Coordinatore di saldatura (ISO 14731)",
                      reference_number="NOM-01", issuing_body="Direzione", issue_date=d(-400)),
    ])

    # ---------------------------------------------------------------- polivalenza
    mat = PolyvalenceMatrix(business_unit="Carpenteria e saldatura")
    db.session.add(mat)
    db.session.flush()
    colonne = [("Saldatura", "Robot"), ("Saldatura", "TIG manuale"), ("Saldatura", "MIG manuale"),
               ("Lamiera", "Taglio laser"), ("Lamiera", "Piegatura"), ("Indiretti", "Controllo qualità"), ("Indiretti", "Carrellista")]
    cols = []
    for k, (g, l) in enumerate(colonne, start=1):
        c = PolyvalenceColumn(matrix_id=mat.id, group_label=g, label=l, sequence=k)
        db.session.add(c)
        cols.append(c)
    emps = []
    for k, n in enumerate(REPARTO[:6], start=1):
        e = PolyvalenceEmployee(matrix_id=mat.id, full_name=n, sequence=k)
        db.session.add(e)
        emps.append(e)
    db.session.flush()
    livelli = [[4, 2, 3, 0, 1, 0, 2], [1, 4, 3, 0, 0, 2, 0], [3, 0, 2, 4, 2, 0, 3], [0, 0, 1, 2, 4, 1, 3],
               [2, 3, 4, 0, 0, 0, 1], [0, 0, 0, 1, 1, 4, 2]]
    for e, riga in zip(emps, livelli):
        for c, lv in zip(cols, riga):
            if lv:
                db.session.add(PolyvalenceEntry(matrix_id=mat.id, employee_id=e.id, column_id=c.id, level=lv))

    # ---------------------------------------------------------------- non conformità 8D (§8.7, §10.2)
    db.session.add_all([
        NonConformity8D(number=f"01_{anno}", opened_at=d(-70), customer="Cliente Alfa Macchine Agricole", article_code="STF-120",
                        pieces=40, where_found="Controllo in accettazione del cliente", responsible="Paolo Neri",
                        d1_team="Responsabile qualità, coordinatore di saldatura, capo reparto robot",
                        d2_description="Porosità superficiale sui cordoni d'angolo della staffa STF-120, lotto di 40 pezzi.",
                        d3_containment="Blocco del lotto, selezione 100% a magazzino e presso il cliente; 6 pezzi ripresi a TIG.",
                        d4_root_cause="Portata del gas di protezione insufficiente per un ugello usurato e corrente d'aria dal portone aperto.",
                        d5_corrective_actions="Sostituzione ugelli a frequenza settimanale, flussimetro con allarme, schermo antivento alla cella 1.",
                        d5_date=d(-55), d6_verification="Nessuna porosità sui 6 lotti successivi (240 pezzi).", d6_date=d(-25),
                        d7_extension="Stessa verifica estesa alla cella 2 e al piano di manutenzione.",
                        d8_notes="Chiusa con il ringraziamento al team.", status="chiusa", closed_at=d(-25)),
        NonConformity8D(number=f"02_{anno}", opened_at=d(-18), customer="Cliente Beta Carrelli", article_code="TEL-450",
                        pieces=12, where_found="Collaudo dimensionale interno", responsible="Giulia Verdi",
                        d1_team="Controllo qualità, programmatore laser, capo reparto piegatura",
                        d2_description="Interasse fori fuori tolleranza (+0,8 mm su ±0,3) dopo la piegatura del telaio TEL-450.",
                        d3_containment="Lotto segregato; verifica dimensionale al 100% dei pezzi in lavorazione.",
                        d4_root_cause="In analisi: possibile errore di sviluppo lamiera nel programma di taglio.",
                        status="aperta"),
        NonConformity8D(number=f"03_{anno}", opened_at=d(-6), customer="Fornitore lamiere Gamma (NC fornitore)",
                        article_code="LAM-S355-8", pieces=3, where_found="Accettazione materiali",
                        d2_description="Lamiere S355 spessore 8 mm misurate a 7,4 mm, fuori tolleranza di laminazione.",
                        d3_containment="Materiale respinto al fornitore; richiesta del certificato 3.1.", status="aperta",
                        responsible="Paolo Neri"),
    ])

    # ---------------------------------------------------------------- obiettivi, azioni, rischi (§6.1, §6.2)
    obiettivi = [("Produzione", "Pezzi non conformi / pezzi prodotti", "%", "≤ 0,5%", "0,8%", "0,6%", "0,55%"),
                 ("Acquisti", "NC fornitori / consegne", "%", "≤ 2%", "3,1%", "2,4%", "1,9%"),
                 ("Clienti", "Consegne puntuali", "%", "≥ 95%", "91%", "93%", "94%"),
                 ("Risorse umane", "Ore di formazione per addetto", "ore", "≥ 16", "11", "8", "13"),
                 ("Manutenzione", "Fermi macchina non programmati", "ore/mese", "≤ 6", "9", "7", "5,5")]
    for proc, ind, un, tgt, py, q1, h1 in obiettivi:
        o = QualityObjective(year=anno, process=proc, indicator_name=ind, unit=un, frequency="Mensile", target_value=tgt,
                             py_consuntivo=py, q1_consuntivo=q1, h1_consuntivo=h1, responsible="Paolo Neri",
                             policy_alignment="Coerente con la Politica: soddisfazione del cliente e miglioramento continuo.")
        db.session.add(o)
        db.session.flush()
        if proc == "Clienti":
            db.session.add(QualityAction(objective_id=o.id, description="Pianificazione a capacità finita con il nuovo cruscotto di reparto",
                                         responsible="Laura Bianchi", due_date=d(60), status="in_corso"))
            db.session.add(QualityRisk(objective_id=o.id, kind="rischio", description="Ritardi dei fornitori di lamiera in alta stagione",
                                       probability=3, impact=4, mitigation="Doppia fonte e scorta di sicurezza sugli spessori principali"))
    db.session.add_all([
        QualityRisk(year=anno, kind="rischio", description="Dipendenza da due clienti per il 60% del fatturato", probability=3, impact=5,
                    mitigation="Piano commerciale verso nuovi settori (logistica, energia)"),
        QualityRisk(year=anno, kind="opportunita", description="Bando regionale per investimenti in automazione e digitalizzazione",
                    probability=4, impact=4, mitigation="Progetto di innovazione PI per il secondo robot con visione"),
        QualityRisk(year=anno, kind="rischio", description="Scarsità di saldatori qualificati sul mercato del lavoro", probability=4, impact=4,
                    mitigation="Scuola interna di saldatura e matrice di polivalenza", status="mitigato"),
    ])

    # ---------------------------------------------------------------- audit interni (§9.2)
    from .audit_iso_clauses import PUNTI_ISO_9001
    from .sgq import AREE_STANDARD_AUDIT, SCOPO_STANDARD_AUDIT
    for k, (area, resp) in enumerate(AREE_STANDARD_AUDIT):
        eseguita = k < 4
        db.session.add(AuditPlanItem(year=anno, area_process=area, auditor=resp, scope=SCOPO_STANDARD_AUDIT,
                                     planned_date=d(-120 + 30 * k), actual_date=d(-118 + 30 * k) if eseguita else None,
                                     status="eseguita" if eseguita else "pianificata",
                                     findings="Nessuna NC; 1 osservazione" if eseguita else None))
    rep = AuditReport(year=anno, audit_dates=d(-40).strftime("%d/%m/%Y"), team_lead="Paolo Neri",
                      team_members="Giulia Verdi, Luca Marini", status="completato", file_reference=f"PG-AUD-02 {anno}")
    db.session.add(rep)
    db.session.flush()
    rilievi = {"4.1": ("Contesto analizzato con matrice SWOT aggiornata a inizio anno.", "Nessuna azione"),
               "6.1": ("Mappa dei rischi completa; manca la valutazione dell'efficacia di due azioni.", "Completare entro il riesame"),
               "7.1.5.1": ("Micrometro MC-25-01 con taratura scaduta da 15 giorni.", "Osservazione: ritarare e verificare i pezzi misurati"),
               "7.2": ("Qualifiche dei saldatori in regola e registrate.", "Nessuna azione"),
               "8.4": ("Fornitore di lamiere con NC ripetute.", "Valutazione straordinaria del fornitore"),
               "8.7": ("8D applicato correttamente sulla NC di porosità.", "Nessuna azione"),
               "10.2": ("Azioni correttive efficaci, verificate sui lotti successivi.", "Nessuna azione")}
    for i, (sez, titolo, intest) in enumerate(PUNTI_ISO_9001, start=1):
        r = rilievi.get(sez)
        db.session.add(AuditReportFinding(report_id=rep.id, sequence=i, sez=sez, iso_title=titolo, is_heading=intest,
                                          findings_text=r[0] if r else None, actions_text=r[1] if r else None))

    # ---------------------------------------------------------------- riesame della direzione (§9.3)
    rv = ManagementReview(review_date=d(-300), participants="Laura Bianchi (DIR), Paolo Neri (RSGQ), capi reparto",
                          input_audit_results="4 audit interni, nessuna NC, 3 osservazioni.",
                          input_customer_feedback="Soddisfazione media 8,4/10; 2 reclami gestiti.",
                          output_improvement_opportunities="Automazione della seconda cella e cruscotto di reparto.",
                          output_resource_needs="Un saldatore qualificato in più; formazione sui simboli di saldatura.")
    db.session.add(rv)
    db.session.flush()
    db.session.add_all([
        ManagementReviewActionItem(review_id=rv.id, kind="nuova_proposta", sort_order=1, activity="Scuola interna di saldatura",
                                   resources="40 ore formatore interno", responsible="Coordinatore di saldatura", status_text="In corso"),
        ManagementReviewActionItem(review_id=rv.id, kind="nuova_proposta", sort_order=2, activity="Sistema di gestione dell'innovazione ISO 56002",
                                   resources="Innovation Manager esterno", responsible="Direzione", status_text="Avviato"),
    ])

    # ---------------------------------------------------------------- ISO 56000
    db.session.add(InnovationStrategy(
        year=anno, budget=180000,
        vision="Diventare il partner di riferimento per la carpenteria saldata ad alta ripetibilità, con celle automatiche, "
               "tracciabilità completa e tempi di consegna dimezzati.",
        policy="Le idee possono venire da chiunque: clienti, fornitori, persone di reparto. Sperimentiamo in piccolo prima di "
               "investire, accettiamo che alcuni progetti si fermino e impariamo da ogni progetto. Collaboriamo con università e "
               "fornitori di tecnologia.",
        focus_areas="Automazione della saldatura con visione artificiale\nTracciabilità di lotti e saldatori con RFID\n"
                    "Dati macchina in tempo reale (IoT) per manutenzione predittiva\nNuovi servizi: co-progettazione con i clienti\n"
                    "Riduzione di energia e scarti",
        objectives="Almeno 30 idee raccolte nell'anno da almeno 15 persone\n3 progetti in validazione o sviluppo\n"
                   "Beneficio annuo atteso ≥ 120.000 € dai progetti avviati\nMaturità del sistema ≥ 3 entro fine anno"))
    progetti = [
        ("PI-%d-001" % anno, "Cella robot con visione artificiale per il riconoscimento dei pezzi", "processo", "radicale",
         "Automazione e robotica", 4, 120000, 45000, 85000, "Bando regionale investimenti 4.0 (domanda presentata)"),
        ("PI-%d-002" % anno, "Tracciabilità RFID di lotti, saldatori e parametri", "processo", "adiacente",
         "RFID e tracciabilità", 3, 35000, 6000, 22000, "Credito d'imposta transizione 4.0"),
        ("PI-%d-003" % anno, "Sensori IoT sui robot per manutenzione predittiva", "processo", "incrementale",
         "IoT e dati macchina", 2, 15000, 0, 18000, None),
        ("PI-%d-004" % anno, "Servizio di co-progettazione delle staffe con i clienti", "modello di business", "adiacente",
         "Software gestionale", 1, 8000, 0, 30000, None),
    ]
    creati = []
    for cod, tit, tipo, oriz, tec, fase, bud, speso, ben, fin in progetti:
        p = InnovationProject(code=cod, title=tit, kind=tipo, horizon=oriz, technology=tec, stage=fase, budget=bud, spent=speso,
                              expected_benefit=ben, funding=fin, responsible="Laura Bianchi", team="Paolo Neri, Luca Marini, Marco Rossi",
                              start_date=d(-200 + 40 * len(creati)), target_date=d(180), objective=tit + ": meno tempi morti, più qualità ripetibile.")
        db.session.add(p)
        db.session.flush()
        for f in range(1, fase):
            db.session.add(InnovationGate(project_id=p.id, from_stage=f, to_stage=f + 1, decision="avanti",
                                          decided_at=d(-190 + 40 * len(creati) + 25 * f), decided_by="Comitato innovazione",
                                          evidence="Evidenze positive: prove in reparto e caso economico aggiornato."))
        creati.append(p)
    stop = InnovationProject(code="PI-%d-005" % (anno - 1), title="Saldatura laser per i telai sottili", kind="processo",
                             horizon="radicale", technology="Processo di saldatura", stage=3, status="chiuso_stop", budget=60000,
                             spent=7000, expected_benefit=25000, end_date=d(-150), responsible="Paolo Neri",
                             lessons="I volumi dei clienti non giustificano l'investimento: rivalutare tra due anni. "
                                     "La prova ha fatto crescere le competenze sul controllo della distorsione.")
    db.session.add(stop)
    db.session.flush()
    db.session.add(InnovationGate(project_id=stop.id, from_stage=3, to_stage=3, decision="stop", decided_at=d(-150),
                                  decided_by="Comitato innovazione", evidence="Rientro oltre 6 anni con i volumi attuali."))
    idee = [("Schermo antivento automatico per le celle", "Marco Rossi", "interna", "processo", "Automazione e robotica", (3, 5, 3, 5), "approvata"),
            ("Etichette RFID sui cestoni dei pezzi", "Giulia Verdi", "interna", "processo", "RFID e tracciabilità", (4, 4, 5, 4), "progetto"),
            ("Kit di staffe standard a catalogo per i clienti piccoli", "Cliente Beta Carrelli", "cliente", "prodotto", None, (4, 3, 4, 3), "in_valutazione"),
            ("Recupero del calore dei forni di essiccazione", "Luca Marini", "interna", "processo", "Energia e sostenibilità", (3, 3, 3, 4), "proposta"),
            ("Tesi di laurea su parametri di saldatura e AI", "Università Demo", "universita", "processo", "Intelligenza artificiale", (4, 3, 4, 3), "in_valutazione"),
            ("Dima universale regolabile per la puntatura", "Andrea Conti", "interna", "processo", None, (3, 4, 3, 5), "proposta"),
            ("Vendita di ore macchina laser ad altre officine", "Laura Bianchi", "interna", "modello di business", None, None, "scartata")]
    for k, (tit, chi, fonte, tipo, tec, voti, stato) in enumerate(idee, start=1):
        i = InnovationIdea(code=f"ID-{anno}-{k:03d}", title=tit, proposer=chi, source=fonte, kind=tipo, technology=tec,
                           submitted_at=d(-90 + 10 * k), status=stato,
                           project_id=creati[1].id if stato == "progetto" else None,
                           evaluation_notes="Margini troppo bassi e rischio di conflitto con i clienti." if stato == "scartata" else None)
        if voti:
            i.score_value, i.score_feasibility, i.score_fit, i.score_risk = voti
        db.session.add(i)
    base = {"4.1": 3, "4.2": 2, "4.4": 2, "5.1": 3, "5.2": 2, "5.3": 2, "6.1": 2, "6.2": 2, "6.3": 1, "7.1": 2, "7.2": 2,
            "7.4": 2, "7.6": 1, "7.7": 1, "8.3.2": 2, "8.3.3": 2, "8.3.4": 1, "8.3.5": 3, "8.3.6": 3, "9.1": 1, "9.2": 0,
            "9.3": 2, "10.1": 2}
    db.session.add(InnovationMaturity(assessed_at=d(-180), assessor="Innovation Manager", scores=base, notes={},
                                      summary="Punto di partenza: buona capacità di sviluppo, poca sistematicità nella raccolta delle idee e negli indicatori."))
    oggi_voti = dict(base, **{"5.2": 3, "6.2": 3, "6.3": 2, "7.6": 2, "8.3.2": 3, "8.3.4": 2, "9.1": 3, "9.2": 1})
    db.session.add(InnovationMaturity(assessed_at=d(-10), assessor="Innovation Manager", scores=oggi_voti,
                                      notes={"9.2": "Primo audit interno del sistema innovazione da pianificare", "7.7": "Nessuna gestione della proprietà intellettuale"},
                                      summary="Cresciute strategia, raccolta idee e indicatori. Priorità: audit interno, proprietà intellettuale, metodi di validazione."))
    db.session.commit()

    from .vsme import seed_vsme_indicators
    seed_vsme_indicators(anno)
    carica_demo_sistemi(oggi)


def carica_demo_sistemi(oggi):
    """ISO 14001, ISO 45001 e SA8000: una prima base da completare con il materiale vero."""
    from .models import ComplianceObligation, MgmtAssessment, MgmtEvent, MgmtRisk
    d = lambda giorni: oggi + timedelta(days=giorni)  # noqa: E731
    R = lambda std, att, voce, eff, cond, p, g, mis, st="aperto": MgmtRisk(  # noqa: E731
        standard=std, activity=att, item=voce, effect=eff, condition=cond, probability=p, severity=g, controls=mis, status=st)
    O = lambda std, fonte, req, gg, resp, ev, st: ComplianceObligation(  # noqa: E731
        standard=std, source=fonte, requirement=req, due_date=d(gg) if gg is not None else None, responsible=resp, evidence=ev, status=st)
    db.session.add_all([
        # ISO 14001 · aspetti ambientali
        R("iso14001", "Saldatura robot e manuale", "Emissione di fumi di saldatura", "Qualità dell'aria", "Normale", 3, 2, "Aspiratori localizzati con filtri, manutenzione semestrale", "sotto_controllo"),
        R("iso14001", "Taglio laser", "Consumo di energia elettrica", "Consumo di risorse, emissioni indirette CO2", "Normale", 4, 2, "Monitoraggio mensile kWh/pezzo, spegnimento in pausa"),
        R("iso14001", "Lavorazioni lamiera", "Rottami e sfridi metallici", "Rifiuti (recuperabili)", "Normale", 4, 1, "Raccolta differenziata e vendita a recuperatore autorizzato", "sotto_controllo"),
        R("iso14001", "Manutenzione", "Oli esausti ed emulsioni", "Rifiuti pericolosi, contaminazione del suolo", "Anomala", 2, 3, "Deposito su bacino di contenimento, smaltitore autorizzato"),
        R("iso14001", "Magazzino gas tecnici", "Perdita da bombole", "Rilascio in atmosfera, incendio", "Emergenza", 1, 4, "Gabbia ventilata, piano di emergenza, prova annuale"),
        O("iso14001", "Autorizzazione unica ambientale (AUA)", "Rinnovo dell'autorizzazione alle emissioni in atmosfera", 400, "Direzione", "AUA protocollo demo", "conforme"),
        O("iso14001", "D.Lgs. 152/06 – rifiuti", "Tenuta del registro di carico e scarico e dei formulari", None, "Amministrazione", "Registro aggiornato", "conforme"),
        O("iso14001", "AUA – prescrizioni", "Analisi annuale delle emissioni dei punti E1-E3", 20, "Responsabile qualità", "Laboratorio esterno da incaricare", "da_verificare"),
        O("iso14001", "Prevenzione incendi", "Rinnovo periodico conformità antincendio", -10, "RSPP", "Pratica da presentare", "da_verificare"),
        MgmtEvent(standard="iso14001", kind="Sversamento", event_date=d(-40), description="Perdita di olio idraulico dalla pressa piegatrice (circa 2 litri).",
                  cause="Raccordo usurato", action="Assorbimento con kit, sostituzione raccordo, controllo raccordi nel piano di manutenzione", status="chiuso"),
        # ISO 45001 · pericoli e rischi
        R("iso45001", "Saldatura", "Radiazioni ottiche artificiali (arco)", "Lesioni a occhi e pelle", "Ordinaria", 2, 3, "Schermi, maschere autoscuranti, formazione", "sotto_controllo"),
        R("iso45001", "Saldatura", "Fumi di saldatura (cancerogeni)", "Malattie respiratorie", "Ordinaria", 3, 4, "Aspirazione localizzata, sorveglianza sanitaria, misure di esposizione"),
        R("iso45001", "Piegatura", "Schiacciamento mani nella pressa", "Lesioni gravi alle mani", "Ordinaria", 2, 4, "Barriere fotoelettriche, verifica giornaliera, addestramento"),
        R("iso45001", "Movimentazione", "Investimento da carrello elevatore", "Traumi", "Ordinaria", 2, 4, "Percorsi segnalati, abilitazione carrellisti, specchi"),
        R("iso45001", "Celle robot", "Accesso alla cella in movimento", "Urto con il robot", "Straordinaria", 1, 4, "Interblocchi porte, procedura LOTO", "sotto_controllo"),
        R("iso45001", "Reparto", "Rumore", "Ipoacusia", "Ordinaria", 3, 2, "Otoprotettori, misure fonometriche"),
        O("iso45001", "D.Lgs. 81/08 art. 28", "Aggiornamento del Documento di valutazione dei rischi (DVR)", 60, "RSPP", "DVR rev. demo", "conforme"),
        O("iso45001", "D.Lgs. 81/08 art. 37", "Aggiornamento quinquennale della formazione dei lavoratori", 25, "RSPP", "3 lavoratori in scadenza", "da_verificare"),
        O("iso45001", "D.Lgs. 81/08 art. 71", "Verifiche periodiche delle attrezzature di sollevamento", -5, "Manutenzione", "Carroponte: verifica da prenotare", "da_verificare"),
        O("iso45001", "D.Lgs. 81/08 art. 41", "Sorveglianza sanitaria secondo il protocollo del medico competente", 120, "Direzione", "Calendario visite", "conforme"),
        MgmtEvent(standard="iso45001", kind="Infortunio", event_date=d(-75), description="Taglio alla mano durante la sbavatura di un pezzo.",
                  cause="Guanto non adatto al rischio di taglio", action="Guanti antitaglio livello D e formazione sui DPI", lost_days=4, status="chiuso"),
        MgmtEvent(standard="iso45001", kind="Quasi infortunio", event_date=d(-12), description="Pallet caduto dalla scaffalatura durante il prelievo, nessun ferito.",
                  cause="Pallet danneggiato", action="Controllo dei pallet in ingresso", status="aperto"),
        # SA8000 · rischi sociali
        R("sa8000", "Picchi di produzione", "Straordinari oltre i limiti contrattuali", "Orario di lavoro (req. 7)", "Interno", 3, 3, "Pianificazione a capacità finita, monitoraggio settimanale delle ore"),
        R("sa8000", "Fornitore di lavorazioni in conto terzi", "Condizioni di lavoro non verificate", "Fornitori (req. 9.10)", "Fornitori", 2, 3, "Questionario sociale e visita annuale"),
        R("sa8000", "Personale con lingue diverse", "Comprensione insufficiente di regole e diritti", "Discriminazione (req. 5)", "Interno", 2, 2, "Regolamento tradotto, mediatore in assunzione", "sotto_controllo"),
        R("sa8000", "Agenzie per il lavoro", "Costi di reclutamento a carico dei lavoratori", "Lavoro forzato (req. 2)", "Appalti", 1, 4, "Clausola contrattuale e verifica a campione"),
        O("sa8000", "SA8000 – requisito 9.2", "Nomina e riunione trimestrale del Social Performance Team", 15, "Direzione", "Verbale ultimo trimestre", "conforme"),
        O("sa8000", "SA8000 – requisito 8", "Verifica che le retribuzioni coprano il salario dignitoso", 90, "Amministrazione", "Analisi da aggiornare", "da_verificare"),
        O("sa8000", "CCNL Metalmeccanici", "Rispetto di minimi retributivi e orari contrattuali", None, "Amministrazione", "Buste paga e presenze", "conforme"),
        MgmtEvent(standard="sa8000", kind="Segnalazione anonima", event_date=d(-20), description="Segnalazione nella cassetta: turni del sabato comunicati con poco preavviso.",
                  action="Calendario dei sabati pubblicato con 4 settimane di anticipo", status="aperto"),
    ])
    voti = {"iso14001": {"4.1": 2, "4.2": 2, "5.2": 1, "6.1.2": 3, "6.1.3": 3, "6.2": 1, "8.1": 2, "8.2": 3, "9.1.2": 2, "10.2": 3},
            "iso45001": {"4.2": 3, "5.2": 2, "5.4": 3, "6.1.2": 4, "6.1.3": 4, "8.1.2": 3, "8.1.4": 2, "8.2": 3, "9.1.2": 3, "10.2": 3},
            "sa8000": {"1": 5, "2": 4, "3": 4, "4": 3, "5": 3, "6": 4, "7": 2, "8": 3, "9.1": 2, "9.2": 3, "9.6": 2, "9.10": 1}}
    for std, v in voti.items():
        db.session.add(MgmtAssessment(standard=std, assessed_at=d(-30), assessor="Consulente", scores=v, notes={}))
    db.session.commit()
