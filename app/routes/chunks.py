from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, request, send_file, url_for


chunks = Blueprint("chunks", __name__)


def service():
    return current_app.extensions["chunk_service"]


def enqueue(job_type: str, document_id: str | None = None, chunk_id: str | None = None):
    return current_app.extensions["job_service"].enqueue(
        job_type, document_id=document_id, chunk_id=chunk_id
    )


def record(event_type: str, message: str, **kwargs):
    current_app.extensions["activity_repository"].record(event_type, message, **kwargs)


@chunks.post("/documents/<document_id>/chunks/generate")
def generate(document_id: str):
    enqueue("generate_document", document_id)
    flash("Génération placée dans la file de traitement.", "success")
    return redirect(url_for("documents.review", document_id=document_id, tab="chunks"))


@chunks.post("/chunks/generate-all")
def generate_all():
    enqueue("generate_all")
    flash("Génération globale placée dans la file de traitement.", "success")
    return redirect(url_for("documents.index"))


@chunks.post("/documents/<document_id>/chunks/enrich")
def enrich(document_id: str):
    enqueue("enrich_document", document_id)
    flash("Enrichissement placé dans la file de traitement.", "success")
    return redirect(url_for("documents.review", document_id=document_id, tab="chunks"))


@chunks.post("/documents/<document_id>/chunks/<chunk_id>/enrich")
def enrich_one(document_id: str, chunk_id: str):
    enqueue("enrich_chunk", document_id, chunk_id)
    flash("Relance de l'IA placée dans la file de traitement.", "success")
    return redirect(
        url_for("documents.review", document_id=document_id, tab="chunks")
        + f"#chunk-{chunk_id}"
    )


@chunks.post("/documents/<document_id>/chunks/<chunk_id>")
def update(document_id: str, chunk_id: str):
    try:
        service().update(
            document_id, chunk_id, request.form,
            expected_version=int(request.form.get("version", "-1")),
        )
    except RuntimeError as error:
        flash(str(error), "error")
        return redirect(url_for("documents.review", document_id=document_id, tab="chunks"))
    record("chunk.updated", "Chunk modifié manuellement.", document_id=document_id, chunk_id=chunk_id)
    flash("Chunk enregistré.", "success")
    return redirect(url_for("documents.review", document_id=document_id, tab="chunks") + f"#chunk-{chunk_id}")


@chunks.post("/documents/<document_id>/chunks/<chunk_id>/delete")
def delete(document_id: str, chunk_id: str):
    service().delete(document_id, chunk_id)
    record("chunk.deleted", "Chunk supprimé.", document_id=document_id, chunk_id=chunk_id)
    flash("Chunk supprimé.", "success")
    return redirect(url_for("documents.review", document_id=document_id, tab="chunks"))


@chunks.post("/documents/<document_id>/chunks/<chunk_id>/merge")
def merge(document_id: str, chunk_id: str):
    try:
        service().merge_with_next(document_id, chunk_id)
        record("chunk.merged", "Chunks fusionnés.", document_id=document_id, chunk_id=chunk_id)
        flash("Chunks fusionnés.", "success")
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("documents.review", document_id=document_id, tab="chunks"))


@chunks.post("/documents/<document_id>/chunks/<chunk_id>/split")
def split(document_id: str, chunk_id: str):
    try:
        service().split(document_id, chunk_id, int(request.form.get("offset", "0")))
        record("chunk.split", "Chunk découpé.", document_id=document_id, chunk_id=chunk_id)
        flash("Chunk découpé.", "success")
    except (ValueError, TypeError) as error:
        flash(str(error), "error")
    return redirect(url_for("documents.review", document_id=document_id, tab="chunks"))


@chunks.post("/documents/<document_id>/vectorize")
def vectorize(document_id: str):
    enqueue("vectorize_document", document_id)
    flash("Vectorisation placée dans la file de traitement.", "success")
    return redirect(url_for("documents.review", document_id=document_id, tab="chunks"))


@chunks.post("/vectorize-all")
def vectorize_all():
    enqueue("vectorize_all")
    flash("Vectorisation globale placée dans la file de traitement.", "success")
    return redirect(url_for("documents.index"))


@chunks.get("/documents/<document_id>/export.jsonl")
def export_jsonl(document_id: str):
    stream, filename = current_app.extensions["export_service"].rag_jsonl(document_id)
    return send_file(stream, mimetype="application/x-ndjson", as_attachment=True, download_name=filename)
