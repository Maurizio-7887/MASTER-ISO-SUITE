"""Modelli dati di MASTER ISO SUITE.

ISO 9001 (sistema qualità), ISO 56001/56002 (gestione dell'innovazione) e
rendicontazione di sostenibilità VSME, su un unico archivio.
I dati dimostrativi sono di un'azienda simulata (vedi seed_demo.py).
"""
from datetime import date, datetime
from flask_login import UserMixin
from .extensions import db, login_manager


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    pin = db.Column(db.String(20), unique=True, nullable=False)  # usare hash prima dell'uso esteso in produzione
    role = db.Column(db.String(20), nullable=False, default="operator")
    active = db.Column(db.Boolean, nullable=False, default=True)

    @property
    def is_owner(self):
        return self.role == "owner"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class SourceDocument(db.Model):
    __tablename__ = "source_document"
    id = db.Column(db.Integer, primary_key=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    mime_type = db.Column(db.String(120), nullable=True)
    extracted_text = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    uploaded_by = db.relationship("User")
    # Archivio controllato (manuale qualita', procedure, CPC, modulistica...): categoria,
    # titolo logico del documento (uguale tra le varie revisioni dello stesso documento),
    # etichetta di revisione libera, ed evidenza della sola versione corrente.
    category = db.Column(db.String(60), nullable=False, default="Altro")
    document_title = db.Column(db.String(255), nullable=True)
    revision_label = db.Column(db.String(60), nullable=True)
    is_current = db.Column(db.Boolean, nullable=False, default=True)
    supersedes_id = db.Column(db.Integer, db.ForeignKey("source_document.id"), nullable=True)
    superseded_by = db.relationship("SourceDocument", remote_side=[id])


class QualityObjective(db.Model):
    """Obiettivo di qualità legato a un indicatore di processo (§6.2 ISO 9001),
    con consuntivazione periodica (anno-1 e anno corrente per trimestre/
    semestre/9 mesi/anno) e azioni/rischi collegati (§6.1)."""
    __tablename__ = "quality_objective"
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    process = db.Column(db.String(150), nullable=True)
    indicator_name = db.Column(db.String(200), nullable=False)
    frequency = db.Column(db.String(40), nullable=True)  # Mensile / Trimestrale / Annuale...
    unit = db.Column(db.String(40), nullable=True)
    responsible = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(30), nullable=False, default="in_corso")  # in_corso / raggiunto / non_raggiunto
    notes = db.Column(db.Text, nullable=True)
    policy_alignment = db.Column(db.Text, nullable=True)  # coerenza con la Politica della Qualità (§6.2.1 c)
    # Anno attuale - 1 (consuntivazione dell'anno precedente)
    py_preventivo = db.Column(db.String(80), nullable=True)
    py_consuntivo = db.Column(db.String(80), nullable=True)
    py_analisi = db.Column(db.Text, nullable=True)
    # Anno attuale
    target_value = db.Column(db.String(80), nullable=True)  # Obiettivo anno attuale
    q1_consuntivo = db.Column(db.String(80), nullable=True)  # Consuntivo trimestrale
    h1_consuntivo = db.Column(db.String(80), nullable=True)  # Consuntivo semestrale
    ninemonths_consuntivo = db.Column(db.String(80), nullable=True)  # Consuntivo a 9 mesi
    year_consuntivo = db.Column(db.String(80), nullable=True)  # Consuntivo anno in corso
    year_analisi = db.Column(db.Text, nullable=True)  # Analisi risultato anno corrente
    current_value = db.Column(db.String(80), nullable=True)  # storico, non piu' usato in UI
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    actions = db.relationship("QualityAction", backref="objective", lazy=True, cascade="all, delete-orphan", order_by="QualityAction.id")
    risks = db.relationship("QualityRisk", backref="objective", lazy=True, cascade="all, delete-orphan", order_by="QualityRisk.id")


