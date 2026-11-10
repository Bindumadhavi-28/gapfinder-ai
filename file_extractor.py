import io
import os
import re
import json
import hashlib
import subprocess
from db_manager import save_uploaded_document, check_duplicate_document

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.getenv("STORAGE_DIR", os.path.join(BASE_DIR, "storage"))

def is_readable_human_text(text: str) -> bool:
    """
    Validates whether extracted text is genuine, readable study material
    rather than decompressed binary bytecode, font glyph tables, or ASCII85 garbage.
    """
    if not text or not isinstance(text, str):
        return False

    clean = text.strip()
    total_len = len(clean)
    if total_len < 15:
        return False

    # 1. Check for massive non-spaced tokens (symptom of unpacked binary streams)
    words = clean.split()
    if not words or (total_len > 120 and len(words) < 5):
        return False

    # Real words in academic English/notes rarely exceed 55 characters
    max_word_len = max(len(w) for w in words)
    if max_word_len > 60:
        return False

    # 2. Check printable character ratio
    printable_count = sum(1 for ch in clean if ch.isprintable() or ch in "\n\r\t")
    if (printable_count / total_len) < 0.88:
        return False

    # 3. Check alphabetic letter density
    alpha_count = sum(1 for ch in clean if ch.isalpha())
    if (alpha_count / total_len) < 0.35:
        return False

    # 4. Check density of unusual non-text symbols
    weird_symbols = sum(1 for ch in clean if ch in "~^#$@&%<>|=_\\*`[]{}~")
    if (weird_symbols / total_len) > 0.12:
        return False

    return True


def extract_pdf_with_pdfjs(pdf_path: str) -> dict:
    """
    Extracts text and page structure from PDF using pdfjs-dist via Node.js.
    Falls back to pypdf if Node.js is unavailable.
    """
    js_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extract_pdf.js")
    if os.path.exists(js_script):
        try:
            res = subprocess.run(
                ["node", js_script, os.path.abspath(pdf_path)],
                capture_output=True,
                text=True,
                timeout=25,
                encoding="utf-8"
            )
            if res.returncode == 0 and res.stdout.strip():
                lines = [l.strip() for l in res.stdout.strip().split("\n") if l.strip().startswith("{")]
                if lines:
                    data = json.loads(lines[-1])
                    return data
        except Exception:
            pass

    # Fallback to pypdf
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        page_count = len(reader.pages)
        pages = []
        total_len = 0
        for i, page in enumerate(reader.pages, 1):
            t = page.extract_text() or ""
            clean_t = t.strip()
            pages.append({"pageNumber": i, "text": clean_t})
            total_len += len(clean_t)

        if total_len < 15:
            return {
                "status": "OCR Required",
                "message": "This PDF contains scanned images or handwritten pages with no embedded text layer. OCR (Optical Character Recognition) is required.",
                "pageCount": page_count,
                "fullText": "",
                "pages": pages
            }

        full_text = "\n\n".join([f"[Page {p['pageNumber']}]\n{p['text']}" for p in pages if p["text"]])
        return {
            "status": "Success",
            "message": "Text successfully extracted.",
            "pageCount": page_count,
            "fullText": full_text,
            "pages": pages
        }
    except Exception as ex:
        return {
            "status": "Error",
            "message": f"Extraction failed: {str(ex)}",
            "pageCount": 0,
            "fullText": "",
            "pages": []
        }


