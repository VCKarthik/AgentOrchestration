import io
from pypdf import PdfReader
from .models import PolicyDocument


def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    pdf_stream = io.BytesIO(file_bytes)
    reader = PdfReader(pdf_stream)

    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)

    return "\n".join(pages)


def extract_text_from_pdf_path(file_path: str) -> str:
    reader = PdfReader(file_path)

    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)

    return "\n".join(pages)


def extract_text_from_document(document: PolicyDocument) -> str:
    if document.file_data:
        return extract_text_from_pdf_bytes(document.file_data)

    if document.file_path:
        return extract_text_from_pdf_path(document.file_path)

    raise ValueError("Document has neither file_data nor file_path")