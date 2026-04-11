"""
file_storage.py — Secure file storage for resumes and capstone submissions

Uses django-storages (already configured in settings.py):
    - If AWS_ACCESS_KEY_ID + AWS_STORAGE_BUCKET_NAME are set → S3
    - Otherwise → local media/ folder (development)

File naming convention:
    resumes/    {user_id}_{timestamp}_{original_filename}
    capstones/  {user_id}_{task_id}_{timestamp}_{original_filename}
"""

import os
from datetime import datetime
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings


def _safe_filename(original: str) -> str:
    """Strip unsafe characters from filename."""
    name, ext = os.path.splitext(original)
    safe_name  = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return f"{safe_name[:50]}{ext.lower()}"


def upload_resume(file, user_id: int) -> dict:
    """
    Upload a resume file to storage (S3 or local).

    Returns:
        { "url": str, "path": str, "size_kb": int, "storage": "s3"|"local" }
    """
    timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name    = _safe_filename(file.name)
    storage_path = f"resumes/{user_id}_{timestamp}_{safe_name}"

    saved_path = default_storage.save(storage_path, file)
    file_url   = default_storage.url(saved_path)
    size_kb    = round(file.size / 1024, 1) if hasattr(file, "size") else 0

    storage_type = "s3" if (settings.AWS_ACCESS_KEY_ID and
                             settings.AWS_STORAGE_BUCKET_NAME) else "local"

    return {
        "url":        file_url,
        "path":       saved_path,
        "size_kb":    size_kb,
        "storage":    storage_type,
    }


def upload_capstone_submission(content: str, user_id: int, task_id: int) -> dict:
    """
    Save a capstone proof-of-work submission as a text file.
    (GitHub URLs + description stored as .txt for audit trail)

    Returns:
        { "url": str, "path": str, "storage": "s3"|"local" }
    """
    timestamp    = datetime.now().strftime("%Y%m%d_%H%M%S")
    storage_path = f"capstones/{user_id}_{task_id}_{timestamp}_submission.txt"

    saved_path = default_storage.save(
        storage_path,
        ContentFile(content.encode("utf-8"))
    )
    file_url = default_storage.url(saved_path)

    storage_type = "s3" if (settings.AWS_ACCESS_KEY_ID and
                             settings.AWS_STORAGE_BUCKET_NAME) else "local"

    return {
        "url":     file_url,
        "path":    saved_path,
        "storage": storage_type,
    }


def delete_file(storage_path: str) -> bool:
    """Delete a file from storage. Returns True on success."""
    try:
        if default_storage.exists(storage_path):
            default_storage.delete(storage_path)
            return True
        return False
    except Exception:
        return False


def get_file_url(storage_path: str) -> str:
    """Get the public URL for a stored file."""
    try:
        return default_storage.url(storage_path)
    except Exception:
        return ""
