
import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({
  breaks: true,
  gfm: true,
});

// LLM output is the untrusted input here. Every marked.parse() result is
// piped through DOMPurify before the HTML reaches dangerouslySetInnerHTML
// or .innerHTML. SSR returns the raw HTML and lets the client sanitize on
// hydration; the same string is never written into the DOM server-side.
function sanitize(html: string): string {
  if (typeof window === 'undefined') return html;
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    // SVG/MathML carry their own script execution surface; foreignObject
    // re-introduces full HTML inside SVG. The CSP still permits unsafe-inline
    // for now (see next.config.ts), so blocking these here cuts the most
    // common LLM-driven XSS shapes (data:image/svg+xml, embedded handlers).
    FORBID_TAGS: [
      'style', 'script', 'iframe', 'object', 'embed', 'form',
      'svg', 'foreignObject', 'math',
    ],
    FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick', 'onmouseover', 'onfocus'],
  });
}

export function markdownToHtml(markdown: string): string {
  if (!markdown) return '';

  try {
    const html = marked.parse(markdown);
    if (typeof html === 'string') {
      return sanitize(html);
    }
    return '';
  } catch (error) {
    console.error('Markdown to HTML conversion failed:', error);
    return `<p>${escapeHtml(markdown)}</p>`;
  }
}

export async function markdownToHtmlAsync(markdown: string): Promise<string> {
  if (!markdown) return '';

  try {
    const html = await Promise.resolve(marked.parse(markdown));
    return sanitize(html);
  } catch (error) {
    console.error('Markdown to HTML conversion failed:', error);
    return `<p>${escapeHtml(markdown)}</p>`;
  }
}

/**
 * Convert HTML to Markdown
 * 
 * This is a simplified converter that handles the common elements
 * used in playbook markdown (headings, lists, paragraphs, bold, italic).
 * 
 * For more complex HTML, consider using the turndown library.
 * 
 * @param html - HTML string to convert
 * @returns Markdown string
 */
export function htmlToMarkdown(html: string): string {
  if (!html) return '';

  let markdown = html;

  markdown = markdown.replace(/<!DOCTYPE[^>]*>/gi, '');
  markdown = markdown.replace(/<\/?html[^>]*>/gi, '');
  markdown = markdown.replace(/<\/?body[^>]*>/gi, '');
  markdown = markdown.replace(/<\/?head[^>]*>[\s\S]*?<\/head>/gi, '');

  markdown = markdown.replace(/<h1[^>]*>([\s\S]*?)<\/h1>/gi, '# $1\n\n');
  markdown = markdown.replace(/<h2[^>]*>([\s\S]*?)<\/h2>/gi, '## $1\n\n');
  markdown = markdown.replace(/<h3[^>]*>([\s\S]*?)<\/h3>/gi, '### $1\n\n');
  markdown = markdown.replace(/<h4[^>]*>([\s\S]*?)<\/h4>/gi, '#### $1\n\n');
  markdown = markdown.replace(/<h5[^>]*>([\s\S]*?)<\/h5>/gi, '##### $1\n\n');
  markdown = markdown.replace(/<h6[^>]*>([\s\S]*?)<\/h6>/gi, '###### $1\n\n');

  markdown = markdown.replace(/<strong[^>]*>([\s\S]*?)<\/strong>/gi, '**$1**');
  markdown = markdown.replace(/<b[^>]*>([\s\S]*?)<\/b>/gi, '**$1**');
  markdown = markdown.replace(/<em[^>]*>([\s\S]*?)<\/em>/gi, '*$1*');
  markdown = markdown.replace(/<i[^>]*>([\s\S]*?)<\/i>/gi, '*$1*');

  markdown = markdown.replace(/<a[^>]*href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/gi, '[$2]($1)');

  markdown = markdown.replace(/<ul[^>]*>([\s\S]*?)<\/ul>/gi, (match, content) => {
    const items = content.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, '- $1\n');
    return items + '\n';
  });

  let listCounter = 0;
  markdown = markdown.replace(/<ol[^>]*>([\s\S]*?)<\/ol>/gi, (match, content) => {
    listCounter = 0;
    const items = content.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, () => {
      listCounter++;
      return `${listCounter}. `;
    });
    const fixedItems = content.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, (_m: string, text: string) => {
      return `1. ${text}\n`;
    });
    return fixedItems + '\n';
  });

  markdown = markdown.replace(/<p[^>]*>([\s\S]*?)<\/p>/gi, '$1\n\n');

  markdown = markdown.replace(/<br\s*\/?>/gi, '\n');

  markdown = markdown.replace(/<hr\s*\/?>/gi, '---\n\n');

  markdown = markdown.replace(/<pre[^>]*><code[^>]*>([\s\S]*?)<\/code><\/pre>/gi, '```\n$1\n```\n\n');
  markdown = markdown.replace(/<code[^>]*>([\s\S]*?)<\/code>/gi, '`$1`');

  markdown = markdown.replace(/<blockquote[^>]*>([\s\S]*?)<\/blockquote>/gi, (match, content) => {
    const lines = content.trim().split('\n');
    return lines.map((line: string) => `> ${line}`).join('\n') + '\n\n';
  });

  markdown = markdown.replace(/<[^>]+>/g, '');

  markdown = decodeHtmlEntities(markdown);

  markdown = markdown.replace(/\n{3,}/g, '\n\n');
  markdown = markdown.trim();

  return markdown;
}

