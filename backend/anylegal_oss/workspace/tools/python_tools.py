"""
Python Interpreter Tool

Executes Python code in a sandboxed Docker container with pre-installed libraries.
Used for complex document generation, data analysis, calculations, validation,
and any task requiring programmatic logic.

The sandbox has NO network access, 256MB memory limit, and 60-second timeout.
Pre-installed: python-docx, openpyxl, pandas, lxml, matplotlib, reportlab,
pymupdf4llm, python-dateutil, Pillow, tabulate, regex.
"""

import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional, List

from ..session import WorkspaceSession

logger = logging.getLogger(__name__)

SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "anylegal-sandbox:latest")
SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "120"))
SANDBOX_MEMORY = os.getenv("SANDBOX_MEMORY", "512m")
SANDBOX_CPUS = os.getenv("SANDBOX_CPUS", "1")
MAX_INPUT_BYTES = 50 * 1024 * 1024                         
MAX_OUTPUT_BYTES = 50 * 1024 * 1024                         
MAX_STDOUT = 10000          
MAX_STDERR = 5000           

SANDBOX_TMPDIR = os.getenv("SANDBOX_TMPDIR", None)

DOCX_EXTENSIONS = {".docx"}
BINARY_EXTENSIONS = {".xlsx", ".pdf", ".png", ".jpg", ".jpeg", ".svg", ".pptx"}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".yaml", ".yml"}

_FORBIDDEN_FILENAME_SUFFIX = re.compile(
    r'[_\-](Part\d+|Final|Draft|v\d+|Copy|Backup|Revised|Updated)(?=\.[^/.]+$|$)',
    re.IGNORECASE,
)

def _strip_forbidden_suffix(name: str) -> str:
    """Return the name with any forbidden fragment suffix removed."""
    return _FORBIDDEN_FILENAME_SUFFIX.sub('', name, count=1)

EXTENSION_MIMES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xml": "application/xml",
    ".html": "text/html",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}

