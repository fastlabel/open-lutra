"""Path-validation dependencies."""

from pathlib import Path

from fastapi import Depends, HTTPException, Query, status

from app.settings import get_settings


def resolve_safe_path(
    path: str = Query(..., description="Relative path inside the output directory"),
) -> Path:
    """Resolve a relative path and prevent path traversal.

    Automatically injected as a query parameter via Depends. To call directly,
    pass it as a keyword argument: resolve_safe_path(path=req.old_name).

    Raises:
        HTTPException: When path traversal is detected (400).
    """
    output_dir = get_settings().output_dir.resolve()
    target = (output_dir / path).resolve()
    if not target.is_relative_to(output_dir):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path")
    return target


def require_dir(target: Path = Depends(resolve_safe_path)) -> Path:
    if not target.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")
    return target