export function escapeHtml(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };
  return text.replace(/[&<>"']/g, (char) => map[char] || char);
}

export function decodeHtmlEntities(text: string): string {
  const map: Record<string, string> = {
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
    '&quot;': '"',
    '&#39;': "'",
    '&nbsp;': ' ',
  };
  return text.replace(/&[^;]+;/g, (entity) => map[entity] || entity);
}

/**
 * Parse playbook markdown sections
 * 
 * Extracts structured data from playbook markdown format.
 * 
 * @param markdown - Playbook markdown content
 * @returns Parsed sections object
 */
export interface PlaybookSection {
  title: string;
  acceptable: string[];
  requiresReview: string[];
  unacceptable: string[];
}

export function parsePlaybookSections(markdown: string): PlaybookSection[] {
  const sections: PlaybookSection[] = [];

  const h2Regex = /^## (.+)$/gm;
  const sectionMatches = markdown.split(h2Regex);

  for (let i = 1; i < sectionMatches.length; i += 2) {
    const title = sectionMatches[i]?.trim();
    const content = sectionMatches[i + 1] || '';

    if (!title) continue;

    const section: PlaybookSection = {
      title,
      acceptable: [],
      requiresReview: [],
      unacceptable: [],
    };

    const h3Regex = /### (Acceptable|Requires Review|Unacceptable)\s*([\s\S]*?)(?=###|$)/gi;
    let match;

    while ((match = h3Regex.exec(content)) !== null) {
      const subsectionType = match[1].toLowerCase();
      const items = extractListItems(match[2]);

      if (subsectionType === 'acceptable') {
        section.acceptable = items;
      } else if (subsectionType === 'requires review') {
        section.requiresReview = items;
      } else if (subsectionType === 'unacceptable') {
        section.unacceptable = items;
      }
    }

    sections.push(section);
  }

  return sections;
}

function extractListItems(content: string): string[] {
  const items: string[] = [];
  const listItemRegex = /^[-*]\s+(.+)$/gm;
  let match;

  while ((match = listItemRegex.exec(content)) !== null) {
    const item = match[1].trim();
    if (item) {
      items.push(item);
    }
  }

  return items;
}

/**
 * Generate playbook markdown from sections
 * 
 * @param title - Playbook title
 * @param sections - Array of playbook sections
 * @returns Formatted markdown string
 */
export function generatePlaybookMarkdown(
  title: string,
  sections: PlaybookSection[]
): string {
  const lines: string[] = [];

  lines.push(`# ${title}`);
  lines.push('');

  for (const section of sections) {
    lines.push(`## ${section.title}`);
    lines.push('');

    if (section.acceptable.length > 0) {
      lines.push('### Acceptable');
      for (const item of section.acceptable) {
        lines.push(`- ${item}`);
      }
      lines.push('');
    }

    if (section.requiresReview.length > 0) {
      lines.push('### Requires Review');
      for (const item of section.requiresReview) {
        lines.push(`- ${item}`);
      }
      lines.push('');
    }

    if (section.unacceptable.length > 0) {
      lines.push('### Unacceptable');
      for (const item of section.unacceptable) {
        lines.push(`- ${item}`);
      }
      lines.push('');
    }

    lines.push('---');
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * Validate playbook markdown structure
 * 
 * @param markdown - Markdown to validate
 * @returns Validation result with any issues
 */
export interface ValidationResult {
  valid: boolean;
  issues: string[];
}

export function validatePlaybookMarkdown(markdown: string): ValidationResult {
  const issues: string[] = [];

  if (!markdown.match(/^# .+$/m)) {
    issues.push('Missing playbook title (H1 header)');
  }

  if (!markdown.match(/^## .+$/m)) {
    issues.push('No clause sections found (H2 headers)');
  }

  const sections = parsePlaybookSections(markdown);
  for (const section of sections) {
    const hasContent = 
      section.acceptable.length > 0 ||
      section.requiresReview.length > 0 ||
      section.unacceptable.length > 0;

    if (!hasContent) {
      issues.push(`Section "${section.title}" has no position definitions`);
    }
  }

  return {
    valid: issues.length === 0,
    issues,
  };
}
