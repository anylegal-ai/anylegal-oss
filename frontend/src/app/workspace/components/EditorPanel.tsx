import React, { RefObject, useState, useEffect, useCallback, useRef } from 'react';
import { EditorContent, Editor } from '@tiptap/react';
import type { WorkspaceTab, ViewMode, PageSettings, EditorLayout, PageSize } from '../types/workspace';
import { UnifiedToolbar } from './UnifiedToolbar';
import { PageViewEditor } from './PageViewEditor';
import styles from '../workspace.module.css';

interface DocumentSection {
  id: string;
  number: string;
  title: string;
  level: number; // 0 for main (1.), 1 for sub (1.1), etc.
  position: number; // character position in document
}

interface EditorPanelProps {
  editor: Editor | null;
  activeTab: WorkspaceTab;
  hasDocument: boolean;
  viewMode: ViewMode;
  trackingEnabled: boolean;
  hasTrackedChanges: boolean;
  selectedText: string;
  documentName: string | null;
  isUploading: boolean;

  sessionContext: string;
  onContextChange: (value: string) => void;

  fileInputRef: RefObject<HTMLInputElement | null>;
  onUploadClick: () => void;
  onFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;

  onViewModeChange: (mode: ViewMode) => void;
  onAcceptAll: () => void;
  onRejectAll: () => void;

  reviseInstruction?: string;
  onReviseInstructionChange?: (value: string) => void;

  draftPrompt?: string;
  onDraftPromptChange?: (value: string) => void;
  onGenerate?: () => void;
  isGenerating?: boolean;

  emptyStateDismissed: boolean;
  onEmptyStateDismiss: () => void;
  onShowEmptyState: () => void;
  onDraftClick: () => void;

  getDocumentText: () => string;

  onExportDocx: (clean: boolean) => void;
  onExportPdf: (clean: boolean) => void;
  onSaveToCloud?: () => void;
  isExporting: boolean;
  isSavingToCloud?: boolean;

  pageSettings: PageSettings;
  onLayoutChange: (layout: EditorLayout) => void;
  onPageSizeChange: (size: PageSize) => void;
  onZoomChange: (zoom: number) => void;
  onInsertPageBreak?: () => void;

  configMode?: { type: string; label: string } | null;
  onClose?: () => void;
  saveFlash?: boolean;
  docxReadOnly?: boolean;
}