class QualityAction(db.Model):
    """Azione pianificata per raggiungere un obiettivo di qualità."""
    __tablename__ = "quality_action"
    id = db.Column(db.Integer, primary_key=True)
    objective_id = db.Column(db.Integer, db.ForeignKey("quality_objective.id"), nullable=False)
    description = db.Column(db.Text, nullable=False)
    responsible = db.Column(db.String(120), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="da_avviare")  # da_avviare / in_corso / completata
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class QualityRisk(db.Model):
    """Rischio (o opportunità) valutato con il metodo a punteggio Probabilità
    x Impatto (matrice 5x5, 1-25). Può essere legato a un obiettivo specifico
    (rischio di mancato raggiungimento del KPI) oppure essere un rischio di
    CONTESTO (§4.1/§4.2 e §6.1), non legato a nessun obiettivo puntuale: in
    questo caso objective_id è nullo e l'anno si registra direttamente qui."""
    __tablename__ = "quality_risk"
    id = db.Column(db.Integer, primary_key=True)
    objective_id = db.Column(db.Integer, db.ForeignKey("quality_objective.id"), nullable=True)
    year = db.Column(db.Integer, nullable=True)  # usato solo per i rischi di contesto (objective_id nullo)
    kind = db.Column(db.String(20), nullable=False, default="rischio")  # rischio / opportunita
    description = db.Column(db.Text, nullable=False)
    probability = db.Column(db.Integer, nullable=False, default=1)  # 1-5
    impact = db.Column(db.Integer, nullable=False, default=1)  # 1-5
    mitigation = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="aperto")  # aperto / mitigato / chiuso
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @property
    def score(self):
        return (self.probability or 0) * (self.impact or 0)

    @property
    def livello(self):
        s = self.score
        if s >= 15:
            return "alto"
        if s >= 8:
            return "medio"
        return "basso"

    @property
    def effective_year(self):
        return self.year or (self.objective.year if self.objective else None)


class Machine(db.Model):
    """Macchina/attrezzatura/dima soggetta a manutenzione (§7.1.3 ISO 9001)."""
    __tablename__ = "machine"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), nullable=False, unique=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(60), nullable=True)  # es. Saldopuntatrice, Robot, Utensile, Dima
    area = db.Column(db.String(100), nullable=True)  # reparto/locazione
    manufacturer = db.Column(db.String(150), nullable=True)
    responsible = db.Column(db.String(120), nullable=True)  # responsabile manutenzione
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    plan_items = db.relationship("MaintenancePlanItem", backref="machine", lazy=True, cascade="all, delete-orphan")
    logs = db.relationship("MaintenanceLog", backref="machine", lazy=True, cascade="all, delete-orphan",
                           order_by="MaintenanceLog.performed_at.desc()")


class MaintenancePlanItem(db.Model):
    """Riga del piano di manutenzione PROGRAMMATA (preventiva): cosa va fatto
    su quella macchina e ogni quanto."""
    __tablename__ = "maintenance_plan_item"
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id"), nullable=False, index=True)
    intervention = db.Column(db.String(250), nullable=False)
    frequency = db.Column(db.String(60), nullable=True)  # testo libero: Mensile/Semestrale/Annuale...
    next_due = db.Column(db.Date, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class MaintenanceLog(db.Model):
    """Registro interventi REALI (programmati eseguiti o straordinari):
    esattamente quello che prima si registrava col pulsante dal telefono."""
    __tablename__ = "maintenance_log"
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id"), nullable=False, index=True)
    plan_item_id = db.Column(db.Integer, db.ForeignKey("maintenance_plan_item.id"), nullable=True)
    kind = db.Column(db.String(20), nullable=False, default="straordinaria")  # programmata / straordinaria
    intervention = db.Column(db.Text, nullable=False)
    operator_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    external_company = db.Column(db.String(150), nullable=True)
    hours = db.Column(db.Numeric(6, 2), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    performed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    operator = db.relationship("User")


class TrainingCourse(db.Model):
    """Corso/sessione di formazione svolta (registro per data corso)."""
    __tablename__ = "training_course"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), nullable=False)
    topic_area = db.Column(db.String(80), nullable=True)  # es. RSPP/RLS/Antincendio/Qualità/Muletti...
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    hours = db.Column(db.Numeric(6, 2), nullable=True)
    teacher = db.Column(db.String(150), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    display_period = db.Column(db.String(60), nullable=True)  # testo esatto da mostrare nel piano (es. "SETT-DIC 2023"), se il calcolo automatico da inizio/fine non basta
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    attendances = db.relationship("TrainingAttendance", backref="course", lazy=True, cascade="all, delete-orphan")
    sessions_list = db.relationship("TrainingSession", backref="course", lazy=True, cascade="all, delete-orphan", order_by="TrainingSession.sequence")


class TrainingEmployee(db.Model):
    """Persona in formazione senza account di accesso al programma (operai
    di reparto senza PIN): nome libero, come per la matrice di polivalenza."""
    __tablename__ = "training_employee"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False, unique=True)
    active = db.Column(db.Boolean, nullable=False, default=True)


