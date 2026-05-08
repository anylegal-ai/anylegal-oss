"""
LibreOffice Document Preview Service

A lightweight FastAPI service that converts office documents to PDF
using LibreOffice headless mode. Designed for high-fidelity preview
of Word, PowerPoint, and Excel files including tracked changes, numbering, and formatting.

Runs as a standalone container alongside DoclingService.
"""

import os
import subprocess
import tempfile
import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

LIBREOFFICE_BIN = os.getenv("LIBREOFFICE_BIN", "libreoffice")


def _check_libreoffice() -> bool:
    """Verify LibreOffice is installed and callable."""
    try:
        result = subprocess.run(
            [LIBREOFFICE_BIN, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


app = FastAPI(
    title="LibreOffice Document Preview Service",
    description="Converts DOCX to PDF via LibreOffice headless",
    version="1.0.0",
)

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    libreoffice_ready: bool


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check — confirms LibreOffice binary is available."""
    ready = _check_libreoffice()
    return HealthResponse(
        status="ok" if ready else "degraded",
        service="libreoffice-preview",
        version="1.0.0",
        libreoffice_ready=ready,
    )


SUPPORTED_INPUTS = {".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"}
OUTPUT_FORMATS = {
    "pdf": {"ext": ".pdf", "mime": "application/pdf"},
    "docx": {
        "ext": ".docx",
        "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
}


@app.post("/convert")
async def convert_document(
    file: UploadFile = File(...),
    format: str = "pdf",
):
    """
    Convert an uploaded Word document using LibreOffice headless.

    Query params:
        format: output format — "pdf" (default) or "docx"

    Returns raw bytes of the converted file.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_INPUTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Supported: {', '.join(SUPPORTED_INPUTS)}",
        )

    out_fmt = OUTPUT_FORMATS.get(format)
    if not out_fmt:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported output format: {format}. Supported: {', '.join(OUTPUT_FORMATS)}",
        )

    try:
        content = await file.read()
        logger.info(f"Converting {file.filename} ({len(content)} bytes) → {format}")

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / f"input{ext}"
            input_path.write_bytes(content)

            result = subprocess.run(
                [
                    LIBREOFFICE_BIN,
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    format,
                    "--outdir",
                    tmpdir,
                    str(input_path),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.error(f"LibreOffice failed: {result.stderr}")
                raise HTTPException(
                    status_code=500,
                    detail=f"LibreOffice conversion failed: {result.stderr[:500]}",
                )

            output_path = Path(tmpdir) / f"input{out_fmt['ext']}"
            if not output_path.exists():
                logger.error(f"Output not produced. stdout={result.stdout}, stderr={result.stderr}")
                raise HTTPException(
                    status_code=500,
                    detail=f"LibreOffice did not produce a {format} file",
                )

            out_bytes = output_path.read_bytes()
            out_name = f"{Path(file.filename).stem}{out_fmt['ext']}"
            logger.info(f"Conversion OK: {file.filename} -> {len(out_bytes)} bytes {format}")

            # RFC 5987: use filename* for non-ASCII names (Cyrillic, Arabic, etc.)
            try:
                out_name.encode('ascii')
                disposition = f'inline; filename="{out_name}"'
            except UnicodeEncodeError:
                encoded = quote(out_name)
                ascii_fallback = f"document{out_fmt['ext']}"
                disposition = f'inline; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'

            return Response(
                content=out_bytes,
                media_type=out_fmt["mime"],
                headers={"Content-Disposition": disposition},
            )

    except subprocess.TimeoutExpired:
        logger.error("LibreOffice conversion timed out (120s)")
        raise HTTPException(status_code=504, detail="Conversion timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Tracked-changes accept/reject via LibreOffice UNO macro dispatch.
#
# Ports Anthropic's accept_changes.py pattern
# (github.com/anthropics/skills/blob/main/skills/docx/scripts/accept_changes.py)
# into a service endpoint so it can be called from the backend without
# shipping soffice into the Docker sandbox.
#
# LibreOffice handles every OOXML edge case we care about — nested changes,
# complex formatting, paragraph-mark deletions, table cell content, content
# controls, comment anchors. Our lxml-based accept/reject missed several of
# these, producing "unreadable content" dialogs in Word.
# ---------------------------------------------------------------------------


LIBREOFFICE_PROFILE = "/tmp/libreoffice_docx_profile"
MACRO_DIR = f"{LIBREOFFICE_PROFILE}/user/basic/Standard"


# Single Basic module with both Accept and Reject subs. LibreOffice seeds the
# Standard library infrastructure (script.xlb / script.xlc etc.) automatically
# during first-run init — we only need to drop Module1.xba in place AFTER
# that init has run. Matches Anthropic's accept_changes.py pattern.
ACCEPT_CHANGES_MACRO = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic">
    Sub AcceptAllTrackedChanges
        Dim document As Object
        Dim dispatcher As Object
        document = ThisComponent.CurrentController.Frame
        dispatcher = createUnoService("com.sun.star.frame.DispatchHelper")
        dispatcher.executeDispatch(document, ".uno:AcceptAllTrackedChanges", "", 0, Array())
        ThisComponent.store()
        ThisComponent.close(True)
    End Sub

    Sub RejectAllTrackedChanges
        Dim document As Object
        Dim dispatcher As Object
        document = ThisComponent.CurrentController.Frame
        dispatcher = createUnoService("com.sun.star.frame.DispatchHelper")
        dispatcher.executeDispatch(document, ".uno:RejectAllTrackedChanges", "", 0, Array())
        ThisComponent.store()
        ThisComponent.close(True)
    End Sub
</script:module>"""


_MACRO_INSTALLED = False


def _install_macro() -> bool:
    """Idempotently write the macro into the LibreOffice user profile.

    If the profile doesn't exist, seed it first by running soffice with
    ``--terminate_after_init`` so LibreOffice scaffolds the Standard
    library structure. Then drop Module1.xba in place. Without the first-
    run init, a hand-created ``user/basic/Standard/`` isn't registered and
    the ``vnd.sun.star.script:Standard.Module1.X`` URL silently resolves
    to nothing.
    """
    global _MACRO_INSTALLED
    if _MACRO_INSTALLED:
        return True
    try:
        macro_dir = Path(MACRO_DIR)
        if not macro_dir.exists():
            subprocess.run(
                [
                    LIBREOFFICE_BIN,
                    "--headless",
                    f"-env:UserInstallation=file://{LIBREOFFICE_PROFILE}",
                    "--terminate_after_init",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
            macro_dir.mkdir(parents=True, exist_ok=True)

        (macro_dir / "Module1.xba").write_text(ACCEPT_CHANGES_MACRO)
        _MACRO_INSTALLED = True
        logger.info(f"Installed tracked-changes macro into {MACRO_DIR}")
        return True
    except Exception as e:
        logger.error(f"Failed to install macro: {e}")
        return False


def _run_macro(input_path: Path, macro_name: str) -> subprocess.CompletedProcess:
    """Run a UNO macro against a file via LibreOffice headless.

    macro_name: "AcceptAllTrackedChanges" | "RejectAllTrackedChanges".
    """
    cmd = [
        LIBREOFFICE_BIN,
        "--headless",
        f"-env:UserInstallation=file://{LIBREOFFICE_PROFILE}",
        "--norestore",
        f"vnd.sun.star.script:Standard.Module1.{macro_name}?language=Basic&location=application",
        str(input_path.absolute()),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


async def _apply_tracked_change_op(file: UploadFile, macro_name: str) -> Response:
    """Shared body for /tracked-changes/accept and /tracked-changes/reject."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext != ".docx":
        raise HTTPException(
            status_code=400,
            detail=f"Only .docx supported for tracked-changes ops, got {ext}",
        )

    if not _install_macro():
        raise HTTPException(status_code=500, detail="Failed to install LibreOffice macro")

    content = await file.read()
    logger.info(
        f"tracked-changes/{macro_name}: {file.filename} ({len(content)} bytes)"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / f"input{ext}"
        input_path.write_bytes(content)

        try:
            result = _run_macro(input_path, macro_name)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Macro execution timed out")

        if result.returncode != 0:
            logger.error(
                f"Macro {macro_name} failed: stdout={result.stdout[:300]} "
                f"stderr={result.stderr[:300]}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Macro failed: {result.stderr[:500]}",
            )

        # LibreOffice writes the macro output back to the same file after
        # ThisComponent.store() + ThisComponent.close().
        if not input_path.exists():
            raise HTTPException(
                status_code=500,
                detail="Output file missing after macro — macro likely closed without storing",
            )

        out_bytes = input_path.read_bytes()
        out_name = f"{Path(file.filename).stem}_{macro_name.lower()}{ext}"
        logger.info(
            f"tracked-changes/{macro_name} ok: {file.filename} -> {len(out_bytes)} bytes"
        )

        try:
            out_name.encode("ascii")
            disposition = f'inline; filename="{out_name}"'
        except UnicodeEncodeError:
            encoded = quote(out_name)
            disposition = (
                f'inline; filename="document{ext}"; filename*=UTF-8\'\'{encoded}'
            )

        return Response(
            content=out_bytes,
            media_type=OUTPUT_FORMATS["docx"]["mime"],
            headers={"Content-Disposition": disposition},
        )


@app.post("/tracked-changes/accept")
async def accept_all_tracked_changes(file: UploadFile = File(...)):
    """Accept all tracked changes in a DOCX. Returns the cleaned DOCX bytes.

    Uses LibreOffice's native ``.uno:AcceptAllTrackedChanges`` dispatch so
    every OOXML edge case — nested changes, complex formatting, paragraph
    marks, table cells, content controls, comment anchors — is handled.
    """
    return await _apply_tracked_change_op(file, "AcceptAllTrackedChanges")


@app.post("/tracked-changes/reject")
async def reject_all_tracked_changes(file: UploadFile = File(...)):
    """Reject all tracked changes in a DOCX. Returns a DOCX that matches the
    original state before any tracked edits."""
    return await _apply_tracked_change_op(file, "RejectAllTrackedChanges")


# ---------------------------------------------------------------------------
# Document compare via LibreOffice UNO macro dispatch.
#
# Generates a redlined DOCX showing the differences between two documents
# (file1 = before / baseline, file2 = after / revised). LibreOffice's
# .uno:CompareDocuments dispatcher loads file1 and merges file2's changes
# in as tracked changes, which the user can then open in Word and accept/
# reject like any other set of redlines.
# ---------------------------------------------------------------------------


COMPARE_MACRO_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script:module PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "module.dtd">
<script:module xmlns:script="http://openoffice.org/2000/script" script:name="Module1" script:language="StarBasic">
    Sub CompareWithSecondFile
        Dim oDoc As Object
        Dim oDispatcher As Object
        Dim args(0) As New com.sun.star.beans.PropertyValue
        args(0).Name = "URL"
        args(0).Value = "__SECOND_FILE_URL__"
        oDoc = ThisComponent.CurrentController.Frame
        oDispatcher = createUnoService("com.sun.star.frame.DispatchHelper")
        oDispatcher.executeDispatch(oDoc, ".uno:CompareDocuments", "", 0, args())
        ThisComponent.store()
        ThisComponent.close(True)
    End Sub
</script:module>"""


def _install_compare_macro(second_file_path: Path) -> bool:
    """Install the compare macro with the second file's URL baked in.

    The macro runs against file1 (passed as ThisComponent on the soffice
    command line) and dispatches CompareDocuments with file2's URL as
    the comparison source.
    """
    try:
        # Ensure the profile + Standard library are scaffolded.
        macro_dir = Path(MACRO_DIR)
        if not macro_dir.exists():
            subprocess.run(
                [
                    LIBREOFFICE_BIN,
                    "--headless",
                    f"-env:UserInstallation=file://{LIBREOFFICE_PROFILE}",
                    "--terminate_after_init",
                ],
                capture_output=True,
                timeout=30,
                check=False,
            )
            macro_dir.mkdir(parents=True, exist_ok=True)

        second_url = "file://" + str(second_file_path.absolute())
        macro_xml = COMPARE_MACRO_TEMPLATE.replace("__SECOND_FILE_URL__", second_url)
        (macro_dir / "Module1.xba").write_text(macro_xml)
        # Force reinstall on next accept/reject call so the macro reverts.
        global _MACRO_INSTALLED
        _MACRO_INSTALLED = False
        logger.info(f"Installed compare macro pointing at {second_url}")
        return True
    except Exception as e:
        logger.error(f"Failed to install compare macro: {e}")
        return False


@app.post("/compare")
async def compare_documents(
    file1: UploadFile = File(..., description="Baseline document (before)"),
    file2: UploadFile = File(..., description="Revised document (after)"),
):
    """Compare two DOCX files. Returns a redlined DOCX showing file2's
    differences from file1 as tracked changes.

    Uses LibreOffice's native ``.uno:CompareDocuments`` dispatcher — which
    handles paragraph-mark migration, run-property tracking, and table-cell
    edge cases that hand-rolled diff approaches miss.
    """
    if not file1.filename or not file2.filename:
        raise HTTPException(status_code=400, detail="Both file1 and file2 require filenames")
    for f in (file1, file2):
        ext = os.path.splitext(f.filename)[1].lower()
        if ext != ".docx":
            raise HTTPException(
                status_code=400,
                detail=f"Only .docx supported, got {ext} for {f.filename}",
            )

    content1 = await file1.read()
    content2 = await file2.read()
    logger.info(
        f"compare: file1={file1.filename} ({len(content1)} bytes), "
        f"file2={file2.filename} ({len(content2)} bytes)"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        path1 = Path(tmpdir) / "before.docx"
        path2 = Path(tmpdir) / "after.docx"
        path1.write_bytes(content1)
        path2.write_bytes(content2)

        if not _install_compare_macro(path2):
            raise HTTPException(status_code=500, detail="Failed to install compare macro")

        cmd = [
            LIBREOFFICE_BIN,
            "--headless",
            f"-env:UserInstallation=file://{LIBREOFFICE_PROFILE}",
            "--norestore",
            "vnd.sun.star.script:Standard.Module1.CompareWithSecondFile?language=Basic&location=application",
            str(path1.absolute()),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="Compare timed out")

        if result.returncode != 0:
            logger.error(
                f"Compare macro failed: stdout={result.stdout[:300]} "
                f"stderr={result.stderr[:300]}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Compare failed: {result.stderr[:500]}",
            )

        if not path1.exists():
            raise HTTPException(
                status_code=500,
                detail="Output missing after compare macro",
            )

        out_bytes = path1.read_bytes()
        out_name = f"{Path(file1.filename).stem}_vs_{Path(file2.filename).stem}_redlined.docx"
        logger.info(f"compare ok: {out_name} ({len(out_bytes)} bytes)")

        try:
            out_name.encode("ascii")
            disposition = f'inline; filename="{out_name}"'
        except UnicodeEncodeError:
            encoded = quote(out_name)
            disposition = (
                f'inline; filename="redlined.docx"; filename*=UTF-8\'\'{encoded}'
            )

        return Response(
            content=out_bytes,
            media_type=OUTPUT_FORMATS["docx"]["mime"],
            headers={"Content-Disposition": disposition},
        )


@app.get("/")
async def root():
    return {
        "service": "LibreOffice Document Preview Service",
        "version": "1.2.0",
        "endpoints": {
            "/convert": "POST - Convert document to PDF/DOCX",
            "/tracked-changes/accept": "POST - Accept all tracked changes, return cleaned DOCX",
            "/tracked-changes/reject": "POST - Reject all tracked changes, return original-state DOCX",
            "/compare": "POST - Compare two DOCX files (file1=before, file2=after), return redlined DOCX",
            "/health": "GET - Health check",
        },
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8002"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.getenv("ENV", "development") == "development",
    )
