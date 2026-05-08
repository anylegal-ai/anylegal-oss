import { useRef, useEffect, useCallback, useState } from 'react';
import { useEditor } from '@tiptap/react';
import { EditorState } from '@tiptap/pm/state';
import StarterKit from '@tiptap/starter-kit';
import Highlight from '@tiptap/extension-highlight';
import Placeholder from '@tiptap/extension-placeholder';
import { TextStyle } from '@tiptap/extension-text-style';
import { Color } from '@tiptap/extension-color';
import FontFamily from '@tiptap/extension-font-family';
import TextAlign from '@tiptap/extension-text-align';
import Subscript from '@tiptap/extension-subscript';
import Superscript from '@tiptap/extension-superscript';
import { Table } from '@tiptap/extension-table';
import { TableRow } from '@tiptap/extension-table-row';
import { TableCell } from '@tiptap/extension-table-cell';
import { TableHeader } from '@tiptap/extension-table-header';
import { FontSize } from '../extensions/fontSize';
import { PageBreak } from '../extensions/pageBreak';
import { ClauseNode, startsWithClauseNumber } from '../extensions/clauseNode';
import { InsertionMark, DeletionMark, TrackChangesExtension, setSkipTracking } from '../trackChangesExtension';
import { convertDocumentToMarkdown } from '../services/documentApi';
import { markdownToHtmlAsync } from '../utils/markdownUtils';
import type { ViewMode, ConfirmModalState } from '../types/workspace';
import styles from '../workspace.module.css';

export interface SelectionPosition {
  top: number;
  left: number;
  bottom: number;
  width: number;
}

interface UseEditorSetupOptions {
  onSelectionChange: (text: string, position: SelectionPosition | null) => void;
  onCursorPlaced: () => void;
  onDocumentLengthChange: (length: number) => void;
  viewMode: ViewMode;
  trackingEnabled: boolean;
  setError: (error: string | null) => void;
  setDocumentName: (name: string | null) => void;
  showConfirmModal: (message: string, onConfirm: () => void) => void;
  hideConfirmModal: () => void;
  onDocumentLoaded?: () => void; // Called after document is loaded to reset tracking state
}