def process_and_store_document(uploaded_file, username: str, doc_type: str = "Study Notes") -> dict:
    """
    Stores uploaded PDF and extracted text in persistent storage,
    runs extraction with pdfjs-dist, prevents duplicates, and saves to database.
    """
    file_bytes = uploaded_file.read()
    filename = uploaded_file.name
    safe_filename = re.sub(r"[^\w\.-]", "_", filename)
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # 1. Prevent duplicate uploads
    dup = check_duplicate_document(username, file_hash)
    if dup:
        return {
            "status": "Duplicate",
            "message": f"'{filename}' has already been uploaded.",
            "filename": filename,
            "doc_id": dup["id"],
            "doc_type": doc_type
        }

    # 2. Setup persistent directories
    user_pdf_dir = os.path.join(STORAGE_DIR, "pdfs", username)
    user_txt_dir = os.path.join(STORAGE_DIR, "texts", username)
    os.makedirs(user_pdf_dir, exist_ok=True)
    os.makedirs(user_txt_dir, exist_ok=True)

    pdf_path = os.path.join(user_pdf_dir, safe_filename)
    with open(pdf_path, "wb") as f:
        f.write(file_bytes)

    # 3. Extract text
    if filename.lower().endswith(".pdf"):
        extract_res = extract_pdf_with_pdfjs(pdf_path)
    else:
        # Plain text / markdown
        try:
            raw_t = file_bytes.decode("utf-8")
        except Exception:
            raw_t = file_bytes.decode("latin-1", errors="ignore")
        extract_res = {
            "status": "Success",
            "message": "Text ingested successfully.",
            "pageCount": 1,
            "fullText": raw_t,
            "pages": [{"pageNumber": 1, "text": raw_t}]
        }

    status = extract_res.get("status", "Success")
    page_count = extract_res.get("pageCount", 1)
    full_text = extract_res.get("fullText", "")
    pages = extract_res.get("pages", [])

    # 4. Save extracted text file
    base_name = os.path.splitext(safe_filename)[0]
    txt_path = os.path.join(user_txt_dir, f"{base_name}_extracted.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    # 5. Persist record in database
    doc_id = save_uploaded_document(
        username=username,
        filename=filename,
        doc_type=doc_type,
        file_path=pdf_path,
        text_path=txt_path,
        extracted_text=full_text,
        page_count=page_count,
        status=status,
        file_hash=file_hash,
        pages_json=json.dumps(pages)
    )

    return {
        "status": status,
        "message": extract_res.get("message", ""),
        "doc_id": doc_id,
        "filename": filename,
        "doc_type": doc_type,
        "page_count": page_count,
        "full_text": full_text,
        "pages": pages,
        "pdf_path": pdf_path,
        "text_path": txt_path
    }


def extract_text_from_file(uploaded_file) -> str:
    """
    Extracts plain text from an uploaded file object (.txt, .md, .pdf).
    Guarantees readable text extraction using pdfjs-dist / pypdf.
    """
    filename = uploaded_file.name
    fname_lower = filename.lower()
    file_bytes = uploaded_file.read()

    # 1. Plain text and Markdown files
    if fname_lower.endswith(".txt") or fname_lower.endswith(".md"):
        try:
            text = file_bytes.decode("utf-8")
        except Exception:
            text = file_bytes.decode("latin-1", errors="ignore")

        if len(text.strip()) > 10:
            return text
        raise ValueError(f"The file '{filename}' contains insufficient or unreadable content.")

    # 2. PDF Documents
    if fname_lower.endswith(".pdf"):
        # Save to temp and extract with pdfjs-dist
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            result = extract_pdf_with_pdfjs(tmp_path)
            if result.get("status") == "OCR Required":
                raise ValueError(
                    f"OCR Required for '{filename}'.\n"
                    "This PDF appears to be a scanned image or handwritten document with no embedded digital text layer.\n"
                    "Please use an OCR tool, upload a digital text PDF, or paste your notes directly."
                )
            if result.get("status") == "Error":
                raise ValueError(f"Extraction failed for '{filename}': {result.get('message')}")

            text = result.get("fullText", "").strip()
            if text:
                return text
            raise ValueError(f"No extractable text found in '{filename}'. OCR is required.")
        finally:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except Exception: pass

    # 3. Fallback
    try:
        text = file_bytes.decode("utf-8", errors="ignore")
        if len(text.strip()) > 10:
            return text
    except Exception:
        pass

    raise ValueError(f"Unsupported file format for '{filename}'. Please upload PDF, TXT, or MD files.")
