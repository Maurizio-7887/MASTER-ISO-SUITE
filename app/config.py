import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "sviluppo-sostituire-prima-della-pubblicazione")
    database_url = os.getenv("DATABASE_URL", "sqlite:///master_iso_suite.db")
    SQLALCHEMY_DATABASE_URI = database_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 240}
    # Archivio documentale controllato: su Railway in un Volume montato in /data
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", os.path.join(os.getcwd(), "instance", "documenti"))
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024
    # Intestazione dei documenti generati (verbali, rapporti di audit, allegato VSME)
    RAGIONE_SOCIALE = os.getenv("RAGIONE_SOCIALE", "ACME Saldature Srl")
    SEDE_LEGALE = os.getenv("SEDE_LEGALE", "Via dell'Esempio 1, 00000 Città Demo")
    # Dati dimostrativi caricati al primo avvio (azienda simulata)
    DEMO_DATA = os.getenv("DEMO_DATA", "1") == "1"