class TrainingAttendance(db.Model):
    """Partecipazione di un dipendente a un corso, con valutazione/esito.
    Puo' riferirsi a un account di accesso (user_id, per l'autoregistrazione
    da telefono) oppure a una persona senza account (employee_id, gestita
    dalla direzione) - sempre e solo uno dei due."""
    __tablename__ = "training_attendance"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("training_course.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("training_employee.id"), nullable=True, index=True)
    outcome = db.Column(db.String(120), nullable=True)  # es. idoneo, superato, in corso
    notes = db.Column(db.Text, nullable=True)
    recorded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user = db.relationship("User")
    employee = db.relationship("TrainingEmployee")
    __table_args__ = (db.UniqueConstraint("course_id", "user_id", name="uq_training_attendance_course_user"),
                      db.UniqueConstraint("course_id", "employee_id", name="uq_training_attendance_course_employee"))


class TrainingSession(db.Model):
    """Singola sessione (data/ore/argomento) di un corso di formazione,
    esattamente come nel registro storico per data corso."""
    __tablename__ = "training_session"
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("training_course.id"), nullable=False, index=True)
    session_date = db.Column(db.Date, nullable=True)
    hours = db.Column(db.Numeric(6, 2), nullable=True)
    topic = db.Column(db.String(300), nullable=True)
    sequence = db.Column(db.Integer, nullable=False, default=0)


class EmployeeTrainingGap(db.Model):
    """Nota libera per dipendente: gap di know-how da colmare (colonna
    dedicata nel piano formazione per singola risorsa). Persona con account
    (user_id) o senza (employee_id) - sempre e solo uno dei due."""
    __tablename__ = "employee_training_gap"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, unique=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("training_employee.id"), nullable=True, unique=True)
    gap_note = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = db.relationship("User")
    employee = db.relationship("TrainingEmployee")


class PianoFormazioneOverride(db.Model):
    """Correzione manuale di una cella del Piano Formazione (persona x area):
    la data scritta a mano vince su quella calcolata dai corsi. Vuota =
    torna al calcolo automatico. Eseguito/pianificato si deduce da sola
    confrontando la data con oggi, come per i corsi normali."""
    __tablename__ = "piano_formazione_override"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("training_employee.id"), nullable=True)
    topic_area = db.Column(db.String(80), nullable=False)
    data = db.Column(db.Date, nullable=True)
    testo = db.Column(db.String(60), nullable=True)
    eseguito = db.Column(db.Boolean, nullable=False, default=True)  # colore: verde se True, blu se False
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "topic_area", name="uq_pf_override_user_area"),
                      db.UniqueConstraint("employee_id", "topic_area", name="uq_pf_override_employee_area"))