def _check_docker_available() -> Optional[str]:
    """Check if Docker is available. Returns error message or None."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return "Docker daemon is not running"
        return None
    except FileNotFoundError:
        return "Docker is not installed or not in PATH"
    except subprocess.TimeoutExpired:
        return "Docker daemon is not responding"

def _convert_doc_to_docx(blob: bytes, filename: str) -> Optional[bytes]:
    """
    Convert .doc binary to .docx via the LibreOffice service.
    Returns .docx bytes or None if conversion fails.
    """
    try:
        import requests as http_requests
        libreoffice_url = os.environ.get("LIBREOFFICE_SERVICE_URL", "http://localhost:8002")
        resp = http_requests.post(
            f"{libreoffice_url}/convert",
            files={"file": (filename, blob, "application/msword")},
            params={"format": "docx"},
            timeout=120,
        )
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/"):
            logger.info(f".doc → .docx conversion succeeded for {filename} ({len(resp.content)} bytes)")
            return resp.content
    except Exception as e:
        logger.warning(f".doc → .docx conversion failed for {filename}: {e}")
    return None

def _extract_input_files(
    session: WorkspaceSession,
    input_files: List[str],
    input_dir: str,
) -> List[Dict[str, Any]]:
    """
    Extract requested workspace files to the sandbox input directory.
    .doc files are auto-converted to .docx via LibreOffice service.
    Returns list of extracted file metadata.
    """
    extracted = []
    total_bytes = 0

    for path in input_files:

        doc = session.get_document(path)
        if doc:
            filename = Path(path).name

            if not doc.docx_blob and doc.binary_blob:
                try:
                    from .document_tools import _ensure_docx_blob
                    _ensure_docx_blob(doc, session)
                    if doc.docx_blob:
                        logger.info(f"On-demand .doc→.docx conversion for sandbox: {filename}")
                except Exception as e:
                    logger.warning(f"_ensure_docx_blob failed for {filename}: {e}")

            if doc.docx_blob:
                data = doc.docx_blob

                if not filename.lower().endswith('.docx'):
                    filename = Path(filename).stem + '.docx'
                out_path = os.path.join(input_dir, filename)
                with open(out_path, "wb") as f:
                    f.write(data)
                total_bytes += len(data)
                extracted.append({"path": path, "filename": filename, "size": len(data), "type": "docx"})
                logger.info(f"Sandbox input: {filename} mounted as DOCX ({len(data)} bytes)")

            elif doc.binary_blob:
                data = doc.binary_blob

                is_doc = filename.lower().endswith(('.doc', '.dot'))
                mime = getattr(doc, "mime_type", "") or ""
                if is_doc or mime in ("application/msword", "application/x-ole-storage"):
                    docx_data = _convert_doc_to_docx(data, filename)
                    if docx_data:
                        filename = Path(filename).stem + '.docx'
                        data = docx_data
                        file_type = "docx"
                    else:
                        logger.warning(f"Could not convert {filename} to .docx — mounting as-is")
                        file_type = "binary"
                        extracted.append({
                            "path": path, "filename": filename, "size": len(data),
                            "type": "binary",
                            "warning": (
                                f"'{filename}' is a .doc file that could not be converted to .docx. "
                                f"LibreOffice service at {os.environ.get('LIBREOFFICE_SERVICE_URL', 'http://localhost:8002')} "
                                f"may not be running. python-docx CANNOT open .doc files. "
                                f"Tell the user to either start the LibreOffice service or upload a .docx version."
                            ),
                        })
                        out_path = os.path.join(input_dir, filename)
                        with open(out_path, "wb") as f:
                            f.write(data)
                        total_bytes += len(data)
                        continue
                else:
                    file_type = "binary"
                out_path = os.path.join(input_dir, filename)
                with open(out_path, "wb") as f:
                    f.write(data)
                total_bytes += len(data)
                extracted.append({"path": path, "filename": filename, "size": len(data), "type": file_type})

            elif doc.content:
                data = doc.content.encode("utf-8")

                if not Path(filename).suffix:
                    filename += ".txt"
                out_path = os.path.join(input_dir, filename)
                with open(out_path, "wb") as f:
                    f.write(data)
                total_bytes += len(data)
                extracted.append({"path": path, "filename": filename, "size": len(data), "type": "text"})

            else:
                logger.warning(f"Document '{path}' has no readable content")
                continue

        else:

            wf_content = session.workspace_files.get(path)
            if wf_content:
                filename = Path(path).name
                data = wf_content.encode("utf-8")
                out_path = os.path.join(input_dir, filename)
                with open(out_path, "wb") as f:
                    f.write(data)
                total_bytes += len(data)
                extracted.append({"path": path, "filename": filename, "size": len(data), "type": "workspace_file"})
            else:
                available = list(session.documents.keys()) + list(session.workspace_files.keys())
                logger.warning(f"File not found in workspace: {path}. Available: {available}")
                extracted.append({
                    "path": path, "filename": Path(path).name, "size": 0,
                    "type": "missing",
                    "error": f"File '{path}' not found. Available documents: {available}"
                })

        if total_bytes > MAX_INPUT_BYTES:
            logger.warning(f"Input file cap reached ({total_bytes} bytes). Skipping remaining files.")
            break

    return extracted

def _import_output_files(
    session: WorkspaceSession,
    output_dir: str,
) -> List[Dict[str, Any]]:
    """
    Import files from sandbox output directory back into the workspace.
    Returns list of imported file metadata.
    """
    imported = []
    total_bytes = 0

    output_dir_real = os.path.realpath(output_dir)

    for name in sorted(os.listdir(output_dir)):

        if name == "_result.json":
            continue

        filepath = os.path.join(output_dir, name)
        # Reject anything that escapes output_dir via symlink. A malicious
        # script could ln -s /etc/passwd /sandbox/output/foo.txt — without
        # this, the host would happily read it back into the workspace.
        try:
            real = os.path.realpath(filepath)
        except OSError:
            continue
        if not real.startswith(output_dir_real + os.sep) and real != output_dir_real:
            logger.warning(
                f"Rejecting sandbox output {name!r}: realpath {real!r} "
                f"outside {output_dir_real!r}"
            )
            continue
        # lstat (not stat) so symlinks-to-files inside output_dir are also
        # caught and rejected; legitimate scripts produce regular files.
        try:
            st = os.lstat(filepath)
        except OSError:
            continue
        from stat import S_ISLNK, S_ISREG
        if S_ISLNK(st.st_mode) or not S_ISREG(st.st_mode):
            logger.warning(f"Rejecting sandbox output {name!r}: not a regular file")
            continue

        if _FORBIDDEN_FILENAME_SUFFIX.search(name):
            base = _strip_forbidden_suffix(name)
            size = os.path.getsize(filepath)
            logger.warning(f"Rejecting forbidden filename: {name!r} → suggested base {base!r}")
            imported.append({
                "path": name,
                "size": size,
                "added_to_workspace": False,
                "type": "rejected",
                "error": (
                    f"Filename '{name}' was REJECTED. Suffixes like _Part1, _Final, "
                    f"_Draft, _v2, _Copy are not permitted — a logical document must "
                    f"live under one filename and grow across calls. "
                    f"Save under the base filename '{base}' instead. "
                    f"To append to an existing document, pass input_files=['{base}'] "
                    f"and save back to '/sandbox/output/{base}'. "
                    f"Do NOT create a second file to work around this."
                ),
            })
            continue

        size = os.path.getsize(filepath)
        total_bytes += size
        if total_bytes > MAX_OUTPUT_BYTES:
            logger.warning(f"Output cap reached ({total_bytes} bytes). Skipping: {name}")
            break

        ext = Path(name).suffix.lower()
        entry = {"path": name, "size": size, "added_to_workspace": False}

        try:
            if ext in DOCX_EXTENSIONS:
                with open(filepath, "rb") as f:
                    docx_bytes = f.read()

                target_name = name
                existing = session.get_document(name)
                if existing is not None and getattr(existing, "docx_blob", None):
                    from .document_tools import (
                        _strip_version_suffix,
                        _find_latest_version,
                    )
                    base = _strip_version_suffix(name)
                    _latest_path, next_version = _find_latest_version(session, base)
                    candidate = _latest_path

                    if candidate == base:
                        from .document_tools import _version_path
                        candidate = _version_path(base, next_version)
                    target_name = candidate
                    if target_name != name:
                        entry["routed_to"] = target_name
                        logger.info(
                            f"run_code DOCX import auto-clone: "
                            f"'{name}' would clobber existing source → routed to '{target_name}'"
                        )

                if target_name not in session.documents:
                    session.add_document(
                        path=target_name,
                        content="",
                        description="Generated by run_python",
                    )
                doc = session.get_document(target_name)
                if doc:
                    doc.update_docx(docx_bytes)
                    doc.format = "docx"
                    entry["path"] = target_name
                    entry["added_to_workspace"] = True
                    entry["type"] = "docx"

            elif ext in BINARY_EXTENSIONS:
                with open(filepath, "rb") as f:
                    blob = f.read()

                content = ""
                if ext == ".xlsx":
                    try:
                        from .document_tools import extract_xlsx_text
                        content = extract_xlsx_text(blob, name)
                    except Exception:
                        pass
                elif ext == ".pptx":
                    try:
                        from .document_tools import extract_pptx_text
                        content = extract_pptx_text(blob, name)
                    except Exception:
                        pass
                session.add_document(path=name, content=content, description="Generated by run_python")
                doc = session.get_document(name)
                if doc:
                    doc.binary_blob = blob
                    doc.mime_type = EXTENSION_MIMES.get(ext, "application/octet-stream")
                    doc.format = ext.lstrip(".")
                    entry["added_to_workspace"] = True
                    entry["type"] = "binary"

            elif ext in TEXT_EXTENSIONS:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
                session.add_document(path=name, content=text, description="Generated by run_python")
                doc = session.get_document(name)
                if doc:
                    doc.mime_type = EXTENSION_MIMES.get(ext, "text/plain")
                    doc.format = "markdown" if ext in (".md", ".markdown") else "text"
                    doc.binary_blob = text.encode('utf-8')
                entry["added_to_workspace"] = True
                entry["type"] = "text"

            else:

                with open(filepath, "rb") as f:
                    blob = f.read()
                session.add_document(path=name, content="", description="Generated by run_python")
                doc = session.get_document(name)
                if doc:
                    doc.binary_blob = blob
                    doc.mime_type = "application/octet-stream"
                    doc.format = "other"
                    entry["added_to_workspace"] = True
                    entry["type"] = "binary"

        except Exception as e:
            logger.error(f"Failed to import output file '{name}': {e}")
            entry["error"] = str(e)

        imported.append(entry)

    return imported

SUPPORTED_LANGUAGES = {"python", "node"}

_JS_SIGNALS = re.compile(
    r"""
    ^\s*(?:
        const\s+\w+\s*=          # const x = ...
      | let\s+\w+\s*=            # let x = ...
      | var\s+\w+\s*=            # var x = ...
      | (?:async\s+)?function\s* # function / async function
      | require\s*\(             # require(...)
      | import\s+[\w{,\s*}]+\s+from\s+['"]  # import X from '...'
      | module\.exports\s*=      # module.exports = ...
    )
    """,
    re.MULTILINE | re.VERBOSE,
)
_PY_SIGNALS = re.compile(
    r"""
    ^\s*(?:
        from\s+[\w.]+\s+import\b   # from X import Y
      | import\s+[\w,\s]+$         # import X, Y  (no `from`)
      | def\s+\w+\s*\(             # def name(
      | class\s+\w+\s*[:\(]        # class Name:
      | print\s*\(                 # print(
      | if\s+__name__\s*==         # if __name__ ==
    )
    """,
    re.MULTILINE | re.VERBOSE,
)

_UNICODE_BULLET_TEXTRUN = re.compile(
    r"""new\s+TextRun\s*\(\s*['"`][•●]""",
    re.VERBOSE,
)
_UNICODE_BULLET_CHILDREN = re.compile(
    r"""children\s*:\s*\[\s*['"`][•●]""",
    re.VERBOSE,
)

def _lint_docx_js_code(code: str) -> Optional[str]:
    """Return an error string to reject the run, or None to allow.

    Implements the SKILL.md "NEVER use unicode bullets" rule as a pre-
    execution check on submitted Node code. The skill says to use
    ``LevelFormat.BULLET`` with a ``numbering`` config, not unicode
    bullet glyphs inside a TextRun.
    """
    for pattern in (_UNICODE_BULLET_TEXTRUN, _UNICODE_BULLET_CHILDREN):
        if pattern.search(code):
            return (
                "Rejected: docx-js code contains a unicode bullet glyph "
                "(`•` or `●`) as a list marker inside a TextRun or "
                "children array. The SKILL.md rule is: use "
                "`LevelFormat.BULLET` with a `numbering` config on the "
                "Document, not hand-typed bullet characters. Replace "
                "`new TextRun('• Item')` with a Paragraph that has "
                "`numbering: { reference: 'bullets', level: 0 }` and "
                "declare `numbering.config` on the Document per the skill's "
                "'Lists (NEVER use unicode bullets)' example. Re-submit."
            )
    return None

def _docx_is_valid(blob: bytes) -> bool:
    """Return True if the blob unzips and has word/document.xml. Used to
    decide whether a prior run_code write was 'good enough' that a second
    overwrite is the split/skeleton anti-pattern rather than a legitimate
    self-correction of a broken first attempt."""
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            if "word/document.xml" not in zf.namelist():
                return False

            try:
                ET.fromstring(zf.read("word/document.xml"))
            except ET.ParseError:
                return False
    except zipfile.BadZipFile:
        return False
    return True

def _detect_split_write(session: "WorkspaceSession", code: str) -> Optional[str]:
    """Return an error to reject, or None to allow.

    Implements the SKILL.md "one document = one run_code call" rule.
    Scans the incoming Node code for ``fs.writeFileSync('/sandbox/output/
    FOO.docx', ...)`` targets. If FOO.docx already exists in the session
    workspace as a valid DOCX, the incoming call is either a split
    (writing Part 2 into the same file) or a skeleton-then-fill (rewriting
    an already-good doc). Either is the anti-pattern and gets rejected.

    If the existing doc fails ``_docx_is_valid`` the model is allowed to
    rewrite — legitimate self-correction of a broken first attempt.
    """

    targets = re.findall(
        r"""fs\.writeFileSync\s*\(\s*['"`](/sandbox/output/[^'"`]+\.docx)['"`]""",
        code,
    )
    for target in targets:
        name = target.rsplit("/", 1)[-1]
        existing = session.get_document(name) if hasattr(session, "get_document") else None
        blob = getattr(existing, "docx_blob", None) if existing else None
        if not blob:
            continue
        if not _docx_is_valid(blob):

            continue
        return (
            f"Rejected: `{name}` already exists in the workspace as a valid "
            f"DOCX ({len(blob):,} bytes) from an earlier run_code call in "
            f"this session. The SKILL.md rule is: one document = one "
            f"run_code call, no exceptions. A second write to the same "
            f"filename is the split-across-calls / skeleton-then-fill "
            f"anti-pattern. If you need to add content, EXPAND the first "
            f"call — do NOT overwrite an already-good document. If you "
            f"need a separate logical document (e.g. a side letter), use "
            f"a different filename. Re-submit."
        )
    return None

def _detect_language_from_code(code: str) -> Optional[str]:
    """Return ``"node"`` / ``"python"`` / ``None`` based on code content.

    ``None`` means ambiguous — the caller should keep the user-supplied
    language field (or the default). We only override when the signal is
    one-sided: JS tokens + no Python tokens ⇒ Node.
    """

    sample_lines: List[str] = []
    for ln in code.splitlines():
        stripped = ln.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        sample_lines.append(ln)
        if len(sample_lines) >= 20:
            break
    sample = "\n".join(sample_lines)
    if not sample:
        return None

    has_js = bool(_JS_SIGNALS.search(sample))
    has_py = bool(_PY_SIGNALS.search(sample))
    if has_js and not has_py:
        return "node"
    if has_py and not has_js:
        return "python"
    return None

def run_code(
    session: WorkspaceSession,
    code: str,
    language: str = "python",
    input_files: Optional[List[str]] = None,
    description: str = "",
    **kwargs
) -> Dict[str, Any]:
    """
    Execute code in a sandboxed Docker container.

    The sandbox image has Python 3.11 + Node.js 20 pre-installed. Other
    interpreters are reachable via ``subprocess`` from within either language.

    Args:
        session: Workspace session (for file I/O).
        code: Source code to execute.
        language: ``"python"`` (default) or ``"node"``. Selects the interpreter
                  that runs ``code`` directly. For ``"python"`` the code runs
                  through ``/sandbox/run.py`` harness which captures stdout/
                  stderr into ``_result.json``. For ``"node"`` the code runs
                  directly under ``node``; stdout/stderr are captured from
                  the subprocess.
        input_files: Optional list of workspace document paths to make
                  available under ``/sandbox/input/``.
        description: Brief description of what the code does.

    Returns:
        Dict with stdout, stderr, exit_code, and any output files added to
        the workspace.
    """
    start_time = time.time()

    if not code or not code.strip():
        return {
            "success": False,
            "error": (
                "run_code requires a non-empty 'code' parameter (the "
                "source code to execute). You called the tool with no "
                "code — likely your tool_arguments object was empty. "
                "Retry with the full schema: "
                "run_code(language=\"python\"|\"node\", code=\"<your code>\", "
                "input_files=[optional], description=\"<brief>\")."
            ),
        }

    language = (language or "python").lower().strip()
    if language not in SUPPORTED_LANGUAGES:
        return {
            "success": False,
            "error": (
                f"Unsupported language: {language!r}. "
                f"Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}."
            ),
        }

    detected = _detect_language_from_code(code)
    if detected and detected != language:
        logger.warning(
            f"[run_code] language mismatch: caller passed {language!r} but "
            f"code looks like {detected!r} — auto-flipping. First 60 chars: "
            f"{code.strip()[:60]!r}"
        )
        language = detected

    if language == "node":
        lint_err = _lint_docx_js_code(code)
        if lint_err:
            return {"success": False, "error": lint_err}
        split_err = _detect_split_write(session, code)
        if split_err:
            return {"success": False, "error": split_err}

    docker_error = _check_docker_available()
    if docker_error:
        return {"success": False, "error": f"Cannot run sandbox: {docker_error}"}

    tmpdir = None
    try:

        tmpdir = tempfile.mkdtemp(prefix="sandbox_", dir=SANDBOX_TMPDIR)
        input_dir = os.path.join(tmpdir, "input")
        output_dir = os.path.join(tmpdir, "output")
        code_filename = "code.py" if language == "python" else "code.js"
        code_path = os.path.join(tmpdir, code_filename)
        os.makedirs(input_dir)
        os.makedirs(output_dir, mode=0o777)
        os.chmod(output_dir, 0o777)                                                

        extracted = []
        if input_files:
            extracted = _extract_input_files(session, input_files, input_dir)

        with open(code_path, "w", encoding="utf-8") as f:
            f.write(code)

        # --read-only makes the root filesystem immutable; LibreOffice's
        # profile dir write goes to /tmp via HOME, which lives on a tmpfs.
        # The /sandbox/output bind is the only writable surface.
        cmd = [
            "docker", "run", "--rm",
            "--read-only",
            "--network", "none",
            "--memory", SANDBOX_MEMORY,
            "--cpus", SANDBOX_CPUS,
            "--pids-limit", "128",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--tmpfs", "/tmp:size=64m",
            "-e", "HOME=/tmp",
            "-v", f"{input_dir}:/sandbox/input:ro",
            "-v", f"{output_dir}:/sandbox/output",
            "-v", f"{code_path}:/sandbox/{code_filename}:ro",
            "--user", "1000:1000",
        ]
        if language == "node":
            cmd += ["--entrypoint", "node", SANDBOX_IMAGE, f"/sandbox/{code_filename}"]
        else:
            cmd += [SANDBOX_IMAGE]

        import concurrent.futures
        try:
            def _run_sandbox():
                return subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=SANDBOX_TIMEOUT,
                )
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_run_sandbox)
                proc = future.result(timeout=SANDBOX_TIMEOUT + 10)
        except (subprocess.TimeoutExpired, concurrent.futures.TimeoutError):
            return {
                "success": False,
                "error": f"Execution timed out after {SANDBOX_TIMEOUT} seconds",
                "execution_time_ms": (time.time() - start_time) * 1000,
                "description": description,
            }

        result_json_path = os.path.join(output_dir, "_result.json")
        sandbox_result = None
        if os.path.exists(result_json_path):
            try:
                with open(result_json_path, "r") as f:
                    sandbox_result = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        if sandbox_result:
            stdout = sandbox_result.get("stdout", "")
            stderr = sandbox_result.get("stderr", "")
            exit_code = sandbox_result.get("exit_code", proc.returncode)
        else:
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            exit_code = proc.returncode

        files_created = _import_output_files(session, output_dir)

        validation_errors = []
        validation_warnings = []
        for f_entry in files_created:
            if f_entry.get("type") == "docx" and f_entry.get("added_to_workspace"):
                try:
                    doc = session.get_document(f_entry["path"])
                    if doc and doc.docx_blob:

                        from .validators.docx_fixer import auto_fix_docx
                        is_new = not bool(input_files)                                         
                        fixed_blob, fixes_applied = auto_fix_docx(doc.docx_blob, is_new_document=is_new)
                        if fixes_applied:
                            doc.update_docx(fixed_blob)
                            logger.info(f"Auto-fixed DOCX {f_entry['path']}: {fixes_applied}")

                        from .validators.docx_validator import validate_docx_output
                        validation = validate_docx_output(
                            doc.docx_blob,
                            level="full",
                        )
                        if validation.get("repaired_bytes"):
                            doc.update_docx(validation["repaired_bytes"])
                            logger.info(
                                f"XSD auto-repaired {validation['repairs_made']} issues "
                                f"in {f_entry['path']}"
                            )
                        if not validation.get("valid", True):
                            validation_errors.extend(validation.get("errors", []))
                        validation_warnings.extend(validation.get("warnings", []))
                except ImportError:
                    pass
                except Exception as e:
                    logger.warning(f"DOCX validation/fix failed for {f_entry['path']}: {e}")

        if any(f.get("added_to_workspace") for f in files_created):
            session.save()

        execution_time_ms = (time.time() - start_time) * 1000
        rejected_files = [f for f in files_created if f.get("type") == "rejected"]

        success = exit_code == 0 and not rejected_files

        ephemeral_hint = ""
        if not success and stderr and "/sandbox/output/" in stderr and "FileNotFoundError" in stderr:
            ephemeral_hint = (
                "HINT: Each run_python execution uses a fresh ephemeral container. "
                "Files from previous runs do NOT persist at /sandbox/output/. "
                "To modify a previously created document, pass it via input_files "
                "and open it from /sandbox/input/<filename> instead."
            )

        result = {
            "success": success,
            "stdout": stdout[:MAX_STDOUT],
            "stderr": stderr[:MAX_STDERR] if stderr else "",
            "exit_code": exit_code,
            "execution_time_ms": round(execution_time_ms, 1),
            "files_created": files_created,
            "files_input": extracted,
            "description": description,
        }

        if ephemeral_hint:
            result["hint"] = ephemeral_hint

        if not success:
            parts: List[str] = []

            runtime_label = "Node.js" if language == "node" else "Python"
            tb_lines = [ln for ln in (stderr or "").splitlines() if ln.strip()]
            if tb_lines:
                tail = tb_lines[-1]
                excerpt = "\n".join(tb_lines[-10:]) if len(tb_lines) > 1 else tail
                parts.append(
                    f"{runtime_label} exited with code {exit_code}: {tail}\n\n"
                    f"Traceback tail:\n{excerpt}"
                )
            elif exit_code != 0:
                parts.append(
                    f"{runtime_label} exited with code {exit_code} (no stderr output; check stdout)"
                )

            for rej in rejected_files:
                parts.append(rej["error"])

            missing_inputs = [f for f in extracted if f.get("type") == "missing"]
            if missing_inputs:
                parts.append(
                    "Missing input files: "
                    + ", ".join(f["path"] for f in missing_inputs)
                    + ". Pass the correct workspace path via input_files, "
                    "or omit input_files if creating from scratch."
                )

            if ephemeral_hint:
                parts.append(ephemeral_hint)

            result["error"] = "\n\n".join(parts) if parts else "Unknown failure"

        if validation_errors:
            result["validation_errors"] = validation_errors
        if validation_warnings:
            result["validation_warnings"] = validation_warnings

            logger.info(f"DOCX formatting warnings for {[f['path'] for f in files_created]}: {validation_warnings}")

        return result

    except Exception as e:
        logger.error(f"run_python tool error: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"Sandbox execution error: {str(e)}",
            "execution_time_ms": round((time.time() - start_time) * 1000, 1),
            "description": description,
        }

    finally:

        if tmpdir and os.path.exists(tmpdir):
            try:
                shutil.rmtree(tmpdir)
            except Exception as e:
                logger.warning(f"Failed to clean up temp dir {tmpdir}: {e}")

PYTHON_TOOLS = {
    "run_code": run_code,
}
