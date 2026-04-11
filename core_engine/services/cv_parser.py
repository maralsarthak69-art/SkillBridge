import json
import re
import io
import PyPDF2
import pdfplumber
from groq import Groq
from django.conf import settings


# ── PDF Extraction ────────────────────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract plain text from a PDF file.
    Tries PyPDF2 first, falls back to pdfplumber for better compatibility
    with complex layouts, tables, and multi-column CVs.
    """
    # Attempt 1: PyPDF2 (fast, works for simple PDFs)
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        if text and len(text) > 50:  # meaningful content
            return text
    except Exception:
        pass

    # Attempt 2: pdfplumber (better for complex layouts, tables, columns)
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = []
            for page in pdf.pages:
                page_text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if page_text:
                    pages.append(page_text)
            text = "\n".join(pages).strip()
            if text and len(text) > 50:
                return text
    except Exception:
        pass

    return ""


# ── Groq Prompt ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are an expert CV/Resume parser. Your job is to extract structured information
from the provided CV text and return ONLY a valid JSON object — no markdown, no
explanation, just raw JSON.

Extract the following fields:
- technical_skills: list of objects with { "skill": string, "years": number or null }
- soft_skills: list of strings
- roles: list of objects with { "title": string, "company": string, "duration": string }
- pii_detected: boolean (true if name, email, phone, address, or national ID is present)

Rules:
- If years of experience for a skill cannot be determined, set "years" to null.
- Do NOT include actual PII values in the output — only flag their presence.
- If a field has no data, return an empty list.
- Return ONLY the JSON object, nothing else.
"""


# ── Parser ────────────────────────────────────────────────────────────────────

def parse_cv(text: str) -> dict:
    """
    Send CV text to Groq LLM and return structured extraction as a dict.
    Raises ValueError if the LLM response cannot be parsed as JSON.
    """
    client = Groq(api_key=settings.GROQ_API_KEY)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Parse this CV:\n\n{text}"},
        ],
        temperature=0.1,  # low temp for consistent structured output
        max_tokens=2048,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if the model wraps output anyway
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}\nRaw output:\n{raw}")


# ── Convenience wrapper ───────────────────────────────────────────────────────

def parse_cv_from_pdf(file_bytes: bytes) -> tuple[dict, str]:
    """Extract text from PDF then parse it. Single call for file uploads."""
    text = extract_text_from_pdf(file_bytes)
    if not text:
        raise ValueError(
            "Could not extract text from this PDF. "
            "Please ensure the file is a text-based PDF (not a scanned image). "
            "Try saving your CV as PDF from Word/Google Docs and re-uploading."
        )
    return parse_cv(text), text
