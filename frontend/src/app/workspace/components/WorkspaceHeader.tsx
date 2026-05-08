import React, { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import type { WorkspaceTab, ReviseScope, DraftMode } from '../types/workspace';
import styles from '../workspace.module.css';
import ModelSelector from '@/components/ModelSelector';

interface HeaderAction {
  id: string;
  label: string;
  icon: string;
  onClick: () => void;
  disabled: boolean;
  loading: boolean;
  active?: boolean;
}

interface WorkspaceHeaderProps {
  activeTab: WorkspaceTab;
  hasDocument: boolean;
  hasSelection: boolean;
  isDocOpen?: boolean;
  isDocPanelVisible?: boolean;
  onToggleDocPanel?: () => void;
  documentName?: string;
  onNewDocument: () => void;

  isAuthenticated?: boolean;

  onFullReview?: () => void;
  onAnalyzeSelection?: () => void;
  onProofread?: () => void;
  isReviewing?: boolean;
  isAnalyzing?: boolean;
  isProofreading?: boolean;

  reviseScope?: ReviseScope;
  onReviseScopeChange?: (scope: ReviseScope) => void;

  draftMode?: DraftMode;
  onDraftModeChange?: (mode: DraftMode) => void;

  actions: HeaderAction[];
}

const Icons = {
  folder: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
    </svg>
  ),
  chat: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
    </svg>
  ),
  clock: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  ),
  user: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/>
    </svg>
  ),
  shield: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>
    </svg>
  ),
  logout: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
  ),
  check: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  ),
  chevronDown: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9"/>
    </svg>
  ),
  word: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 4h16a2 2 0 012 2v12a2 2 0 01-2 2H4a2 2 0 01-2-2V6a2 2 0 012-2z"/>
      <path d="M7 8l2 8 2-6 2 6 2-8"/>
    </svg>
  ),
  externalLink: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
    </svg>
  ),
  copy: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
    </svg>
  ),
  sparkles: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707"/>
      <circle cx="12" cy="12" r="4"/>
    </svg>
  ),
  close: (className?: string) => (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  ),
};