class Qualification(db.Model):
    """Attestato conseguito o nomina formale (es. Coordinatore di Saldatura
    RWC), con la copia del documento vero collegata a Documenti."""
    __tablename__ = "qualification"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False, default="attestato")  # attestato / nomina
    title = db.Column(db.String(250), nullable=False)
    reference_number = db.Column(db.String(100), nullable=True)
    issuing_body = db.Column(db.String(200), nullable=True)
    issue_date = db.Column(db.Date, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    document_id = db.Column(db.Integer, db.ForeignKey("source_document.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user = db.relationship("User")
    document = db.relationship("SourceDocument")


class PolyvalenceMatrix(db.Model):
    """Matrice di polivalenza per Business Unit (es. Carpenteria, Saldatura robot):
    righe (dipendenti) e colonne (mansioni/postazioni) libere, entrambe
    modificabili - non legate agli account di accesso al programma."""
    __tablename__ = "polyvalence_matrix"
    id = db.Column(db.Integer, primary_key=True)
    business_unit = db.Column(db.String(150), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    columns = db.relationship("PolyvalenceColumn", backref="matrix", lazy=True, cascade="all, delete-orphan", order_by="PolyvalenceColumn.sequence")
    employees = db.relationship("PolyvalenceEmployee", backref="matrix", lazy=True, cascade="all, delete-orphan", order_by="PolyvalenceEmployee.sequence")
    entries = db.relationship("PolyvalenceEntry", backref="matrix", lazy=True, cascade="all, delete-orphan")


class PolyvalenceColumn(db.Model):
    """Una colonna (mansione/postazione) della matrice, con eventuale
    raggruppamento (es. 'INDIRETTI', 'SALDO-PROIEZ.')."""
    __tablename__ = "polyvalence_column"
    id = db.Column(db.Integer, primary_key=True)
    matrix_id = db.Column(db.Integer, db.ForeignKey("polyvalence_matrix.id"), nullable=False, index=True)
    group_label = db.Column(db.String(100), nullable=True)
    label = db.Column(db.String(100), nullable=False)
    sequence = db.Column(db.Integer, nullable=False, default=0)


class PolyvalenceEmployee(db.Model):
    """Una riga (persona) della matrice: nome libero, aggiungibile/modificabile/
    eliminabile - non richiede un account di accesso al programma."""
    __tablename__ = "polyvalence_employee"
    id = db.Column(db.Integer, primary_key=True)
    matrix_id = db.Column(db.Integer, db.ForeignKey("polyvalence_matrix.id"), nullable=False, index=True)
    full_name = db.Column(db.String(150), nullable=False)
    sequence = db.Column(db.Integer, nullable=False, default=0)


class PolyvalenceEntry(db.Model):
    """Livello di polivalenza di un dipendente su una colonna: 0 non idoneo,
    1 formazione avviata, 2 in formazione, 3 formazione da completare, 4 formato
    (stessa scala della legenda storica)."""
    __tablename__ = "polyvalence_entry"
    id = db.Column(db.Integer, primary_key=True)
    matrix_id = db.Column(db.Integer, db.ForeignKey("polyvalence_matrix.id"), nullable=False, index=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("polyvalence_employee.id"), nullable=False, index=True)
    column_id = db.Column(db.Integer, db.ForeignKey("polyvalence_column.id"), nullable=False, index=True)
    level = db.Column(db.Integer, nullable=False, default=0)
    __table_args__ = (db.UniqueConstraint("employee_id", "column_id", name="uq_polyvalence_entry_employee_column"),)


class CalibrationDevice(db.Model):
    """Strumento/dispositivo soggetto a taratura (registro generale
    dispositivi + scheda individuale)."""
    __tablename__ = "calibration_device"
    id = db.Column(db.Integer, primary_key=True)
    sheet_number = db.Column(db.String(40), nullable=True)  # "Scheda nr."
    name = db.Column(db.String(200), nullable=False)  # denominazione strumento
    code = db.Column(db.String(100), nullable=True)  # costruttore/matricola
    assigned_to = db.Column(db.String(150), nullable=True)  # "in gestione a"
    frequency = db.Column(db.String(60), nullable=True)  # Annuale/Quinquennale...
    last_check = db.Column(db.Date, nullable=True)
    next_due = db.Column(db.Date, nullable=True)
    resolution_tolerance = db.Column(db.String(150), nullable=True)
    supplier = db.Column(db.String(150), nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    records = db.relationship("CalibrationRecord", backref="device", lazy=True, cascade="all, delete-orphan",
                              order_by="CalibrationRecord.checked_at.desc()")


class CalibrationRecord(db.Model):
    """Singolo controllo/taratura eseguita su uno strumento."""
    __tablename__ = "calibration_record"
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.Integer, db.ForeignKey("calibration_device.id"), nullable=False, index=True)
    checked_at = db.Column(db.Date, nullable=False, default=date.today)
    next_due = db.Column(db.Date, nullable=True)
    outcome = db.Column(db.String(60), nullable=True)  # conforme / non conforme
    responsible = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class NonConformity8D(db.Model):
    """Non conformità gestita con report 8D (D1-D8), secondo il metodo 8D
    usato nell'automotive (procedura PG-NC)."""
    __tablename__ = "non_conformity_8d"
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(40), nullable=True)  # numerazione interna, es. 02_2023
    opened_at = db.Column(db.Date, nullable=False, default=date.today)
    customer = db.Column(db.String(150), nullable=True)  # es. Cliente Alfa
    article_code = db.Column(db.String(80), nullable=True)
    pieces = db.Column(db.Integer, nullable=True)
    where_found = db.Column(db.String(200), nullable=True)  # "Dove"
    d1_team = db.Column(db.Text, nullable=True)
    d2_description = db.Column(db.Text, nullable=True)
    d3_containment = db.Column(db.Text, nullable=True)
    d4_root_cause = db.Column(db.Text, nullable=True)
    d5_corrective_actions = db.Column(db.Text, nullable=True)
    d5_date = db.Column(db.Date, nullable=True)
    d6_verification = db.Column(db.Text, nullable=True)
    d6_date = db.Column(db.Date, nullable=True)
    d7_extension = db.Column(db.Text, nullable=True)
    d8_notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="aperta")  # aperta / chiusa
    responsible = db.Column(db.String(120), nullable=True)
    closed_at = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditReport(db.Model):
    """Rapporto di Audit (verifica ispettiva interna) strutturato per punti
    norma ISO 9001:2015, stesso formato usato storicamente in azienda
    (PG-AUD-02 Rapporto di Audit). Un rapporto per verifica svolta: la
    tabella dei rilievi (AuditReportFinding) si genera da sola sui punti
    norma standard e si compila online, poi si stampa nel formato noto."""
    __tablename__ = "audit_report"
    id = db.Column(db.Integer, primary_key=True)
    plan_item_id = db.Column(db.Integer, db.ForeignKey("audit_plan_item.id"), nullable=True)
    year = db.Column(db.Integer, nullable=False)
    audit_dates = db.Column(db.String(120), nullable=True)  # es. "11 e 12 Agosto 2025"
    team_lead = db.Column(db.String(150), nullable=True)  # responsabile del Gruppo di Audit
    team_members = db.Column(db.String(300), nullable=True)  # esperti d'area
    status = db.Column(db.String(30), nullable=False, default="bozza")  # bozza / completato / archiviato
    file_reference = db.Column(db.String(150), nullable=True)  # es. "PG-AUD-02r02"
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    findings = db.relationship("AuditReportFinding", backref="report", lazy=True, cascade="all, delete-orphan", order_by="AuditReportFinding.sequence")


class AuditReportFinding(db.Model):
    """Una riga della tabella del Rapporto di Audit: un punto norma ISO 9001,
    con il rilievo/valutazione e le azioni decise, esattamente come nel
    formato PG-AUD-02 storico (colonne Sez./ISO 9001/Descrizione anomalie
    valutazione giudizio/Azioni decise)."""
    __tablename__ = "audit_report_finding"
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey("audit_report.id"), nullable=False, index=True)
    sequence = db.Column(db.Integer, nullable=False)
    sez = db.Column(db.String(20), nullable=False)
    iso_title = db.Column(db.String(250), nullable=False)
    is_heading = db.Column(db.Boolean, nullable=False, default=False)  # riga titolo di sezione, senza rilievo
    findings_text = db.Column(db.Text, nullable=True)
    actions_text = db.Column(db.Text, nullable=True)
    attachments = db.relationship("AuditReportAttachment", backref="finding", lazy=True, cascade="all, delete-orphan")


class AuditReportAttachment(db.Model):
    """Documento allegato a un rilievo del Rapporto di Audit (es. copia
    politica qualità, organigramma...): il file vive nell'archivio
    Documenti, qui c'e' solo il collegamento."""
    __tablename__ = "audit_report_attachment"
    id = db.Column(db.Integer, primary_key=True)
    finding_id = db.Column(db.Integer, db.ForeignKey("audit_report_finding.id"), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey("source_document.id"), nullable=False)
    label = db.Column(db.String(200), nullable=True)
    document = db.relationship("SourceDocument")


class AuditPlanItem(db.Model):
    """Pianificazione ed esito di una verifica ispettiva interna (§9.2)."""
    __tablename__ = "audit_plan_item"
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    area_process = db.Column(db.String(200), nullable=False)
    planned_date = db.Column(db.Date, nullable=True)
    actual_date = db.Column(db.Date, nullable=True)
    auditor = db.Column(db.String(150), nullable=True)
    scope = db.Column(db.Text, nullable=True)
    findings = db.Column(db.Text, nullable=True)  # esito/rilievi
    status = db.Column(db.String(30), nullable=False, default="pianificata")  # pianificata/eseguita/annullata
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class ManagementReview(db.Model):
    """Riesame della Direzione (§9.3): un record per ogni riesame periodico,
    con gli ingressi/uscite tipici richiesti dalla norma come campi separati
    (non un unico testo libero) così restano tracciabili e confrontabili."""
    __tablename__ = "management_review"
    id = db.Column(db.Integer, primary_key=True)
    review_date = db.Column(db.Date, nullable=False, default=date.today)
    participants = db.Column(db.Text, nullable=True)
    input_audit_results = db.Column(db.Text, nullable=True)
    input_customer_feedback = db.Column(db.Text, nullable=True)
    input_process_performance = db.Column(db.Text, nullable=True)
    input_nonconformities = db.Column(db.Text, nullable=True)
    input_corrective_actions_status = db.Column(db.Text, nullable=True)
    input_objectives_status = db.Column(db.Text, nullable=True)
    input_resources_adequacy = db.Column(db.Text, nullable=True)
    input_risks_opportunities = db.Column(db.Text, nullable=True)
    output_improvement_opportunities = db.Column(db.Text, nullable=True)
    output_system_changes = db.Column(db.Text, nullable=True)
    output_resource_needs = db.Column(db.Text, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # --- Formato storico "MOD-RD" (Verbale Riesame della Direzione), lo
    # stesso già noto al certificatore e usato negli anni precedenti: campi
    # aggiuntivi che riproducono le sezioni del verbale cartaceo, accanto
    # (non al posto) alla struttura generica §9.3 sopra.
    reference_period = db.Column(db.String(80), nullable=True)  # es. "2025"
    basis_audit_reports = db.Column(db.Boolean, nullable=False, default=True)  # rapporti verifiche ispettive interne
    basis_certification_reports = db.Column(db.Boolean, nullable=False, default=True)  # rapporti verifiche certificative
    basis_previous_review_actions = db.Column(db.Boolean, nullable=False, default=True)  # azioni condotte in conseguenza del precedente riesame
    basis_customer_feedback = db.Column(db.Boolean, nullable=False, default=True)  # reclami/informazioni di ritorno dai clienti
    basis_corrective_actions_trend = db.Column(db.Boolean, nullable=False, default=True)  # analisi andamento azioni correttive
    basis_preventive_actions_trend = db.Column(db.Boolean, nullable=False, default=True)  # analisi andamento azioni preventive
    basis_rac = db.Column(db.Boolean, nullable=False, default=True)  # RAC avviate nelle diverse aree/attività
    basis_context_analysis = db.Column(db.Boolean, nullable=False, default=True)  # analisi del contesto
    risk_management_notes = db.Column(db.Text, nullable=True)  # Sistema Risk Management - Risk Based Thinking
    quality_policy_review = db.Column(db.Text, nullable=True)  # Verifica Politica della Qualità
    improvement_development_notes = db.Column(db.Text, nullable=True)  # Attività di sviluppo e miglioramento del SGQ
    internal_audit_summary = db.Column(db.Text, nullable=True)  # Sintesi risultati verifiche ispettive interne (per area)
    certification_audit_summary = db.Column(db.Text, nullable=True)  # Sintesi risultati verifiche ispettive enti di certificazione
    complaints_analysis = db.Column(db.Text, nullable=True)  # Analisi reclami clienti/lavoratori/stakeholders
    nonconformities_analysis = db.Column(db.Text, nullable=True)  # Analisi delle non conformità riscontrate (8D)
    injuries_analysis = db.Column(db.Text, nullable=True)  # Analisi infortuni
    training_analysis = db.Column(db.Text, nullable=True)  # Formazione ed addestramento erogata
    suppliers_evaluation = db.Column(db.Text, nullable=True)  # Valutazione fornitori
    indicators_adequacy = db.Column(db.Text, nullable=True)  # Analisi adeguatezza indicatori sistema qualità
    previous_review_followup = db.Column(db.Text, nullable=True)  # Aspetti dei riesami precedenti
    conclusions = db.Column(db.Text, nullable=True)
    signature_date = db.Column(db.Date, nullable=True)  # data del "Visto: Direzione"
    action_items = db.relationship("ManagementReviewActionItem", backref="review", lazy=True,
                                    cascade="all, delete-orphan", order_by="ManagementReviewActionItem.sort_order")
    sections = db.relationship("ManagementReviewSection", backref="review", lazy=True,
                                cascade="all, delete-orphan", order_by="ManagementReviewSection.sort_order")


class ManagementReviewSection(db.Model):
    """Un punto del Riesame della Direzione (es. Verifica Politica della
    Qualità, Sintesi VII interne, Formazione...): per ogni punto l'ispettore
    vuole un'analisi della situazione (cosa va bene / cosa non va) e gli
    allegati a supporto, riportati poi nella stampa finale. Una riga per
    punto e per riesame, creata automaticamente dalla lista standard
    SEZIONI_RIESAME la prima volta che si apre il dettaglio."""
    __tablename__ = "management_review_section"
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey("management_review.id"), nullable=False, index=True)
    section_key = db.Column(db.String(60), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    positives_text = db.Column(db.Text, nullable=True)  # cosa va bene
    negatives_text = db.Column(db.Text, nullable=True)  # cosa non va / criticità
    attachments = db.relationship("ManagementReviewSectionAttachment", backref="section", lazy=True,
                                   cascade="all, delete-orphan")


class ManagementReviewSectionAttachment(db.Model):
    """Documento allegato a un punto del Riesame della Direzione: il file
    vive nell'archivio Documenti, qui c'è solo il collegamento (come per
    AuditReportAttachment)."""
    __tablename__ = "management_review_section_attachment"
    id = db.Column(db.Integer, primary_key=True)
    section_id = db.Column(db.Integer, db.ForeignKey("management_review_section.id"), nullable=False, index=True)
    document_id = db.Column(db.Integer, db.ForeignKey("source_document.id"), nullable=False)
    label = db.Column(db.String(200), nullable=True)
    document = db.relationship("SourceDocument")


class ManagementReviewActionItem(db.Model):
    """Riga della tabella 'Piani di miglioramento' del Riesame della
    Direzione, formato storico MOD-RD. Stesso modello per due usi
    (distinti da 'kind'): verifica dell'esito dei piani dell'anno
    precedente (colonna 'Risultati al 31/12') e nuove proposte di
    miglioramento decise in questo riesame (colonna 'Data effettuazione')."""
    __tablename__ = "management_review_action_item"
    id = db.Column(db.Integer, primary_key=True)
    review_id = db.Column(db.Integer, db.ForeignKey("management_review.id"), nullable=False, index=True)
    kind = db.Column(db.String(30), nullable=False, default="nuova_proposta")  # verifica_precedente / nuova_proposta
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    activity = db.Column(db.Text, nullable=True)
    resources = db.Column(db.String(200), nullable=True)
    responsible = db.Column(db.String(150), nullable=True)
    status_text = db.Column(db.Text, nullable=True)  # risultati al 31/12 (verifica) oppure data/stato effettuazione (proposta)


class VsmeIndicator(db.Model):
    """Voce del Registro Indicatori VSME (Voluntary SME Standard - EFRAG),
    Modulo Base B1-B12. Ogni voce è un indicatore compilabile per anno di
    rendicontazione: la struttura (modulo/indicatore/unità/descrizione) è
    precaricata dal registro standard; direzione compila valore, note e stato.
    Pensato per alimentare in futuro anche l'estratto pubblicato sul sito."""
    __tablename__ = "vsme_indicator"
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    module_code = db.Column(db.String(5), nullable=False)  # B1..B12
    module_name = db.Column(db.String(160), nullable=False)
    indicator_name = db.Column(db.String(255), nullable=False)
    unit = db.Column(db.String(60), nullable=True)
    description = db.Column(db.Text, nullable=True)  # guida alla compilazione
    value = db.Column(db.String(255), nullable=True)  # dato compilato
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="da_compilare")  # da_compilare / completato / non_applicabile
    publish_on_site = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

# ============================================================ ISO 56000 ==
class InnovationStrategy(db.Model):
    """Visione, politica e ambiti di innovazione dell'anno (ISO 56001 §5.2, §6.2)."""
    __tablename__ = "innovation_strategy"
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, unique=True)
    vision = db.Column(db.Text, nullable=True)
    policy = db.Column(db.Text, nullable=True)
    focus_areas = db.Column(db.Text, nullable=True)        # ambiti di ricerca delle opportunità, uno per riga
    objectives = db.Column(db.Text, nullable=True)         # obiettivi di innovazione misurabili
    budget = db.Column(db.Numeric(12, 2), nullable=True)   # risorse destinate all'innovazione
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class InnovationIdea(db.Model):
    """Opportunità o idea raccolta (ISO 56001 §8.3: identificare e valutare le opportunità)."""
    __tablename__ = "innovation_idea"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=True, unique=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    proposer = db.Column(db.String(150), nullable=True)
    source = db.Column(db.String(40), nullable=False, default="interna")  # interna/cliente/fornitore/universita/bando/tecnologia
    area = db.Column(db.String(80), nullable=True)
    kind = db.Column(db.String(30), nullable=False, default="processo")  # prodotto/processo/organizzativa/modello di business
    technology = db.Column(db.String(80), nullable=True)                 # automazione, robotica, RFID, IoT, AI...
    submitted_at = db.Column(db.Date, nullable=False, default=date.today)
    # valutazione 1-5 (rischio: 5 = rischio basso)
    score_value = db.Column(db.Integer, nullable=True)
    score_feasibility = db.Column(db.Integer, nullable=True)
    score_fit = db.Column(db.Integer, nullable=True)
    score_risk = db.Column(db.Integer, nullable=True)
    evaluation_notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="proposta")  # proposta/in_valutazione/approvata/scartata/progetto
    project_id = db.Column(db.Integer, db.ForeignKey("innovation_project.id"), nullable=True)

    @property
    def priority(self):
        voti = [self.score_value, self.score_feasibility, self.score_fit, self.score_risk]
        if any(v is None for v in voti):
            return None
        # valore e coerenza strategica pesano di più
        return round(self.score_value * 0.35 + self.score_fit * 0.25 + self.score_feasibility * 0.25 + self.score_risk * 0.15, 2)


