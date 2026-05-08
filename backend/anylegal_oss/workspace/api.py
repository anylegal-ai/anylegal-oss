"""
Flask API routes for the Document Editor module.

Provides endpoints for clause analysis, redline generation, and 
playbook management. Designed to be consumed by Word Add-in and 
future web editor clients.
"""

import io
import json
import logging
import os
import re
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse, Response, PlainTextResponse
from functools import wraps

from .services import PlaybookService, get_provider_extra_body
from .db import init_document_editor_tables

from anylegal_oss.db.database import (
    get_user_preferred_model, log_chat_to_thread,
)

logger = logging.getLogger(__name__)

OSS_USER_ID = 1                              
router = APIRouter(prefix='/api/v1/editor', tags=['editor'])

@router.get('/chat/agentic/tools')
def list_agentic_tools():
    """
    List available tools for the agentic workspace.

    Response:
        {
            "tools": [
                {"name": "read_document", "description": "...", "category": "document_management"},
                ...
            ],
            "categories": ["document_management", "web_research", "playbook", "legal_analysis"]
        }
    """
    from .tools.workspace_tools import WORKSPACE_TOOLS, TOOL_CATEGORIES

    tools = []
    for tool in WORKSPACE_TOOLS:

        category = "other"
        for cat, tool_names in TOOL_CATEGORIES.items():
            if tool["name"] in tool_names:
                category = cat
                break

        tools.append({
            "name": tool["name"],
            "description": tool["description"],
            "category": category,
            "parameters": tool["input_schema"]
        })

    return ({
        "tools": tools,
        "categories": list(TOOL_CATEGORIES.keys()),
        "count": len(tools)
    })

@router.get('/chat/agentic/skills')
def list_agentic_skills():
    """
    List available skills and slash commands.

    Response:
        {
            "skills": [
                {"name": "contract-review", "emoji": "📋", "description": "...", "tags": [...]},
                ...
            ],
            "slash_commands": [
                {"command": "/review", "skill": "contract-review", "emoji": "📋", "description": "..."},
                ...
            ]
        }
    """
    from .skills.skill_loader import create_skill_loader

    loader = create_skill_loader()
    skills = loader.discover_skills()

    skill_list = [
        {
            "name": s.name,
            "emoji": s.emoji,
            "description": s.description,
            "tags": s.tags,
        }
        for s in skills
    ]
    slash_commands = [
        {
            "command": f"/{s.name}",
            "skill": s.name,
            "description": s.description,
            "emoji": s.emoji,
        }
        for s in skills
    ]

    return ({
        "skills": skill_list,
        "slash_commands": slash_commands,
    })

@router.get('/chat/agentic/workspace/tree')
def get_workspace_tree():
    """
    Get the workspace file tree for the sidebar.

    Returns a tree structure with:
    - agents.md (user-controlled config)
    - Documents/ (session documents)
    - Playbook/ (positions, preferences)
    - Skills/ (read-only skill definitions)

    Query params:
        session_id: (deprecated) Ignored — workspace is loaded by user_id
    """
    from .workspace import Workspace
    user_id = OSS_USER_ID
    workspace = Workspace.get_or_create(user_id)

    return ({
        "tree": workspace.get_file_tree(),
        "session_id": workspace.workspace_id,                   
        "workspace_id": workspace.workspace_id,
    })

@router.get('/chat/agentic/workspace/file')
def get_workspace_file(request: Request):
    """
    Read a workspace file by path.

    Query params:
        session_id: (deprecated) Ignored — workspace is loaded by user_id
        path: File path (e.g., "agents.md", "Playbook/positions.md", "Skills/review/SKILL.md")
    """
    user_id = OSS_USER_ID
    file_path = request.query_params.get('path', '')

    if not file_path:
        raise HTTPException(status_code=400, detail="path parameter required")

    if file_path.startswith("Skills/"):
        import os
        skills_base = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills"))
        relative = file_path.replace("Skills/", "", 1)
        full_path = os.path.normpath(os.path.join(skills_base, relative))

        if not full_path.startswith(skills_base + os.sep) and full_path != skills_base:
            raise HTTPException(status_code=403, detail="Invalid path")

        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail=f"Skill file not found: {file_path}")

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        return ({
            "path": file_path,
            "content": content,
            "format": "markdown",
            "editable": False,
        })

    from .workspace import Workspace
    workspace = Workspace.get_or_create(user_id)

    if file_path.endswith("anylegal.md") or file_path in ("agents.md",):
        content = workspace.workspace_files.get(file_path, "")

        if file_path == "agents.md":
            content = workspace.agents_md or ""
        return ({
            "path": file_path,
            "content": content,
            "format": "markdown",
            "editable": True,
        })

    if file_path.startswith("Playbook/"):
        content = workspace.get_workspace_file(file_path)
        return ({
            "path": file_path,
            "content": content or "",
            "format": "markdown",
            "editable": True,
        })

    doc = workspace.get_document(file_path)
    if doc:
        return ({
            "path": file_path,
            "content": doc.content,
            "description": doc.description,
            "format": doc.format,
            "editable": True,
            "has_docx": doc.docx_blob is not None,
        })

    raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

