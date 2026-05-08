
function getApiBase(): string {
  if (process.env.NEXT_PUBLIC_BASE_URL) return process.env.NEXT_PUBLIC_BASE_URL;

  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://localhost:8000';
    }
    return window.location.origin;
  }

  return '';
}

const API_BASE = getApiBase();

interface SessionMetadata {
  id: string;
  document_name: string;
  session_name: string;
  created_at: string;
  updated_at: string;
  status: string;
}

interface SessionDocument {
  path: string;
  description: string;
  content?: string;
  format: 'html' | 'docx';
  has_docx: boolean;
  is_synced: boolean;
  created_at: string;
  modified_at: string;
}

interface WorkspaceSession {
  id: string;
  documents: SessionDocument[];
  active_document: string | null;
  session_name: string;
  created_at: string;
  updated_at: string;
}

function getAuthHeaders(): HeadersInit {
  const token = localStorage.getItem('auth_token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
  };
}

export async function listWorkspaceSessions(): Promise<SessionMetadata[]> {
  const response = await fetch(`${API_BASE}/api/v1/editor/workspace/sessions`, {
    headers: getAuthHeaders(),
  });

  if (!response.ok) {
    throw new Error(`Failed to list sessions: ${response.status}`);
  }

  const data = await response.json();
  return data.sessions || [];
}

export async function getWorkspaceSession(sessionId: string): Promise<WorkspaceSession | null> {
  const response = await fetch(`${API_BASE}/api/v1/editor/workspace/sessions/${sessionId}`, {
    headers: getAuthHeaders(),
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(`Failed to get session: ${response.status}`);
  }

  const data = await response.json();

  return {
    id: data.session_id,
    documents: data.documents || [],
    active_document: data.active_document || null,
    session_name: data.session_name || '',
    created_at: data.created_at || '',
    updated_at: data.updated_at || '',
  };
}

export async function getSessionDocument(
  sessionId: string,
  documentPath: string
): Promise<SessionDocument | null> {
  const response = await fetch(
    `${API_BASE}/api/v1/editor/workspace/sessions/${sessionId}/documents/${encodeURIComponent(documentPath)}`,
    { headers: getAuthHeaders() }
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(`Failed to get document: ${response.status}`);
  }

  return response.json();
}

export async function deleteWorkspaceSession(sessionId: string): Promise<boolean> {
  const response = await fetch(`${API_BASE}/api/v1/editor/workspace/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });

  return response.ok;
}

export async function uploadDocxToSession(
  sessionId: string,
  file: File
): Promise<{
  success: boolean;
  document_path: string;
  html_content: string;
  metadata: Record<string, any>;
}> {
  const token = localStorage.getItem('auth_token');

  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(
    `${API_BASE}/api/v1/editor/workspace/sessions/${sessionId}/docx/upload`,
    {
      method: 'POST',
      headers: {
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: formData,
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Upload failed' }));
    throw new Error(error.error || 'Upload failed');
  }

  return response.json();
}

export function getDocxExportUrl(sessionId: string, documentPath: string): string {
  return `${API_BASE}/api/v1/editor/workspace/sessions/${sessionId}/docx/export/${encodeURIComponent(documentPath)}`;
}

export async function downloadDocxExport(
  sessionId: string,
  documentPath: string,
  filename?: string
): Promise<void> {
  const token = localStorage.getItem('auth_token');

  const ext = documentPath.split('.').pop()?.toLowerCase() || '';
  const isNonDocx = ['pptx', 'ppt', 'xlsx', 'xls', 'pdf', 'png', 'jpg', 'jpeg', 'svg'].includes(ext);
  const url = isNonDocx
    ? `${API_BASE}/api/v1/editor/chat/agentic/workspace/download?path=${encodeURIComponent(documentPath)}`
    : getDocxExportUrl(sessionId, documentPath);

  const response = await fetch(url, {
    headers: {
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
  });

  if (!response.ok) {
    throw new Error('Export failed');
  }

  const blob = await response.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  const downloadName = filename || (isNonDocx
    ? documentPath.split('/').pop() || documentPath
    : documentPath.replace(/\.[^/.]+$/, '.docx'));
  a.download = downloadName;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(blobUrl);
}

export async function syncDocxHtml(
  sessionId: string,
  documentPath: string,
  direction: 'html_to_docx' | 'docx_to_html' = 'html_to_docx'
): Promise<{
  success: boolean;
  is_synced: boolean;
  format: string;
}> {
  const response = await fetch(
    `${API_BASE}/api/v1/editor/workspace/sessions/${sessionId}/docx/sync`,
    {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        document_path: documentPath,
        direction,
      }),
    }
  );

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Sync failed' }));
    throw new Error(error.error || 'Sync failed');
  }

  return response.json();
}

export async function convertDocxToHtml(
  file: File
): Promise<{
  html_content: string;
  metadata: Record<string, any>;
}> {
  const token = localStorage.getItem('auth_token');

  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE}/api/v1/editor/docx/convert`, {
    method: 'POST',
    headers: {
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Conversion failed' }));
    throw new Error(error.error || 'Conversion failed');
  }

  return response.json();
}

export type {
  SessionMetadata,
  SessionDocument,
  WorkspaceSession,
};