export function EditorPanel({
  editor,
  activeTab,
  hasDocument,
  viewMode,
  trackingEnabled,
  hasTrackedChanges,
  selectedText,
  documentName,
  isUploading,
  sessionContext,
  onContextChange,
  fileInputRef,
  onUploadClick,
  onFileUpload,
  onViewModeChange,
  onAcceptAll,
  onRejectAll,
  reviseInstruction,
  onReviseInstructionChange,
  draftPrompt,
  onDraftPromptChange,
  onGenerate,
  isGenerating,
  emptyStateDismissed,
  onEmptyStateDismiss,
  onShowEmptyState,
  onDraftClick,
  getDocumentText,
  onExportDocx,
  onExportPdf,
  onSaveToCloud,
  isExporting,
  isSavingToCloud,
  pageSettings,
  onLayoutChange,
  onPageSizeChange,
  onZoomChange,
  onInsertPageBreak,
  configMode,
  onClose,
  saveFlash,
  docxReadOnly,
}: EditorPanelProps) {

  const formatRelativeTime = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };
  const [sections, setSections] = useState<DocumentSection[]>([]);
  const [currentSection, setCurrentSection] = useState<DocumentSection | null>(null);
  const [instructionsBannerDismissed, setInstructionsBannerDismissed] = useState(false);
  const editorAreaRef = useRef<HTMLDivElement>(null);
  const isManualNavigating = useRef(false);

  const parseSections = useCallback(() => {
    if (!editor) return [];

    const text = editor.getText();
    const sections: DocumentSection[] = [];

    const sectionRegex = /^(\d+)[.\\]?\s+([A-Z][A-Z\s]+)/gm;

    let match;
    while ((match = sectionRegex.exec(text)) !== null) {
      const number = match[1];
      let title = match[2].trim();

      const words = title.split(/\s+/).filter(w => w === w.toUpperCase() && w.length > 1);
      title = words.join(' ');

      if (title.length > 3) {
        sections.push({
          id: `section-${number}`,
          number: number,
          title: title,
          level: 0,
          position: match.index,
        });
      }
    }

    return sections;
  }, [editor]);

  useEffect(() => {
    if (!editor || !hasDocument) {
      setSections([]);
      setCurrentSection(null);
      return;
    }

    setSections(parseSections());
    setCurrentSection(null);

    const handleUpdate = () => {
      setSections(parseSections());
    };

    editor.on('update', handleUpdate);
    return () => {
      editor.off('update', handleUpdate);
    };
  }, [editor, hasDocument, parseSections]);

  useEffect(() => {
    if (!editor || sections.length === 0) return;

    const editorArea = editorAreaRef.current;
    if (!editorArea) return;

    const handleScroll = () => {
      if (isManualNavigating.current) return;

      const text = editor.getText();
      const editorRect = editorArea.getBoundingClientRect();

      let visibleSection: DocumentSection | null = null;

      for (let i = sections.length - 1; i >= 0; i--) {
        const section = sections[i];

        const searchPattern = `${section.number}. ${section.title.split(' ')[0]}`;
        const pos = text.indexOf(searchPattern);

        if (pos >= 0) {
          try {
            const { view } = editor;
            const coords = view.coordsAtPos(pos + 1);

            if (coords && coords.top <= editorRect.top + 150) {
              visibleSection = section;
              break;
            }
          } catch {
          }
        }
      }

      if (visibleSection && visibleSection.id !== currentSection?.id) {
        setCurrentSection(visibleSection);
      }
    };

    editorArea.addEventListener('scroll', handleScroll);
    const timer = setTimeout(handleScroll, 100);

    return () => {
      editorArea.removeEventListener('scroll', handleScroll);
      clearTimeout(timer);
    };
  }, [editor, sections, currentSection]);

  const scrollToSection = useCallback((section: DocumentSection) => {
    if (!editor) return;

    isManualNavigating.current = true;

    setCurrentSection(section);

    const text = editor.getText();
    const searchPattern = `${section.number}. ${section.title.split(' ')[0]}`;
    let pos = text.indexOf(searchPattern);

    if (pos < 0) {
      const linePattern = `\n${section.number}. `;
      pos = text.indexOf(linePattern);
      if (pos >= 0) pos += 1; // Skip the newline
    }

    if (pos < 0) {
      const escapedPattern = `${section.number}\\. `;
      pos = text.indexOf(escapedPattern);
    }

    if (pos >= 0) {
      const { view } = editor;
      const domAtPos = view.domAtPos(pos + 1);

      if (domAtPos && domAtPos.node) {
        let targetElement: Element | null = domAtPos.node instanceof Element 
          ? domAtPos.node 
          : domAtPos.node.parentElement;

        while (targetElement && !['P', 'H1', 'H2', 'H3', 'DIV'].includes(targetElement.tagName)) {
          targetElement = targetElement.parentElement;
        }

        if (targetElement && editorAreaRef.current) {
          const editorArea = editorAreaRef.current;

          let offsetTop = 0;
          let el: HTMLElement | null = targetElement as HTMLElement;

          while (el && el !== editorArea) {
            offsetTop += el.offsetTop;
            el = el.offsetParent as HTMLElement | null;
          }

          const targetScrollTop = Math.max(0, offsetTop - 20);

          editorArea.scrollTop = targetScrollTop;

          editor.commands.setTextSelection(pos + 1);
          editor.commands.focus();

          requestAnimationFrame(() => {
            editorArea.scrollTop = targetScrollTop;
          });
        }
      }
    }

    setTimeout(() => {
      isManualNavigating.current = false;
    }, 600);
  }, [editor]);

  return (
    <div className={styles.editorWrapper}>
      {/* Hidden file input removed — WorkspaceClient mounts a single always-present
          <input ref={fileInputRef}> so the ref is never stolen or nullified
          when EditorPanel unmounts in DOCX mode. */}

      {/* Full-panel loading overlay */}
      {isUploading && (
        <div className={styles.fullPanelLoading}>
          <div className={styles.loadingSpinner} />
          <span>Opening document...</span>
        </div>
      )}

      {/* Unified Toolbar - combines file ops, formatting, view mode, context */}
      {hasDocument && (
        <UnifiedToolbar
          editor={editor}
          documentName={documentName}
          onUploadClick={onUploadClick}
          onExportDocx={onExportDocx}
          onExportPdf={onExportPdf}
          onSaveToCloud={onSaveToCloud}
          isExporting={isExporting}
          isSavingToCloud={isSavingToCloud}
          sections={sections}
          currentSection={currentSection}
          onScrollToSection={scrollToSection}
          sessionContext={sessionContext}
          onContextChange={onContextChange}
          viewMode={viewMode}
          onViewModeChange={onViewModeChange}
          trackingEnabled={trackingEnabled}
          hasTrackedChanges={hasTrackedChanges}
          onAcceptAll={onAcceptAll}
          onRejectAll={onRejectAll}
          getDocumentText={getDocumentText}
          pageSettings={pageSettings}
          onLayoutChange={onLayoutChange}
          onPageSizeChange={onPageSizeChange}
          onZoomChange={onZoomChange}
          onInsertPageBreak={onInsertPageBreak}
          configMode={configMode}
          onClose={onClose}
          saveFlash={saveFlash}
          docxReadOnly={docxReadOnly}
        />
      )}

      <div ref={editorAreaRef} className={`${styles.editorArea} ${viewMode === 'clean' ? styles.editorCleanMode : ''} ${pageSettings.layout === 'page' ? styles.pageView : ''}`}>
        {/* Show options link - when dismissed but still empty (user chose to draft) */}
        {!hasDocument && emptyStateDismissed && activeTab !== 'draft' && (
          <button 
            className={styles.showOptionsLink}
            onClick={onShowEmptyState}
          >
            ← Back to open/generate options
          </button>
        )}

        {/* Instructions banner for anylegal.md */}
        {configMode?.type === 'agent' && !instructionsBannerDismissed && (
          <div className={styles.instructionsBanner}>
            <span>
              This is your <strong>Instructions</strong> file. The AI reads it before every conversation to tailor its advice to you.
              Fill it in and Save — or type <code>/setup</code> in chat to have the AI set up your whole workspace.
            </span>
            <button
              className={styles.instructionsBannerDismiss}
              onClick={() => setInstructionsBannerDismissed(true)}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        )}

        {/* Read-only banner for agent-generated markdown files */}
        {configMode?.type === 'markdown' && (
          <div className={styles.instructionsBanner}>
            <span>
              This file was generated by the assistant. To revise it, ask in chat — e.g. <em>&ldquo;rewrite section 3 to be more cautious about MAS rules.&rdquo;</em>
            </span>
          </div>
        )}

        {/* Render editor in scroll or page view mode */}
        {pageSettings.layout === 'page' && hasDocument ? (
          <PageViewEditor
            editor={editor}
            pageSettings={pageSettings}
            documentName={documentName}
          />
        ) : (
          <EditorContent editor={editor} />
        )}
      </div>

      {selectedText && (
        <div className={styles.selectionInfo}>
          Selected: {selectedText.length} characters
        </div>
      )}
    </div>
  );
}
