from flask import Blueprint, current_app, flash, render_template, request


rag = Blueprint("rag", __name__)


@rag.route("/rag", methods=["GET", "POST"])
def lab():
    query = request.form.get("query", "") if request.method == "POST" else ""
    document_id = ((request.form.get("document_id") or None) if request.method == "POST"
                   else (request.args.get("document_id") or None))
    try:
        limit = int(request.form.get("limit", "8")) if request.method == "POST" else 8
    except ValueError:
        limit = 8
    limit = max(1, min(limit, 20))
    results = []
    if request.method == "POST":
        try:
            results = current_app.extensions["search_service"].search(
                query, document_id=document_id, limit=limit
            )
            current_app.extensions["activity_repository"].record(
                "rag.searched", "Recherche RAG exécutée.",
                document_id=document_id, details={"results": len(results)},
            )
        except RuntimeError as error:
            flash(str(error), "error")
    return render_template(
        "rag.html", documents=current_app.extensions["repository"].list(),
        query=query, selected_document=document_id, limit=limit, results=results,
    )
