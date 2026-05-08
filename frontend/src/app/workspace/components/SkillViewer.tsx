import React, { useMemo } from 'react';
import { markdownToHtml } from '../utils/markdownUtils';
import styles from '../workspace.module.css';

interface SkillViewerProps {
  filePath: string;
  rawContent: string;
  onClose: () => void;
}

interface SkillMeta {
  name: string;
  emoji: string;
  description: string;
  tools: string[];
}

function parseFrontmatter(raw: string): { meta: SkillMeta; body: string } {
  const meta: SkillMeta = { name: '', emoji: '', description: '', tools: [] };
  let body = raw;

  const fmMatch = raw.match(/^---\s*\n([\s\S]*?)\n---\s*\n?/);
  if (fmMatch) {
    const fm = fmMatch[1];
    body = raw.slice(fmMatch[0].length);

    const nameMatch = fm.match(/^name:\s*(.+)$/m);
    if (nameMatch) meta.name = nameMatch[1].trim().replace(/^["']|["']$/g, '');

    const emojiMatch = fm.match(/^emoji:\s*(.+)$/m);
    if (emojiMatch) {
      let val = emojiMatch[1].trim().replace(/^["']|["']$/g, '');
      val = val.replace(/\\U([0-9A-Fa-f]{8})/g, (_, hex) =>
        String.fromCodePoint(parseInt(hex, 16))
      );
      meta.emoji = val;
    }

    const descMatch = fm.match(/^description:\s*(.+)$/m);
    if (descMatch) meta.description = descMatch[1].trim().replace(/^["']|["']$/g, '');

    const toolsMatch = fm.match(/tools:\s*\[([^\]]*)\]/);
    if (toolsMatch) {
      meta.tools = toolsMatch[1].split(',').map(t => t.trim()).filter(Boolean);
    }
  }

  return { meta, body };
}

export function SkillViewer({ filePath, rawContent, onClose }: SkillViewerProps) {
  const { meta, body } = useMemo(() => parseFrontmatter(rawContent), [rawContent]);

  const titleMatch = body.match(/^# (.+)$/m);
  const title = titleMatch ? titleMatch[1].trim() : meta.name;

  const bodyWithoutH1 = body.replace(/^# .+\n*/m, '');
  const bodyHtml = useMemo(() => markdownToHtml(bodyWithoutH1), [bodyWithoutH1]);

  const command = filePath.split('/')[1] || meta.name;

  return (
    <div className={styles.skillViewer}>
      {/* Close button */}
      <button className={styles.skillClose} onClick={onClose} title="Close">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>

      {/* Header card */}
      <div className={styles.skillHeader}>
        <div className={styles.skillTitleRow}>
          {meta.emoji && <span className={styles.skillEmoji}>{meta.emoji}</span>}
          <h1 className={styles.skillTitle}>{title}</h1>
        </div>
        {meta.description && (
          <p className={styles.skillDescription}>{meta.description}</p>
        )}
        <div className={styles.skillBadges}>
          <span className={styles.skillCommand}>/{command}</span>
          {meta.tools.map(tool => (
            <span key={tool} className={styles.skillBadge}>{tool}</span>
          ))}
        </div>
      </div>

      {/* Rendered markdown body */}
      <div
        className={styles.skillBody}
        dangerouslySetInnerHTML={{ __html: bodyHtml }}
      />
    </div>
  );
}
