"""MASTER ISO SUITE — qualità ISO 9001, innovazione ISO 56000, ambiente ISO 14001,
salute e sicurezza ISO 45001, responsabilità sociale SA8000 e sostenibilità VSME, per PMI manifatturiere.

Applicazione dimostrativa e didattica: i dati di partenza sono di un'azienda
simulata (ACME Saldature Srl). Con DEMO_DATA=0 parte vuota per l'uso reale.
"""
import os

from flask import Flask, redirect, render_template, url_for
from flask_login import current_user, login_required

from .config import Config
from .extensions import db, login_manager


def create_app(config=Config):
    app = Flask(__name__)
    app.config.from_object(config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Accedi con il tuo PIN per continuare."
    login_manager.login_message_category = "error"

    from . import models  # noqa: F401 - registra i modelli
    from .auth.routes import auth_bp
    from .documents import documents_bp
    from .innovazione import innovazione_bp
    from .quality_objectives import quality_objectives_bp
    from .risorse import risorse_bp
    from .sgq import sgq_bp
    from .sistemi import sistemi_bp
    from .vsme import vsme_bp
    from .vsme_report import vsme_report_bp
    for bp in (auth_bp, documents_bp, innovazione_bp, quality_objectives_bp, risorse_bp, sgq_bp, sistemi_bp, vsme_bp, vsme_report_bp):
        app.register_blueprint(bp)

    @app.context_processor
    def _azienda():
        return {"RAGIONE_SOCIALE": app.config["RAGIONE_SOCIALE"]}

    @app.route("/")
    def home():
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_owner:
            return redirect(url_for("documents.index"))
        return redirect(url_for("launchpad"))

    @app.route("/cruscotto")
    @login_required
    def launchpad():
        from datetime import date
        from .innovazione import indicatori
        from .models import AuditPlanItem, CalibrationDevice, NonConformity8D, QualityObjective, QualityRisk
        oggi = date.today()
        numeri = {
            "nc_aperte": NonConformity8D.query.filter_by(status="aperta").count(),
            "audit_da_fare": AuditPlanItem.query.filter_by(year=oggi.year, status="pianificata").count(),
            "tarature_scadute": sum(1 for d in CalibrationDevice.query.all()
                                    if getattr(d, "next_due", None) and d.next_due < oggi),
            "obiettivi": QualityObjective.query.filter_by(year=oggi.year).count(),
            "rischi_aperti": QualityRisk.query.filter_by(status="aperto").count(),
            "anno": oggi.year,
        }
        from .sistemi import sintesi
        return render_template("launchpad.html", n=numeri, k=indicatori(oggi.year),
                               sist={c: sintesi(c) for c in ("iso14001", "iso45001", "sa8000")})

    with app.app_context():
        db.create_all()
        if app.config.get("DEMO_DATA"):
            from .seed_demo import carica_demo
            carica_demo()
    return app