const renderActionIcon = (icon: string) => {
  switch (icon) {
    case 'clipboard':
      return <svg className={styles.headerActionIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>;
    case 'check-circle':
      return <svg className={styles.headerActionIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>;
    case 'check':
      return <svg className={styles.headerActionIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round"/></svg>;
    case 'edit':
      return <svg className={styles.headerActionIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>;
    case 'sparkles':
      return <svg className={styles.headerActionIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707"/></svg>;
    default:
      return null;
  }
};

export function WorkspaceHeader({
  activeTab,
  hasDocument,
  hasSelection,
  isDocOpen,
  isDocPanelVisible,
  onToggleDocPanel,
  documentName,
  isAuthenticated,
  onFullReview,
  onAnalyzeSelection,
  onProofread,
  isReviewing,
  isAnalyzing,
  isProofreading,
  reviseScope,
  onReviseScopeChange,
  draftMode,
  onDraftModeChange,
  actions,
}: WorkspaceHeaderProps) {
  const router = useRouter();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [showModelSelector, setShowModelSelector] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSignOut = () => {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('isAuthenticated');
    router.push('/');
  };

  return (
    <header className={styles.workspaceHeader}>
      <div className={styles.headerActions}>
        {/* Quick action buttons - always visible when document loaded */}
        {hasDocument && (
          <>
            {/* Analyze Selection - enabled when text is selected */}
            {onAnalyzeSelection && (
              <button
                className={styles.headerActionBtn}
                onClick={onAnalyzeSelection}
                disabled={!hasSelection || isAnalyzing}
                title="Analyze the selected text"
              >
                <svg className={styles.headerActionIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/>
                </svg>
                <span>{isAnalyzing ? 'Analyzing...' : 'Analyze Selection'}</span>
              </button>
            )}

            {/* Full Review - document-level analysis */}
            {onFullReview && (
              <button
                className={`${styles.headerActionBtn} ${styles.headerActionPrimary}`}
                onClick={onFullReview}
                disabled={isReviewing}
                title="Get a comprehensive review of the entire agreement"
              >
                <svg className={styles.headerActionIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <span>{isReviewing ? 'Reviewing...' : 'Full Review'}</span>
              </button>
            )}

            {/* Proofread - grammar and consistency check */}
            {onProofread && (
              <button
                className={styles.headerActionBtn}
                onClick={onProofread}
                disabled={isProofreading}
                title="Check for grammar, typos, and inconsistencies"
              >
                <svg className={styles.headerActionIcon} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <span>{isProofreading ? 'Checking...' : 'Proofread'}</span>
              </button>
            )}

            {/* Legacy tab-specific actions - for backwards compatibility during transition */}
            {actions.map(action => (
              <button
                key={action.id}
                className={`${styles.headerActionBtn} ${action.active ? styles.headerActionActive : ''}`}
                onClick={action.onClick}
                disabled={action.disabled}
              >
                {renderActionIcon(action.icon)}
                <span>{action.loading ? 'Working...' : action.label}</span>
              </button>
            ))}

            {/* Revise scope toggle */}
            {activeTab === 'revise' && onReviseScopeChange && (
              <>
                <div className={styles.headerDivider} />
                <div className={styles.scopeToggle} style={{ margin: 0 }}>
                  <button className={reviseScope === 'selection' ? styles.active : ''} onClick={() => onReviseScopeChange('selection')}>
                    Selection
                  </button>
                  <button className={reviseScope === 'document' ? styles.active : ''} onClick={() => onReviseScopeChange('document')}>
                    Document
                  </button>
                </div>
              </>
            )}
          </>
        )}

        {/* Draft mode controls only shown when no document */}
        {!hasDocument && activeTab === 'draft' && onDraftModeChange && (
          <div className={styles.scopeToggle} style={{ margin: 0 }}>
            <button className={draftMode === 'clause' ? styles.active : ''} onClick={() => onDraftModeChange('clause')}>
              Clause
            </button>
            <button className={draftMode === 'agreement' ? styles.active : ''} onClick={() => onDraftModeChange('agreement')}>
              Agreement
            </button>
          </div>
        )}
      </div>

      {/* Center: doc name (when doc open + panel hidden) per §2.3 — click to reopen */}
      <div className={styles.headerCenter}>
        {isDocOpen && !isDocPanelVisible && documentName && onToggleDocPanel && (
          <button className={styles.headerCenterDocName} onClick={onToggleDocPanel} title="Show document panel">
            {documentName}
          </button>
        )}
      </div>

      <div className={styles.headerRight}>
        {/* Balance Pill — hidden for demo/org users */}
        {/* BalancePill stripped for OSS */}

        {/* User Menu */}
        {isAuthenticated && (
          <div className={styles.userMenuWrapper} ref={userMenuRef}>
            <button
              className={`${styles.userMenuBtn} ${userMenuOpen ? styles.userMenuOpen : ''}`}
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              title="Account & Settings"
            >
              <span className={styles.userMenuIcon}>
                {Icons.user()}
              </span>
              {Icons.chevronDown(styles.userMenuArrowIcon)}
            </button>

            {userMenuOpen && (
              <div className={styles.userMenuDropdown}>
                <div className={styles.userMenuSection}>
                  <button
                    className={styles.userMenuItem}
                    onClick={() => {
                      setShowModelSelector(true);
                      setUserMenuOpen(false);
                    }}
                  >
                    <span className={styles.userMenuItemIcon}>{Icons.sparkles()}</span>
                    <div className={styles.userMenuItemContent}>
                      <span className={styles.userMenuItemTitle}>Select Model</span>
                      <span className={styles.userMenuItemDesc}>Choose your preferred AI model</span>
                    </div>
                  </button>
                </div>
                <div className={styles.userMenuDivider} />
                <div className={styles.userMenuSection}>
                  <button className={styles.userMenuItem} onClick={handleSignOut}>
                    <span className={styles.userMenuItemIcon}>{Icons.logout()}</span>
                    <div className={styles.userMenuItemContent}>
                      <span className={styles.userMenuItemTitle}>Sign Out</span>
                    </div>
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Model Selector Modal */}
      {showModelSelector && (
        <div className={styles.modalOverlay} onClick={() => setShowModelSelector(false)}>
          <div className={styles.modalContent} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h2 className={styles.modalTitle}>AI Model Selection</h2>
              <button 
                className={styles.modalClose}
                onClick={() => setShowModelSelector(false)}
              >
                {Icons.close()}
              </button>
            </div>
            <ModelSelector 
              onModelChange={() => {
              }}
            />
          </div>
        </div>
      )}
    </header>
  );
}
