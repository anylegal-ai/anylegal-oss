'use client';

import React, { useState, useEffect } from 'react';
import styles from './PlaybookPickerModal.module.css';

interface ContextTemplate {
  id: number;
  name: string;
  description?: string;
  context_text: string;
  document_types: string[];
  is_default: boolean;
}

interface DocumentTemplate {
  id: number;
  name: string;
  description?: string;
  template_type: string;
  content: string;
  variables: string[];
  jurisdiction: string;
}

interface PlaybookClause {
  id: number;
  clause_type: string;
  position: string;
  title: string;
  clause_text: string;
  explanation?: string;
}

type PickerTab = 'contexts' | 'templates' | 'clauses';

interface PlaybookPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectContext?: (context: ContextTemplate) => void;
  onSelectTemplate?: (template: DocumentTemplate) => void;
  onSelectClause?: (clause: PlaybookClause) => void;
  showTabs?: PickerTab[];
  initialTab?: PickerTab;
  title?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_BASE_URL || '';

export default function PlaybookPickerModal({
  isOpen,
  onClose,
  onSelectContext,
  onSelectTemplate,
  onSelectClause,
  showTabs = ['contexts', 'templates', 'clauses'],
  initialTab,
  title = 'Select from Playbook',
}: PlaybookPickerModalProps) {
  const [activeTab, setActiveTab] = useState<PickerTab>(initialTab || showTabs[0]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [contexts, setContexts] = useState<ContextTemplate[]>([]);
  const [templates, setTemplates] = useState<DocumentTemplate[]>([]);
  const [clauses, setClauses] = useState<PlaybookClause[]>([]);

  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen]);

  const getAuthHeaders = () => {
    const token = localStorage.getItem('auth_token');
    return token ? { 'Authorization': `Bearer ${token}` } : {};
  };

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      const headers = {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      } as Record<string, string>;

      const [contextsRes, templatesRes, clausesRes] = await Promise.all([
        showTabs.includes('contexts') 
          ? fetch(`${API_BASE}/api/v1/editor/templates/contexts`, { headers })
          : Promise.resolve(null),
        showTabs.includes('templates')
          ? fetch(`${API_BASE}/api/v1/editor/templates/documents`, { headers })
          : Promise.resolve(null),
        showTabs.includes('clauses')
          ? fetch(`${API_BASE}/api/v1/editor/playbook/clauses`, { headers })
          : Promise.resolve(null),
      ]);

      if (contextsRes?.ok) {
        const data = await contextsRes.json();
        setContexts(data || []);
      }
      if (templatesRes?.ok) {
        const data = await templatesRes.json();
        setTemplates(data || []);
      }
      if (clausesRes?.ok) {
        const data = await clausesRes.json();
        setClauses(data || []);
      }
    } catch (err) {
      setError('Failed to load playbook data');
      console.error('PlaybookPickerModal load error:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredContexts = contexts.filter(c => 
    c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.context_text.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredTemplates = templates.filter(t =>
    t.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    t.template_type.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredClauses = clauses.filter(c =>
    c.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    c.clause_type.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (!isOpen) return null;

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div className={styles.overlay} onClick={handleBackdropClick}>
      <div className={styles.modal}>
        {/* Header */}
        <div className={styles.header}>
          <h2 className={styles.title}>{title}</h2>
          <button className={styles.closeBtn} onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"/>
              <line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className={styles.searchContainer}>
          <svg className={styles.searchIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        {/* Tabs */}
        {showTabs.length > 1 && (
          <div className={styles.tabs}>
            {showTabs.includes('contexts') && (
              <button
                className={`${styles.tab} ${activeTab === 'contexts' ? styles.tabActive : ''}`}
                onClick={() => setActiveTab('contexts')}
              >
                Context Presets ({filteredContexts.length})
              </button>
            )}
            {showTabs.includes('templates') && (
              <button
                className={`${styles.tab} ${activeTab === 'templates' ? styles.tabActive : ''}`}
                onClick={() => setActiveTab('templates')}
              >
                Document Templates ({filteredTemplates.length})
              </button>
            )}
            {showTabs.includes('clauses') && (
              <button
                className={`${styles.tab} ${activeTab === 'clauses' ? styles.tabActive : ''}`}
                onClick={() => setActiveTab('clauses')}
              >
                Clauses ({filteredClauses.length})
              </button>
            )}
          </div>
        )}

        {/* Content */}
        <div className={styles.content}>
          {loading ? (
            <div className={styles.loadingState}>
              <div className={styles.spinner}></div>
              <p>Loading...</p>
            </div>
          ) : error ? (
            <div className={styles.errorState}>
              <p>{error}</p>
              <button onClick={loadData}>Retry</button>
            </div>
          ) : (
            <>
              {/* Contexts Tab */}
              {activeTab === 'contexts' && (
                <div className={styles.list}>
                  {filteredContexts.length === 0 ? (
                    <div className={styles.emptyState}>
                      <p>No context presets found</p>
                      <a href="/playbook" className={styles.linkBtn}>Create in Playbook</a>
                    </div>
                  ) : (
                    filteredContexts.map((ctx) => (
                      <button
                        key={ctx.id}
                        className={`${styles.item} ${ctx.is_default ? styles.itemDefault : ''}`}
                        onClick={() => {
                          onSelectContext?.(ctx);
                          onClose();
                        }}
                      >
                        <div className={styles.itemHeader}>
                          <span className={styles.itemTitle}>{ctx.name}</span>
                          {ctx.is_default && <span className={styles.defaultBadge}>Default</span>}
                        </div>
                        {ctx.description && (
                          <p className={styles.itemDescription}>{ctx.description}</p>
                        )}
                        <p className={styles.itemPreview}>&quot;{ctx.context_text.slice(0, 100)}...&quot;</p>
                      </button>
                    ))
                  )}
                </div>
              )}

              {/* Templates Tab */}
              {activeTab === 'templates' && (
                <div className={styles.list}>
                  {filteredTemplates.length === 0 ? (
                    <div className={styles.emptyState}>
                      <p>No document templates found</p>
                      <a href="/playbook" className={styles.linkBtn}>Upload in Playbook</a>
                    </div>
                  ) : (
                    filteredTemplates.map((template) => (
                      <button
                        key={template.id}
                        className={styles.item}
                        onClick={() => {
                          onSelectTemplate?.(template);
                          onClose();
                        }}
                      >
                        <div className={styles.itemHeader}>
                          <span className={styles.itemTitle}>{template.name}</span>
                          <span className={styles.typeBadge}>{template.template_type.toUpperCase()}</span>
                        </div>
                        {template.description && (
                          <p className={styles.itemDescription}>{template.description}</p>
                        )}
                        <div className={styles.itemMeta}>
                          <span>{template.jurisdiction}</span>
                          {template.variables.length > 0 && (
                            <span>{template.variables.length} variables</span>
                          )}
                        </div>
                      </button>
                    ))
                  )}
                </div>
              )}

              {/* Clauses Tab */}
              {activeTab === 'clauses' && (
                <div className={styles.list}>
                  {filteredClauses.length === 0 ? (
                    <div className={styles.emptyState}>
                      <p>No clauses found</p>
                      <a href="/playbook" className={styles.linkBtn}>Add in Playbook</a>
                    </div>
                  ) : (
                    filteredClauses.map((clause) => (
                      <button
                        key={clause.id}
                        className={styles.item}
                        onClick={() => {
                          onSelectClause?.(clause);
                          onClose();
                        }}
                      >
                        <div className={styles.itemHeader}>
                          <span className={styles.itemTitle}>{clause.title}</span>
                          <span className={`${styles.positionBadge} ${styles[clause.position]}`}>
                            {clause.position.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <p className={styles.itemType}>{clause.clause_type.replace(/_/g, ' ')}</p>
                        <p className={styles.itemPreview}>{clause.clause_text.slice(0, 120)}...</p>
                      </button>
                    ))
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
