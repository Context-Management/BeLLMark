# backend/app/api/results.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session
import json
import logging
import re

from app.db.database import get_db
from app.core.exports.common import prepare_export_data
from app.core.exports.pptx_export import generate_pptx
from app.core.exports.pdf_export import generate_pdf
from app.core.exports.html_export import generate_html
from app.core.exports.json_export import generate_json
from app.core.exports.csv_export import generate_csv
from app.core.run_statistics import compute_run_statistics
from app.core.bias import compute_bias_report
from app.core.calibration import compute_calibration_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/benchmarks", tags=["results"])

EXPORT_FORMATS = {
    "pptx": {
        "generator": generate_pptx,
        "media_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "binary": True,
    },
    "pdf": {
        "generator": generate_pdf,
        "media_type": "application/pdf",
        "binary": True,
    },
    "html": {
        "generator": generate_html,
        "media_type": "text/html",
        "binary": False,
    },
    "json": {
        "generator": generate_json,
        "media_type": "application/json",
        "binary": False,
    },
    "csv": {
        "generator": generate_csv,
        "media_type": "text/csv",
        "binary": False,
    },
}


def _sanitize_filename(name: str) -> str:
    """Sanitize a run name for use in export filenames."""
    name = re.sub(r'[<>:"|?*\\/\x00]', '-', name)
    name = name.replace('..', '')
    name = re.sub(r'-+', '-', name).strip('- ')
    return name[:50] or "export"


@router.get("/{id}/statistics")
async def get_run_statistics(id: int, db: Session = Depends(get_db)):
    """Get full statistical analysis for a benchmark run."""
    result = compute_run_statistics(db, id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@router.get("/{id}/bias")
async def get_bias_report(id: int, db: Session = Depends(get_db)):
    """Get bias detection report for a benchmark run."""
    result = compute_bias_report(db, id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@router.get("/{id}/calibration")
async def get_calibration_report(id: int, db: Session = Depends(get_db)):
    """Get judge calibration report for a benchmark run."""
    result = compute_calibration_report(db, id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@router.get("/{id}/export/{format}")
async def export_benchmark(id: int, format: str, theme: str = "light", db: Session = Depends(get_db)):
    """Export benchmark in specified format (pptx, pdf, html, json, csv).

    Args:
        id: Benchmark run ID
        format: Export format (pptx, pdf, html, json, csv)
        theme: Theme for pptx/pdf exports ("light" or "dark", default "light")
    """
    if format not in EXPORT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format: {format}. Use: {', '.join(EXPORT_FORMATS)}"
        )

    # Validate theme parameter
    if theme not in ("light", "dark"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid theme: {theme}. Use: light, dark"
        )

    data = prepare_export_data(db, id)
    if not data:
        raise HTTPException(status_code=404, detail="Benchmark run not found")

    fmt = EXPORT_FORMATS[format]

    try:
        # Pass theme to generators that support it (pptx, pdf, html)
        if format in ("pptx", "pdf", "html"):
            content = fmt["generator"](data, theme=theme)
        else:
            content = fmt["generator"](data)
    except Exception as e:
        logger.error(f"Export failed for run {id} format {format}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate {format.upper()} export. Please try again."
        )

    run_name = _sanitize_filename(data["run"]["name"])
    # Include theme in filename for pptx/pdf/html
    if format in ("pptx", "pdf", "html"):
        filename = f"bellmark-{run_name}-{theme}-{id}.{format}"
    else:
        filename = f"bellmark-{run_name}-{id}.{format}"

    if format == "json":
        return JSONResponse(
            content=json.loads(content),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    if format == "html":
        return HTMLResponse(
            content=content,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    return Response(
        content=content,
        media_type=fmt["media_type"],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
