import React, { useState, useEffect, useRef } from 'react';
import { Editor } from '@tiptap/react';
import styles from '../workspace.module.css';

interface WordToolbarProps {
  editor: Editor | null;
}

const FONT_FAMILIES = [
  { name: 'Default', value: '' },
  { name: 'Arial', value: 'Arial, sans-serif' },
  { name: 'Times New Roman', value: 'Times New Roman, serif' },
  { name: 'Georgia', value: 'Georgia, serif' },
  { name: 'Verdana', value: 'Verdana, sans-serif' },
  { name: 'Courier New', value: 'Courier New, monospace' },
  { name: 'Calibri', value: 'Calibri, sans-serif' },
];

const FONT_SIZES = [
  '8pt', '9pt', '10pt', '11pt', '12pt', '14pt', '16pt', '18pt', '20pt', '24pt', '28pt', '36pt', '48pt', '72pt'
];

const HIGHLIGHT_COLORS = [
  { name: 'Yellow', value: '#fef08a' },
  { name: 'Green', value: '#bbf7d0' },
  { name: 'Cyan', value: '#a5f3fc' },
  { name: 'Pink', value: '#fbcfe8' },
  { name: 'Orange', value: '#fed7aa' },
  { name: 'None', value: '' },
];

const TEXT_COLORS = [
  { name: 'Black', value: '#000000' },
  { name: 'Dark Gray', value: '#4b5563' },
  { name: 'Red', value: '#dc2626' },
  { name: 'Blue', value: '#2563eb' },
  { name: 'Green', value: '#16a34a' },
  { name: 'Orange', value: '#ea580c' },
  { name: 'Purple', value: '#9333ea' },
];

