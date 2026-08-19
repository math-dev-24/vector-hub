import pymupdf


class InvalidDocumentError(ValueError):
    pass


def extract_pdf(pdf_path: str, max_pages: int = 500):
    try:
        document = pymupdf.open(pdf_path)
    except (pymupdf.FileDataError, RuntimeError) as error:
        raise InvalidDocumentError("Le fichier n'est pas un PDF valide.") from error

    if document.page_count > max_pages:
        document.close()
        raise InvalidDocumentError(f"Le PDF dépasse la limite de {max_pages} pages.")

    pages = []

    for page_number, page in enumerate(document):
        text = page.get_text("text")

        pages.append({
            "page": page_number + 1,
            "original_text": text,
            "corrected_text": text,
            "status": "ok" if text.strip() else "warning"
        })

    document.close()

    return pages
