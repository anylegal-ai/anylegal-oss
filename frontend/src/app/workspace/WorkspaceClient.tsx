'use client';
import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { EditorState } from '@tiptap/pm/state';
import { WorkspaceChat } from '@/components/workspace-chat/WorkspaceChat';
import DocumentManager from '@/components/DocumentManager';
import HistoryModal from '@/components/HistoryModal';
import OpenDocumentModal from '@/components/OpenDocumentModal';
import { isTokenExpired, refreshAccessToken } from '@/utils/auth';
import { OrganizationProvider, useOrganization } from '@/contexts/OrganizationContext';
import styles from './workspace.module.css';
import type { RedlineSuggestion, ViewMode } from './types/workspace';

import {
  useWorkspaceState,
  useEditorSetup,
  useTextReplacement,
  useChatActions,
} from './hooks';
import type { SelectionPosition } from './hooks';
import { markdownToHtml, htmlToMarkdown } from './utils/markdownUtils';

import {
  ConfirmModal,
  DocxUploadModal,
  WorkspaceSidebar,
  WorkspaceHeader,
  EditorPanel,
  SelectionToolbar,
  WorkspaceSessionsModal,
} from './components';
import { SkillViewer } from './components/SkillViewer';
import { KnowledgePanel } from './components/KnowledgePanel';
import ModelSelector from '@/components/ModelSelector';
import dynamic from 'next/dynamic';

const PdfPreview = dynamic(() => import('@/components/PdfPreview'), { ssr: false });

import type { WorkspaceSession, SessionDocument } from './services/workspaceSessionService';
import { downloadDocxExport, getSessionDocument } from './services/workspaceSessionService';

type PrivacyMode = 'private' | 'cloud';

export default function WorkspaceClient() {
  return (
    <OrganizationProvider>
      <WorkspaceClientInner />
    </OrganizationProvider>
  );
}