export function WordToolbar({ editor }: WordToolbarProps) {
  const [fontDropdownOpen, setFontDropdownOpen] = useState(false);
  const [sizeDropdownOpen, setSizeDropdownOpen] = useState(false);
  const [colorDropdownOpen, setColorDropdownOpen] = useState(false);
  const [highlightDropdownOpen, setHighlightDropdownOpen] = useState(false);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest(`.${styles.wordToolbarDropdown}`)) {
        setFontDropdownOpen(false);
        setSizeDropdownOpen(false);
        setColorDropdownOpen(false);
        setHighlightDropdownOpen(false);
      }
    };

    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, []);

  if (!editor) return null;

  const currentFontFamily = editor.getAttributes('textStyle').fontFamily || '';
  const currentFontName = FONT_FAMILIES.find(f => f.value === currentFontFamily)?.name || 'Font';

  const currentFontSize = editor.getAttributes('textStyle').fontSize || '11pt';

  return (
    <div className={styles.wordToolbar}>
      {/* Font Group */}
      <div className={styles.wordToolbarGroup}>
        <div className={styles.wordToolbarGroupLabel}>Font</div>
        <div className={styles.wordToolbarGroupContent}>
          {/* Font Family Dropdown */}
          <div className={styles.wordToolbarDropdown}>
            <button
              className={styles.wordToolbarSelect}
              onClick={(e) => { e.stopPropagation(); setFontDropdownOpen(!fontDropdownOpen); setSizeDropdownOpen(false); }}
              title="Font Family"
            >
              <span className={styles.selectText}>{currentFontName}</span>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>
            {fontDropdownOpen && (
              <div className={styles.wordToolbarDropdownMenu}>
                {FONT_FAMILIES.map((font) => (
                  <button
                    key={font.value}
                    className={styles.wordToolbarDropdownItem}
                    style={{ fontFamily: font.value || 'inherit' }}
                    onClick={() => {
                      if (font.value) {
                        editor.chain().focus().setFontFamily(font.value).run();
                      } else {
                        editor.chain().focus().unsetFontFamily().run();
                      }
                      setFontDropdownOpen(false);
                    }}
                  >
                    {font.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Font Size Dropdown */}
          <div className={styles.wordToolbarDropdown}>
            <button
              className={styles.wordToolbarSelectSmall}
              onClick={(e) => { e.stopPropagation(); setSizeDropdownOpen(!sizeDropdownOpen); setFontDropdownOpen(false); }}
              title="Font Size"
            >
              <span className={styles.selectText}>{currentFontSize}</span>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>
            {sizeDropdownOpen && (
              <div className={styles.wordToolbarDropdownMenu}>
                {FONT_SIZES.map((size) => (
                  <button
                    key={size}
                    className={styles.wordToolbarDropdownItem}
                    onClick={() => {
                      editor.chain().focus().setFontSize(size).run();
                      setSizeDropdownOpen(false);
                    }}
                  >
                    {size}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className={styles.wordToolbarDivider} />

      {/* Formatting Group */}
      <div className={styles.wordToolbarGroup}>
        <div className={styles.wordToolbarGroupLabel}>Format</div>
        <div className={styles.wordToolbarGroupContent}>
          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive('bold') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleBold().run()}
            title="Bold (Ctrl+B)"
          >
            <strong>B</strong>
          </button>
          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive('italic') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleItalic().run()}
            title="Italic (Ctrl+I)"
          >
            <em>I</em>
          </button>
          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive('underline') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleUnderline().run()}
            title="Underline (Ctrl+U)"
          >
            <span style={{ textDecoration: 'underline' }}>U</span>
          </button>
          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive('strike') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleStrike().run()}
            title="Strikethrough"
          >
            <span style={{ textDecoration: 'line-through' }}>S</span>
          </button>
          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive('subscript') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleSubscript().run()}
            title="Subscript"
          >
            X<sub>2</sub>
          </button>
          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive('superscript') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleSuperscript().run()}
            title="Superscript"
          >
            X<sup>2</sup>
          </button>

          {/* Text Color */}
          <div className={styles.wordToolbarDropdown}>
            <button
              className={styles.wordToolbarBtn}
              onClick={(e) => { e.stopPropagation(); setColorDropdownOpen(!colorDropdownOpen); setHighlightDropdownOpen(false); }}
              title="Text Color"
            >
              <span style={{ borderBottom: `3px solid ${editor.getAttributes('textStyle').color || '#000'}` }}>A</span>
            </button>
            {colorDropdownOpen && (
              <div className={styles.wordToolbarColorMenu}>
                {TEXT_COLORS.map((color) => (
                  <button
                    key={color.value}
                    className={styles.wordToolbarColorBtn}
                    style={{ backgroundColor: color.value }}
                    title={color.name}
                    onClick={() => {
                      editor.chain().focus().setColor(color.value).run();
                      setColorDropdownOpen(false);
                    }}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Highlight */}
          <div className={styles.wordToolbarDropdown}>
            <button
              className={styles.wordToolbarBtn}
              onClick={(e) => { e.stopPropagation(); setHighlightDropdownOpen(!highlightDropdownOpen); setColorDropdownOpen(false); }}
              title="Highlight"
            >
              <span style={{ backgroundColor: editor.getAttributes('highlight').color || '#fef08a', padding: '0 2px' }}>ab</span>
            </button>
            {highlightDropdownOpen && (
              <div className={styles.wordToolbarColorMenu}>
                {HIGHLIGHT_COLORS.map((color) => (
                  <button
                    key={color.value || 'none'}
                    className={styles.wordToolbarColorBtn}
                    style={{ backgroundColor: color.value || '#fff', border: color.value ? 'none' : '1px solid #ccc' }}
                    title={color.name}
                    onClick={() => {
                      if (color.value) {
                        editor.chain().focus().toggleHighlight({ color: color.value }).run();
                      } else {
                        editor.chain().focus().unsetHighlight().run();
                      }
                      setHighlightDropdownOpen(false);
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className={styles.wordToolbarDivider} />

      {/* Paragraph Group */}
      <div className={styles.wordToolbarGroup}>
        <div className={styles.wordToolbarGroupLabel}>Paragraph</div>
        <div className={styles.wordToolbarGroupContent}>
          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive({ textAlign: 'left' }) ? styles.active : ''}`}
            onClick={() => editor.chain().focus().setTextAlign('left').run()}
            title="Align Left"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="3" y1="12" x2="15" y2="12"/>
              <line x1="3" y1="18" x2="18" y2="18"/>
            </svg>
          </button>
          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive({ textAlign: 'center' }) ? styles.active : ''}`}
            onClick={() => editor.chain().focus().setTextAlign('center').run()}
            title="Align Center"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="6" y1="12" x2="18" y2="12"/>
              <line x1="4" y1="18" x2="20" y2="18"/>
            </svg>
          </button>
          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive({ textAlign: 'right' }) ? styles.active : ''}`}
            onClick={() => editor.chain().focus().setTextAlign('right').run()}
            title="Align Right"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="9" y1="12" x2="21" y2="12"/>
              <line x1="6" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive({ textAlign: 'justify' }) ? styles.active : ''}`}
            onClick={() => editor.chain().focus().setTextAlign('justify').run()}
            title="Justify"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="6" x2="21" y2="6"/>
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>

          <div className={styles.wordToolbarSeparator} />

          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive('bulletList') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            title="Bullet List"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="4" cy="6" r="1.5" fill="currentColor"/>
              <circle cx="4" cy="12" r="1.5" fill="currentColor"/>
              <circle cx="4" cy="18" r="1.5" fill="currentColor"/>
              <line x1="9" y1="6" x2="21" y2="6"/>
              <line x1="9" y1="12" x2="21" y2="12"/>
              <line x1="9" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
          <button
            className={`${styles.wordToolbarBtn} ${editor.isActive('orderedList') ? styles.active : ''}`}
            onClick={() => editor.chain().focus().toggleOrderedList().run()}
            title="Numbered List"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <text x="2" y="8" fontSize="7" fill="currentColor" stroke="none">1</text>
              <text x="2" y="14" fontSize="7" fill="currentColor" stroke="none">2</text>
              <text x="2" y="20" fontSize="7" fill="currentColor" stroke="none">3</text>
              <line x1="9" y1="6" x2="21" y2="6"/>
              <line x1="9" y1="12" x2="21" y2="12"/>
              <line x1="9" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
        </div>
      </div>

      <div className={styles.wordToolbarDivider} />

      {/* Undo/Redo */}
      <div className={styles.wordToolbarGroup}>
        <div className={styles.wordToolbarGroupLabel}>Edit</div>
        <div className={styles.wordToolbarGroupContent}>
          <button
            className={styles.wordToolbarBtn}
            onClick={() => editor.chain().focus().undo().run()}
            disabled={!editor.can().undo()}
            title="Undo (Ctrl+Z)"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 7v6h6"/>
              <path d="M3 13a9 9 0 1 0 2.6-6.4L3 9"/>
            </svg>
          </button>
          <button
            className={styles.wordToolbarBtn}
            onClick={() => editor.chain().focus().redo().run()}
            disabled={!editor.can().redo()}
            title="Redo (Ctrl+Y)"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 7v6h-6"/>
              <path d="M21 13a9 9 0 1 1-2.6-6.4L21 9"/>
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
