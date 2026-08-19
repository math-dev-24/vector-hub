from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for


documents = Blueprint("documents", __name__)


def service():
    return current_app.extensions["document_service"]


def record(event_type: str, message: str, **kwargs):
    current_app.extensions["activity_repository"].record(event_type, message, **kwargs)


@documents.get("/")
def index():
    document_list = service().get_documents_info()
    return render_template(
        "index.html", documents=document_list,
        jobs=current_app.extensions["job_repository"].list_recent(limit=8),
        events=current_app.extensions["activity_repository"].list_recent(limit=8),
    )


@documents.post("/upload")
def upload():
    files = request.files.getlist("pdfs") or request.files.getlist("pdf")
    files = [file for file in files if file and file.filename]
    if not files:
        flash("Aucun fichier envoyé.", "error")
        return redirect(url_for("documents.index"))
    if len(files) > current_app.config["MAX_FILES_PER_UPLOAD"]:
        flash(f"Un lot ne peut pas dépasser {current_app.config['MAX_FILES_PER_UPLOAD']} fichiers.", "error")
        return redirect(url_for("documents.index"))
    imported_ids, errors = [], []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            errors.append(f"{file.filename} : extension non PDF")
            continue
        try:
            document_id = service().upload_document(file, max_pages=current_app.config["MAX_PDF_PAGES"])
            imported_ids.append(document_id)
            record("document.uploaded", f"Document importé : {file.filename}.", document_id=document_id)
            if request.form.get("ai_correction") == "1":
                current_app.extensions["job_service"].enqueue(
                    "correct_document_ai", document_id=document_id
                )
        except ValueError as error:
            errors.append(f"{file.filename} : {error}")
    if imported_ids:
        flash(f"{len(imported_ids)} document(s) importé(s).", "success")
    if errors:
        flash("Certains fichiers ont été ignorés : " + " · ".join(errors), "error")
    if len(imported_ids) == 1 and len(files) == 1:
        return redirect(url_for("documents.review", document_id=imported_ids[0]))
    return redirect(url_for("documents.index"))


@documents.get("/documents/<document_id>")
def review(document_id: str):
    try:
        document = service().get_document(document_id)
    except KeyError:
        flash("Document introuvable.", "error")
        return redirect(url_for("documents.index"))
    publication_service = current_app.extensions["publication_service"]
    return render_template(
        "review.html", document=document, active_tab=request.args.get("tab", "pages"),
        jobs=current_app.extensions["job_repository"].list_recent(document_id, limit=5),
        ocr_available=current_app.extensions["ocr_service"].is_available(),
        preprocessing_rules=service().preprocessor.RULES,
        selected_preprocessing_rules=service().preprocessor.DEFAULT_RULES,
        preprocessing_preview=False,
        remote_vectors_configured=publication_service.configured,
        remote_collection=publication_service.display_name,
        publication_summary=current_app.extensions["publication_repository"].summary(
            document_id, publication_service.collection
        ),
    )


@documents.post("/documents/<document_id>/pages")
def save_pages(document_id: str):
    try:
        service().save_pages(document_id, request.form, int(request.form.get("version", "-1")))
    except RuntimeError as error:
        flash(str(error), "error")
        return redirect(url_for("documents.review", document_id=document_id, tab="pages"))
    record("pages.saved", "Corrections des pages enregistrées.", document_id=document_id)
    flash("Pages enregistrées.", "success")
    return redirect(url_for("documents.review", document_id=document_id, tab="pages"))


@documents.post("/documents/<document_id>/preprocess")
def preview_preprocessing(document_id: str):
    rules = request.form.getlist("preprocess_rules")
    document, result = service().preview_preprocessing(document_id, request.form, rules)
    record("pages.preprocess_preview", "Aperçu du prétraitement généré.",
           document_id=document_id, details={"rules": result.applied_rules,
                                             "changed_pages": result.changed_pages})
    flash(f"Aperçu généré : {result.changed_pages} page(s) modifiée(s). Vérifie puis enregistre.",
          "success")
    return render_template(
        "review.html", document=document, active_tab="pages",
        jobs=current_app.extensions["job_repository"].list_recent(document_id, limit=5),
        ocr_available=current_app.extensions["ocr_service"].is_available(),
        preprocessing_rules=service().preprocessor.RULES,
        selected_preprocessing_rules=result.applied_rules,
        preprocessing_preview=True,
        remote_vectors_configured=current_app.extensions["publication_service"].configured,
        remote_collection=current_app.extensions["publication_service"].display_name,
        publication_summary=current_app.extensions["publication_repository"].summary(
            document_id, current_app.extensions["publication_service"].collection
        ),
    )


@documents.post("/documents/<document_id>/pages/<page_id>/delete")
def delete_page(document_id: str, page_id: str):
    try:
        deleted = service().delete_page(
            document_id, page_id, request.form, int(request.form.get("version", "-1"))
        )
    except RuntimeError as error:
        flash(str(error), "error")
        return redirect(url_for("documents.review", document_id=document_id, tab="pages"))
    if deleted:
        record("page.deleted", "Page supprimée.", document_id=document_id, details={"page_id": page_id})
        flash("Page supprimée.", "success")
    else:
        flash("Page introuvable.", "error")
    return redirect(url_for("documents.review", document_id=document_id, tab="pages"))


@documents.post("/documents/<document_id>/delete")
def delete_document(document_id: str):
    try:
        source_removed = service().delete_document(document_id)
        if source_removed:
            record("document.deleted", "Document et données associées supprimés.", document_id=document_id)
            flash("Document et toutes ses données supprimés.", "success")
        else:
            flash("Données supprimées, mais le fichier PDF source n'a pas pu être retiré.", "error")
    except KeyError:
        flash("Document introuvable.", "error")
    return redirect(url_for("documents.index"))


@documents.post("/documents/<document_id>/ocr")
def run_ocr(document_id: str):
    current_app.extensions["job_service"].enqueue("ocr_document", document_id=document_id)
    flash("OCR ajouté à la file de traitement.", "success")
    return redirect(url_for("documents.review", document_id=document_id, tab="pages"))


@documents.post("/documents/<document_id>/pages/<page_id>/correct-ai")
def correct_page_ai(document_id: str, page_id: str):
    try:
        document = service().save_pages(
            document_id, request.form, int(request.form.get("version", "-1"))
        )
    except RuntimeError as error:
        flash(str(error), "error")
        return redirect(url_for("documents.review", document_id=document_id, tab="pages"))
    page = next((item for item in document.pages if item.id == page_id), None)
    if page is None:
        flash("Page introuvable.", "error")
    else:
        current_app.extensions["job_service"].enqueue(
            "correct_page_ai", document_id=document_id,
            payload={"page_id": page_id, "expected_text": page.corrected_text},
        )
        flash(f"Pré-correction IA de la page {page.page} ajoutée à la file.", "success")
    return redirect(url_for("documents.review", document_id=document_id, tab="pages"))