export function useEditorSetup({
  onSelectionChange,
  onCursorPlaced,
  onDocumentLengthChange,
  viewMode,
  trackingEnabled,
  setError,
  setDocumentName,
  showConfirmModal,
  hideConfirmModal,
  onDocumentLoaded,
}: UseEditorSetupOptions) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const viewModeRef = useRef(viewMode);
  const [isLoadingFile, setIsLoadingFile] = useState(false);

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      Highlight.configure({ multicolor: true }),
      TextStyle,
      Color,
      FontFamily,
      FontSize,
      TextAlign.configure({
        types: ['heading', 'paragraph', 'clause'],
      }),
      Subscript,
      Superscript,
      Table.configure({
        resizable: false,
        HTMLAttributes: {
          class: 'document-table',
        },
      }),
      TableRow,
      TableCell,
      TableHeader,
      Placeholder.configure({
        placeholder: 'Paste your contract text here, or open a document...',
      }),
      InsertionMark,
      DeletionMark,
      TrackChangesExtension.configure({
        enabled: false, // Start disabled - user must enable after loading document
      }),
      PageBreak,
      ClauseNode,
    ],
    content: '',
    onSelectionUpdate: ({ editor }) => {
      const { from, to } = editor.state.selection;
      if (from !== to) {
        const text = editor.state.doc.textBetween(from, to, ' ');

        let position: SelectionPosition | null = null;
        const domSelection = window.getSelection();
        if (domSelection && domSelection.rangeCount > 0) {
          const range = domSelection.getRangeAt(0);
          const rect = range.getBoundingClientRect();
          position = {
            top: rect.top,
            left: rect.left,
            bottom: rect.bottom,
            width: rect.width,
          };
        }

        onSelectionChange(text, position);
      } else {
        onSelectionChange('', null);
      }
      onCursorPlaced();
    },
    onFocus: () => {
      onCursorPlaced();
    },
    onUpdate: ({ editor }) => {
      onDocumentLengthChange(editor.getText().length);
    },
    editorProps: {
      attributes: {
        class: styles.editorContent,
      },
    },
  });

  useEffect(() => {
    viewModeRef.current = viewMode;
    if (editor) {
      const shouldTrack = viewMode === 'redline' && trackingEnabled;
      editor.commands.setTrackChangesEnabled(shouldTrack);
    }
  }, [viewMode, trackingEnabled, editor]);

  const getDocumentText = useCallback(() => {
    return editor?.getText() || '';
  }, [editor]);

  const hasTrackedChanges = useCallback(() => {
    if (!editor) return false;
    let found = false;
    editor.state.doc.descendants((node) => {
      if (node.marks.some(m => m.type.name === 'insertion' || m.type.name === 'deletion')) {
        found = true;
        return false; // Stop traversal
      }
    });
    return found;
  }, [editor]);

  const convertParagraphsToClauses = useCallback(() => {
    if (!editor) return;

    const { state, view } = editor;
    const clauseType = state.schema.nodes.clause;

    if (!clauseType) {
      console.warn('ClauseNode type not found in schema');
      return;
    }

    const nodesToConvert: { pos: number; node: any; clauseNum: string; parts: number[]; level: number }[] = [];

    state.doc.forEach((node, offset) => {
      if (node.type.name === 'paragraph') {
        const text = node.textContent;
        const clauseCheck = startsWithClauseNumber(text);

        if (clauseCheck.match && clauseCheck.number && clauseCheck.parts && clauseCheck.level) {
          nodesToConvert.push({
            pos: offset,
            node,
            clauseNum: clauseCheck.number,
            parts: clauseCheck.parts,
            level: clauseCheck.level,
          });
        }
      }
    });

    if (nodesToConvert.length === 0) {
      console.log('No paragraphs to convert to ClauseNodes');
      return;
    }

    console.log(`Converting ${nodesToConvert.length} paragraphs to ClauseNodes`);

    let tr = state.tr;

    for (let i = nodesToConvert.length - 1; i >= 0; i--) {
      const { pos, node, clauseNum, parts, level } = nodesToConvert[i];

      const clauseNode = clauseType.create(
        { number: clauseNum, parts, level },
        node.content,
        node.marks
      );

      tr = tr.replaceWith(pos, pos + node.nodeSize, clauseNode);
    }

    tr.setMeta('addToHistory', false);
    tr.setMeta('skipTracking', true);

    view.dispatch(tr);
    console.log(`Successfully converted ${nodesToConvert.length} paragraphs to ClauseNodes`);
  }, [editor]);

  const handleUploadClick = useCallback(() => {
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
      fileInputRef.current.click();
    }
  }, []);

  const processUploadedFile = useCallback(async (file: File) => {
    if (!editor) return;

    setError(null);
    setDocumentName(file.name);
    setIsLoadingFile(true);

    try {
      const markdown = await convertDocumentToMarkdown(file);
      const html = await markdownToHtmlAsync(markdown);

      // CRITICAL: Fully disable track changes during content load
      setSkipTracking(true);
      editor.commands.setTrackChangesEnabled(false);

      editor.commands.setContent(html as string);

      onDocumentLoaded?.();

      setTimeout(() => {
        setSkipTracking(false);

        convertParagraphsToClauses();

        if (editor && editor.view) {
          const { state, view } = editor;
          const newState = EditorState.create({
            doc: state.doc,
            plugins: state.plugins,
          });
          view.updateState(newState);
        }
      }, 100);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to process document');
      setDocumentName(null);
    } finally {
      setIsLoadingFile(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }, [editor, setError, setDocumentName, onDocumentLoaded, convertParagraphsToClauses]);

  const handleFileUpload = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (fileInputRef.current) fileInputRef.current.value = '';

    const allowedTypes = ['.docx', '.doc', '.txt', '.pdf'];
    const extension = '.' + file.name.split('.').pop()?.toLowerCase();

    if (!allowedTypes.includes(extension)) {
      setError(`Unsupported file type. Supported: ${allowedTypes.join(', ')}`);
      return;
    }

    const existingContent = editor?.getText()?.trim() || '';
    if (existingContent.length > 0) {
      showConfirmModal('Replace current document with the new file?', () => {
        hideConfirmModal();
        processUploadedFile(file);
      });
      return;
    }

    processUploadedFile(file);
  }, [editor, setError, showConfirmModal, hideConfirmModal, processUploadedFile]);

  return {
    editor,
    fileInputRef,
    viewModeRef,
    getDocumentText,
    hasTrackedChanges,
    handleUploadClick,
    handleFileUpload,
    processUploadedFile,
    isLoadingFile,
    convertParagraphsToClauses, // Utility to convert paragraphs to ClauseNodes
  };
}
