"""
resume_service.py
Handles resume file validation, text extraction, and AI-powered skill parsing.
"""
import io
import magic
from django.conf import settings
from groq import Groq
import json


# ──────────────────────────────────────────────
# File Validation
# ──────────────────────────────────────────────

def validate_resume_file(file):
    """
    Validates uploaded file is PDF or DOCX and within size limit.
    Raises ValueError on failure.
    """
    max_bytes = settings.RESUME_MAX_SIZE_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValueError(f"File too large. Maximum size is {settings.RESUME_MAX_SIZE_MB}MB.")

    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)  # reset pointer after reading

    if mime not in settings.RESUME_ALLOWED_TYPES:
        raise ValueError(f"Invalid file type '{mime}'. Only PDF and DOCX are accepted.")


# ──────────────────────────────────────────────
# Text Extraction
# ──────────────────────────────────────────────

def extract_text_from_resume(file):
    """
    Extracts plain text from a PDF or DOCX file.
    Returns extracted text string.
    """
    mime = magic.from_buffer(file.read(2048), mime=True)
    file.seek(0)

    if mime == "application/pdf":
        return _extract_from_pdf(file)
    else:
        return _extract_from_docx(file)


def _extract_from_pdf(file):
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file.read()))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        # pypdf not installed — return raw bytes decoded best-effort
        file.seek(0)
        return file.read().decode("utf-8", errors="ignore")


def _extract_from_docx(file):
    try:
        import docx
        doc = docx.Document(io.BytesIO(file.read()))
        return "\n".join(para.text for para in doc.paragraphs)
    except ImportError:
        file.seek(0)
        return file.read().decode("utf-8", errors="ignore")


# ──────────────────────────────────────────────
# AI Skill Extraction via Groq
# ──────────────────────────────────────────────

def extract_skills_with_ai(resume_text: str) -> list[str]:
    """
    Sends resume text to Groq and returns a list of detected skill names.
    """
    client = Groq(api_key=settings.GROQ_API_KEY)

    prompt = f"""
You are a technical recruiter AI. Analyze the resume text below and extract all technical skills mentioned.
Return ONLY a valid JSON array of skill name strings. No explanation, no markdown, just the JSON array.

Example output: ["Python", "Django", "PostgreSQL", "REST APIs", "Docker"]

Resume text:
\"\"\"
{resume_text[:4000]}
\"\"\"
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    raw = response.choices[0].message.content.strip()

    try:
        skills = json.loads(raw)
        if isinstance(skills, list):
            return [str(s).strip() for s in skills if s]
    except json.JSONDecodeError:
        pass

    # Fallback: try to extract array from response if wrapped in text
    import re
    match = re.search(r'\[.*?\]', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return []