function WorkspaceClientInner() {
  const searchParams = useSearchParams();

  const workspaceState = useWorkspaceState();
  const {
    isAuthenticated,
    activeTab,
    setActiveTab,
    sessionContext,
    setSessionContext,
    documentName,
    setDocumentName,
    documentLength,
    setDocumentLength,
    cursorPlaced,
    setCursorPlaced,
    insertNotice,
    setInsertNotice,
    viewMode,
    setViewMode,
    trackingEnabled,
    setTrackingEnabled,
    chatPanelOpen,
    setChatPanelOpen,
    emptyStateDismissed,
    setEmptyStateDismissed,
    error,
    setError,
    confirmModal,
    showConfirmModal,
    hideConfirmModal,
    pageSettings,
    setPageLayout,
    setPageSize,
    setPageZoom,
    hasDocument,
  } = workspaceState;

  const [selectedText, setSelectedText] = useState('');
  const [selectionPosition, setSelectionPosition] = useState<SelectionPosition | null>(null);
  const [showFloatingToolbar, setShowFloatingToolbar] = useState(false);
  const floatingToolbarTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const [clauseInstruction, setClauseInstruction] = useState('');
  const [includeResearch, setIncludeResearch] = useState(false);
  const [explainText, setExplainText] = useState('');

  const [configBanner, setConfigBanner] = useState<{ type: string; message: string } | null>(null);
  const [saveFlash, setSaveFlash] = useState(false);
  const configInitialContent = React.useRef<string | null>(null);
  const [skillViewerContent, setSkillViewerContent] = useState<string | null>(null);
  const [isDocxFile, _setIsDocxFile] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('anylegal_workspace_is_docx') === 'true';
    }
    return false;
  });
  const setIsDocxFile = useCallback((value: boolean) => {
    _setIsDocxFile(value);
    if (value) {
      localStorage.setItem('anylegal_workspace_is_docx', 'true');
    } else {
      localStorage.removeItem('anylegal_workspace_is_docx');
    }
  }, []);
  const [imageViewerUrl, setImageViewerUrl] = useState<string | null>(null);
  const [pdfData, setPdfData] = useState<Uint8Array | null>(null);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [scrollToText, setScrollToText] = useState<string | null>(null);

  const [showDocxModal, setShowDocxModal] = useState(false);
  const pendingDocxFileRef = useRef<File | null>(null);
  const pendingNonDocxNameRef = useRef<string | null>(null);
  const [uploadTargetFolder, setUploadTargetFolder] = useState<string | null>(null);
  const uploadTargetFolderRef = useRef<string | null>(null);
  const [workspaceFolders, setWorkspaceFolders] = useState<string[]>([]);

  const [sidebarRefreshTrigger, setSidebarRefreshTrigger] = useState(0);

  const [hasUserContent, setHasUserContent] = useState(true); // default true = established (safer on slow load)

  const [memoContext, setMemoContext] = useState<{ content: string; query: string } | null>(null);

  const editorContainerRef = useRef<HTMLDivElement>(null);

  const [isDocPanelVisible, setIsDocPanelVisible] = useState(true);

  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' && window.innerWidth <= 768);
  const [mobileSheetOpen, setMobileSheetOpen] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [showMobileModelSelector, setShowMobileModelSelector] = useState(false);

  const [showDocumentManager, setShowDocumentManager] = useState(false);

  const [showOpenDocumentModal, setShowOpenDocumentModal] = useState(false);

  const [showSessionsModal, setShowSessionsModal] = useState(false);
  const [currentSessionId, _setCurrentSessionId] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('anylegal_workspace_session_id');
    }
    return null;
  });
  const setCurrentSessionId = useCallback((idOrUpdater: string | null | ((prev: string | null) => string | null)) => {
    _setCurrentSessionId(prev => {
      const next = typeof idOrUpdater === 'function' ? idOrUpdater(prev) : idOrUpdater;
      if (next) {
        localStorage.setItem('anylegal_workspace_session_id', next);
      } else {
        localStorage.removeItem('anylegal_workspace_session_id');
      }
      return next;
    });
  }, []);

  const [documentId, setDocumentId] = useState<string | null>(null);

  const getDocumentContextKey = useCallback((docId: string | null, docName: string | null): string | null => {
    if (docId) return `document_context_${docId}`;
    if (docName) return `document_context_name_${docName}`;
    return null;
  }, []);

  const loadDocumentContext = useCallback((docId: string | null, docName: string | null): string => {
    const key = getDocumentContextKey(docId, docName);
    if (!key) return sessionContext; // Fall back to session context if no document
    const stored = localStorage.getItem(key);
    return stored || sessionContext; // Fall back to session context if no stored value
  }, [getDocumentContextKey, sessionContext]);

  const saveDocumentContext = useCallback((context: string, docId: string | null, docName: string | null) => {
    const key = getDocumentContextKey(docId, docName);
    if (key && context.trim()) {
      localStorage.setItem(key, context);
    }
    setSessionContext(context);
  }, [getDocumentContextKey, setSessionContext]);

  const [isSavingToCloud, setIsSavingToCloud] = useState(false);
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [saveTitle, setSaveTitle] = useState('');

  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  const [showHistoryModal, setShowHistoryModal] = useState(false);

  const [privacyMode, setPrivacyMode] = useState<PrivacyMode>('cloud');

  const [chatKey, setChatKey] = useState(0);

  const currentChatThreadIdRef = useRef<string | null>(null);

  const [activeThreadId, setActiveThreadId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return null;
    const stored = localStorage.getItem('activeThreadId');
    if (stored) {
      localStorage.removeItem('activeThreadId');
      return stored;
    }
    return null;
  });

  const handleThreadIdChanged = useCallback((threadId: string | null) => {
    setActiveThreadId(threadId);
    currentChatThreadIdRef.current = threadId;
  }, []);

  const resetChatState = useCallback(() => {
    setActiveThreadId(null);
    setChatKey(k => k + 1);
  }, []);

  const handleSelectThread = useCallback((threadId: string) => {
    setActiveThreadId(threadId);
    setChatPanelOpen(true);
  }, []);

  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth <= 768);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {
    const tabParam = searchParams.get('tab');
    if (tabParam === 'workspace') {
      setActiveTab(tabParam);
    }
  }, [searchParams, setActiveTab]);

  useEffect(() => {
    const onOpenPage = () => setActiveTab('knowledge');
    window.addEventListener('anylegal:openMemoryPage', onOpenPage);
    return () => {
      window.removeEventListener('anylegal:openMemoryPage', onOpenPage);
    };
  }, [setActiveTab]);

  const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || '';

  const fetchPdfPreview = useCallback(async (sessionId: string, docPath: string) => {
    const token = localStorage.getItem('auth_token');
    setPdfError(null);
    try {
      const url = `${BASE_URL}/api/v1/editor/workspace/sessions/${sessionId}/docx/preview/${encodeURIComponent(docPath)}`;
      const resp = await fetch(url, {
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
      });
      if (!resp.ok) {
        setPdfError(`PDF preview failed: ${resp.status}`);
        return;
      }
      const buffer = await resp.arrayBuffer();
      setPdfData(new Uint8Array(buffer));
      setPdfError(null);
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : 'Preview unavailable');
    }
  }, [BASE_URL]);

  const sessionRestoredRef = useRef(false);
  useEffect(() => {
    if (!isAuthenticated || sessionRestoredRef.current) return;
    sessionRestoredRef.current = true;

    (async () => {
      try {
        const token = localStorage.getItem('auth_token');
        const res = await fetch(`${BASE_URL}/api/v1/editor/chat/agentic/workspace/tree`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const data = await res.json();
          const wsId = data.workspace_id || data.session_id;
          if (wsId) {
            setCurrentSessionId(wsId);
          }

          const tree = data.tree;
          if (tree && Array.isArray(tree)) {
            const allFiles = new Set<string>();
            const walkNodes = (nodes: Array<Record<string, unknown>>) => {
              for (const node of nodes) {
                if (node.type === 'file' && typeof node.path === 'string') {
                  allFiles.add(node.path);
                }
                if (Array.isArray(node.children)) {
                  walkNodes(node.children as Array<Record<string, unknown>>);
                }
              }
            };
            walkNodes(tree);

            const DEFAULT_TOP_LEVEL = new Set(['Instructions', 'Playbook', 'Templates', 'Skills']);
            const SYSTEM_FILE_PREFIXES = ['Playbook/', 'Templates/', 'Skills/'];
            const SYSTEM_FILES = new Set(['anylegal.md']);
            const topLevelNames = tree.map((n: Record<string, unknown>) => n.name as string);
            const hasExtra = topLevelNames.some(name => !DEFAULT_TOP_LEVEL.has(name));
            const userFileCount = [...allFiles].filter(p =>
              !SYSTEM_FILES.has(p) && !SYSTEM_FILE_PREFIXES.some(prefix => p.startsWith(prefix))
            ).length;
            setHasUserContent(hasExtra || userFileCount > 0);

            const savedDocName = localStorage.getItem('anylegal_workspace_doc_name');
            if (savedDocName && allFiles.has(savedDocName)) {
              setDocumentName(savedDocName);
              setEmptyStateDismissed(true);
              setActiveTab('workspace');
              const isDocx = /\.(docx?|pdf)$/i.test(savedDocName);
              if (isDocx && wsId) {
                setIsDocxFile(true);
                fetchPdfPreview(wsId, savedDocName);
              }
            } else {
              localStorage.removeItem('anylegal_workspace_doc_name');
              setIsDocxFile(false);  // clears localStorage 'anylegal_workspace_is_docx' + resets state
            }
          }
          setSidebarRefreshTrigger(t => t + 1);
        }
      } catch {
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, BASE_URL, fetchPdfPreview, setDocumentName, setEmptyStateDismissed, setActiveTab, setCurrentSessionId]);

  const prevDocumentNameRef = useRef<string | null>(null);
  const prevDocumentIdRef = useRef<string | null>(null);
  const suppressChatResetRef = useRef(false);
  useEffect(() => {
    if (suppressChatResetRef.current) {
      suppressChatResetRef.current = false;
      prevDocumentNameRef.current = documentName;
      prevDocumentIdRef.current = documentId;
      return;
    }
    if (documentName !== prevDocumentNameRef.current &&
        prevDocumentNameRef.current !== null &&
        documentName !== null &&
        !documentId) {
      resetChatState();
    }
    prevDocumentNameRef.current = documentName;
    prevDocumentIdRef.current = documentId;
  }, [documentName, documentId]);

  useEffect(() => {
    return () => {
      if (floatingToolbarTimeoutRef.current) {
        clearTimeout(floatingToolbarTimeoutRef.current);
      }
    };
  }, []);

  const FLOATING_TOOLBAR_MIN_CHARS = 20;
  const FLOATING_TOOLBAR_DELAY_MS = 500;

  const editorSetup = useEditorSetup({
    onSelectionChange: (text, position) => {
      setSelectedText(text);
      setSelectionPosition(position);
      setCursorPlaced(true);
      setInsertNotice(null);

      if (floatingToolbarTimeoutRef.current) {
        clearTimeout(floatingToolbarTimeoutRef.current);
        floatingToolbarTimeoutRef.current = null;
      }

      if (!text || text.length < FLOATING_TOOLBAR_MIN_CHARS) {
        setShowFloatingToolbar(false);
        return;
      }

      floatingToolbarTimeoutRef.current = setTimeout(() => {
        setShowFloatingToolbar(true);
      }, FLOATING_TOOLBAR_DELAY_MS);
    },
    onCursorPlaced: () => {
      setCursorPlaced(true);
      setInsertNotice(null);
    },
    onDocumentLengthChange: setDocumentLength,
    viewMode,
    trackingEnabled,
    setError,
    setDocumentName,
    showConfirmModal,
    hideConfirmModal,
    onDocumentLoaded: () => {
      setViewMode('clean');
      setTrackingEnabled(false);

      const fileName = pendingNonDocxNameRef.current;
      if (fileName) {
        pendingNonDocxNameRef.current = null;
        setTimeout(async () => {
          try {
            const token = localStorage.getItem('auth_token');
            const editorEl = document.querySelector('.ProseMirror');
            const content = editorEl?.innerHTML || '';
            if (content.length < 10) return;

            await fetch(`${BASE_URL}/api/v1/documents`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
              },
              body: JSON.stringify({
                title: fileName,
                content,
                document_type: 'general',
              }),
            });

          } catch (err) {
            console.error('Auto-save failed:', err);
          }
        }, 300);
      }
    },
  });

  const {
    editor,
    fileInputRef,
    getDocumentText,
    hasTrackedChanges,
    handleUploadClick,
    handleFileUpload,
    isLoadingFile,
  } = editorSetup;

  const handleDownloadDocx = useCallback(async () => {
    if (!currentSessionId || !documentName) return;
    try {
      await downloadDocxExport(currentSessionId, documentName);
    } catch (err) {
      console.error('DOCX download failed:', err);
      setError('Failed to download document');
    }
  }, [currentSessionId, documentName, setError]);

  const handleDownloadDocumentFromChat = useCallback(async (sessionId: string, documentPath: string) => {
    try {
      await downloadDocxExport(sessionId, documentPath);
    } catch (err) {
      console.error('Document download failed:', err);
      setError('Failed to download document');
    }
  }, [setError]);

  const handleFileInputChange = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const extension = ('.' + (file.name.split('.').pop()?.toLowerCase() || ''));

    if (extension === '.docx' || extension === '.doc') {
      pendingDocxFileRef.current = file;
      setShowDocxModal(true);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } else {
      if (fileInputRef.current) fileInputRef.current.value = '';
      const targetFolder = uploadTargetFolderRef.current || '';

      let token = localStorage.getItem('auth_token');
      if (!token || isTokenExpired()) {
        const refreshed = await refreshAccessToken();
        if (!refreshed) { setError('Session expired. Please sign in again.'); return; }
        token = localStorage.getItem('auth_token');
      }

      const formData = new FormData();
      formData.append('file', file);
      if (targetFolder) formData.append('folder_path', targetFolder);

      try {
        const res = await fetch(`${BASE_URL}/api/v1/editor/chat/agentic/workspace/upload`, {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: formData,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          setError(err.error || 'Failed to upload file');
          return;
        }
        const data = await res.json();
        setSidebarRefreshTrigger(t => t + 1);
        const docPath = data.document_path || file.name;
        setDocumentName(docPath);
        setEmptyStateDismissed(true);

        if (data.format === 'pdf' || data.format === 'pptx' || data.format === 'xlsx') {
          setIsDocxFile(true);
          setConfigBanner(null);
          const wsId = currentSessionId;
          if (wsId) fetchPdfPreview(wsId, docPath);
          if (editor) {
            editor.setEditable(false);
            editor.commands.setContent('');
          }
          localStorage.setItem('anylegal_workspace_doc_name', docPath);
          setActiveTab('workspace');
        }
      } catch {
        setError('Failed to upload file');
      } finally {
        setUploadTargetFolder(null);
        uploadTargetFolderRef.current = null;
      }
    }
  }, [fileInputRef, BASE_URL, setError, setDocumentName, setEmptyStateDismissed, currentSessionId, fetchPdfPreview, editor, setActiveTab]);

  const handleDocxUploadConfirm = useCallback(async (folderPath?: string) => {
    const file = pendingDocxFileRef.current;
    if (!file || !editor) {
      setShowDocxModal(false);
      pendingDocxFileRef.current = null;
      setUploadTargetFolder(null);
      uploadTargetFolderRef.current = null;
      return;
    }
    setShowDocxModal(false);

    const targetFolder = folderPath || uploadTargetFolderRef.current || uploadTargetFolder || '';

    try {
      let token = localStorage.getItem('auth_token');
      if (!token || isTokenExpired()) {
        const refreshed = await refreshAccessToken();
        if (!refreshed) { setError('Session expired. Please sign in again.'); return; }
        token = localStorage.getItem('auth_token');
      }

      const formData = new FormData();
      formData.append('file', file);
      if (targetFolder) {
        formData.append('folder_path', targetFolder);
      }

      const response = await fetch(
        `${BASE_URL}/api/v1/editor/chat/agentic/workspace/upload`,
        {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${token}` },
          body: formData,
        }
      );

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        setError(err.error || 'Failed to upload DOCX');
        return;
      }

      const data = await response.json();
      const docPath = data.document_path || file.name;

      setIsDocxFile(true);
      setConfigBanner(null);

      const wsId = currentSessionId;
      if (wsId) fetchPdfPreview(wsId, docPath);

      if (editor) {
        editor.setEditable(false);
        editor.commands.setTrackChangesEnabled(false);
        editor.commands.setContent('');
      }

      setDocumentName(docPath);
      localStorage.setItem('anylegal_workspace_doc_name', docPath);
      setDocumentId(null); // Workspace doc, not a cloud document
      setEmptyStateDismissed(true);
      resetChatState();
      setActiveTab('workspace');

      setSidebarRefreshTrigger(t => t + 1);
    } catch (err) {
      console.error('DOCX upload failed:', err);
      setError('Failed to upload DOCX file');
    } finally {
      pendingDocxFileRef.current = null;
      setUploadTargetFolder(null);
      uploadTargetFolderRef.current = null;
    }
  }, [editor, currentSessionId, BASE_URL, setDocumentName, setEmptyStateDismissed, setActiveTab, setError, fetchPdfPreview, uploadTargetFolder]);

  const { applySuggestion } = useTextReplacement({
    editor,
    onError: setError,
    onEnableTracking: () => {
      setViewMode('redline');
      setTrackingEnabled(true);
      editor?.commands.setTrackChangesEnabled(true);
    },
    viewMode,
    trackingEnabled,
  });

  const chatActions = useChatActions({
    editor,
    viewMode,
    trackingEnabled,
    setViewMode,
    setTrackingEnabled,
    setActiveTab,
  });

  const handleViewModeChange = useCallback((mode: ViewMode) => {
    setViewMode(mode);
    if (mode === 'redline' && !trackingEnabled) {
      const content = editor?.getText()?.trim() || '';
      if (content.length > 0) {
        setTrackingEnabled(true);
      }
    }
  }, [editor, trackingEnabled, setViewMode, setTrackingEnabled]);

  const handleNewDocument = useCallback(() => {
    showConfirmModal('Clear current document and start fresh?', () => {
      hideConfirmModal();
      editor?.commands.clearContent();
      setDocumentName(null);
      setDocumentId(null);
      setIsDocxFile(false);
      setPdfData(null);
      if (editor) editor.setEditable(true);
      resetChatState();
      setEmptyStateDismissed(false);
      setActiveTab('workspace');
    });
  }, [editor, showConfirmModal, hideConfirmModal, setDocumentName, setEmptyStateDismissed, setActiveTab]);

  const handleCloseDocument = useCallback(() => {
    editor?.commands.clearContent();
    setDocumentName(null);
    setDocumentId(null);
    setConfigBanner(null);
    setIsDocxFile(false);
    setPdfData(null);
    setImageViewerUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null; });
    if (editor) editor.setEditable(true);
    setEmptyStateDismissed(false);
    setActiveTab('workspace');
    setShowCloseConfirm(false);
    configInitialContent.current = null;
  }, [editor, setDocumentName, setEmptyStateDismissed, setActiveTab]);

  const handleLogoClick = useCallback(() => {
    if (configBanner) {
      const isDirty = editor && configInitialContent.current !== null && editor.getHTML() !== configInitialContent.current;
      if (isDirty) {
        setShowCloseConfirm(true);
      } else {
        handleCloseDocument();
      }
    } else if (hasDocument || isDocxFile || imageViewerUrl) {
      handleCloseDocument();
    } else {
      resetChatState();
      setDocumentName(null);
      setDocumentId(null);
      setConfigBanner(null);
      setIsDocxFile(false);
      setPdfData(null);
      setImageViewerUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null; });
      if (editor) editor.setEditable(true);
      setEmptyStateDismissed(false);
      setActiveTab('workspace');
    }
  }, [configBanner, hasDocument, isDocxFile, editor, handleCloseDocument, resetChatState, setDocumentName, setEmptyStateDismissed, setActiveTab]);

  const CONFIG_BANNERS: Record<string, { type: string; message: string }> = {
    'anylegal.md': {
      type: 'agent',
      message: 'anylegal.md — workspace instructions the agent reads automatically: your role, risk posture, and preferences.',
    },
    'agents.md': {
      type: 'agent',
      message: 'anylegal.md — workspace instructions the agent reads automatically: your role, risk posture, and preferences.',
    },
  };

  const getPlaybookBanner = (path: string) => ({
    type: 'playbook',
    message: `Playbook — ${path}. Your standard clause positions. Referenced during contract reviews, drafting, and negotiations.`,
  });

  const handleWorkspaceFileSelect = useCallback(async (filePath: string, format?: string) => {
    const isSkillPath = filePath.startsWith('Skills/') && filePath.endsWith('/SKILL.md');
    if (!isSkillPath) setSkillViewerContent(null);
    setImageViewerUrl(prev => { if (prev) URL.revokeObjectURL(prev); return null; });

    const isImage = /\.(png|jpe?g|gif|svg|webp|bmp|ico)$/i.test(filePath);

    const docx = format === 'docx' || /\.docx?$/i.test(filePath);
    const pdf = format === 'pdf' || /\.pdf$/i.test(filePath);
    const pptx = /\.pptx?$/i.test(filePath);
    const xlsx = /\.xlsx?$/i.test(filePath);
    const usesPdfPreview = !isImage && (docx || pdf || pptx || xlsx);

    const isAnylegalFile = filePath === 'anylegal.md' || filePath === 'agents.md' || filePath.endsWith('/anylegal.md') || filePath.endsWith('/agents.md');
    const isPlaybookFile = filePath.startsWith('Playbook/');
    const isMarkdownExt = format === 'markdown' || /\.(md|markdown)$/i.test(filePath);
    const isReadOnlyMarkdown = isMarkdownExt && !isAnylegalFile && !isPlaybookFile && !isSkillPath && !isImage;

    setIsDocxFile(usesPdfPreview);
    setPdfData(null);  // Always clear — prevents stale preview when switching between documents
    if (editor) editor.setEditable(!usesPdfPreview && !isImage && !isReadOnlyMarkdown);

    if (isSkillPath) setSkillViewerContent('loading');

    if (isAnylegalFile) {
      setConfigBanner(CONFIG_BANNERS['anylegal.md']);
    } else if (isPlaybookFile) {
      setConfigBanner(getPlaybookBanner(filePath));
    } else if (isReadOnlyMarkdown) {
      setConfigBanner({
        type: 'markdown',
        message: 'Generated by the assistant — read-only. Ask in chat to revise.',
      });
    } else {
      setConfigBanner(null);
    }

    const ANYLEGAL_TEMPLATE =
      '<h2>About Me</h2>' +
      '<p><em>Who you are and what you do. The AI reads this at the start of every conversation to tailor its advice to you.</em></p>' +
      '<p>Example: \u201cI\u2019m a corporate lawyer at a mid-market firm. We represent technology vendors in SaaS, licensing, and M&amp;A transactions.\u201d</p>' +
      '<h2>My Role in Contracts</h2>' +
      '<p><em>Are you typically the buyer, seller, landlord, tenant, or neutral advisor? What\u2019s your risk posture?</em></p>' +
      '<p>Example: \u201cI represent the vendor side. I take a moderate risk posture \u2014 willing to negotiate but firm on key positions.\u201d</p>' +
      '<h2>Jurisdictions</h2>' +
      '<p><em>Which legal systems do you work in most? The AI will cite the right law and use appropriate terminology.</em></p>' +
      '<p>Example: \u201cPrimarily England &amp; Wales, occasionally UAE and Singapore for cross-border deals.\u201d</p>' +
      '<h2>How I Like to Work</h2>' +
      '<p><em>How should the AI communicate? Level of detail, tone, any standing preferences.</em></p>' +
      '<p>Example: \u201cAssume 10 years M&amp;A experience. Be concise and technical. Flag anything that would concern a sophisticated buyer\u2019s counsel.\u201d</p>';

    try {
      const params = new URLSearchParams();
      params.set('path', filePath);
      const token = localStorage.getItem('auth_token');

      const res = await fetch(`${BASE_URL}/api/v1/editor/chat/agentic/workspace/file?${params}`, {
        headers: {
          ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
        },
      });

      if (res.ok) {
        if (isImage) {
          const token2 = localStorage.getItem('auth_token');
          const imgRes = await fetch(`${BASE_URL}/api/v1/editor/chat/agentic/workspace/download?path=${encodeURIComponent(filePath)}`, {
            headers: { ...(token2 ? { 'Authorization': `Bearer ${token2}` } : {}) },
          });
          if (imgRes.ok) {
            const blob = await imgRes.blob();
            setImageViewerUrl(URL.createObjectURL(blob));
          }
        } else {
        const data = await res.json();
        const isSkillFile = filePath.startsWith('Skills/') && filePath.endsWith('/SKILL.md');
        if (isSkillFile && data.content) {
          setSkillViewerContent(data.content);
        } else if (usesPdfPreview && currentSessionId) {
          fetchPdfPreview(currentSessionId, filePath);
        } else if (editor) {
          const content = data.content;
          if (content) {
            const isMarkdown = filePath.endsWith('.md');
            let html = isMarkdown ? markdownToHtml(content) : content;
            const isConfigFile2 = filePath === 'agents.md' || filePath === 'anylegal.md' || filePath.endsWith('/anylegal.md');
            if (isConfigFile2) html = html.replace(/^<h1>[\s\S]*?<\/h1>\s*/i, '');
            editor.commands.setContent(html);
            setDocumentLength(content.length);
            if (isAnylegalFile || filePath.startsWith('Playbook/')) configInitialContent.current = editor.getHTML();
          } else {
            const isConfigFile = filePath === 'agents.md' || filePath === 'anylegal.md' || filePath.endsWith('/anylegal.md');
            const template = isConfigFile ? ANYLEGAL_TEMPLATE : '<p></p>';
            editor.commands.setContent(template);
            setDocumentLength(template.length);
            if (isAnylegalFile || filePath.startsWith('Playbook/')) configInitialContent.current = editor.getHTML();
          }
        }
        } // end non-image branch
      } else {
        if (editor) {
          const isConfigFile = filePath === 'agents.md' || filePath === 'anylegal.md' || filePath.endsWith('/anylegal.md');
          const template = isConfigFile ? ANYLEGAL_TEMPLATE : '<p></p>';
          editor.commands.setContent(template);
          setDocumentLength(template.length);
          if (isAnylegalFile || filePath.startsWith('Playbook/')) configInitialContent.current = editor.getHTML();
        }
      }
    } catch {
      if (editor) {
        const isConfigFile = filePath === 'agents.md' || filePath === 'anylegal.md' || filePath.endsWith('/anylegal.md');
        const template = isConfigFile ? ANYLEGAL_TEMPLATE : '<p></p>';
        editor.commands.setContent(template);
        if (isAnylegalFile || filePath.startsWith('Playbook/')) configInitialContent.current = editor.getHTML();
        setDocumentLength(template.length);
      }
    }

    suppressChatResetRef.current = true;
    setDocumentName(filePath);
    setDocumentId(null);
    setEmptyStateDismissed(true);
    setIsDocPanelVisible(true);
  }, [editor, currentSessionId, setDocumentName, setEmptyStateDismissed, fetchPdfPreview, BASE_URL]);

  const handleUploadToFolder = useCallback((folderPath: string) => {
    const folder = folderPath || null;
    setUploadTargetFolder(folder);
    uploadTargetFolderRef.current = folder;
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
      fileInputRef.current.click();
    }
  }, [fileInputRef]);

  useEffect(() => {
    if (!showDocxModal || !currentSessionId) {
      setWorkspaceFolders([]);
      return;
    }
    const token = localStorage.getItem('auth_token');
    fetch(`${BASE_URL}/api/v1/editor/chat/agentic/workspace/tree`, {
      headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    })
      .then(r => r.ok ? r.json() : { tree: [] })
      .then(data => {
        const paths: string[] = [];
        function walk(nodes: any[]) {
          for (const n of nodes) {
            if (n.type === 'folder') {
              paths.push(n.path);
              if (n.children) walk(n.children);
            }
          }
        }
        walk(data.tree || []);
        setWorkspaceFolders(paths);
      })
      .catch(() => setWorkspaceFolders([]));
  }, [showDocxModal, currentSessionId, BASE_URL]);

  const handleDeleteWorkspaceFile = useCallback((filePath: string) => {
    const fileName = filePath.split('/').pop() || filePath;
    showConfirmModal(`Remove "${fileName}" from your workspace?`, async () => {
      hideConfirmModal();
      try {
        const params = new URLSearchParams();
        params.set('path', filePath);
        const token = localStorage.getItem('auth_token');

        await fetch(`${BASE_URL}/api/v1/editor/chat/agentic/workspace/file?${params}`, {
          method: 'DELETE',
          headers: {
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
          },
        });
        setSidebarRefreshTrigger(t => t + 1);

        if (documentName === filePath || documentName === fileName) {
          editor?.commands.clearContent();
          setDocumentName(null);
          setDocumentId(null);
          setIsDocxFile(false); // also clears localStorage 'anylegal_workspace_is_docx'
          setPdfData(null);
          if (editor) editor.setEditable(true);
          setEmptyStateDismissed(false);
          localStorage.removeItem('anylegal_workspace_doc_name');
        }
      } catch {
      }
    });
  }, [currentSessionId, BASE_URL, showConfirmModal, hideConfirmModal, documentName, editor, setDocumentName, setEmptyStateDismissed]);

  const handleSaveAndClose = useCallback(async () => {
    if (!editor || !configBanner || !documentName) return;

    setIsSavingToCloud(true);
    try {
      const token = localStorage.getItem('auth_token');
      await fetch(`${BASE_URL}/api/v1/editor/chat/agentic/workspace/file`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          path: documentName,
          content: editor.getText(),
        }),
      });

      handleCloseDocument();
    } catch (err) {
      console.error('Save error:', err);
      setError('Failed to save');
    } finally {
      setIsSavingToCloud(false);
    }
  }, [editor, documentName, configBanner, BASE_URL, handleCloseDocument, setError]);

  const handleExportDocx = useCallback(async (clean: boolean) => {
    if (!editor) return;

    if (documentName && /\.(md|markdown)$/i.test(documentName)) {
      try {
        setIsExporting(true);
        const token = localStorage.getItem('auth_token');
        const res = await fetch(
          `${BASE_URL}/api/v1/editor/chat/agentic/workspace/download?path=${encodeURIComponent(documentName)}`,
          { headers: token ? { Authorization: `Bearer ${token}` } : {} }
        );
        if (!res.ok) throw new Error('Download failed');
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = documentName.split('/').pop() || 'document.md';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } catch (err) {
        console.error('Markdown download error:', err);
        setError('Failed to download file');
      } finally {
        setIsExporting(false);
      }
      return;
    }

    setIsExporting(true);
    try {
      if (currentSessionId && documentName && !clean) {
        try {
          await downloadDocxExport(currentSessionId, documentName);
          return;
        } catch (sessionErr) {
          console.log('Session export not available, falling back to HTML conversion');
        }
      }

      let htmlContent: string;
      if (clean) {
        const originalContent = editor.getHTML();
        htmlContent = originalContent
          .replace(/<s[^>]*style="[^"]*color:\s*(?:rgb\(220,\s*38,\s*38\)|#dc2626)[^"]*"[^>]*>.*?<\/s>/gi, '')
          .replace(/<span[^>]*style="[^"]*text-decoration:\s*line-through[^"]*color:\s*(?:rgb\(220,\s*38,\s*38\)|#dc2626)[^"]*"[^>]*>.*?<\/span>/gi, '')
          .replace(/<u[^>]*style="[^"]*color:\s*(?:rgb\(37,\s*99,\s*235\)|#2563eb)[^"]*"[^>]*>(.*?)<\/u>/gi, '$1');
      } else {
        htmlContent = editor.getHTML();
      }

      const baseFilename = documentName?.replace(/\.[^/.]+$/, '') || 'document';
      const filename = clean ? `${baseFilename}_clean.docx` : `${baseFilename}_redline.docx`;

      const response = await fetch(`${process.env.NEXT_PUBLIC_BASE_URL || ''}/api/v1/editor/export/docx`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('auth_token') || ''}`,
        },
        body: JSON.stringify({
          content: htmlContent,
          filename,
          format: 'html'
        }),
      });

      if (!response.ok) {
        throw new Error('Export failed');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Export error:', err);
      setError('Failed to export document');
    } finally {
      setIsExporting(false);
    }
  }, [editor, documentName, currentSessionId, BASE_URL, setError]);

  const handleExportPdf = useCallback(async (clean: boolean) => {
    if (!editor) return;

    setIsExporting(true);
    try {
      const rawHtml = editor.getHTML();
      console.log('[PDF Export] Raw HTML from editor:', rawHtml.substring(0, 1000));
      console.log('[PDF Export] Contains <s> tags:', rawHtml.includes('<s'));
      console.log('[PDF Export] Contains <u> tags:', rawHtml.includes('<u'));
      console.log('[PDF Export] Contains rgb(220:', rawHtml.includes('rgb(220'));
      console.log('[PDF Export] Contains rgb(37:', rawHtml.includes('rgb(37'));

      let htmlContent: string;
      if (clean) {
        htmlContent = rawHtml
          .replace(/<s[^>]*style="[^"]*color:\s*(?:rgb\(220,\s*38,\s*38\)|#dc2626)[^"]*"[^>]*>.*?<\/s>/gi, '')
          .replace(/<span[^>]*style="[^"]*text-decoration:\s*line-through[^"]*color:\s*(?:rgb\(220,\s*38,\s*38\)|#dc2626)[^"]*"[^>]*>.*?<\/span>/gi, '')
          .replace(/<u[^>]*style="[^"]*color:\s*(?:rgb\(37,\s*99,\s*235\)|#2563eb)[^"]*"[^>]*>(.*?)<\/u>/gi, '$1');
      } else {
        htmlContent = rawHtml;
      }

      console.log('[PDF Export] Final HTML being sent:', htmlContent.substring(0, 1000));

      const baseFilename = documentName?.replace(/\.[^/.]+$/, '') || 'document';
      const filename = clean ? `${baseFilename}_clean.pdf` : `${baseFilename}_redline.pdf`;

      const response = await fetch(`${process.env.NEXT_PUBLIC_BASE_URL || ''}/api/v1/editor/export/pdf`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('auth_token') || ''}`,
        },
        body: JSON.stringify({
          content: htmlContent,
          filename,
        }),
      });

      if (!response.ok) {
        throw new Error('Export failed');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error('Export error:', err);
      setError('Failed to export PDF');
    } finally {
      setIsExporting(false);
    }
  }, [editor, documentName, setError]);

  const handleSaveToCloud = useCallback(async () => {
    if (!editor) return;

    if (configBanner && documentName && !documentId) {
      setIsSavingToCloud(true);
      try {
        const token = localStorage.getItem('auth_token');
        const isMarkdown = documentName.endsWith('.md');
        const content = isMarkdown ? htmlToMarkdown(editor.getHTML()) : editor.getText();
        const res = await fetch(`${BASE_URL}/api/v1/editor/chat/agentic/workspace/file`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            path: documentName,
            content,
          }),
        });
        if (!res.ok) throw new Error('Failed to save workspace file');
        configInitialContent.current = editor.getHTML();
        setSaveFlash(true);
        setTimeout(() => setSaveFlash(false), 2000);
      } catch (err) {
        console.error('Save workspace file error:', err);
        setError('Failed to save file');
      } finally {
        setIsSavingToCloud(false);
      }
      return;
    }

    if (documentId) {
      setIsSavingToCloud(true);
      try {
        const token = localStorage.getItem('auth_token');
        const content = editor.getHTML();

        const response = await fetch(`${BASE_URL}/api/v1/documents/${documentId}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify({ content }),
        });

        if (!response.ok) throw new Error('Failed to save');
      } catch (err) {
        console.error('Save to cloud error:', err);
        setError('Failed to save to cloud');
      } finally {
        setIsSavingToCloud(false);
      }
    } else {
      setSaveTitle(documentName || 'Untitled Document');
      setShowSaveDialog(true);
    }
  }, [editor, documentId, documentName, configBanner, BASE_URL, setError]);

  const handleSaveNewToCloud = useCallback(async () => {
    if (!editor || !saveTitle.trim()) return;

    setIsSavingToCloud(true);
    try {
      const token = localStorage.getItem('auth_token');
      const content = editor.getHTML();

      const response = await fetch(`${BASE_URL}/api/v1/documents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify({
          title: saveTitle.trim(),
          content,
          document_type: 'general',
        }),
      });

      if (!response.ok) throw new Error('Failed to save');

      const data = await response.json();
      const newDocId = data.id || data.document_id;

      setDocumentId(newDocId);
      setDocumentName(saveTitle.trim());
      setShowSaveDialog(false);
      setSaveTitle('');
    } catch (err) {
      console.error('Save to cloud error:', err);
      setError('Failed to save to cloud');
    } finally {
      setIsSavingToCloud(false);
    }
  }, [editor, saveTitle, BASE_URL, setDocumentName, setError]);

  const handleChatDocumentUpdate = useCallback((path: string, content: string, docType?: string, replacementText?: string) => {
    if (docType === 'docx' && currentSessionId) {
      fetchPdfPreview(currentSessionId, path);
      if (replacementText) setScrollToText(replacementText);
    } else if (content) {
      chatActions.handleReplaceDocument(content);
    }
  }, [currentSessionId, fetchPdfPreview, chatActions]);

  const handleChatOpenDocument = useCallback(async (_sessionId: string, documentPath: string) => {
    handleWorkspaceFileSelect(documentPath);
  }, [handleWorkspaceFileSelect]);

  const handleChatDocumentDeleted = useCallback((path: string) => {
    setSidebarRefreshTrigger(t => t + 1);
    const fileName = path.split('/').pop() || path;
    if (documentName === path || documentName === fileName) {
      editor?.commands.clearContent();
      setDocumentName(null);
      setDocumentId(null);
      setIsDocxFile(false);
      setPdfData(null);
      if (editor) editor.setEditable(true);
      setEmptyStateDismissed(false);
      localStorage.removeItem('anylegal_workspace_doc_name');
    }
  }, [documentName, editor, setDocumentName, setEmptyStateDismissed]);

  const handleChatDocumentCreated = useCallback(() => {
    setSidebarRefreshTrigger(t => t + 1);
  }, []);

  const handleChatAgenticSessionCreated = useCallback((sessionId: string) => {
    setCurrentSessionId(sessionId);
    setSidebarRefreshTrigger(t => t + 1);
  }, [setCurrentSessionId]);

  const isNoDocState = !hasDocument && !isDocxFile && !imageViewerUrl;

  const chatVariant = (isMobile && !isNoDocState) ? 'sheet' as const
    : (isNoDocState || !isDocPanelVisible) ? 'fullscreen' as const
    : 'sidebar' as const;
  const chatShowHeader = isNoDocState || (!isMobile && isDocPanelVisible);
  const chatWrapperClass = isNoDocState
    ? styles.chatModeFullWidth
    : isMobile
      ? `${styles.chatMobileSheet} ${mobileSheetOpen ? styles.chatMobileSheetOpen : ''}`
      : `${styles.chatPanel}${!isDocPanelVisible ? ` ${styles.chatPanelExpanded}` : ''}`;

  const getHeaderActions = useCallback(() => {
    return [];
  }, []);

  if (isAuthenticated === null) {
    return (
      <div className={styles.loadingContainer}>
        <div className={styles.spinner}></div>
        <p>Loading...</p>
      </div>
    );
  }

  const hasSelection = selectedText.length >= 10;
  const trackedChanges = hasTrackedChanges();

  return (
    <div className={styles.workspace}>
      {/* Conversion Wall — blocks workspace when balance depleted */}

      {/* Hidden file input — always mounted so sidebar + home screen upload works */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".docx,.doc,.txt,.pdf,.pptx,.ppt,.xlsx,.xls"
        onChange={handleFileInputChange}
        style={{ display: 'none' }}
      />
      {/* Left Mode Sidebar — always rendered, collapsed in chat mode */}
      <WorkspaceSidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        hasDocument={hasDocument}
        onLogoClick={handleLogoClick}
        onNeedDocument={(targetTab) => {
          sessionStorage.setItem('pendingTab', targetTab);
          setShowOpenDocumentModal(true);
        }}
        onOpenSessions={() => setShowSessionsModal(true)}
        onFileSelect={(path, format) => {
          handleWorkspaceFileSelect(path, format);
          setMobileDrawerOpen(false);
        }}
        onUploadToFolder={handleUploadToFolder}
        onDeleteFile={handleDeleteWorkspaceFile}
        onConfirmAction={(message, onConfirm) => showConfirmModal(message, () => { hideConfirmModal(); onConfirm(); })}
        onUploadClick={handleUploadClick}
        sessionId={currentSessionId || undefined}
        refreshTrigger={sidebarRefreshTrigger}
        mobileDrawerOpen={mobileDrawerOpen}
        onToggleMobileDrawer={() => setMobileDrawerOpen(v => !v)}
        onOpenModelSelector={() => { setShowMobileModelSelector(true); setMobileDrawerOpen(false); }}
        onSignOut={() => {
          localStorage.removeItem('auth_token');
          localStorage.removeItem('isAuthenticated');
          window.location.href = '/';
        }}
        isAuthenticated={isAuthenticated === true}
      />

      {/* Main Area */}
      <div className={styles.mainArea}>
        {/* Header with Actions */}
        <WorkspaceHeader
          activeTab={activeTab}
          hasDocument={hasDocument}
          hasSelection={hasSelection}
          isDocOpen={hasDocument || isDocxFile || !!imageViewerUrl}
          isDocPanelVisible={isDocPanelVisible}
          onToggleDocPanel={() => setIsDocPanelVisible(v => !v)}
          documentName={documentName || undefined}
          onNewDocument={handleNewDocument}
          isAuthenticated={isAuthenticated}
          actions={getHeaderActions()}
        />

        {/* Error Banner */}
        {error && (
          <div className={styles.errorBanner}>
            {error}
            <button onClick={() => setError(null)}>×</button>
          </div>
        )}

        <div className={styles.workspaceBody}>
          <main className={styles.workspaceMain}>
            {/* Knowledge tab takes over the main area entirely when active.
                Compiled per-workspace wiki: clauses, parties, jurisdictions, findings. */}
            {activeTab === 'knowledge' ? (
              <KnowledgePanel sessionId={currentSessionId || undefined} />
            ) : (
            <div className={styles.splitPanel}>

              {/* ─── Document panel (only when a doc is open and visible) ─── */}
              {!isNoDocState && isDocPanelVisible && (
              <div className={styles.contentPanel} ref={editorContainerRef}>
                {/* Document Panel Header — close / filename / accept / download / hide */}
                {/* Hidden for: PDF-previewed files, config files (controls in UnifiedToolbar) */}
                {(hasDocument || isDocxFile) && !isDocxFile && !imageViewerUrl && !configBanner && (
                  <div className={styles.docPanelHeader}>
                    <button
                      className={styles.docPanelClose}
                      onClick={handleCloseDocument}
                      title="Close document"
                    >✕</button>
                    <span className={styles.docPanelFilename}>
                      {documentName || 'Untitled'}
                    </span>
                    <div className={styles.docPanelActions}>
                      {skillViewerContent && documentName?.startsWith('Skills/') ? (
                        null
                      ) : (
                        <>
                          <button
                            className={styles.docPanelBtn}
                            onClick={() => editor?.commands.acceptAllChanges()}
                            title="Accept all changes"
                          >Accept all</button>
                          <button
                            className={styles.docPanelBtn}
                            onClick={() => editor?.commands.rejectAllChanges()}
                            title="Reject all changes"
                          >Reject all</button>
                        </>
                      )}
                      {!(skillViewerContent && documentName?.startsWith('Skills/')) && (
                        <button
                          className={styles.docPanelBtn}
                          onClick={() => setIsDocPanelVisible(false)}
                          title="Hide document panel"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="3" y="3" width="18" height="18" rx="2"/>
                            <line x1="9" y1="3" x2="9" y2="21"/>
                            <polyline points="15 9 12 12 15 15"/>
                          </svg>
                          {!isMobile && 'Hide'}
                        </button>
                      )}
                    </div>
                  </div>
                )}
                {/* Selection Floating Toolbar — only for HTML-native docs */}
                {hasDocument && showFloatingToolbar && !isMobile && !isDocxFile && (
                  <SelectionToolbar
                    selectedText={selectedText}
                    position={selectionPosition}
                    containerRef={editorContainerRef}
                    onRevise={(instruction, capturedText) => {
                      const prompt = instruction
                        ? `Please revise the following text: "${capturedText}"\n\nInstruction: ${instruction}`
                        : `Please revise the following text: "${capturedText}"`;
                      setExplainText(prompt);
                      setChatPanelOpen(true);
                      setSelectedText('');
                      setSelectionPosition(null);
                    }}
                    onExplain={() => {
                      setExplainText(selectedText);
                      setChatPanelOpen(true);
                      setSelectedText('');
                      setSelectionPosition(null);
                    }}
                    onHighlightSelection={() => {
                      if (editor) {
                        editor.chain().focus().setHighlight({ color: '#b3d4fc' }).run();
                      }
                    }}
                    onClearHighlight={() => {
                      if (editor) {
                        editor.chain().focus().unsetHighlight().run();
                      }
                    }}
                  />
                )}

                {/* Skill viewer mode: structured card for SKILL.md files */}
                {skillViewerContent && documentName?.startsWith('Skills/') ? (
                  skillViewerContent === 'loading' ? null : (
                  <SkillViewer
                    filePath={documentName}
                    rawContent={skillViewerContent}
                    onClose={() => { setSkillViewerContent(null); setEmptyStateDismissed(false); }}
                  />)

                ) : imageViewerUrl ? (
                  <div className={styles.imageViewer}>
                    <div className={styles.imageViewerHeader}>
                      <button
                        onClick={handleCloseDocument}
                        title="Close image"
                        style={{ alignItems: 'center', background: 'none', border: 'none', cursor: 'pointer', display: 'flex', padding: '4px 6px', color: '#666', fontSize: 15, fontWeight: 500, lineHeight: 1, flexShrink: 0 }}
                      >✕</button>
                      {!isMobile && documentName && (
                        <div style={{ padding: '0 4px', fontSize: 12, fontWeight: 500, color: '#555', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', minWidth: 0, maxWidth: 200, flexShrink: 1 }} title={documentName}>
                          {documentName}
                        </div>
                      )}
                      <div style={{ flex: 1 }} />
                      <button
                        onClick={() => {
                          if (imageViewerUrl) {
                            const a = document.createElement('a');
                            a.href = imageViewerUrl;
                            a.download = documentName?.split('/').pop() || 'image';
                            document.body.appendChild(a);
                            a.click();
                            document.body.removeChild(a);
                          }
                        }}
                        title="Download image"
                        style={{ alignItems: 'center', background: 'none', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer', display: 'flex', gap: 4, fontSize: 12, padding: '4px 8px', marginRight: 4, color: '#333', flexShrink: 0 }}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                        {!isMobile && (documentName?.split('.').pop()?.toUpperCase() || 'IMG')}
                      </button>
                      {!isMobile && (
                        <button
                          onClick={() => setIsDocPanelVisible(false)}
                          title="Hide document panel"
                          style={{ alignItems: 'center', background: 'none', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer', display: 'flex', gap: 4, fontSize: 12, padding: '4px 8px', marginRight: 4, color: '#333', flexShrink: 0 }}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="3" y="3" width="18" height="18" rx="2"/>
                            <line x1="9" y1="3" x2="9" y2="21"/>
                            <polyline points="15 9 12 12 15 15"/>
                          </svg>
                          Hide
                        </button>
                      )}
                    </div>
                    <div className={styles.imageViewerBody}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={imageViewerUrl}
                        alt={documentName || 'Image preview'}
                        className={styles.imageViewerImg}
                      />
                    </div>
                  </div>
                ) : isDocxFile && documentName ? (
                  <div style={{ flex: 1, overflow: 'hidden' }}>
                    <PdfPreview
                      pdfData={pdfData}
                      pdfError={pdfError}
                      onDownloadDocx={handleDownloadDocx}
                      downloadLabel={
                        documentName?.match(/\.(xlsx?)$/i) ? 'XLSX'
                        : documentName?.match(/\.(pptx?)$/i) ? 'PPTX'
                        : documentName?.match(/\.pdf$/i) ? 'PDF'
                        : 'DOCX'
                      }
                      documentName={documentName || undefined}
                      scrollToText={scrollToText}
                      onScrollComplete={() => setScrollToText(null)}
                      isMobile={isMobile}
                      onClose={handleCloseDocument}
                      onHide={() => setIsDocPanelVisible(false)}
                    />
                  </div>
                ) : (
                  <EditorPanel
                    editor={editor}
                    activeTab={activeTab}
                    hasDocument={hasDocument}
                    viewMode={viewMode}
                    trackingEnabled={trackingEnabled}
                    hasTrackedChanges={trackedChanges}
                    selectedText={selectedText}
                    documentName={documentName}
                    isUploading={isLoadingFile}
                    sessionContext={sessionContext}
                    onContextChange={setSessionContext}
                    fileInputRef={fileInputRef}
                    onUploadClick={() => setShowOpenDocumentModal(true)}
                    onFileUpload={handleFileUpload}
                    onViewModeChange={handleViewModeChange}
                    onAcceptAll={() => editor?.commands.acceptAllChanges()}
                    onRejectAll={() => editor?.commands.rejectAllChanges()}
                    emptyStateDismissed={emptyStateDismissed}
                    onEmptyStateDismiss={() => setEmptyStateDismissed(true)}
                    onShowEmptyState={() => setEmptyStateDismissed(false)}
                    onDraftClick={() => {
                      setEmptyStateDismissed(true);
                    }}
                    getDocumentText={getDocumentText}
                    onExportDocx={handleExportDocx}
                    onExportPdf={handleExportPdf}
                    onSaveToCloud={handleSaveToCloud}
                    isExporting={isExporting}
                    isSavingToCloud={isSavingToCloud}
                    pageSettings={pageSettings}
                    onLayoutChange={setPageLayout}
                    onPageSizeChange={setPageSize}
                    onZoomChange={setPageZoom}
                    onInsertPageBreak={() => editor?.commands.setPageBreak()}
                    configMode={configBanner ? { type: configBanner.type, label: configBanner.type === 'agent' ? 'anylegal.md — workspace instructions' : configBanner.type === 'markdown' ? (documentName || '') : `Playbook \u00b7 ${documentName || ''}` } : null}
                    onClose={configBanner ? () => {
                      if (configBanner.type === 'markdown') {
                        handleCloseDocument();
                        return;
                      }
                      const isDirty = editor && configInitialContent.current !== null && editor.getHTML() !== configInitialContent.current;
                      if (isDirty) {
                        setShowCloseConfirm(true);
                      } else {
                        handleCloseDocument();
                      }
                    } : undefined}
                    saveFlash={saveFlash}
                    docxReadOnly={isDocxFile}
                  />
                )}
              </div>
              )}

              {/* ─── Persistent Chat — single instance, never unmounts ─── */}
              <div className={chatWrapperClass}>
                {/* Mobile sheet chrome (handle + header) */}
                {isMobile && !isNoDocState && (
                  <>
                    <div className={styles.mobileSheetHandle} onClick={() => setMobileSheetOpen(false)} />
                    <div className={styles.mobileSheetHeader}>
                      <span className={styles.mobileSheetTitle}>Chat</span>
                      <div className={styles.mobileSheetActions}>
                        <button className={styles.mobileSheetNewBtn} onClick={() => resetChatState()} title="New chat">+</button>
                        <button className={styles.mobileSheetClose} onClick={() => setMobileSheetOpen(false)}>×</button>
                      </div>
                    </div>
                  </>
                )}
                <div className={styles.chatPanelContent}>
                  <WorkspaceChat
                    variant={chatVariant}
                    showHeader={chatShowHeader}
                    documentText={getDocumentText()}
                    selectedText={selectedText}
                    sessionContext={sessionContext}
                    documentId={documentId || undefined}
                    documentName={documentName || undefined}
                    hasDocument={hasDocument}
                    hasUserContent={hasUserContent}
                    workspaceSessionId={currentSessionId || undefined}
                    newChatTrigger={chatKey}
                    initialThreadId={activeThreadId}
                    onThreadIdChanged={handleThreadIdChanged}
                    onSelectThread={handleSelectThread}
                    onDocumentUpdate={handleChatDocumentUpdate}
                    onOpenDocument={handleChatOpenDocument}
                    onDownloadDocument={handleDownloadDocumentFromChat}
                    onDocumentDeleted={handleChatDocumentDeleted}
                    onDocumentCreated={handleChatDocumentCreated}
                    onAgenticSessionCreated={handleChatAgenticSessionCreated}
                  />
                </div>
              </div>

            </div>
            )}
          </main>
        </div>
      </div>

      {/* Mobile: collapsed bottom bar + backdrop (chat is the persistent instance above) */}
      {isMobile && !isNoDocState && (
        <>
          <div className={`${styles.mobileBottomBar} ${mobileSheetOpen ? styles.hidden : ''}`}>
            <button
              className={styles.mobileBottomBarInput}
              onClick={() => setMobileSheetOpen(true)}
            >
              {hasDocument ? 'Ask or request changes...' : 'Ask a question or draft a document...'}
            </button>
            <button
              className={styles.mobileBottomBarExpand}
              onClick={() => setMobileSheetOpen(true)}
            >
              ↑
            </button>
          </div>
          <div
            className={`${styles.mobileSheetBackdrop} ${mobileSheetOpen ? styles.visible : ''}`}
            onClick={() => setMobileSheetOpen(false)}
          />
        </>
      )}

      {/* Mobile Model Selector Modal */}
      {showMobileModelSelector && (
        <div className={styles.modalOverlay} onClick={() => setShowMobileModelSelector(false)}>
          <div className={styles.modalContent} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h2 className={styles.modalTitle}>AI Model Selection</h2>
              <button
                className={styles.modalClose}
                onClick={() => setShowMobileModelSelector(false)}
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <ModelSelector onModelChange={() => {}} />
          </div>
        </div>
      )}

      {/* Document Manager Modal */}
      {showDocumentManager && (
        <div className={styles.modalOverlay} onClick={() => setShowDocumentManager(false)}>
          <div className={styles.documentManagerModal} onClick={(e) => e.stopPropagation()}>
            <DocumentManager
              onSelectDocument={(content, title, docId) => {
                if (editor) {
                  editor.commands.setContent(content);
                  setTimeout(() => {
                    if (editor.view) {
                      const { state, view } = editor;
                      const newState = EditorState.create({
                        doc: state.doc,
                        plugins: state.plugins,
                      });
                      view.updateState(newState);
                    }
                  }, 100);
                  setDocumentName(title);
                  setDocumentId(docId || null); // Track document ID for chat history
                  setEmptyStateDismissed(true);
                  resetChatState();
                }
                setShowDocumentManager(false);
              }}
              currentDocumentContent={editor?.getHTML() || ''}
              currentDocumentId={documentId || undefined}
              onClose={() => setShowDocumentManager(false)}
              onDocumentSaved={async (newDocId, title) => {
                setDocumentId(newDocId);
                setDocumentName(title);

                const threadId = currentChatThreadIdRef.current;
                if (threadId && newDocId) {
                  try {
                    const token = localStorage.getItem('auth_token');
                    const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL || '';
                    await fetch(`${BASE_URL}/api/v1/threads/${threadId}/document`, {
                      method: 'PATCH',
                      headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`,
                      },
                      body: JSON.stringify({
                        document_id: newDocId,
                        document_name: title,
                      }),
                    });
                  } catch (err) {
                    console.error('Failed to link thread to document:', err);
                  }
                }
              }}
            />
          </div>
        </div>
      )}

      {/* History Modal */}
      <HistoryModal
        isOpen={showHistoryModal}
        onClose={() => setShowHistoryModal(false)}
        onThreadSelect={(threadId) => {
          setShowHistoryModal(false);
          setActiveThreadId(threadId);
          setChatKey(k => k + 1);
          setChatPanelOpen(true);
        }}
        privacyMode={privacyMode}
      />

      {/* Workspace Sessions Modal */}
      <WorkspaceSessionsModal
        isOpen={showSessionsModal}
        onClose={() => setShowSessionsModal(false)}
        currentSessionId={currentSessionId}
        onLoadSession={(session) => {
          setCurrentSessionId(session.id);
          if (session.documents.length > 0) {
            const activeDoc = session.documents.find(d => d.path === session.active_document) 
              || session.documents[0];
            if (activeDoc.content) {
              editor?.commands.setContent(activeDoc.content);
              setTimeout(() => {
                if (editor && editor.view) {
                  const { state, view } = editor;
                  const newState = EditorState.create({
                    doc: state.doc,
                    plugins: state.plugins,
                  });
                  view.updateState(newState);
                }
              }, 100);
              setDocumentName(activeDoc.path);
              setEmptyStateDismissed(true);
              resetChatState();
            }
          }
        }}
        onOpenDocument={async (sessionId, doc) => {
          setCurrentSessionId(sessionId);

          let content = doc.content;
          if (!content) {
            try {
              const fetchedDoc = await getSessionDocument(sessionId, doc.path);
              content = fetchedDoc?.content || '';
            } catch (err) {
              console.error('Failed to fetch document content:', err);
              setError('Failed to load document content');
              return;
            }
          }

          if (content) {
            editor?.commands.setContent(content);
            setTimeout(() => {
              if (editor && editor.view) {
                const { state, view } = editor;
                const newState = EditorState.create({
                  doc: state.doc,
                  plugins: state.plugins,
                });
                view.updateState(newState);
              }
            }, 100);
            setDocumentName(doc.path);
            setEmptyStateDismissed(true);
            resetChatState();
          }
        }}
      />

      {/* Open Document Modal */}
      <OpenDocumentModal
        isOpen={showOpenDocumentModal}
        onClose={() => { setShowOpenDocumentModal(false); setUploadTargetFolder(null); uploadTargetFolderRef.current = null; }}
        onSelectCloudDocument={(content, title, docId) => {
          editor?.commands.setContent(content);
          setTimeout(() => {
            if (editor && editor.view) {
              const { state, view } = editor;
              const newState = EditorState.create({
                doc: state.doc,
                plugins: state.plugins,
              });
              view.updateState(newState);
            }
          }, 100);
          setDocumentName(title);
          setDocumentId(docId);
          setEmptyStateDismissed(true);
          resetChatState();

          const pendingTab = sessionStorage.getItem('pendingTab');
          if (pendingTab) {
            sessionStorage.removeItem('pendingTab');
            setActiveTab(pendingTab as any);
          }
        }}
        onUploadClick={handleUploadClick}
      />

      {/* Confirmation Modal */}
      <ConfirmModal
        open={confirmModal.open}
        message={confirmModal.message}
        onConfirm={confirmModal.onConfirm}
        onCancel={hideConfirmModal}
      />

      {/* File Upload Modal (DOCX, PDF, images, etc.) */}
      <DocxUploadModal
        open={showDocxModal}
        fileName={pendingDocxFileRef.current?.name}
        folders={workspaceFolders}
        defaultFolder={uploadTargetFolder || undefined}
        onConfirm={handleDocxUploadConfirm}
        onCancel={() => {
          setShowDocxModal(false);
          pendingDocxFileRef.current = null;
          setUploadTargetFolder(null);
          uploadTargetFolderRef.current = null;
        }}
      />

      {/* Config file unsaved-changes modal (anylegal.md, playbooks) */}
      {showCloseConfirm && configBanner && (
        <div className={styles.modalOverlay} onClick={() => setShowCloseConfirm(false)}>
          <div className={styles.modalContent} onClick={e => e.stopPropagation()} style={{ maxWidth: 380, padding: '2rem', textAlign: 'center' }}>
            <div style={{
              width: 48, height: 48, borderRadius: 12,
              background: 'linear-gradient(135deg, #f59e0b 0%, #f97316 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 12px',
              boxShadow: '0 4px 12px rgba(245, 158, 11, 0.25)',
            }}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z" />
                <polyline points="17 21 17 13 7 13 7 21" />
                <polyline points="7 3 7 8 15 8" />
              </svg>
            </div>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#111', margin: '0 0 6px' }}>
              Save before closing?
            </h3>
            <p style={{ fontSize: '0.85rem', color: '#64748b', margin: '0 0 20px', lineHeight: 1.5 }}>
              Your changes will be lost if you don&apos;t save.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <button
                className={styles.modalBtnPrimary}
                onClick={handleSaveAndClose}
                disabled={isSavingToCloud}
              >
                {isSavingToCloud ? 'Saving...' : 'Save & Close'}
              </button>
              <button
                className={styles.modalBtnDanger}
                onClick={handleCloseDocument}
              >
                Discard & Close
              </button>
              <button
                className={styles.modalBtnCancel}
                onClick={() => setShowCloseConfirm(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Save to Cloud Dialog */}
      {showSaveDialog && (
        <div className={styles.modalOverlay} onClick={() => setShowSaveDialog(false)}>
          <div className={styles.modalContent} onClick={e => e.stopPropagation()}>
            <h3 className={styles.modalTitle}>Save to Encrypted Cloud</h3>
            <input
              type="text"
              value={saveTitle}
              onChange={(e) => setSaveTitle(e.target.value)}
              placeholder="Document title"
              className={styles.modalInput}
              autoFocus
            />
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button 
                className={styles.modalBtnCancel}
                onClick={() => setShowSaveDialog(false)}
                style={{ flex: 1 }}
              >
                Cancel
              </button>
              <button 
                className={styles.modalBtnPrimary}
                onClick={handleSaveNewToCloud}
                disabled={isSavingToCloud || !saveTitle.trim()}
                style={{ flex: 1 }}
              >
                {isSavingToCloud ? 'Saving...' : 'Save'}
              </button>
            </div>
            <p className={styles.modalNote}>Documents are encrypted at rest</p>
          </div>
        </div>
      )}

    </div>
  );
}