@router.put('/chat/agentic/workspace/file')
async def save_workspace_file(request: Request):
    """
    Save a workspace file (agents.md, playbook files).

    Body:
        {
            "path": "agents.md",
            "content": "# My Agent Config\n..."
        }
    """
    from .workspace import Workspace

    user_id = OSS_USER_ID
    data = await request.json()

    if not data:
        raise HTTPException(status_code=400, detail="JSON body required")

    file_path = data.get('path', '')
    content = data.get('content', '')

    if not file_path:
        raise HTTPException(status_code=400, detail="path is required")

    if file_path.startswith("Skills/"):
        raise HTTPException(status_code=403, detail="Skill files are read-only")

    workspace = Workspace.get_or_create(user_id)

    if not Workspace.validate_path(file_path):
        raise HTTPException(status_code=400, detail="Invalid file path")

    if file_path in ("anylegal.md", "agents.md"):
        workspace.set_agents_md(content)
    elif file_path.endswith("/anylegal.md"):

        top_folder = file_path.split("/")[0]
        if top_folder in Workspace.NO_INSTRUCTIONS_FOLDERS:
            return ({"error": f"Instructions (anylegal.md) not allowed in {top_folder}/"}), 400
        workspace.set_workspace_file(file_path, content)
    elif file_path.startswith("Playbook/"):
        workspace.set_workspace_file(file_path, content)
    else:
        doc = workspace.get_document(file_path)
        if doc and doc.format == 'markdown':
            workspace.add_document(file_path, content, description=doc.description, set_active=False)
            refreshed = workspace.get_document(file_path)
            if refreshed:
                refreshed.format = 'markdown'
                refreshed.mime_type = 'text/markdown'
                refreshed.binary_blob = content.encode('utf-8')
        else:
            raise HTTPException(status_code=400, detail=f"Cannot save to path: {file_path}")

    workspace.save()

    return ({
        "success": True,
        "path": file_path,
        "session_id": workspace.workspace_id,                   
        "workspace_id": workspace.workspace_id,
    })

@router.delete('/chat/agentic/workspace/file')
def delete_workspace_file(request: Request):
    """
    Delete a workspace file (playbook files, anylegal.md, etc.).

    Query params:
        path: File path to delete (e.g., "Playbook/positions.md")
    """
    from .workspace import Workspace

    user_id = OSS_USER_ID
    file_path = request.query_params.get('path', '')

    if not file_path:
        raise HTTPException(status_code=400, detail="path is required")

    if file_path.startswith("Skills/"):
        raise HTTPException(status_code=403, detail="Skill files are read-only")

    workspace = Workspace.get_or_create(user_id)

    if not Workspace.validate_path(file_path):
        raise HTTPException(status_code=400, detail="Invalid file path")

    if file_path in ("anylegal.md", "agents.md"):
        workspace.workspace_files.pop("anylegal.md", None)
    elif file_path.endswith("/anylegal.md"):
        workspace.workspace_files.pop(file_path, None)
    elif file_path.startswith("Playbook/"):
        workspace.workspace_files.pop(file_path, None)
    else:
        workspace.workspace_files.pop(file_path, None)

    workspace.remove_document(file_path)

    workspace.save()

    return ({
        "success": True,
        "path": file_path,
        "session_id": workspace.workspace_id,                   
        "workspace_id": workspace.workspace_id,
    })

@router.post('/chat/agentic/workspace/folders')
async def create_workspace_folder(request: Request):
    """
    Create a folder in the workspace.

    Body:
        {
            "folder_path": "Clients/Acme/"
        }
    """
    from .workspace import Workspace

    user_id = OSS_USER_ID
    data = await request.json()

    if not data:
        raise HTTPException(status_code=400, detail="JSON body required")

    folder_path = data.get('folder_path', '')

    if not folder_path:
        raise HTTPException(status_code=400, detail="folder_path is required")

    if not Workspace.validate_path(folder_path.rstrip('/') + '/x'):
        raise HTTPException(status_code=400, detail="Invalid folder path")

    workspace = Workspace.get_or_create(user_id)
    workspace.create_folder(folder_path)
    workspace.save()

    return ({
        "success": True,
        "folder_path": folder_path.replace("\\", "/").strip("/") + "/",
        "session_id": workspace.workspace_id,                   
        "workspace_id": workspace.workspace_id,
    })

@router.delete('/chat/agentic/workspace/folders')
async def delete_workspace_folder(request: Request):
    """
    Delete a folder and all its contents.

    Body:
        {
            "folder_path": "Clients/Acme/"
        }
    """
    from .workspace import Workspace

    user_id = OSS_USER_ID
    data = await request.json()

    if not data:
        raise HTTPException(status_code=400, detail="JSON body required")

    folder_path = data.get('folder_path', '')

    if not folder_path:
        raise HTTPException(status_code=400, detail="folder_path is required")

    if not Workspace.validate_path(folder_path.rstrip('/') + '/x'):
        raise HTTPException(status_code=400, detail="Invalid folder path")

    workspace = Workspace.get_or_create(user_id)

    try:
        deleted_count = workspace.delete_folder(folder_path)
    except ValueError as e:
        return ({"error": str(e)}), 403
    workspace.save()

    return ({
        "success": True,
        "folder_path": folder_path,
        "deleted_items": deleted_count,
        "session_id": workspace.workspace_id,                   
        "workspace_id": workspace.workspace_id,
    })

