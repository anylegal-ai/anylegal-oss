'use client';

import React, { useEffect, useCallback } from 'react';
import { EditorContent } from '@tiptap/react';
import { usePlaybookEditor } from '../hooks/usePlaybookEditor';
import styles from './PlaybookEditor.module.css';

export interface PlaybookEditorProps {
  isOpen: boolean;
  onClose: () => void;
  onSave?: () => void;
}

export function PlaybookEditor({ isOpen, onClose, onSave }: PlaybookEditorProps) {
  const {
    editor,
    state,
    loadPlaybook,
    savePlaybook,
    resetPlaybook,
    getMarkdown,
  } = usePlaybookEditor();

  useEffect(() => {
    if (isOpen && editor) {
      loadPlaybook();
    }
  }, [isOpen, editor, loadPlaybook]);

  const handleSave = useCallback(async () => {
    const success = await savePlaybook();
    if (success) {
      onSave?.();
    }
  }, [savePlaybook, onSave]);

  const handleReset = useCallback(async () => {
    if (window.confirm('Reset playbook to default? Your custom rules will be lost.')) {
      await resetPlaybook();
    }
  }, [resetPlaybook]);

  const handleClose = useCallback(() => {
    if (state.hasChanges) {
      if (window.confirm('You have unsaved changes. Discard them?')) {
        onClose();
      }
    } else {
      onClose();
    }
  }, [state.hasChanges, onClose]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }

      if (e.key === 'Escape') {
        handleClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, handleSave, handleClose]);

  if (!isOpen) return null;

  return (
    <div className={styles.overlay} onClick={handleClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h2 className={styles.title}>Edit Playbook</h2>
            {state.hasChanges && (
              <span className={styles.unsavedBadge}>Unsaved changes</span>
            )}
          </div>
          <div className={styles.headerRight}>
            {state.lastSaved && (
              <span className={styles.lastSaved}>
                Last saved: {state.lastSaved.toLocaleTimeString()}
              </span>
            )}
            <button
              className={styles.closeButton}
              onClick={handleClose}
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        {/* Toolbar */}
        <div className={styles.toolbar}>
          <div className={styles.toolbarLeft}>
            <button
              className={styles.toolbarButton}
              onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}
              disabled={!editor}
              title="Heading 2 (Section)"
            >
              H2
            </button>
            <button
              className={styles.toolbarButton}
              onClick={() => editor?.chain().focus().toggleHeading({ level: 3 }).run()}
              disabled={!editor}
              title="Heading 3 (Position)"
            >
              H3
            </button>
            <span className={styles.toolbarDivider} />
            <button
              className={styles.toolbarButton}
              onClick={() => editor?.chain().focus().toggleBulletList().run()}
              disabled={!editor}
              title="Bullet List"
            >
              • List
            </button>
            <button
              className={styles.toolbarButton}
              onClick={() => editor?.chain().focus().toggleBold().run()}
              disabled={!editor}
              title="Bold"
            >
              B
            </button>
            <span className={styles.toolbarDivider} />
            <button
              className={styles.toolbarButton}
              onClick={() => editor?.chain().focus().setHorizontalRule().run()}
              disabled={!editor}
              title="Horizontal Rule (Section Divider)"
            >
              —
            </button>
          </div>
          <div className={styles.toolbarRight}>
            <button
              className={`${styles.toolbarButton} ${styles.resetButton}`}
              onClick={handleReset}
              disabled={state.isLoading || state.isSaving}
              title="Reset to Default"
            >
              Reset
            </button>
          </div>
        </div>

        {/* Error/Warning display */}
        {state.error && (
          <div className={styles.errorBanner}>
            {state.error}
          </div>
        )}

        {state.validationIssues.length > 0 && (
          <div className={styles.warningBanner}>
            <strong>Validation Issues:</strong>
            <ul>
              {state.validationIssues.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Editor */}
        <div className={styles.editorContainer}>
          {state.isLoading ? (
            <div className={styles.loading}>Loading playbook...</div>
          ) : (
            <EditorContent editor={editor} className={styles.editor} />
          )}
        </div>

        {/* Help text */}
        <div className={styles.helpText}>
          <p>
            <strong>Structure:</strong> Use H2 (##) for clause types, H3 (###) for positions 
            (Acceptable, Requires Review, Unacceptable), and bullet lists for rules.
          </p>
        </div>

        {/* Footer */}
        <div className={styles.footer}>
          <button
            className={styles.cancelButton}
            onClick={handleClose}
            disabled={state.isSaving}
          >
            Cancel
          </button>
          <button
            className={styles.saveButton}
            onClick={handleSave}
            disabled={state.isSaving || state.isLoading || !state.hasChanges}
          >
            {state.isSaving ? 'Saving...' : 'Save Playbook'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default PlaybookEditor;
