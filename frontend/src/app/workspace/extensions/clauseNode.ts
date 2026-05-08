import { Node, mergeAttributes } from '@tiptap/core';
import { InputRule } from '@tiptap/core';

export interface ClauseNodeOptions {
  HTMLAttributes: Record<string, unknown>;
}

export const CLAUSE_NUMBER_PATTERN = /^(\d+(?:\.\d+)*)[.\s]/;

const CLAUSE_INPUT_RULE_PATTERN = /^(\d+(?:\.\d+)*)\s$/;

export function parseClauseNumber(clauseNum: string): { parts: number[]; level: number } {
  const parts = clauseNum.split('.').map(p => parseInt(p, 10)).filter(n => !isNaN(n));
  return {
    parts,
    level: parts.length,
  };
}

export function startsWithClauseNumber(text: string): { match: boolean; number?: string; parts?: number[]; level?: number } {
  const match = text.match(CLAUSE_NUMBER_PATTERN);
  if (!match) {
    return { match: false };
  }
  const number = match[1];
  const { parts, level } = parseClauseNumber(number);
  return { match: true, number, parts, level };
}

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    clause: {
      setClause: (attrs: { number: string; parts: number[]; level: number }) => ReturnType;
      convertToClause: (number: string) => ReturnType;
      insertClauseAt: (pos: number, content: string, attrs: { number: string; parts: number[]; level: number }) => ReturnType;
    };
  }
}

export const ClauseNode = Node.create<ClauseNodeOptions>({
  name: 'clause',

  addOptions() {
    return {
      HTMLAttributes: {},
    };
  },

  group: 'block',

  content: 'inline*',

  defining: true,

  addAttributes() {
    return {
      number: {
        default: '',
        parseHTML: element => element.getAttribute('data-clause') || '',
        renderHTML: attributes => {
          if (!attributes.number) return {};
          return { 'data-clause': attributes.number };
        },
      },
      parts: {
        default: [],
        parseHTML: element => {
          const clauseNum = element.getAttribute('data-clause');
          if (!clauseNum) return [];
          return clauseNum.split('.').map((p: string) => parseInt(p, 10)).filter((n: number) => !isNaN(n));
        },
        renderHTML: () => ({}), // parts is derived from number, no need to render
      },
      level: {
        default: 1,
        parseHTML: element => {
          const level = element.getAttribute('data-level');
          if (level) return parseInt(level, 10);
          const clauseNum = element.getAttribute('data-clause');
          if (!clauseNum) return 1;
          return clauseNum.split('.').length;
        },
        renderHTML: attributes => {
          if (!attributes.level) return {};
          return { 'data-level': attributes.level.toString() };
        },
      },
    };
  },

  parseHTML() {
    return [
      { tag: 'p[data-clause]' },
      { tag: 'div[data-clause]' },
    ];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      'p',
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        'data-clause': node.attrs.number,
        'data-level': node.attrs.level?.toString(),
        class: `clause clause-level-${node.attrs.level}`,
      }),
      0, // Content placeholder
    ];
  },

  addCommands() {
    return {
      setClause:
        (attrs) =>
        ({ commands }) => {
          return commands.setNode(this.name, attrs);
        },

      convertToClause:
        (number: string) =>
        ({ commands }) => {
          const { parts, level } = parseClauseNumber(number);
          return commands.setNode(this.name, { number, parts, level });
        },

      insertClauseAt:
        (pos: number, content: string, attrs) =>
        ({ tr, dispatch }) => {
          if (dispatch) {
            const node = this.type.create(attrs, this.editor.schema.text(content));
            tr.insert(pos, node);
          }
          return true;
        },
    };
  },

  addInputRules() {
    return [
      new InputRule({
        find: CLAUSE_INPUT_RULE_PATTERN,
        handler: ({ state, range, match }): void => {
          const clauseNum = match[1];
          const { parts, level } = parseClauseNumber(clauseNum);

          const { tr } = state;
          const start = range.from;
          const end = range.to;

          const $from = state.doc.resolve(start);
          const node = $from.parent;

          if ($from.parentOffset !== 0) {
            return;
          }

          tr.replaceRangeWith(
            start - 1, // Include the position before the match
            end,
            this.type.create(
              { number: clauseNum, parts, level },
              state.schema.text(clauseNum + ' ')
            )
          );
        },
      }),
    ];
  },
});

export default ClauseNode;
