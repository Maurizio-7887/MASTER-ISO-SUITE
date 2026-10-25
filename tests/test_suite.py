"""Percorso completo della demo: accesso, moduli ISO 9001, innovazione ISO 56000, VSME."""
from datetime import date

import pytest

from app import create_app
from app.config import Config
from app.models import InnovationGate, InnovationIdea, InnovationMaturity, InnovationProject


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    TESTING = True
    UPLOAD_FOLDER = "/tmp/master-iso-test"


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    with app.app_context(), app.test_client() as c:
        yield c


def _login(c, pin="9999"):
    return c.post("/auth/login", data={"pin": pin})


def test_tutte_le_pagine_rispondono(client):
    _login(client)
    app = client.application
    for rule in app.url_map.iter_rules():
        if "GET" in rule.methods and not rule.arguments and not rule.rule.startswith("/static"):
            assert client.get(rule.rule).status_code < 400, rule.rule
    anno = date.today().year
    for url in ["/innovazione/progetti/1", "/sistema-qualita/non-conformita/1", "/sistema-qualita/audit/rapporti/1",
                "/sistema-qualita/riesame-direzione/1", "/sistema-qualita/formazione/polivalenza/1", f"/vsme/allegato/{anno}"]:
        assert client.get(url).status_code == 200, url


def test_nessun_nome_reale_nelle_pagine(client):
    _login(client)
    testo = "".join(client.get(u).get_data(as_text=True) for u in
                    ["/cruscotto", "/sistema-qualita/audit/rapporti/1", "/sistema-qualita/non-conformita", "/innovazione/idee"])
    assert "ACME Saldature" in testo
    for vietato in ("TL Saldature", "SMS Meccanica", "Overmek", "Stellantis"):
        assert vietato.lower() not in testo.lower()


def test_idea_valutazione_progetto_e_gate(client):
    _login(client, "1234")  # chiunque può proporre un'idea
    client.post("/innovazione/idee/nuova", data={"title": "Pinza di presa rapida", "source": "interna", "kind": "processo"})
    idea = InnovationIdea.query.filter_by(title="Pinza di presa rapida").one()
    assert idea.code.startswith("ID-") and idea.status == "proposta"
    assert client.post(f"/innovazione/idee/{idea.id}/valuta", data={"score_value": 5}).status_code == 403
    client.post("/auth/logout")
    _login(client)
    client.post(f"/innovazione/idee/{idea.id}/valuta", data={"score_value": 5, "score_feasibility": 4, "score_fit": 4,
                                                             "score_risk": 3, "status": "approvata"})
    assert idea.priority == 4.2
    client.post(f"/innovazione/idee/{idea.id}/progetto")
    p = db_get(InnovationProject, idea.project_id)
    assert p.stage == 2 and idea.status == "progetto"
    client.post(f"/innovazione/progetti/{p.id}/gate", data={"decision": "avanti", "evidence": "Prova riuscita"})
    assert p.stage == 3 and InnovationGate.query.filter_by(project_id=p.id).count() == 2
    client.post(f"/innovazione/progetti/{p.id}/gate", data={"decision": "stop"})
    assert p.status == "chiuso_stop"


def test_autovalutazione_maturita(client):
    _login(client)
    prima = InnovationMaturity.query.count()
    dati = {"s_4.1": "4", "s_5.2": "3", "s_9.2": "1", "n_9.2": "Audit da pianificare", "assessor": "Test"}
    client.post("/innovazione/maturita", data=dati)
    m = InnovationMaturity.query.order_by(InnovationMaturity.id.desc()).first()
    assert InnovationMaturity.query.count() == prima + 1 and m.scores["4.1"] == 4 and m.notes["9.2"]
    assert "Profilo per capitolo" in client.get("/innovazione/maturita").get_data(as_text=True)


def db_get(model, pk):
    from app.extensions import db
    return db.session.get(model, pk)


def test_sistemi_14001_45001_sa8000(client):
    from app.models import ComplianceObligation, MgmtEvent, MgmtRisk
    _login(client)
    for c in ("iso14001", "iso45001", "sa8000"):
        for tab in ("rischi", "obblighi", "eventi", "autovalutazione"):
            assert client.get(f"/sistemi/{c}?tab={tab}").status_code == 200
    client.post("/sistemi/iso45001/rischio", data={"item": "Caduta dall'alto", "probability": "3", "severity": "4"})
    r = MgmtRisk.query.filter_by(item="Caduta dall'alto").one()
    from app.sistemi import livello_rischio, sintesi
    assert livello_rischio(r.probability, r.severity) == (12, "alto")
    client.post("/sistemi/iso14001/obbligo", data={"requirement": "Test scadenza", "due_date": "2000-01-01"})
    assert sintesi("iso14001")["obblighi_critici"] >= 1
    client.post("/sistemi/sa8000/evento", data={"kind": "Reclamo dei lavoratori", "description": "Prova"})
    assert MgmtEvent.query.filter_by(description="Prova").one().status == "aperto"
    assert client.get("/sistemi/iso9999").status_code == 404