@router.post('/chat/agentic/workspace/move')
async def move_workspace_item(request: Request):
    """
    Move/rename a file or folder.

    Body:
        {
            "old_path": "contract.docx",
            "new_path": "Clients/Acme/contract.docx"
        }
    """
    from .workspace import Workspace

    user_id = OSS_USER_ID
    data = await request.json()

    if not data:
        raise HTTPException(status_code=400, detail="JSON body required")

    old_path = data.get('old_path', '')
    new_path = data.get('new_path', '')

    if not old_path or not new_path:
        raise HTTPException(status_code=400, detail="old_path and new_path are required")

    if not Workspace.validate_path(old_path) or not Workspace.validate_path(new_path):
        raise HTTPException(status_code=400, detail="Invalid path")

    workspace = Workspace.get_or_create(user_id)

    is_folder = old_path.endswith('/')

    if is_folder:

        old_prefix = old_path.rstrip('/') + '/'
        new_prefix = new_path.rstrip('/') + '/'
        if new_prefix.startswith(old_prefix):
            raise HTTPException(status_code=400, detail="Cannot move a folder into itself or its descendants")
        success = workspace.rename_folder(old_path, new_path)
    else:
        success = workspace.move_document(old_path, new_path)

    if not success:
        raise HTTPException(status_code=404, detail=f"Item not found: {old_path}")

    workspace.save()

    return ({
        "success": True,
        "old_path": old_path,
        "new_path": new_path,
        "session_id": workspace.workspace_id,                   
        "workspace_id": workspace.workspace_id,
    })