class InnovationProject(db.Model):
    """Iniziativa di innovazione gestita a fasi e gate (ISO 56001 §8.3, ISO 56002 §8.3)."""
    __tablename__ = "innovation_project"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=True, unique=True)
    title = db.Column(db.String(200), nullable=False)
    objective = db.Column(db.Text, nullable=True)
    kind = db.Column(db.String(30), nullable=False, default="processo")
    horizon = db.Column(db.String(20), nullable=False, default="incrementale")  # incrementale/adiacente/radicale
    technology = db.Column(db.String(80), nullable=True)
    stage = db.Column(db.Integer, nullable=False, default=1)  # 1..6 (vedi FASI in innovazione.py)
    status = db.Column(db.String(20), nullable=False, default="attivo")  # attivo/sospeso/chiuso_successo/chiuso_stop
    responsible = db.Column(db.String(150), nullable=True)
    team = db.Column(db.String(300), nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    target_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    budget = db.Column(db.Numeric(12, 2), nullable=True)
    spent = db.Column(db.Numeric(12, 2), nullable=True)
    expected_benefit = db.Column(db.Numeric(12, 2), nullable=True)  # beneficio annuo atteso, euro
    realized_benefit = db.Column(db.Numeric(12, 2), nullable=True)
    funding = db.Column(db.String(200), nullable=True)  # bando, credito d'imposta, voucher...
    ip_notes = db.Column(db.Text, nullable=True)         # proprietà intellettuale (ISO 56005)
    lessons = db.Column(db.Text, nullable=True)          # lezioni apprese
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    gates = db.relationship("InnovationGate", backref="project", lazy=True, cascade="all, delete-orphan",
                            order_by="InnovationGate.decided_at")
    ideas = db.relationship("InnovationIdea", backref="project", lazy=True)


class InnovationGate(db.Model):
    """Decisione a un gate: avanti, fermo, ripeti, stop."""
    __tablename__ = "innovation_gate"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("innovation_project.id"), nullable=False, index=True)
    from_stage = db.Column(db.Integer, nullable=False)
    to_stage = db.Column(db.Integer, nullable=True)
    decision = db.Column(db.String(20), nullable=False)  # avanti/attesa/ripeti/stop
    decided_at = db.Column(db.Date, nullable=False, default=date.today)
    decided_by = db.Column(db.String(150), nullable=True)
    evidence = db.Column(db.Text, nullable=True)


