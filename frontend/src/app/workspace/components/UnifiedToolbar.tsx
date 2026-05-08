import React, { useState, useEffect } from 'react';
import { Editor } from '@tiptap/react';
import type { ViewMode, PageSettings, EditorLayout, PageSize } from '../types/workspace';
import { PAGE_DIMENSIONS } from '../types/workspace';
import styles from '../workspace.module.css';

interface DocumentSection {
  id: string;
  number: string;
  title: string;
  level: number;
  position: number;
}

interface UnifiedToolbarProps {
  editor: Editor | null;
  documentName: string | null;
  documentFormat?: 'html' | 'docx' | null;  // DOCX-native vs HTML-native indicator
  onUploadClick: () => void;
  onExportDocx: (clean: boolean) => void;
  onExportPdf: (clean: boolean) => void;
  onSaveToCloud?: () => void;
  isExporting: boolean;
  isSavingToCloud?: boolean;
  sections: DocumentSection[];
  currentSection: DocumentSection | null;
  onScrollToSection: (section: DocumentSection) => void;
  sessionContext: string;
  onContextChange: (value: string) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  trackingEnabled: boolean;
  hasTrackedChanges: boolean;
  onAcceptAll: () => void;
  onRejectAll: () => void;
  getDocumentText: () => string;
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

const FONT_FAMILIES = [
  { name: 'Default', value: '' },
  { name: 'Arial', value: 'Arial, sans-serif' },
  { name: 'Times New Roman', value: 'Times New Roman, serif' },
  { name: 'Georgia', value: 'Georgia, serif' },
  { name: 'Calibri', value: 'Calibri, sans-serif' },
];

const FONT_SIZES = ['9pt', '10pt', '11pt', '12pt', '14pt', '16pt', '18pt', '24pt'];

const HIGHLIGHT_COLORS = [
  { name: 'Yellow', value: '#fef08a' },
  { name: 'Green', value: '#bbf7d0' },
  { name: 'Cyan', value: '#a5f3fc' },
  { name: 'Pink', value: '#fbcfe8' },
  { name: 'None', value: '' },
];

const TEXT_COLORS = [
  { name: 'Black', value: '#000000' },
  { name: 'Red', value: '#dc2626' },
  { name: 'Blue', value: '#2563eb' },
  { name: 'Green', value: '#16a34a' },
];

export function UnifiedToolbar({
  editor,
  documentName,
  documentFormat,
  onUploadClick,
  onExportDocx,
  onExportPdf,
  onSaveToCloud,
  isExporting,
  isSavingToCloud,
  sections,
  currentSection,
  onScrollToSection,
  sessionContext,
  onContextChange,
  viewMode,
  onViewModeChange,
  trackingEnabled,
  hasTrackedChanges,
  onAcceptAll,
  onRejectAll,
  getDocumentText,
  pageSettings,
  onLayoutChange,
  onPageSizeChange,
  onZoomChange,
  onInsertPageBreak,
  configMode,
  onClose,
  saveFlash,
  docxReadOnly,
}: UnifiedToolbarProps) {
  const [saveDropdownOpen, setSaveDropdownOpen] = useState(false);
  const [sectionDropdownOpen, setSectionDropdownOpen] = useState(false);
  const [contextDropdownOpen, setContextDropdownOpen] = useState(false);
  const [fontDropdownOpen, setFontDropdownOpen] = useState(false);
  const [sizeDropdownOpen, setSizeDropdownOpen] = useState(false);
  const [colorDropdownOpen, setColorDropdownOpen] = useState(false);
  const [highlightDropdownOpen, setHighlightDropdownOpen] = useState(false);
  const [changesDropdownOpen, setChangesDropdownOpen] = useState(false);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(`.${styles.uToolbarDropdown}`)) {
        setSaveDropdownOpen(false);
        setSectionDropdownOpen(false);
        setContextDropdownOpen(false);
        setFontDropdownOpen(false);
        setSizeDropdownOpen(false);
        setColorDropdownOpen(false);
        setHighlightDropdownOpen(false);
        setChangesDropdownOpen(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  const closeAllDropdowns = () => {
    setSaveDropdownOpen(false);
    setSectionDropdownOpen(false);
    setContextDropdownOpen(false);
    setFontDropdownOpen(false);
    setSizeDropdownOpen(false);
    setColorDropdownOpen(false);
    setHighlightDropdownOpen(false);
    setChangesDropdownOpen(false);
  };

  const currentFontFamily = editor?.getAttributes('textStyle').fontFamily || '';
  const currentFontName = FONT_FAMILIES.find(f => f.value === currentFontFamily)?.name || 'Font';
  const currentFontSize = editor?.getAttributes('textStyle').fontSize || '11pt';

  if (docxReadOnly && editor) {
    return (
      <div className={styles.unifiedToolbar}>
        <div className={styles.uToolbarRow}>
          {/* Word icon + document name */}
          <svg className={styles.uDocxIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#2b579a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/>
            <text x="7" y="18" fontSize="8" fill="#2b579a" stroke="none" fontWeight="bold">W</text>
          </svg>
          {documentName && (
            <span className={styles.uToolbarDocName} title={documentName}>
              {documentName.length > 30 ? documentName.substring(0, 27) + '...' : documentName}
            </span>
          )}

          <div className={styles.uToolbarSpacer} />

          {/* Read-only notice */}
          <span className={styles.uDocxNotice}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>
            </svg>
            DOCX Preview &middot; Request changes via chat
          </span>

          {/* Export */}
          <button className={styles.uToolbarBtn} onClick={() => onExportDocx(true)} title="Download original DOCX">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
          </button>
        </div>
      </div>
    );
  }

  if (configMode?.type === 'markdown' && editor) {
    return (
      <div className={styles.unifiedToolbar}>
        <div className={styles.uToolbarRow}>
          {onClose && (
            <button
              className={styles.uToolbarBtn}
              onClick={onClose}
              title="Back to workspace"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
              </svg>
            </button>
          )}

          <span className={styles.uConfigLabel} title={configMode.label}>{configMode.label}</span>

          <div className={styles.uToolbarSpacer} />

          <span className={styles.uDocxNotice}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>
            </svg>
            Read-only &middot; ask in chat to revise
          </span>

          <button
            className={styles.uToolbarBtn}
            onClick={() => onExportDocx(true)}
            title="Download markdown"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
            </svg>
          </button>
        </div>
      </div>
    );
  }

  if (configMode && editor) {
    return (
      <div className={styles.unifiedToolbar}>
        <div className={styles.uToolbarRow}>
          {/* Back button — closes config file */}
          {onClose && (
            <button
              className={styles.uToolbarBtn}
              onClick={onClose}
              title="Back to workspace"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
              </svg>
            </button>
          )}

          {/* Config label */}
          <span className={styles.uConfigLabel}>{configMode.label}</span>

          <div className={styles.uToolbarSpacer} />

          {/* Markdown-safe formatting only: Bold, Italic, Lists */}
          <button
            className={`${styles.uToolbarBtn} ${editor.isActive('bold') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleBold().run()}
            title="Bold"
          ><strong>B</strong></button>
          <button
            className={`${styles.uToolbarBtn} ${editor.isActive('italic') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleItalic().run()}
            title="Italic"
          ><em>I</em></button>

          <span className={styles.uToolbarDivider} />

          <button
            className={`${styles.uToolbarBtn} ${editor.isActive('bulletList') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            title="Bullet List"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
              <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
            </svg>
          </button>
          <button
            className={`${styles.uToolbarBtn} ${editor.isActive('orderedList') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            title="Numbered List"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="10" y1="6" x2="21" y2="6"/><line x1="10" y1="12" x2="21" y2="12"/><line x1="10" y1="18" x2="21" y2="18"/>
              <path d="M4 6h1v4"/><path d="M4 10h2"/><path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/>
            </svg>
          </button>

          <span className={styles.uToolbarDivider} />

          {/* Save button */}
          {onSaveToCloud && (
            <button
              className={styles.uConfigSaveBtn}
              onClick={onSaveToCloud}
              disabled={isSavingToCloud}
              title="Save to workspace"
            >{isSavingToCloud ? 'Saving…' : saveFlash ? '✓ Saved' : 'Save'}</button>
          )}

          <span className={styles.uToolbarDivider} />

          {/* Word count */}
          <span className={styles.uToolbarWordCount}>
            {editor.storage.characterCount?.words?.() ?? 0} words
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.unifiedToolbar}>
      {/* === ROW 1: File & Navigation === */}
      <div className={styles.uToolbarRow}>
        <button className={styles.uToolbarBtn} onClick={onUploadClick} title="Open File">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
          </svg>
        </button>

        {documentName && (
          <>
            <span className={styles.uToolbarDocName} title={documentName}>
              {documentName.length > 20 ? documentName.substring(0, 17) + '...' : documentName}
            </span>
            {documentFormat && (
              <span 
                className={styles.uToolbarFormatBadge}
                title={documentFormat === 'docx' 
                  ? 'DOCX-native: AI edits apply as Word tracked changes' 
                  : 'HTML-native: editable in browser, export to DOCX available'}
              >
                {documentFormat === 'docx' ? 'DOCX' : 'HTML'}
              </span>
            )}
          </>
        )}

      {/* Save Dropdown */}
      <div className={styles.uToolbarDropdown}>
        <button
          className={styles.uToolbarBtn}
          onClick={(e) => { e.stopPropagation(); closeAllDropdowns(); setSaveDropdownOpen(!saveDropdownOpen); }}
          disabled={isExporting || !editor?.getText()}
          title="Save"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>
            <polyline points="17 21 17 13 7 13 7 21"/>
            <polyline points="7 3 7 8 15 8"/>
          </svg>
          <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>
        {saveDropdownOpen && (
          <div className={styles.uToolbarMenu} style={{ minWidth: '180px' }}>
            {onSaveToCloud && (
              <>
                <button 
                  onClick={() => { onSaveToCloud(); setSaveDropdownOpen(false); }}
                  disabled={isSavingToCloud}
                  className={styles.uToolbarMenuHighlight}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                  </svg>
                  {isSavingToCloud ? 'Saving...' : 'Save to Cloud'}
                </button>
                <div className={styles.uToolbarMenuDivider} />
              </>
            )}
            <button onClick={() => { onExportDocx(true); setSaveDropdownOpen(false); }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              Download DOCX
            </button>
            <button onClick={() => { onExportPdf(true); setSaveDropdownOpen(false); }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              Download PDF
            </button>
            {hasTrackedChanges && (
              <>
                <div className={styles.uToolbarMenuDivider} />
                <button onClick={() => { onExportPdf(false); setSaveDropdownOpen(false); }}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  Download Redline
                </button>
              </>
            )}
          </div>
        )}
      </div>

      {/* Sections Dropdown */}
      {sections.length > 0 && (
        <div className={styles.uToolbarDropdown}>
          <button
            className={styles.uToolbarBtn}
            onClick={(e) => { e.stopPropagation(); closeAllDropdowns(); setSectionDropdownOpen(!sectionDropdownOpen); }}
            title={`${sections.length} sections`}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
            <span style={{ fontSize: '0.7rem' }}>{currentSection ? `§${currentSection.number}` : `§${sections.length}`}</span>
          </button>
          {sectionDropdownOpen && (
            <div className={styles.uToolbarMenuWide}>
              {sections.map((section) => (
                <button
                  key={section.id}
                  className={currentSection?.id === section.id ? styles.active : ''}
                  onClick={() => { onScrollToSection(section); setSectionDropdownOpen(false); }}
                >
                  <span className={styles.uSectionNum}>{section.number}.</span>
                  <span className={styles.uSectionTitle}>{section.title}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* View Mode Toggle */}
      <div className={styles.uToolbarGroup}>
        <div className={styles.uToolbarViewToggle}>
          <button
            className={viewMode === 'clean' ? styles.active : ''}
            onClick={() => onViewModeChange('clean')}
          >
            Clean
          </button>
          <button
            className={viewMode === 'redline' ? styles.active : ''}
            onClick={() => onViewModeChange('redline')}
          >
            {trackingEnabled ? 'Redline' : 'Track'}
          </button>
        </div>

        {/* Changes Dropdown - only when tracked changes exist */}
        {viewMode === 'redline' && hasTrackedChanges && (
          <div className={styles.uToolbarDropdown}>
            <button
              className={styles.uToolbarBtn}
              onClick={(e) => { e.stopPropagation(); closeAllDropdowns(); setChangesDropdownOpen(!changesDropdownOpen); }}
              title="Accept/Reject Changes"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 11l3 3L22 4"/>
              </svg>
            </button>
            {changesDropdownOpen && (
              <div className={styles.uToolbarMenu}>
                <button onClick={() => { setChangesDropdownOpen(false); setTimeout(onAcceptAll, 10); }}>
                  Accept All
                </button>
                <button onClick={() => { setChangesDropdownOpen(false); setTimeout(onRejectAll, 10); }}>
                  Reject All
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Undo/Redo */}
      {editor && (
        <div className={styles.uToolbarGroup}>
          <button
            className={styles.uToolbarBtn}
            onClick={() => editor.chain().focus().undo().run()}
            disabled={!editor.can().undo()}
            title="Undo"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 7v6h6"/><path d="M3 13a9 9 0 1 0 2.6-6.4L3 9"/>
            </svg>
          </button>
          <button
            className={styles.uToolbarBtn}
            onClick={() => editor.chain().focus().redo().run()}
            disabled={!editor.can().redo()}
            title="Redo"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 7v6h-6"/><path d="M21 13a9 9 0 1 1-2.6-6.4L21 9"/>
            </svg>
          </button>
        </div>
      )}

      {/* Page View Controls */}
      <div className={styles.pageToolbar}>
        {/* Layout Toggle */}
        <div className={styles.layoutToggle}>
          <button
            className={pageSettings.layout === 'scroll' ? styles.active : ''}
            onClick={() => onLayoutChange('scroll')}
            title="Scroll View"
          >
            Scroll
          </button>
          <button
            className={pageSettings.layout === 'page' ? styles.active : ''}
            onClick={() => onLayoutChange('page')}
            title="Page View"
          >
            Page
          </button>
        </div>

        {/* Page Size & Zoom - only in page view */}
        {pageSettings.layout === 'page' && (
          <>
            <div className={styles.pageToolbarDivider} />
            <select
              className={styles.pageSizeSelect}
              value={pageSettings.pageSize}
              onChange={(e) => onPageSizeChange(e.target.value as PageSize)}
              title="Page Size"
            >
              <option value="a4">A4</option>
              <option value="letter">Letter</option>
              <option value="legal">Legal</option>
            </select>
            <select
              className={styles.zoomSelect}
              value={pageSettings.zoom}
              onChange={(e) => onZoomChange(parseInt(e.target.value))}
              title="Zoom"
            >
              <option value="50">50%</option>
              <option value="75">75%</option>
              <option value="100">100%</option>
              <option value="125">125%</option>
              <option value="150">150%</option>
            </select>
            {onInsertPageBreak && (
              <button
                className={styles.uToolbarBtn}
                onClick={onInsertPageBreak}
                title="Insert Page Break"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 12h16M12 4v16"/>
                </svg>
              </button>
            )}
          </>
        )}
      </div>
      </div>

      {/* === ROW 2: Formatting === */}
      {editor && (
        <div className={styles.uToolbarRow}>
          {/* Font Family */}
          <div className={styles.uToolbarDropdown}>
            <button
              className={styles.uToolbarSelectBtn}
              onClick={(e) => { e.stopPropagation(); closeAllDropdowns(); setFontDropdownOpen(!fontDropdownOpen); }}
              title="Font"
            >
              <span>{currentFontName}</span>
              <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>
            {fontDropdownOpen && (
              <div className={styles.uToolbarMenu}>
                {FONT_FAMILIES.map((font) => (
                  <button
                    key={font.value}
                    style={{ fontFamily: font.value || 'inherit' }}
                    onClick={() => {
                      if (font.value) editor.chain().focus().setFontFamily(font.value).run();
                      else editor.chain().focus().unsetFontFamily().run();
                      setFontDropdownOpen(false);
                    }}
                  >
                    {font.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Font Size */}
          <div className={styles.uToolbarDropdown}>
            <button
              className={styles.uToolbarSelectBtnSmall}
              onClick={(e) => { e.stopPropagation(); closeAllDropdowns(); setSizeDropdownOpen(!sizeDropdownOpen); }}
              title="Size"
            >
              <span>{currentFontSize}</span>
              <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>
            {sizeDropdownOpen && (
              <div className={styles.uToolbarMenu}>
                {FONT_SIZES.map((size) => (
                  <button key={size} onClick={() => { editor.chain().focus().setFontSize(size).run(); setSizeDropdownOpen(false); }}>
                    {size}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className={styles.uToolbarDivider} />

          {/* === FORMAT GROUP === */}
          <div className={styles.uToolbarGroup}>
            <button
              className={`${styles.uToolbarBtn} ${editor.isActive('bold') ? styles.active : ''}`}
              onClick={() => editor.chain().focus().toggleBold().run()}
              title="Bold"
            >
              <strong>B</strong>
            </button>
            <button
              className={`${styles.uToolbarBtn} ${editor.isActive('italic') ? styles.active : ''}`}
              onClick={() => editor.chain().focus().toggleItalic().run()}
              title="Italic"
            >
              <em>I</em>
            </button>
            <button
              className={`${styles.uToolbarBtn} ${editor.isActive('underline') ? styles.active : ''}`}
              onClick={() => editor.chain().focus().toggleUnderline().run()}
              title="Underline"
            >
              <span style={{ textDecoration: 'underline' }}>U</span>
            </button>
            <button
              className={`${styles.uToolbarBtn} ${editor.isActive('strike') ? styles.active : ''}`}
              onClick={() => editor.chain().focus().toggleStrike().run()}
              title="Strikethrough"
            >
              <span style={{ textDecoration: 'line-through' }}>S</span>
            </button>

            {/* Text Color */}
            <div className={styles.uToolbarDropdown}>
              <button
                className={styles.uToolbarBtn}
                onClick={(e) => { e.stopPropagation(); closeAllDropdowns(); setColorDropdownOpen(!colorDropdownOpen); }}
                title="Text Color"
              >
                <span style={{ borderBottom: `2px solid ${editor.getAttributes('textStyle').color || '#000'}` }}>A</span>
              </button>
              {colorDropdownOpen && (
                <div className={styles.uToolbarColorGrid}>
                  {TEXT_COLORS.map((color) => (
                    <button
                      key={color.value}
                      style={{ backgroundColor: color.value }}
                      title={color.name}
                      onClick={() => { editor.chain().focus().setColor(color.value).run(); setColorDropdownOpen(false); }}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Highlight */}
            <div className={styles.uToolbarDropdown}>
              <button
                className={styles.uToolbarBtn}
                onClick={(e) => { e.stopPropagation(); closeAllDropdowns(); setHighlightDropdownOpen(!highlightDropdownOpen); }}
                title="Highlight"
              >
                <span style={{ backgroundColor: '#fef08a', padding: '0 3px', fontSize: '12px' }}>ab</span>
              </button>
              {highlightDropdownOpen && (
                <div className={styles.uToolbarColorGrid}>
                  {HIGHLIGHT_COLORS.map((color) => (
                    <button
                      key={color.value || 'none'}
                      style={{ backgroundColor: color.value || '#fff', border: color.value ? 'none' : '1px solid #ccc' }}
                      title={color.name}
                      onClick={() => {
                        if (color.value) editor.chain().focus().toggleHighlight({ color: color.value }).run();
                        else editor.chain().focus().unsetHighlight().run();
                        setHighlightDropdownOpen(false);
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* === PARAGRAPH GROUP === */}
          <div className={styles.uToolbarGroup}>
            <button
              className={`${styles.uToolbarBtn} ${editor.isActive({ textAlign: 'left' }) ? styles.active : ''}`}
              onClick={() => editor.chain().focus().setTextAlign('left').run()}
              title="Align Left"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="15" y2="12"/><line x1="3" y1="18" x2="18" y2="18"/>
              </svg>
            </button>
            <button
              className={`${styles.uToolbarBtn} ${editor.isActive({ textAlign: 'center' }) ? styles.active : ''}`}
              onClick={() => editor.chain().focus().setTextAlign('center').run()}
              title="Center"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="6" x2="21" y2="6"/><line x1="6" y1="12" x2="18" y2="12"/><line x1="4" y1="18" x2="20" y2="18"/>
              </svg>
            </button>
            <button
              className={`${styles.uToolbarBtn} ${editor.isActive({ textAlign: 'right' }) ? styles.active : ''}`}
              onClick={() => editor.chain().focus().setTextAlign('right').run()}
              title="Align Right"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="6" x2="21" y2="6"/><line x1="9" y1="12" x2="21" y2="12"/><line x1="6" y1="18" x2="21" y2="18"/>
              </svg>
            </button>
            <button
              className={`${styles.uToolbarBtn} ${editor.isActive('bulletList') ? styles.active : ''}`}
              onClick={() => editor.chain().focus().toggleBulletList().run()}
              title="Bullets"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="4" cy="6" r="1.5" fill="currentColor"/><circle cx="4" cy="12" r="1.5" fill="currentColor"/>
                <line x1="9" y1="6" x2="21" y2="6"/><line x1="9" y1="12" x2="21" y2="12"/>
              </svg>
            </button>
            <button
              className={`${styles.uToolbarBtn} ${editor.isActive('orderedList') ? styles.active : ''}`}
              onClick={() => editor.chain().focus().toggleOrderedList().run()}
              title="Numbering"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <text x="2" y="8" fontSize="7" fill="currentColor" stroke="none">1</text>
                <text x="2" y="15" fontSize="7" fill="currentColor" stroke="none">2</text>
                <line x1="9" y1="6" x2="21" y2="6"/><line x1="9" y1="12" x2="21" y2="12"/>
              </svg>
            </button>
          </div>

          {/* Word count */}
          {(() => {
            const text = getDocumentText();
            const charCount = text.length;
            const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0;
            const wordDisplay = wordCount >= 1000 
              ? `~${(wordCount / 1000).toFixed(1)}K words` 
              : `${wordCount} words`;
            return (
              <span 
                className={styles.uToolbarCharCount}
                title={`${wordCount.toLocaleString()} words | ${charCount.toLocaleString()} characters`}
              >
                {wordDisplay}
              </span>
            );
          })()}
        </div>
      )}
    </div>
  );
}
