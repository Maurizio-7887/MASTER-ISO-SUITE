"""Regressioni del laboratorio avanzato 56002/56001 (modelli originali Flask)."""
from datetime import date, timedelta

import pytest
from app import create_app
from app.config import Config

class LabTestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    TESTING = True
    UPLOAD_FOLDER = "/tmp/master-iso-lab-test"

@pytest.fixture()
def client():
    app = create_app(LabTestConfig)
    with app.app_context(), app.test_client() as c:
        yield c

from app.innovation_lab import evaluate_criteria
from app.models import (
    InnovationChallenge, InnovationChallengeIdea, InnovationCorrectiveAction,
    InnovationGateReview, InnovationIdea, InnovationProject,
)
from app.extensions import db


def _token(client):
    with client.session_transaction() as sess:
        return sess["_innovation_lab_csrf"]


def test_scoring_no_compensation_by_hard_gate():
    rows = [
        dict(key="fit", score=5, evidence=3, threshold=0, must_pass=False),
        dict(key="value", score=5, evidence=3, threshold=0, must_pass=False),
        dict(key="feasibility", score=2, evidence=3, threshold=3, must_pass=True),
        dict(key="finance", score=5, evidence=3, threshold=0, must_pass=False),
    ]
    score, coverage, blockers, recommendation = evaluate_criteria(
        rows, "Motivazione completa", "Esperimento controllato", 100, date.today())
    assert score > .8 and coverage == 1
    assert "Fattibilità tecnica" in blockers[0]
    assert recommendation == "stop_istruttoria"


def test_coverage_distinta_dallo_scoring():
    rows = [
        dict(key=key, score=5, evidence=0, threshold=0, must_pass=False)
        for key, _, _ in (("fit", "a", 30), ("value", "b", 30),
                          ("feasibility", "c", 25), ("finance", "d", 15))
    ]
    score, evidence, blocks, recommendation = evaluate_criteria(
        rows, "Motivazione completa", "Esperimento controllato", 100, date.today())
    assert score == 1.0 and evidence == 0
    assert not blocks and recommendation == "integra_evidenze"


def test_laboratori_accessi_database_and_action(client):
    assert client.get("/innovazione/lab/").status_code in (302, 401)
    assert client.post("/auth/login", data={"pin": "1234"}).status_code in (302, 303)
    assert client.get("/innovazione/lab/").status_code == 403
    client.post("/auth/logout")
    client.post("/auth/login", data={"pin": "9999"})
    assert client.get("/innovazione/lab/").status_code == 200
    token = _token(client)
    assert client.post("/innovazione/lab/sfida", data={"title":"A"*8}).status_code == 400
    resp = client.post("/innovazione/lab/sfida", data={
        "_csrf": token, "title":"Riduzione scarti",
        "question":"Come evitare scarti di saldatura?", "strategic_goal":"Migliorare qualita e costi",
        "owner":"Responsabile innovazione",
    })
    assert resp.status_code == 302
    challenge = InnovationChallenge.query.filter_by(title="Riduzione scarti").one()
    idea = InnovationIdea(title="Nuovo sensore", source="interna")
    db.session.add(idea); db.session.commit()
    assert client.post(f"/innovazione/lab/sfida/{challenge.id}/idea", data={
        "_csrf":token,"idea_id":idea.id}).status_code==302
    assert InnovationChallengeIdea.query.filter_by(idea_id=idea.id).count() == 1
    project = InnovationProject(title="Prova laboratorio",stage=2,status="attivo")
    db.session.add(project); db.session.commit()
    payload = {"_csrf":token,"rationale":"La soluzione va provata per capire le evidenze disponibili.",
        "next_experiment":"Provare con tre campioni e misurare il beneficio realizzato.",
        "max_commitment":"2500","next_review":(date.today()+timedelta(days=30)).isoformat()}
    for key in ("fit","value","feasibility","finance"):
        payload.update({"score_"+key:"4","evidence_"+key:"3","threshold_"+key:"3",
                        "source_"+key:"Prova pilota e verbale datato"})
    assert client.post(f"/innovazione/lab/gate/{project.id}",data=payload).status_code==302
    review = InnovationGateReview.query.filter_by(project_id=project.id).one()
    assert review.recommendation=="valutabile" and project.stage==2
    assert client.post("/innovazione/lab/azione", data={
        "_csrf":token,"kind":"apprendimento", "issue":"La prova di saldatura e fallita",
        "source":"Esperimento 2026 n. 42", "cause":"Sensore non tarato correttamente",
        "action":"Ripetere test con procedura controllata",
        "owner":"Responsabile laboratorio","due_date":date.today().isoformat(),
    }).status_code==302
    action=InnovationCorrectiveAction.query.filter_by(kind="apprendimento").order_by(InnovationCorrectiveAction.id.desc()).first()
    assert action.status=="aperta"
    client.post(f"/innovazione/lab/azione/{action.id}/chiudi",data={
        "_csrf":token,"effectiveness":"Il test ripetuto ha dimostrato stabilita della misura."})
    assert action.status=="chiusa_verificata"