class InnovationMaturity(db.Model):
    """Autovalutazione di maturità del sistema di gestione dell'innovazione (0-5 per capitolo)."""
    __tablename__ = "innovation_maturity"
    id = db.Column(db.Integer, primary_key=True)
    assessed_at = db.Column(db.Date, nullable=False, default=date.today)
    assessor = db.Column(db.String(150), nullable=True)
    scores = db.Column(db.JSON, nullable=False, default=dict)  # {"4.1": 3, ...}
    notes = db.Column(db.JSON, nullable=False, default=dict)
    summary = db.Column(db.Text, nullable=True)


# ============================================ ISO 14001 · ISO 45001 · SA8000 ==
class MgmtRisk(db.Model):
    """Aspetto ambientale (14001), pericolo (45001) o rischio sociale (SA8000), valutato P × G (1-4)."""
    __tablename__ = "mgmt_risk"
    id = db.Column(db.Integer, primary_key=True)
    standard = db.Column(db.String(20), nullable=False, index=True)  # iso14001 / iso45001 / sa8000
    activity = db.Column(db.String(200), nullable=True)   # attività, reparto o fornitore
    item = db.Column(db.String(250), nullable=False)      # aspetto / pericolo / rischio
    effect = db.Column(db.String(250), nullable=True)     # impatto / danno / persone coinvolte
    condition = db.Column(db.String(40), nullable=True)
    probability = db.Column(db.Integer, nullable=True)
    severity = db.Column(db.Integer, nullable=True)
    controls = db.Column(db.Text, nullable=True)          # misure in atto e da attuare
    responsible = db.Column(db.String(150), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="aperto")  # aperto / sotto_controllo / chiuso
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class ComplianceObligation(db.Model):
    """Obbligo di conformità o requisito legale con scadenza (14001 §6.1.3, 45001 §6.1.3, SA8000)."""
    __tablename__ = "compliance_obligation"
    id = db.Column(db.Integer, primary_key=True)
    standard = db.Column(db.String(20), nullable=False, index=True)
    source = db.Column(db.String(200), nullable=True)      # norma, autorizzazione, contratto
    requirement = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    responsible = db.Column(db.String(150), nullable=True)
    evidence = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="da_verificare")
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class MgmtEvent(db.Model):
    """Evento da registrare: infortunio, quasi infortunio, emergenza ambientale, reclamo o segnalazione sociale."""
    __tablename__ = "mgmt_event"
    id = db.Column(db.Integer, primary_key=True)
    standard = db.Column(db.String(20), nullable=False, index=True)
    kind = db.Column(db.String(60), nullable=True)
    event_date = db.Column(db.Date, nullable=False, default=date.today)
    description = db.Column(db.Text, nullable=False)
    cause = db.Column(db.Text, nullable=True)
    action = db.Column(db.Text, nullable=True)
    lost_days = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="aperto")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class MgmtAssessment(db.Model):
    """Autovalutazione per punto della norma (0-5)."""
    __tablename__ = "mgmt_assessment"
    id = db.Column(db.Integer, primary_key=True)
    standard = db.Column(db.String(20), nullable=False, index=True)
    assessed_at = db.Column(db.Date, nullable=False, default=date.today)
    assessor = db.Column(db.String(150), nullable=True)
    scores = db.Column(db.JSON, nullable=False, default=dict)
    notes = db.Column(db.JSON, nullable=False, default=dict)
