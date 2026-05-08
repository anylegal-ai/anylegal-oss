import { Mark, Extension, mergeAttributes } from '@tiptap/core';
import { Plugin, PluginKey, TextSelection } from '@tiptap/pm/state';

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    trackChanges: {
      setTrackChangesEnabled: (enabled: boolean) => ReturnType;
      enableTrackingImmediate: () => ReturnType;
      acceptAllChanges: () => ReturnType;
      rejectAllChanges: () => ReturnType;
    };
  }
}

export const InsertionMark = Mark.create({
  name: 'insertion',

  addAttributes() {
    return {
      author: {
        default: 'user',
      },
      timestamp: {
        default: () => new Date().toISOString(),
      },
      source: {
        default: 'user', // 'user' for local edits, 'docx' for imported Word revisions
      },
    };
  },

  parseHTML() {
    return [
      { tag: 'span[data-insertion]' },
      {
        tag: 'ins[data-docx-revision]',
        getAttrs: (dom: HTMLElement) => ({
          author: dom.getAttribute('data-author') || 'Word',
          timestamp: dom.getAttribute('data-date') || new Date().toISOString(),
          source: 'docx',
        }),
      },
      {
        tag: 'ins[cite]',
        getAttrs: (dom: HTMLElement) => ({
          author: 'Word',
          timestamp: dom.getAttribute('cite') || new Date().toISOString(),
          source: 'docx',
        }),
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return ['span', mergeAttributes(HTMLAttributes, { 'data-insertion': 'true', class: 'track-insertion' }), 0];
  },
});

export const DeletionMark = Mark.create({
  name: 'deletion',

  excludes: 'insertion', // Deletion and insertion are mutually exclusive

  addAttributes() {
    return {
      author: {
        default: 'user',
      },
      timestamp: {
        default: () => new Date().toISOString(),
      },
      source: {
        default: 'user', // 'user' for local edits, 'docx' for imported Word revisions
      },
    };
  },

  parseHTML() {
    return [
      { tag: 'span[data-deletion]' },
      {
        tag: 'del[data-docx-revision]',
        getAttrs: (dom: HTMLElement) => ({
          author: dom.getAttribute('data-author') || 'Word',
          timestamp: dom.getAttribute('data-date') || new Date().toISOString(),
          source: 'docx',
        }),
      },
      {
        tag: 'del[cite]',
        getAttrs: (dom: HTMLElement) => ({
          author: 'Word',
          timestamp: dom.getAttribute('cite') || new Date().toISOString(),
          source: 'docx',
        }),
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return ['span', mergeAttributes(HTMLAttributes, { 'data-deletion': 'true', class: 'track-deletion' }), 0];
  },
});

const trackChangesPluginKey = new PluginKey('trackChanges');

let skipTrackingFlag = false;
let trackChangesEnabled = false;
let insertionTrackingActive = false;

export function setSkipTracking(skip: boolean) {
  skipTrackingFlag = skip;
}

export interface TrackChangesOptions {
  enabled: boolean;
  onStatusChange?: (enabled: boolean) => void;
}

export const TrackChangesExtension = Extension.create<TrackChangesOptions>({
  name: 'trackChanges',

  addOptions() {
    return {
      enabled: true,
      onStatusChange: undefined,
    };
  },

  addCommands() {
    return {
      setTrackChangesEnabled: (enabled: boolean) => () => {
        trackChangesEnabled = enabled;
        this.options.enabled = enabled;

        if (enabled) {
          insertionTrackingActive = false;
          setTimeout(() => {
            insertionTrackingActive = true;
          }, 300);
        } else {
          insertionTrackingActive = false;
        }
        if (this.options.onStatusChange) {
          this.options.onStatusChange(enabled);
        }
        return true;
      },

      enableTrackingImmediate: () => () => {
        trackChangesEnabled = true;
        insertionTrackingActive = true;
        this.options.enabled = true;
        return true;
      },

      acceptAllChanges: () => ({ editor }) => {

        setTimeout(() => {
          try {
            const view = editor.view;
            const state = view.state;
            const deletionMark = state.schema.marks.deletion;
            const insertionMark = state.schema.marks.insertion;

            if (!insertionMark && !deletionMark) return;

            const rangesToDelete: { from: number; to: number }[] = [];
            if (deletionMark) {
              state.doc.descendants((node, pos) => {
                if (node.isText && node.marks.some(m => m.type === deletionMark)) {
                  rangesToDelete.push({ from: pos, to: pos + node.nodeSize });
                }
              });
            }

            const tr = view.state.tr;

            rangesToDelete.sort((a, b) => b.from - a.from).forEach(range => {
              tr.delete(range.from, range.to);
            });

            const newDocSize = tr.doc.content.size;
            if (newDocSize > 0) {
              if (insertionMark) tr.removeMark(0, newDocSize, insertionMark);
              if (deletionMark) tr.removeMark(0, newDocSize, deletionMark);
            }

            tr.setMeta('skipTracking', true);
            view.dispatch(tr);
          } catch (e) {
            console.error('acceptAllChanges error:', e);
          }
        }, 0);

        return true;
      },

      rejectAllChanges: () => ({ editor }) => {

        setTimeout(() => {
          try {
            const view = editor.view;
            const state = view.state;
            const insertionMark = state.schema.marks.insertion;
            const deletionMark = state.schema.marks.deletion;

            if (!insertionMark && !deletionMark) return;

            const rangesToDelete: { from: number; to: number }[] = [];
            if (insertionMark) {
              state.doc.descendants((node, pos) => {
                if (node.isText && node.marks.some(m => m.type === insertionMark)) {
                  rangesToDelete.push({ from: pos, to: pos + node.nodeSize });
                }
              });
            }

            const tr = view.state.tr;

            rangesToDelete.sort((a, b) => b.from - a.from).forEach(range => {
              tr.delete(range.from, range.to);
            });

            const newDocSize = tr.doc.content.size;
            if (newDocSize > 0) {
              if (insertionMark) tr.removeMark(0, newDocSize, insertionMark);
              if (deletionMark) tr.removeMark(0, newDocSize, deletionMark);
            }

            tr.setMeta('skipTracking', true);
            view.dispatch(tr);
          } catch (e) {
            console.error('rejectAllChanges error:', e);
          }
        }, 0);

        return true;
      },
    };
  },

  addProseMirrorPlugins() {
    const extension = this;

    return [
      new Plugin({
        key: trackChangesPluginKey,

        appendTransaction(transactions, oldState, newState) {
          if (skipTrackingFlag) return null;
          if (!trackChangesEnabled) return null;
          if (!insertionTrackingActive) return null;

          let hasInsert = false;
          transactions.forEach(tr => {
            if (tr.getMeta('skipTracking')) return;
            if (tr.getMeta('trackChangesApplied')) return;

            if (tr.docChanged) {
              tr.steps.forEach((step: any) => {
                if (step.slice && step.slice.content.size > 0) {
                  hasInsert = true;
                }
              });
            }
          });

          if (!hasInsert) return null;

          const tr = newState.tr;
          let modified = false;

          transactions.forEach(transaction => {
            if (transaction.getMeta('skipTracking')) return;
            if (transaction.getMeta('trackChangesApplied')) return;
            if (!transaction.docChanged) return;

            transaction.steps.forEach((step: any, index: number) => {
              if (step.slice && step.slice.content.size > 0) {
                const map = transaction.mapping.maps[index];
                if (map) {
                  map.forEach((oldStart: number, oldEnd: number, newStart: number, newEnd: number) => {
                    if (newEnd > newStart) {
                      const insertionMark = newState.schema.marks.insertion.create({ author: 'user' });
                      tr.addMark(newStart, newEnd, insertionMark);
                      modified = true;
                    }
                  });
                }
              }
            });
          });

          if (modified) {
            tr.setMeta('trackChangesApplied', true);
            return tr;
          }

          return null;
        },

        props: {

          handleKeyDown(view, event) {
            if (!trackChangesEnabled) return false;

            const { state } = view;
            const { selection } = state;
            const { from, to, empty } = selection;

            if (event.key === 'Backspace') {
              if (empty) {
                if (from === 0) return false; // Nothing to delete at start

                const $from = state.doc.resolve(from);
                const beforePos = from - 1;

                const nodeBeforeCursor = state.doc.nodeAt(beforePos);
                if (nodeBeforeCursor) {
                  const hasDeletionMark = nodeBeforeCursor.marks.some(
                    m => m.type.name === 'deletion'
                  );

                  if (hasDeletionMark) {
                    return false;
                  }

                  const hasInsertionMark = nodeBeforeCursor.marks.some(
                    m => m.type.name === 'insertion'
                  );

                  if (hasInsertionMark) {
                    return false;
                  }
                }

                const deletionMark = state.schema.marks.deletion.create({ author: 'user' });
                const tr = state.tr.addMark(beforePos, from, deletionMark);
                tr.setSelection(TextSelection.create(tr.doc, beforePos));
                view.dispatch(tr);
                return true;
              } else {
                return handleSelectionDelete(view, from, to, extension);
              }
            }

            if (event.key === 'Delete') {
              if (empty) {
                const afterPos = from + 1;
                if (afterPos > state.doc.content.size) return false;

                const nodeAfterCursor = state.doc.nodeAt(from);
                if (nodeAfterCursor) {
                  const hasDeletionMark = nodeAfterCursor.marks.some(
                    m => m.type.name === 'deletion'
                  );

                  if (hasDeletionMark) {
                    return false; // Already deleted
                  }

                  const hasInsertionMark = nodeAfterCursor.marks.some(
                    m => m.type.name === 'insertion'
                  );

                  if (hasInsertionMark) {
                    return false; // Inserted text - actually delete
                  }
                }

                const deletionMark = state.schema.marks.deletion.create({ author: 'user' });
                const tr = state.tr.addMark(from, afterPos, deletionMark);
                view.dispatch(tr);
                return true;
              } else {
                return handleSelectionDelete(view, from, to, extension);
              }
            }

            return false;
          },
        },
      }),
    ];
  },
});

function handleSelectionDelete(
  view: any,
  from: number,
  to: number,
  extension: any
): boolean {
  const { state } = view;
  const deletionMark = state.schema.marks.deletion.create({ author: 'user' });
  const insertionMark = state.schema.marks.insertion;

  let allInsertions = true;
  state.doc.nodesBetween(from, to, (node: any) => {
    if (!node.marks.some((m: any) => m.type === insertionMark)) {
      allInsertions = false;
    }
  });

  if (allInsertions) {
    return false;
  }

  const tr = state.tr.addMark(from, to, deletionMark);
  tr.setSelection(TextSelection.create(tr.doc, to));
  view.dispatch(tr);
  return true;
}

export default TrackChangesExtension;
