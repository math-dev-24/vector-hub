import os
from flask import Blueprint, current_app, jsonify, render_template


jobs = Blueprint("jobs", __name__)


EVENT_LABELS = {
    "document.uploaded": "Document importé",
    "document.deleted": "Document supprimé",
    "page.saved": "Page enregistrée",
    "page.deleted": "Page supprimée",
    "page.preprocessed": "Prétraitement prévisualisé",
    "chunk.updated": "Chunk enregistré",
    "chunk.deleted": "Chunk supprimé",
    "chunk.split": "Chunk découpé",
    "rag.searched": "Recherche RAG",
}


def _readable_details(details: dict) -> str:
    """Keep useful event context while hiding internal identifiers."""
    labels = {
        "results": "Résultats",
        "rules": "Règles",
        "pages": "Pages",
        "chunks": "Chunks",
        "count": "Total",
        "model": "Modèle",
    }
    parts = []
    for key, value in details.items():
        if key == "id" or key.endswith("_id"):
            continue
        label = labels.get(key, key.replace("_", " ").capitalize())
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        elif isinstance(value, bool):
            value = "Oui" if value else "Non"
        parts.append(f"{label} : {value}")
    return " · ".join(parts)


@jobs.get("/activity")
def activity():
    documents = current_app.extensions["repository"].list()
    document_names = {document.id: document.filename for document in documents}
    recent_events = current_app.extensions["activity_repository"].list_recent(limit=100)
    events = [
        event | {
            "document_name": document_names.get(event["document_id"]),
            "event_label": EVENT_LABELS.get(
                event["event_type"], event["event_type"].replace(".", " · ").replace("_", " ")
            ),
            "detail_summary": _readable_details(event["details"]),
        }
        for event in recent_events
    ]
    database_path = current_app.extensions["repository"].database_path
    return render_template(
        "activity.html",
        jobs=current_app.extensions["job_repository"].list_recent(limit=100),
        events=events,
        document_names=document_names,
        metrics={
            "documents": len(documents),
            "pages": sum(item.pages_count for item in documents),
            "chunks": sum(item.chunks_count for item in documents),
            "database_mb": round(database_path.stat().st_size / 1024 / 1024, 2),
            "openai": bool(os.environ.get("OPENAI_API_KEY")),
            "workers": int(os.environ.get("OCR_PIPE_WORKERS", "2")),
            "ocr": current_app.extensions["ocr_service"].is_available(),
        },
    )


@jobs.get("/api/jobs/<job_id>")
def status(job_id: str):
    try:
        job = current_app.extensions["job_repository"].get(job_id)
    except KeyError:
        return jsonify({"error": "Job introuvable"}), 404
    return jsonify(job.model_dump(mode="json"))


@jobs.post("/jobs/<job_id>/cancel")
def cancel(job_id: str):
    from flask import flash, redirect, request, url_for
    if current_app.extensions["job_service"].cancel(job_id):
        flash("Annulation demandée.", "success")
    else:
        flash("Ce job ne peut plus être annulé.", "error")
    return redirect(request.referrer or url_for("jobs.activity"))
