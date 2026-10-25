import os
import uuid
import shutil
from pathlib import Path
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from .extensions import db
from .models import SourceDocument, User

documents_bp = Blueprint("documents", __name__, url_prefix="/documenti")
ALLOWED = {"pdf", "txt", "csv", "xlsx", "xls", "docx", "png", "jpg", "jpeg"}
CATEGORIE = ["Manuale Qualità", "Procedura gestionale", "Piano di controllo", "Modulistica", "Disegno/Foto articolo", "Audit interno", "Mansionario e Organigramma", "Altro"]


def owner_only():
    if not current_user.is_owner: abort(403)


def extract_text(path, extension):
    try:
        if extension == "pdf":
            return "\n".join((page.extract_text() or "") for page in PdfReader(path).pages)[:200000]
        if extension in {"txt", "csv"}:
            return Path(path).read_text(encoding="utf-8", errors="ignore")[:200000]
    except Exception:
        return ""
    return ""


@documents_bp.route("/")
@login_required
def index():
    # Consultazione ed interrogazione disponibili a tutti gli utenti autenticati:
    # l'archivio documentale controllato deve poter essere letto da chiunque.
    term = request.args.get("q", "").strip()
    categoria = request.args.get("categoria", "").strip()
    query = SourceDocument.query.filter_by(is_current=True)
    if term:
        pattern = f"%{term}%"
        query = query.filter(
            (SourceDocument.original_name.ilike(pattern))
            | (SourceDocument.document_title.ilike(pattern))
            | (SourceDocument.extracted_text.ilike(pattern))
        )
    if categoria:
        query = query.filter(SourceDocument.category == categoria)
    documenti = query.order_by(SourceDocument.category, SourceDocument.document_title, SourceDocument.uploaded_at.desc()).all()

    return render_template("documents/index.html", documents=documenti, term=term,
                            categoria=categoria, categorie=CATEGORIE)


@documents_bp.post("/carica")
@login_required
def upload():
    # Il caricamento di una nuova versione controllata resta riservato alla direzione,
    # cosi' come da prassi di gestione documentale ISO (approvazione della revisione).
    owner_only()
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Seleziona un file.", "error"); return redirect(url_for("documents.index"))
    original = secure_filename(file.filename)
    ext = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if ext not in ALLOWED:
        flash("Formato non supportato. Usa PDF, CSV, TXT, Excel, Word o immagine.", "error"); return redirect(url_for("documents.index"))
    categoria = request.form.get("category", "Altro").strip() or "Altro"
    if categoria not in CATEGORIE:
        categoria = "Altro"
    titolo = request.form.get("document_title", "").strip() or original
    revisione = request.form.get("revision_label", "").strip() or None
    sostituisce_id = request.form.get("supersedes_id", "").strip()

    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    stored = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(folder, stored)
    file.save(path)

    nuovo = SourceDocument(
        original_name=original, stored_name=stored, mime_type=file.mimetype,
        extracted_text=extract_text(path, ext), uploaded_by_id=current_user.id,
        category=categoria, document_title=titolo, revision_label=revisione, is_current=True,
    )
    if sostituisce_id:
        precedente = SourceDocument.query.get(int(sostituisce_id))
        if precedente:
            precedente.is_current = False
            nuovo.supersedes_id = precedente.id
    db.session.add(nuovo)
    db.session.commit()
    flash("Documento caricato e impostato come versione corrente.", "success")
    return redirect(url_for("documents.index"))


@documents_bp.route("/<int:document_id>/file")
@login_required
def download(document_id):
    # Lettura/apertura disponibile a tutti gli utenti autenticati.
    # as_attachment=False: il file si apre nella scheda del browser (i PDF si
    # visualizzano direttamente; per Word/Excel il browser puo' comunque
    # scaricarlo se non ha un proprio visualizzatore Office integrato).
    document = db.get_or_404(SourceDocument, document_id)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], document.stored_name,
                                download_name=document.original_name, as_attachment=False)


@documents_bp.route("/<int:document_id>/storico")
@login_required
def history(document_id):
    # Storico delle revisioni di uno stesso documento (versione corrente + tutte le precedenti).
    corrente = db.get_or_404(SourceDocument, document_id)
    catena = [corrente]
    cursore = corrente
    while cursore.supersedes_id:
        cursore = SourceDocument.query.get(cursore.supersedes_id)
        if not cursore: break
        catena.append(cursore)
    return render_template("documents/history.html", catena=catena, corrente=corrente)


@documents_bp.post("/<int:document_id>/elimina")
@login_required
def delete(document_id):
    # Eliminazione riservata alla direzione, come il caricamento di nuove versioni.
    owner_only()
    document = db.get_or_404(SourceDocument, document_id)
    # Se un'altra revisione lo indicava come "precedente", ricollega la catena
    # storica al documento che questo a sua volta sostituiva (nessun buco nello storico).
    figlio = SourceDocument.query.filter_by(supersedes_id=document.id).first()
    if figlio:
        figlio.supersedes_id = document.supersedes_id
    folder = current_app.config["UPLOAD_FOLDER"]
    percorso = os.path.join(folder, document.stored_name)
    if os.path.exists(percorso):
        os.remove(percorso)
    titolo = document.document_title or document.original_name
    db.session.delete(document)
    db.session.commit()
    flash(f"Documento eliminato: {titolo}.", "success")
    return redirect(url_for("documents.index"))