@router.post('/chat/agentic/workspace/upload')
async def upload_workspace_file(file: UploadFile = File(...), folder_path: str = Form('')):
    """
    Upload any file to the workspace (DOCX, PDF, PPTX, images, etc.).

    Request: multipart/form-data
        - file: the file to upload
        - folder_path: (optional) target folder, e.g. "Clients/Acme/"

    DOCX files get HTML conversion + XML editing support.
    Other files are stored as binary blobs (downloadable, shown in tree).
    """
    from .workspace import Workspace

    user_id = OSS_USER_ID

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")

    folder_path = folder_path.strip()

    filename = file.filename
    if folder_path:
        if not Workspace.validate_path(folder_path.rstrip('/') + '/' + filename):
            raise HTTPException(status_code=400, detail="Invalid folder path")
        doc_path = folder_path.rstrip('/') + '/' + filename
    else:
        doc_path = filename

    if not Workspace.validate_path(doc_path):
        raise HTTPException(status_code=400, detail="Invalid file name")

    def _flag_wiki_pending() -> None:
        from anylegal_oss.lexwiki_compiler.db import update_workspace_wiki_status
        try:
            update_workspace_wiki_status(workspace.workspace_id, 'pending')
        except Exception as e:
            logger.warning(f"Failed to mark wiki pending after upload: {e}")

    try:
        file_bytes = await file.read()
        if len(file_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty file")

        workspace = Workspace.get_or_create(user_id)

        lower_name = filename.lower()

        if lower_name.endswith('.docx') or lower_name.endswith('.doc'):

            from .docx_service import DocxService

            docx_bytes = file_bytes

            if lower_name.endswith('.doc') and not lower_name.endswith('.docx'):
                import requests as http_requests
                libreoffice_url = os.environ.get(
                    "LIBREOFFICE_SERVICE_URL", "http://localhost:8002"
                )
                try:
                    resp = http_requests.post(
                        f"{libreoffice_url}/convert",
                        files={"file": (filename, file_bytes, "application/msword")},
                        params={"format": "docx"},
                        timeout=120,
                    )
                    if resp.status_code == 200 and resp.headers.get(
                        "content-type", ""
                    ).startswith("application/"):
                        docx_bytes = resp.content

                        doc_path = doc_path.rsplit('.', 1)[0] + '.docx'
                        logger.info(
                            f".doc → .docx conversion succeeded ({len(file_bytes)} → {len(docx_bytes)} bytes)"
                        )
                    else:
                        logger.warning(
                            f".doc → .docx conversion failed (status {resp.status_code}), storing raw .doc blob"
                        )
                except Exception as e:
                    logger.warning(f".doc → .docx conversion unavailable ({e}), storing raw .doc blob")

            html_content = ""
            metadata: dict = {}
            try:
                html_content, conversion_messages = DocxService.docx_to_html(docx_bytes)
                metadata = DocxService.get_docx_metadata(docx_bytes)
            except Exception:

                html_content = f"<p>[Word document: {filename}]</p>"
                metadata = {"title": filename}

            workspace.add_document(
                path=doc_path,
                content=html_content,
                description=metadata.get('title') or filename,
                set_active=True,
            )
            doc = workspace.get_document(doc_path)
            if doc:
                doc.update_docx(docx_bytes, html_content)

            workspace.save()
            _flag_wiki_pending()
            return ({
                "success": True,
                "document_path": doc_path,
                "html_content": html_content,
                "metadata": metadata,
                "format": "docx",
                "size_bytes": len(docx_bytes),
            })

        elif lower_name.endswith('.pdf'):

            from .tools.web_tools import _extract_pdf_text

            result = _extract_pdf_text(file_bytes, filename, max_chars=200_000, max_pages=None)
            if result.get('success'):
                content = result['content']
            else:
                content = f"[PDF text extraction failed: {result.get('error', 'unknown error')}]"

            workspace.add_document(
                path=doc_path,
                content=content,
                description=filename,
                set_active=True,
            )
            doc = workspace.get_document(doc_path)
            if doc:
                doc.binary_blob = file_bytes
                doc.mime_type = 'application/pdf'
                doc.format = 'pdf'

            workspace.save()
            _flag_wiki_pending()
            return ({
                "success": True,
                "document_path": doc_path,
                "format": "pdf",
                "mime_type": "application/pdf",
                "size_bytes": len(file_bytes),
                "pdf_pages": result.get('pdf_pages'),
            })

        elif lower_name.endswith('.xlsx') or lower_name.endswith('.xls'):

            from .tools.document_tools import extract_xlsx_text
            xlsx_bytes = file_bytes

            if lower_name.endswith('.xls') and not lower_name.endswith('.xlsx'):
                import requests as http_requests
                libreoffice_url = os.environ.get("LIBREOFFICE_SERVICE_URL", "http://localhost:8002")
                try:
                    resp = http_requests.post(
                        f"{libreoffice_url}/convert",
                        files={"file": (filename, file_bytes, "application/vnd.ms-excel")},
                        params={"format": "xlsx"},
                        timeout=120,
                    )
                    if resp.status_code == 200:
                        xlsx_bytes = resp.content
                        doc_path = doc_path.rsplit('.', 1)[0] + '.xlsx'
                        logger.info(f".xls → .xlsx conversion succeeded ({len(file_bytes)} → {len(xlsx_bytes)} bytes)")
                    else:
                        logger.warning(f".xls → .xlsx conversion failed (status {resp.status_code})")
                except Exception as e:
                    logger.warning(f".xls → .xlsx conversion unavailable ({e}), attempting direct extraction")

            content = extract_xlsx_text(xlsx_bytes, filename)

            workspace.add_document(
                path=doc_path,
                content=content,
                description=filename,
                set_active=True,
            )
            doc = workspace.get_document(doc_path)
            if doc:
                doc.binary_blob = xlsx_bytes
                doc.mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                doc.format = 'xlsx'

            workspace.save()
            _flag_wiki_pending()
            return ({
                "success": True,
                "document_path": doc_path,
                "format": "xlsx",
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size_bytes": len(xlsx_bytes),
            })

        elif lower_name.endswith('.pptx') or lower_name.endswith('.ppt'):

            from .tools.document_tools import extract_pptx_text
            pptx_bytes = file_bytes

            if lower_name.endswith('.ppt') and not lower_name.endswith('.pptx'):
                import requests as http_requests
                libreoffice_url = os.environ.get("LIBREOFFICE_SERVICE_URL", "http://localhost:8002")
                try:
                    resp = http_requests.post(
                        f"{libreoffice_url}/convert",
                        files={"file": (filename, file_bytes, "application/vnd.ms-powerpoint")},
                        params={"format": "pptx"},
                        timeout=120,
                    )
                    if resp.status_code == 200:
                        pptx_bytes = resp.content
                        doc_path = doc_path.rsplit('.', 1)[0] + '.pptx'
                        logger.info(f".ppt → .pptx conversion succeeded ({len(file_bytes)} → {len(pptx_bytes)} bytes)")
                    else:
                        logger.warning(f".ppt → .pptx conversion failed (status {resp.status_code})")
                except Exception as e:
                    logger.warning(f".ppt → .pptx conversion unavailable ({e}), attempting direct extraction")

            content = extract_pptx_text(pptx_bytes, filename)

            workspace.add_document(
                path=doc_path,
                content=content,
                description=filename,
                set_active=True,
            )
            doc = workspace.get_document(doc_path)
            if doc:
                doc.binary_blob = pptx_bytes
                doc.mime_type = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
                doc.format = 'pptx'

            workspace.save()
            _flag_wiki_pending()
            return ({
                "success": True,
                "document_path": doc_path,
                "format": "pptx",
                "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "size_bytes": len(pptx_bytes),
            })

        elif lower_name.endswith(('.md', '.markdown', '.txt')):

            try:
                text_content = file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                text_content = file_bytes.decode('utf-8', errors='replace')

            is_md = lower_name.endswith(('.md', '.markdown'))
            fmt = 'markdown' if is_md else 'text'
            mime = 'text/markdown' if is_md else 'text/plain'

            workspace.add_document(
                path=doc_path,
                content=text_content,
                description=filename,
                set_active=True,
            )
            doc = workspace.get_document(doc_path)
            if doc:
                doc.binary_blob = file_bytes
                doc.mime_type = mime
                doc.format = fmt

            workspace.save()
            _flag_wiki_pending()
            return ({
                "success": True,
                "document_path": doc_path,
                "format": fmt,
                "mime_type": mime,
                "size_bytes": len(file_bytes),
            })

        else:

            import mimetypes
            mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

            workspace.add_document(
                path=doc_path,
                content=f"[Binary file: {filename} ({mime}, {len(file_bytes)} bytes)]",
                description=filename,
                set_active=False,
            )
            doc = workspace.get_document(doc_path)
            if doc:
                doc.binary_blob = file_bytes
                doc.mime_type = mime
                doc.format = mime.split('/')[1] if '/' in mime else 'binary'

            workspace.save()
            return ({
                "success": True,
                "document_path": doc_path,
                "format": doc.format if doc else "binary",
                "mime_type": mime,
                "size_bytes": len(file_bytes),
            })

    except ValueError as e:
        return ({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to process file")

@router.get('/chat/agentic/workspace/download')
def download_workspace_file(request: Request):
    """
    Download a binary file from the workspace.

    Query params:
        - path: document path (e.g., "Clients/Acme/report.pdf")
    """
    from .workspace import Workspace
    import io

    user_id = OSS_USER_ID
    file_path = request.query_params.get('path', '')

    if not file_path:
        raise HTTPException(status_code=400, detail="path parameter required")

    workspace = Workspace.get_or_create(user_id)
    doc = workspace.get_document(file_path)
    if not doc:
        raise HTTPException(status_code=404, detail="File not found")

    if doc.format in ('markdown', 'text') and doc.content is not None:
        blob = doc.content.encode('utf-8')
    else:

        blob = doc.binary_blob or doc.docx_blob
    if not blob:
        raise HTTPException(status_code=404, detail="No downloadable content for this file")

    mime = doc.mime_type or 'application/octet-stream'
    if doc.docx_blob and not doc.binary_blob:
        mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

    filename = file_path.split('/')[-1]
    return Response(
        content=blob,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

def _wiki_index_response(index_key: str):
    """Shared loader: returns the named LLM-generated index markdown for the
    current user's wiki. Used by /clauses /parties /jurisdictions /by-type.

    `index_key` is the LexWiki index name without the leading underscore and
    .md (e.g. 'clause_library', 'by_party', 'by_jurisdiction', 'by_type').
    """
    from .workspace import Workspace
    from anylegal_oss.lexwiki_compiler.db import get_workspace_wiki

    workspace = Workspace.get_or_create(OSS_USER_ID)
    wiki = get_workspace_wiki(workspace.workspace_id)
    if not wiki:
        return ({
            "status": "pending",
            "compiled_at": None,
            "markdown": "",
        })

    wiki_data = wiki.get("wiki_data") or {}
    indexes = wiki_data.get("indexes") or {}
    return ({
        "status": wiki.get("compile_status"),
        "compiled_at": wiki.get("compiled_at"),
        "source_doc_count": wiki.get("source_doc_count"),
        "markdown": indexes.get(index_key, ""),
    })

@router.get('/chat/agentic/workspace/wiki/status')
def get_wiki_status():
    """Compile status + freshness for the user's wiki.

    Drives the Knowledge tab's loading / empty / error states.
    """
    from .workspace import Workspace
    from anylegal_oss.lexwiki_compiler.db import get_workspace_wiki, auto_expire_stale_compiling

    workspace = Workspace.get_or_create(OSS_USER_ID)

    auto_expire_stale_compiling(workspace.workspace_id)
    wiki = get_workspace_wiki(workspace.workspace_id)

    if not wiki:
        return ({
            "workspace_id": workspace.workspace_id,
            "status": "pending",
            "compiled_at": None,
            "source_doc_count": 0,
            "page_count": 0,
            "error": None,
        })

    wiki_data = wiki.get("wiki_data") or {}
    pages = wiki_data.get("pages") or {}
    return ({
        "workspace_id": workspace.workspace_id,
        "status": wiki.get("compile_status"),
        "compiled_at": wiki.get("compiled_at"),
        "source_doc_count": wiki.get("source_doc_count") or 0,
        "page_count": len(pages),
        "error": wiki.get("compile_error"),
    })

@router.get('/chat/agentic/workspace/wiki/clauses')
def get_wiki_clauses():
    """LLM-generated clause library — rendered as markdown by the frontend."""
    return _wiki_index_response("clause_library")

@router.get('/chat/agentic/workspace/wiki/parties')
def get_wiki_parties():
    """LLM-generated party index."""
    return _wiki_index_response("by_party")

@router.get('/chat/agentic/workspace/wiki/jurisdictions')
def get_wiki_jurisdictions():
    """LLM-generated jurisdiction index."""
    return _wiki_index_response("by_jurisdiction")

@router.get('/chat/agentic/workspace/wiki/documents')
def get_wiki_documents():
    """Per-doc list — one row per compiled wiki page.

    Powers the primary "Documents" view in the Memory tab: the lawyer's
    "show me what the AI remembers about each of my files" surface.
    Returns frontmatter (parties, jurisdiction, etc.) extracted by the
    compiler, plus a short summary derived from the page body.
    """
    from .workspace import Workspace
    from anylegal_oss.lexwiki_compiler.db import get_workspace_wiki

    workspace = Workspace.get_or_create(OSS_USER_ID)
    wiki = get_workspace_wiki(workspace.workspace_id)
    if not wiki or not wiki.get("wiki_data"):
        return ({"status": "pending", "compiled_at": None, "documents": []})

    pages = (wiki["wiki_data"].get("pages") or {})
    docs = []
    for slug, page in pages.items():
        fm = page.get("frontmatter") or {}
        body = page.get("compiled_body") or page.get("content") or ""

        summary = ""
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('---'):
                summary = line
                break
        if len(summary) > 280:
            summary = summary[:277] + "…"

        def _as_list(v):
            if v is None:
                return []
            if isinstance(v, list):
                return [str(x) for x in v if x]
            return [str(v)]

        docs.append({
            "slug": slug,
            "category": page.get("category"),
            "title": fm.get("title") or slug.rsplit('/', 1)[-1].replace('-', ' '),
            "parties": _as_list(fm.get("parties")),
            "jurisdiction": fm.get("jurisdiction") or "",
            "subject_areas": _as_list(fm.get("subject_areas")),
            "effective_date": fm.get("effective_date") or "",
            "source": fm.get("source") or "",
            "summary": summary,
        })

    by_category: dict = {}
    for d in docs:
        by_category.setdefault(d["category"] or "other", []).append(d)
    for cat in by_category:
        by_category[cat].sort(key=lambda x: (x.get("title") or "").lower())

    return ({
        "status": wiki.get("compile_status"),
        "compiled_at": wiki.get("compiled_at"),
        "document_count": len(docs),
        "documents": sorted(docs, key=lambda x: (x.get("category") or "", (x.get("title") or "").lower())),
        "by_category": by_category,
    })

@router.get('/chat/agentic/workspace/wiki/page')
def get_wiki_page(request: Request):
    """Read a single compiled wiki page by slug (`?slug=contracts/acme-msa`).

    Used by the per-doc drawer in the Memory tab and by the agent's
    `read_wiki_page` tool.
    """
    from .workspace import Workspace
    from anylegal_oss.lexwiki_compiler.db import get_workspace_wiki

    slug = request.query_params.get('slug', '').strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug parameter required")

    workspace = Workspace.get_or_create(OSS_USER_ID)
    wiki = get_workspace_wiki(workspace.workspace_id)
    if not wiki:
        raise HTTPException(status_code=404, detail="wiki not yet compiled")

    wiki_data = wiki.get("wiki_data") or {}
    pages = wiki_data.get("pages") or {}
    page = pages.get(slug)
    if not page:
        raise HTTPException(status_code=404, detail=f"page not found: {slug}")

    return ({
        "slug": slug,
        "category": page.get("category"),
        "frontmatter": page.get("frontmatter") or {},

        "compiled_body": page.get("compiled_body") or page.get("content") or "",
        "annotations": page.get("annotations") or [],
        "content": page.get("compiled_body") or page.get("content") or "",
    })

@router.get('/chat/agentic/workspace/wiki/workspace_notes')
def get_wiki_workspace_notes():
    """Workspace-level AI journal — annotations not tied to any specific doc.

    Drives the "Workspace" card in the Memory tab's Documents view: the
    surface where cross-cutting AI insights (counterparty intel, user
    preferences, strategic context) live.
    """
    from .workspace import Workspace
    from anylegal_oss.lexwiki_compiler.db import get_workspace_wiki

    workspace = Workspace.get_or_create(OSS_USER_ID)
    wiki = get_workspace_wiki(workspace.workspace_id)
    if not wiki:
        return ({
            "workspace_id": workspace.workspace_id,
            "status": "pending",
            "compiled_at": None,
            "annotations": [],
        })

    wiki_data = wiki.get("wiki_data") or {}
    notes = wiki_data.get("workspace_notes") or {}
    return ({
        "workspace_id": workspace.workspace_id,
        "status": wiki.get("compile_status"),
        "compiled_at": wiki.get("compiled_at"),
        "annotations": notes.get("annotations") or [],
    })

@router.post('/chat/agentic/workspace/wiki/recompile')
def trigger_wiki_recompile():
    """Mark the user's wiki as `pending` so the next compiler pass picks it up.

    Bypasses the source_docs_hash skip — sets status='pending' and clears
    the hash so the compiler unconditionally rebuilds.
    """
    from .workspace import Workspace
    from anylegal_oss.lexwiki_compiler.db import update_workspace_wiki_status, get_workspace_wiki
    from anylegal_oss.db.database import get_db_connection

    workspace = Workspace.get_or_create(OSS_USER_ID)
    wid = workspace.workspace_id

    update_workspace_wiki_status(wid, 'pending')

    try:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE workspace_wikis SET source_docs_hash = NULL WHERE workspace_id = ?",
                (wid,),
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to clear source_docs_hash for {wid}: {e}")

    wiki = get_workspace_wiki(wid)
    return ({
        "workspace_id": wid,
        "status": (wiki or {}).get("compile_status", "pending"),
        "queued": True,
    })

DOCLING_SERVICE_URL = "http://localhost:8001/convert"

@router.get('/workspace/sessions')
def list_workspace_sessions(request: Request):
    """
    List workspace sessions for the authenticated user.

    Query params:
        status: Filter by status ('active', 'archived')

    Response:
        {
            "sessions": [
                {
                    "id": "uuid",
                    "document_name": "Contract.docx",
                    "session_name": "Review: Contract",
                    "created_at": "2024-01-01T00:00:00",
                    "updated_at": "2024-01-01T00:00:00",
                    "status": "active"
                }
            ]
        }
    """
    from anylegal_oss.workspace.session import WorkspaceSession

    if not OSS_USER_ID:
        raise HTTPException(status_code=401, detail="Authentication required")

    status = request.query_params.get('status')
    sessions = WorkspaceSession.list_sessions(OSS_USER_ID, status)

    return ({
        "sessions": sessions,
        "count": len(sessions)
    })

@router.get('/workspace/sessions/{session_id}')
def get_workspace_session(session_id):
    """
    Get a workspace session with all documents.

    Response:
        {
            "session_id": "uuid",
            "documents": [
                {
                    "path": "document.md",
                    "description": "Summary document",
                    "size": 1234,
                    "is_active": true
                }
            ],
            "active_document": "document.md",
            "playbook": "...",
            "context": {...}
        }
    """
    from anylegal_oss.workspace.session import WorkspaceSession

    if not OSS_USER_ID:
        raise HTTPException(status_code=401, detail="Authentication required")

    session = WorkspaceSession.load(session_id, OSS_USER_ID)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return ({
        "session_id": session.session_id,
        "documents": session.list_documents(),
        "active_document": session.active_document,
        "has_playbook": bool(session.playbook),
        "context": session.context,
        "session_name": session._generate_session_name(),
        "created_at": session.created_at.isoformat(),
    })

@router.get('/workspace/sessions/{session_id}/documents')
def list_session_documents(session_id):
    """
    List documents in a workspace session.

    Response:
        {
            "documents": [
                {
                    "path": "Client_Revisions_Summary.md",
                    "description": "Summary of proposed revisions",
                    "size": 2048,
                    "is_active": false,
                    "created_at": "...",
                    "modified_at": "..."
                }
            ]
        }
    """
    from anylegal_oss.workspace.session import WorkspaceSession

    if not OSS_USER_ID:
        raise HTTPException(status_code=401, detail="Authentication required")

    session = WorkspaceSession.load(session_id, OSS_USER_ID)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return ({
        "session_id": session_id,
        "documents": session.list_documents()
    })

@router.get('/workspace/sessions/{session_id}/documents/{document_path:path}')
def get_session_document(session_id, document_path):
    """
    Get a specific document from a workspace session.

    Response:
        {
            "path": "Client_Revisions_Summary.md",
            "content": "# Summary...",
            "description": "Summary of proposed revisions",
            "created_at": "...",
            "modified_at": "..."
        }
    """
    from anylegal_oss.workspace.db import get_session_document as db_get_doc

    if not OSS_USER_ID:
        raise HTTPException(status_code=401, detail="Authentication required")

    doc_data = db_get_doc(session_id, OSS_USER_ID, document_path)
    if not doc_data:
        raise HTTPException(status_code=404, detail="Document not found")

    return ({
        "path": document_path,
        "content": doc_data.get('content', ''),
        "description": doc_data.get('description', ''),
        "created_at": doc_data.get('created_at'),
        "modified_at": doc_data.get('modified_at')
    })

@router.delete('/workspace/sessions/{session_id}')
def delete_workspace_session(session_id):
    """Delete a workspace session."""
    from anylegal_oss.workspace.db import delete_workspace_session as db_delete

    if not OSS_USER_ID:
        raise HTTPException(status_code=401, detail="Authentication required")

    if db_delete(session_id, OSS_USER_ID):
        return ({"success": True, "message": "Session deleted"})
    else:
        raise HTTPException(status_code=404, detail="Session not found or already deleted")

@router.post('/workspace/sessions/{session_id}/docx/upload')
async def upload_docx_to_session(session_id: str, file: UploadFile = File(...), folder_path: str = Form('')):
    """
    Upload a DOCX file to a workspace session.

    Converts DOCX to HTML for Tiptap display and stores the original
    DOCX as the source of truth.

    Request: multipart/form-data with 'file' field

    Returns:
        JSON with document_path, html_content, and metadata
    """
    from .workspace import Workspace
    from .docx_service import DocxService

    if not OSS_USER_ID:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")

    if not file.filename.lower().endswith('.docx'):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")

    try:

        docx_bytes = await file.read()

        if len(docx_bytes) == 0:
            raise HTTPException(status_code=400, detail="Empty file")

        html_content, conversion_messages = DocxService.docx_to_html(docx_bytes)

        metadata = DocxService.get_docx_metadata(docx_bytes)

        workspace = Workspace.get_or_create(OSS_USER_ID)

        folder_path = 'folder_path', ''.strip().strip('/')
        document_path = f"{folder_path}/{file.filename}" if folder_path else file.filename
        workspace.add_document(
            path=document_path,
            content=html_content,
            description=metadata.get('title') or file.filename,
            set_active=True
        )

        doc = workspace.get_document(document_path)
        if doc:
            doc.update_docx(docx_bytes, html_content)

        workspace.save()

        return ({
            "success": True,
            "document_path": document_path,
            "html_content": html_content,
            "metadata": metadata,
            "conversion_messages": conversion_messages,
            "format": "docx",
            "size_bytes": len(docx_bytes)
        })

    except ValueError as e:
        return ({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"DOCX upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to process DOCX file")

@router.get('/workspace/sessions/{session_id}/docx/export/{document_path:path}')
def export_session_docx(session_id, document_path):
    """
    Export a document from a session as DOCX.

    If the document has an original DOCX blob, returns that.
    Otherwise, converts the HTML content to DOCX.

    Returns:
        DOCX file download
    """
    from .workspace import Workspace
    from .docx_service import DocxService

    if not OSS_USER_ID:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:

        workspace = Workspace.get_or_create(OSS_USER_ID)

        doc = workspace.get_document(document_path)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if doc.docx_blob:

            docx_bytes = doc.docx_blob
        else:

            docx_bytes = DocxService.html_to_docx(
                doc.content,
                title=doc.description or document_path
            )

        filename = document_path
        if not filename.lower().endswith('.docx'):
            filename = filename.rsplit('.', 1)[0] + '.docx' if '.' in filename else filename + '.docx'

        return Response(
            content=docx_bytes,
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except Exception as e:
        logger.error(f"DOCX export failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to export DOCX")

@router.get('/workspace/sessions/{session_id}/docx/preview/{document_path:path}')
def preview_session_docx_as_pdf(session_id, document_path):
    """
    Return a PDF preview of a DOCX document via LibreOffice headless.

    Sends the DOCX blob to the LibreOffice microservice (port 8002)
    and proxies the resulting PDF back to the client.
    """
    from .workspace import Workspace

    if not OSS_USER_ID:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:

        workspace = Workspace.get_or_create(OSS_USER_ID)

        doc = workspace.get_document(document_path)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if getattr(doc, 'mime_type', None) == 'application/pdf' and doc.binary_blob:
            pdf_filename = (document_path.rsplit(".", 1)[0] + ".pdf") if "." in document_path else (document_path + ".pdf")
            return Response(
                content=doc.binary_blob,
                media_type="application/pdf",
                headers={"Content-Disposition": f'inline; filename="{pdf_filename}"'},
            )

        blob = doc.docx_blob
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if not blob and hasattr(doc, 'binary_blob') and doc.binary_blob:
            blob = doc.binary_blob
            mime = getattr(doc, 'mime_type', None) or "application/msword"
        if not blob:
            raise HTTPException(status_code=400, detail="Document has no binary data for preview")

        import requests as http_requests
        libreoffice_url = os.environ.get("LIBREOFFICE_SERVICE_URL", "http://localhost:8002")
        try:
            resp = http_requests.post(
                f"{libreoffice_url}/convert",
                files={"file": (document_path, blob, mime)},
                timeout=120,
            )
            if resp.status_code != 200:
                logger.error(f"LibreOffice service error: {resp.status_code} {resp.text[:300]}")
                raise HTTPException(status_code=502, detail="PDF conversion failed")
        except http_requests.ConnectionError:
            logger.error("LibreOffice service unavailable")
            raise HTTPException(status_code=503, detail="PDF preview service unavailable")
        except http_requests.Timeout:
            logger.error("LibreOffice service timed out")
            raise HTTPException(status_code=504, detail="PDF conversion timed out")

        pdf_filename = (document_path.rsplit(".", 1)[0] + ".pdf") if "." in document_path else (document_path + ".pdf")
        return Response(
            content=resp.content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{pdf_filename}"'},
        )

    except Exception as e:
        logger.error(f"DOCX PDF preview failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate PDF preview")

@router.post('/workspace/sessions/{session_id}/docx/sync')
async def sync_docx_html(request: Request, session_id):
    """
    Synchronize HTML content back to DOCX for a document.

    Called when user has edited in Tiptap and wants to update the DOCX.

    Request JSON:
        document_path: Path of the document to sync
        direction: "html_to_docx" or "docx_to_html" (default: html_to_docx)

    Returns:
        Updated document status
    """
    from .workspace import Workspace
    from .docx_service import DocxService

    if not OSS_USER_ID:
        raise HTTPException(status_code=401, detail="Authentication required")

    data = await request.json() or {}
    document_path = data.get('document_path')
    direction = data.get('direction', 'html_to_docx')

    if not document_path:
        raise HTTPException(status_code=400, detail="document_path required")

    try:

        workspace = Workspace.get_or_create(OSS_USER_ID)

        doc = workspace.get_document(document_path)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        if direction == 'html_to_docx':

            base_docx = doc.docx_blob if doc.docx_blob else None
            new_docx = DocxService.html_to_docx(
                doc.content,
                title=doc.description,
                base_docx=base_docx
            )
            doc.update_docx(new_docx, doc.content)
            doc.mark_synced()

        elif direction == 'docx_to_html':

            if not doc.docx_blob:
                raise HTTPException(status_code=400, detail="No DOCX to convert")

            html, _ = DocxService.docx_to_html(doc.docx_blob)
            doc.content = html
            doc.mark_synced()

        else:
            raise HTTPException(status_code=400, detail="Invalid direction. Use 'html_to_docx' or 'docx_to_html'")

        workspace.save()

        return ({
            "success": True,
            "document_path": document_path,
            "direction": direction,
            "is_synced": doc.is_synced,
            "format": doc.format
        })

    except Exception as e:
        logger.error(f"DOCX sync failed: {e}")
        return ({"error": f"Sync failed: {str(e)}"}), 500

@router.post('/docx/convert')
async def convert_docx(file: UploadFile = File(...)):
    """
    Convert a DOCX file to HTML without saving to a session.

    Useful for preview or one-off conversions.

    Request: multipart/form-data with 'file' field

    Returns:
        JSON with html_content and metadata
    """
    from .docx_service import DocxService

    if not OSS_USER_ID:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not file.filename or not file.filename.lower().endswith('.docx'):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")

    try:
        docx_bytes = await file.read()
        html_content, messages = DocxService.docx_to_html(docx_bytes)
        metadata = DocxService.get_docx_metadata(docx_bytes)

        return ({
            "success": True,
            "html_content": html_content,
            "metadata": metadata,
            "conversion_messages": messages,
            "filename": file.filename,
            "size_bytes": len(docx_bytes)
        })

    except Exception as e:
        logger.error(f"DOCX conversion failed: {e}")
        return ({"error": str(e)}), 400

@router.get('/health')
def health_check():
    """Health check endpoint."""
    import requests

    docling_service_available = False
    try:
        response = requests.get("http://localhost:8001/health", timeout=2)
        docling_service_available = response.status_code == 200
    except Exception:
        pass

    return ({
        "status": "ok",
        "module": "workspace",
        "version": "1.0.0",
        "docling_service_available": docling_service_available,
        "docling_service_url": DOCLING_SERVICE_URL
    })

