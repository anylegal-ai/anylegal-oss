import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { isTokenExpired } from '@/utils/auth';
import type { 
  WorkspaceTab, 
  ViewMode, 
  ConfirmModalState,
  PageSettings,
  EditorLayout,
  PageSize,
} from '../types/workspace';

export interface UseWorkspaceStateReturn {
  isAuthenticated: boolean | null;

  activeTab: WorkspaceTab;
  setActiveTab: (tab: WorkspaceTab) => void;

  sessionContext: string;
  setSessionContext: (context: string) => void;

  documentName: string | null;
  setDocumentName: (name: string | null) => void;
  documentLength: number;
  setDocumentLength: (length: number) => void;
  cursorPlaced: boolean;
  setCursorPlaced: (placed: boolean) => void;
  insertNotice: string | null;
  setInsertNotice: (notice: string | null) => void;

  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
  trackingEnabled: boolean;
  setTrackingEnabled: (enabled: boolean) => void;

  chatPanelOpen: boolean;
  setChatPanelOpen: (open: boolean) => void;
  emptyStateDismissed: boolean;
  setEmptyStateDismissed: (dismissed: boolean) => void;

  error: string | null;
  setError: (error: string | null) => void;

  confirmModal: ConfirmModalState;
  setConfirmModal: (state: ConfirmModalState) => void;
  showConfirmModal: (message: string, onConfirm: () => void) => void;
  hideConfirmModal: () => void;

  pageSettings: PageSettings;
  setPageLayout: (layout: EditorLayout) => void;
  setPageSize: (size: PageSize) => void;
  setPageZoom: (zoom: number) => void;
  setShowPageNumbers: (show: boolean) => void;
  setHeaderText: (text: string) => void;
  setFooterText: (text: string) => void;

  hasDocument: boolean;
}

export function useWorkspaceState(): UseWorkspaceStateReturn {
  const router = useRouter();

  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);

  const [activeTab, setActiveTab] = useState<WorkspaceTab>('workspace');

  const [sessionContext, setSessionContext] = useState('');

  const [documentName, setDocumentName] = useState<string | null>(null);
  const [documentLength, setDocumentLength] = useState(0);
  const [cursorPlaced, setCursorPlaced] = useState(false);
  const [insertNotice, setInsertNotice] = useState<string | null>(null);

  const [viewMode, setViewMode] = useState<ViewMode>('clean');
  const [trackingEnabled, setTrackingEnabled] = useState(false);

  const [chatPanelOpen, setChatPanelOpen] = useState(true);
  const [emptyStateDismissed, setEmptyStateDismissed] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [confirmModal, setConfirmModal] = useState<ConfirmModalState>({
    open: false,
    message: '',
    onConfirm: () => {},
  });

  const [pageSettings, setPageSettings] = useState<PageSettings>({
    layout: 'scroll',
    pageSize: 'a4',
    zoom: 100,
    showPageNumbers: true,
    showHeaders: false,
    headerText: '',
    footerText: '',
  });

  const setPageLayout = useCallback((layout: EditorLayout) => {
    setPageSettings(prev => ({ ...prev, layout }));
  }, []);

  const setPageSize = useCallback((pageSize: PageSize) => {
    setPageSettings(prev => ({ ...prev, pageSize }));
  }, []);

  const setPageZoom = useCallback((zoom: number) => {
    setPageSettings(prev => ({ ...prev, zoom }));
  }, []);

  const setShowPageNumbers = useCallback((showPageNumbers: boolean) => {
    setPageSettings(prev => ({ ...prev, showPageNumbers }));
  }, []);

  const setHeaderText = useCallback((headerText: string) => {
    setPageSettings(prev => ({ ...prev, headerText, showHeaders: true }));
  }, []);

  const setFooterText = useCallback((footerText: string) => {
    setPageSettings(prev => ({ ...prev, footerText }));
  }, []);

  useEffect(() => {
    const saved = localStorage.getItem('workspace_session_context');
    if (saved) setSessionContext(saved);
  }, []);

  useEffect(() => {
    localStorage.setItem('workspace_session_context', sessionContext);
  }, [sessionContext]);

  useEffect(() => {
    if (documentLength === 0 && !documentName) {
      setEmptyStateDismissed(false);
    }
  }, [documentLength, documentName]);

  useEffect(() => {
    setIsAuthenticated(true);
  }, []);

  const showConfirmModal = useCallback((message: string, onConfirm: () => void) => {
    setConfirmModal({ open: true, message, onConfirm });
  }, []);

  const hideConfirmModal = useCallback(() => {
    setConfirmModal({ open: false, message: '', onConfirm: () => {} });
  }, []);

  const hasDocument = documentLength > 10 || !!documentName;

  return {
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
    setConfirmModal,
    showConfirmModal,
    hideConfirmModal,
    pageSettings,
    setPageLayout,
    setPageSize,
    setPageZoom,
    setShowPageNumbers,
    setHeaderText,
    setFooterText,
    hasDocument,
  };
}
