'use client';

import { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import styles from '../workspace.module.css';

type SubTab = 'documents' | 'clauses' | 'parties' | 'jurisdictions';

type Status = 'pending' | 'compiling' | 'ready' | 'error';

interface StatusPayload {
  workspace_id: string;
  status: Status | null;
  compiled_at: string | null;
  source_doc_count: number;
  page_count: number;
  error: string | null;
}

interface IndexPayload {
  status: Status | null;
  compiled_at: string | null;
  source_doc_count?: number;
  markdown: string;
}

interface MemoryDoc {
  slug: string;
  category: string;
  title: string;
  parties: string[];
  jurisdiction: string;
  subject_areas: string[];
  effective_date: string;
  source: string;
  summary: string;
}

interface DocumentsPayload {
  status: Status | null;
  compiled_at: string | null;
  document_count: number;
  documents: MemoryDoc[];
  by_category: Record<string, MemoryDoc[]>;
}

interface Annotation {
  author?: string;
  ts?: string;
  text?: string;
}

interface PagePayload {
  slug: string;
  category: string;
  frontmatter: Record<string, unknown>;
  compiled_body?: string;
  content?: string;
  annotations?: Annotation[];
}

function getBaseUrl(): string {
  if (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_BASE_URL) {
    return process.env.NEXT_PUBLIC_BASE_URL;
  }
  return 'http://localhost:8000';
}

function authHeaders(): HeadersInit {
  if (typeof window === 'undefined') return {};
  const token = window.localStorage.getItem('auth_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return 'never';
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

function stripLeadingFrontmatter(body: string): string {
  let s = body.replace(/^[\s﻿]+/, '');
  if (!s) return s;

  if (s.startsWith('---\n')) {
    const end = s.indexOf('\n---', 4);
    if (end !== -1) {
      s = s.slice(end + 4).replace(/^\s*\n+/, '');
    }
  }

  const fenceMatch = s.match(/^```(?:yaml|yml|json)?\s*\n([\s\S]*?)\n```\s*\n*/);
  if (fenceMatch) {
    s = s.slice(fenceMatch[0].length);
  }

  const lines = s.split('\n');
  let headingIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    if (/^#{1,6}\s/.test(lines[i])) {
      headingIdx = i;
      break;
    }
  }
  if (headingIdx > 0) {
    let allYamlish = true;
    for (const line of lines.slice(0, headingIdx)) {
      const stripped = line.trim();
      if (!stripped) continue;
      if (stripped === '```' || /^```(?:yaml|yml|json)?$/.test(stripped)) continue;
      if (
        /^[A-Za-z_][A-Za-z0-9_-]*\s*:/.test(line) ||
        /^\s+/.test(line) ||
        /^\s*[-*]\s/.test(line)
      ) {
        continue;
      }
      allYamlish = false;
      break;
    }
    if (allYamlish) {
      const rest = lines.slice(headingIdx).join('\n').trim();
      if (rest.length > 50) return rest;
    }
  }
  return s;
}

function WikiMarkdown({ children }: { children: string }) {
  const stripped = stripLeadingFrontmatter(children);

  const transformed = stripped.replace(
    /\[\[([^\]\n|]+?)(?:\|([^\]\n]+?))?\]\]/g,
    (_full, slug: string, label?: string) => {
      const cleanSlug = slug.trim();
      const text = (label || cleanSlug.split('/').pop() || cleanSlug).trim();
      const safeText = text.replace(/[\[\]]/g, '');
      return `[${safeText}](anylegal-wiki:${encodeURIComponent(cleanSlug)})`;
    },
  );
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ href, children: linkChildren, ...props }) => {
          if (typeof href === 'string' && href.startsWith('anylegal-wiki:')) {
            const slug = decodeURIComponent(href.slice('anylegal-wiki:'.length));
            return (
              <button
                type="button"
                className={styles.wikiLinkChip}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  window.dispatchEvent(
                    new CustomEvent('anylegal:openMemoryPage', { detail: { slug } }),
                  );
                }}
                title={`Open ${slug} in Memory`}
              >
                {linkChildren}
              </button>
            );
          }
          return (
            <a href={href} {...props}>
              {linkChildren}
            </a>
          );
        },
      }}
    >
      {transformed}
    </ReactMarkdown>
  );
}

const SUB_TABS: { id: SubTab; label: string }[] = [
  { id: 'documents', label: 'Documents' },
  { id: 'clauses', label: 'Clauses' },
  { id: 'parties', label: 'Parties' },
  { id: 'jurisdictions', label: 'Jurisdictions' },
];

export interface KnowledgePanelProps {
  sessionId?: string;
}

export function KnowledgePanel({ sessionId }: KnowledgePanelProps) {
  const [subTab, setSubTab] = useState<SubTab>('documents');
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [openDocSlug, setOpenDocSlug] = useState<string | null>(null);

  useEffect(() => {
    const onOpenPage = (e: Event) => {
      const slug = (e as CustomEvent<{ slug?: string }>).detail?.slug;
      if (slug) {
        setSubTab('documents');
        setOpenDocSlug(slug);
      }
    };
    window.addEventListener('anylegal:openMemoryPage', onOpenPage);
    return () => {
      window.removeEventListener('anylegal:openMemoryPage', onOpenPage);
    };
  }, []);
  const [statusLoading, setStatusLoading] = useState(true);
  const [recompiling, setRecompiling] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/v1/editor/chat/agentic/workspace/wiki/status`, {
        headers: authHeaders(),
      });
      if (!res.ok) {
        setStatus(null);
        return;
      }
      const data = (await res.json()) as StatusPayload;
      setStatus(data);
    } catch {
      setStatus(null);
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus, sessionId]);

  useEffect(() => {
    if (status?.status !== 'compiling' && status?.status !== 'pending') return;
    const t = setInterval(fetchStatus, 5000);
    return () => clearInterval(t);
  }, [status?.status, fetchStatus]);

  const handleRecompile = useCallback(async () => {
    setRecompiling(true);
    try {
      await fetch(`${getBaseUrl()}/api/v1/editor/chat/agentic/workspace/wiki/recompile`, {
        method: 'POST',
        headers: authHeaders(),
      });
      await fetchStatus();
    } finally {
      setRecompiling(false);
    }
  }, [fetchStatus]);

  return (
    <div className={styles.knowledgePanel}>
      <div className={styles.knowledgeHeader}>
        <div>
          <h2 className={styles.knowledgeTitle}>Memory</h2>
          <p className={styles.knowledgeSubtitle}>
            What Anylegal.ai knows about your workspace. Everything in Chat is
            grounded here — open any item to verify what the AI sees.
          </p>
        </div>
        <div className={styles.knowledgeStatusBar}>
          <KnowledgeStatusPill status={status?.status} />
          <span className={styles.knowledgeMeta}>
            Last compiled: {formatTimestamp(status?.compiled_at ?? null)}
            {status?.source_doc_count != null && status.source_doc_count > 0 ? (
              <> · {status.source_doc_count} {status.source_doc_count === 1 ? 'doc' : 'docs'}</>
            ) : null}
            {' · '}
            <button
              type="button"
              className={styles.knowledgeRecompileLink}
              onClick={handleRecompile}
              disabled={recompiling || status?.status === 'compiling'}
              title="Force a fresh compile of the wiki from your source documents"
            >
              {recompiling ? 'Queuing…' : 'Refresh'}
            </button>
          </span>
        </div>
      </div>

      <nav className={styles.knowledgeSubTabBar}>
        {SUB_TABS.map((tab) => (
          <button
            key={tab.id}
            className={
              subTab === tab.id ? styles.knowledgeSubTabActive : styles.knowledgeSubTab
            }
            onClick={() => setSubTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className={styles.knowledgeBody}>
        {statusLoading ? (
          <KnowledgeLoading />
        ) : status?.status === 'compiling' ? (
          <KnowledgeCompiling />
        ) : status?.status === 'error' ? (
          <KnowledgeError error={status.error} />
        ) : !status || status.status !== 'ready' || (status.source_doc_count ?? 0) === 0 ? (
          <KnowledgeEmpty status={status?.status} />
        ) : subTab === 'documents' ? (
          <DocumentsView onOpenDoc={setOpenDocSlug} />
        ) : (
          <IndexView subTab={subTab} />
        )}
      </div>

      {openDocSlug ? (
        <DocDrawer slug={openDocSlug} onClose={() => setOpenDocSlug(null)} />
      ) : null}
    </div>
  );
}

function KnowledgeStatusPill({ status }: { status?: Status | null }) {
  const label = status ?? 'pending';
  const cls =
    status === 'ready'
      ? styles.knowledgePillReady
      : status === 'error'
      ? styles.knowledgePillError
      : styles.knowledgePillPending;
  return <span className={cls}>{label}</span>;
}

function KnowledgeLoading() {
  return (
    <div className={styles.knowledgeStatePanel}>
      <div className={styles.loadingSpinner} />
      <p>Loading knowledge…</p>
    </div>
  );
}

function KnowledgeCompiling() {
  return (
    <div className={styles.knowledgeStatePanel}>
      <div className={styles.loadingSpinner} />
      <h3>Compiling your knowledge base</h3>
      <p>
        We&apos;re reading every document in your workspace and building a cross-referenced
        summary. This usually takes a minute or two.
      </p>
    </div>
  );
}

function KnowledgeError({ error }: { error: string | null }) {
  return (
    <div className={styles.knowledgeStatePanel}>
      <h3>Compile failed</h3>
      <p>{error || 'An unexpected error occurred while compiling the knowledge base.'}</p>
      <p>Try the Recompile button above to retry, or contact support if the issue persists.</p>
    </div>
  );
}

function KnowledgeEmpty({ status }: { status?: Status | null }) {
  return (
    <div className={styles.knowledgeStatePanel}>
      <h3>Knowledge base not ready yet</h3>
      <p>
        {status === 'pending'
          ? 'Your workspace is queued for compilation. This page will refresh automatically.'
          : 'Add some contracts, statutes or memos to your workspace and the knowledge base will compile in the background.'}
      </p>
    </div>
  );
}

function IndexView({ subTab }: { subTab: SubTab }) {
  const [data, setData] = useState<IndexPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setFilter(''); // clear filter on tab switch
    fetch(`${getBaseUrl()}/api/v1/editor/chat/agentic/workspace/wiki/${subTab}`, {
      headers: authHeaders(),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((payload: IndexPayload | null) => {
        if (cancelled) return;
        setData(payload);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [subTab]);

  if (loading) {
    return (
      <div className={styles.knowledgeStatePanel}>
        <div className={styles.loadingSpinner} />
      </div>
    );
  }

  const md = data?.markdown ?? '';
  if (!md.trim()) {
    return (
      <div className={styles.knowledgeStatePanel}>
        <p>No {subTab} extracted yet — your wiki may need more documents to surface patterns.</p>
      </div>
    );
  }

  const filtered = filterMarkdownSections(md, filter);
  const placeholder = subTab === 'clauses'
    ? 'Filter clauses…'
    : subTab === 'parties'
    ? 'Filter parties…'
    : 'Filter jurisdictions…';

  return (
    <div className={styles.indexView}>
      <div className={styles.documentsToolbar}>
        <input
          type="search"
          className={styles.documentsFilter}
          placeholder={placeholder}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      <div className={styles.knowledgeMarkdown}>
        {filtered.trim() ? (
          <WikiMarkdown>{filtered}</WikiMarkdown>
        ) : (
          <p style={{ color: '#6b7280', fontStyle: 'italic' }}>
            No matches for &quot;{filter}&quot;.
          </p>
        )}
      </div>
    </div>
  );
}

const META_HEADINGS_RE = /^##\s+(table\s+of\s+contents|index|overview|contents)\s*$/i;

function filterMarkdownSections(md: string, query: string): string {
  const q = query.trim().toLowerCase();
  if (!q) return md;

  const lines = md.split('\n');
  const h2Indices: number[] = [];
  for (let i = 0; i < lines.length; i++) {
    if (/^##\s/.test(lines[i])) h2Indices.push(i);
  }
  if (h2Indices.length === 0) {
    return md.toLowerCase().includes(q) ? md : '';
  }

  const titleLine = lines.slice(0, h2Indices[0]).find((l) => /^#\s/.test(l));
  const intro = titleLine || '';

  const matched: string[] = [];
  for (let i = 0; i < h2Indices.length; i++) {
    const start = h2Indices[i];
    const end = i + 1 < h2Indices.length ? h2Indices[i + 1] : lines.length;
    const headingLine = lines[start];
    if (META_HEADINGS_RE.test(headingLine)) continue; // skip ToC etc.
    const section = lines.slice(start, end).join('\n');
    if (section.toLowerCase().includes(q)) {
      matched.push(section);
    }
  }
  return [intro, ...matched].filter(Boolean).join('\n\n');
}

function DocumentsView({ onOpenDoc }: { onOpenDoc: (slug: string) => void }) {
  const [data, setData] = useState<DocumentsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`${getBaseUrl()}/api/v1/editor/chat/agentic/workspace/wiki/documents`, {
      headers: authHeaders(),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((payload: DocumentsPayload | null) => {
        if (cancelled) return;
        setData(payload);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className={styles.knowledgeStatePanel}>
        <div className={styles.loadingSpinner} />
      </div>
    );
  }

  const docs = data?.documents ?? [];
  if (docs.length === 0) {
    return (
      <div className={styles.knowledgeStatePanel}>
        <p>
          No documents in memory yet. Add some contracts, statutes or memos to your
          workspace and the AI will read them in the background.
        </p>
      </div>
    );
  }

  const q = filter.trim().toLowerCase();
  const visible = q
    ? docs.filter((d) => {
        return (
          (d.title || '').toLowerCase().includes(q) ||
          (d.summary || '').toLowerCase().includes(q) ||
          d.parties.some((p) => p.toLowerCase().includes(q)) ||
          (d.jurisdiction || '').toLowerCase().includes(q) ||
          d.subject_areas.some((s) => s.toLowerCase().includes(q))
        );
      })
    : docs;

  const grouped = visible.reduce<Record<string, MemoryDoc[]>>((acc, d) => {
    const cat = d.category || 'other';
    (acc[cat] = acc[cat] || []).push(d);
    return acc;
  }, {});

  const categoryOrder = ['contracts', 'statutes', 'cases', 'memos', 'topics', 'other'];
  const categoryLabels: Record<string, string> = {
    contracts: 'Contracts',
    statutes: 'Statutes',
    cases: 'Cases',
    memos: 'Memos',
    topics: 'Topics',
    other: 'Other',
  };

  return (
    <div className={styles.documentsView}>
      <div className={styles.documentsToolbar}>
        <input
          type="search"
          className={styles.documentsFilter}
          placeholder="Filter by title, party, jurisdiction, topic…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <span className={styles.documentsCount}>
          {visible.length} of {docs.length}
        </span>
      </div>

      {/* Workspace card — pinned, opens the AI's cross-cutting journal.
          Hidden when the user is filtering (the filter is for docs only). */}
      {!q ? (
        <button
          type="button"
          className={`${styles.documentCard} ${styles.workspaceCard}`}
          onClick={() => onOpenDoc('_workspace')}
        >
          <div className={styles.documentCardHeader}>
            <h4 className={styles.documentCardTitle}>Workspace</h4>
            <span className={`${styles.docChip} ${styles.docChipWorkspace}`}>This matter</span>
          </div>
          <p className={styles.documentCardSummary}>
            AnyLegal&apos;s cross-cutting notes on this workspace — counterparty intel,
            user preferences, decisions made earlier. Not tied to any single document.
          </p>
        </button>
      ) : null}

      {categoryOrder
        .filter((cat) => grouped[cat]?.length)
        .map((cat) => (
          <section key={cat} className={styles.documentsSection}>
            <h3 className={styles.documentsSectionTitle}>
              {categoryLabels[cat]}
              <span className={styles.documentsSectionCount}>{grouped[cat].length}</span>
            </h3>
            <div className={styles.documentsGrid}>
              {grouped[cat].map((d) => (
                <button
                  key={d.slug}
                  className={styles.documentCard}
                  onClick={() => onOpenDoc(d.slug)}
                  type="button"
                >
                  <div className={styles.documentCardHeader}>
                    <h4 className={styles.documentCardTitle}>{d.title}</h4>
                  </div>
                  {d.summary ? (
                    <p className={styles.documentCardSummary}>{d.summary}</p>
                  ) : null}
                  <div className={styles.documentCardChips}>
                    {d.jurisdiction ? (
                      <span className={`${styles.docChip} ${styles.docChipJurisdiction}`}>
                        {d.jurisdiction}
                      </span>
                    ) : null}
                    {d.parties.slice(0, 4).map((p, i) => (
                      <span key={`p${i}`} className={`${styles.docChip} ${styles.docChipParty}`}>
                        {p}
                      </span>
                    ))}
                    {d.parties.length > 4 ? (
                      <span className={styles.docChip}>+{d.parties.length - 4}</span>
                    ) : null}
                    {d.subject_areas.slice(0, 3).map((s, i) => (
                      <span key={`s${i}`} className={`${styles.docChip} ${styles.docChipSubject}`}>
                        {s}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </section>
        ))}

      {visible.length === 0 ? (
        <div className={styles.knowledgeStatePanel}>
          <p>No documents match &quot;{filter}&quot;.</p>
        </div>
      ) : null}
    </div>
  );
}

function DocDrawer({ slug, onClose }: { slug: string; onClose: () => void }) {
  const [page, setPage] = useState<PagePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const isWorkspaceJournal = slug === '_workspace';

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const url = isWorkspaceJournal
      ? `${getBaseUrl()}/api/v1/editor/chat/agentic/workspace/wiki/workspace_notes`
      : `${getBaseUrl()}/api/v1/editor/chat/agentic/workspace/wiki/page?slug=${encodeURIComponent(slug)}`;
    fetch(url, { headers: authHeaders() })
      .then(async (r) => {
        if (!r.ok) {
          const body = await r.json().catch(() => ({}));
          throw new Error(body.error || `HTTP ${r.status}`);
        }
        return r.json();
      })
      .then((payload: PagePayload | { annotations?: Annotation[] }) => {
        if (cancelled) return;
        if (isWorkspaceJournal) {
          const wp = payload as { annotations?: Annotation[] };
          setPage({
            slug,
            category: 'workspace',
            frontmatter: { title: 'Workspace Memory' },
            compiled_body: '',
            annotations: wp.annotations ?? [],
          });
        } else {
          setPage(payload as PagePayload);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [slug, isWorkspaceJournal]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const fm = page?.frontmatter || {};
  const title = (fm['title'] as string) || slug.split('/').pop()?.replace(/-/g, ' ') || slug;
  const parties = ensureStringList(fm['parties']);
  const jurisdiction = (fm['jurisdiction'] as string) || '';
  const subjectAreas = ensureStringList(fm['subject_areas']);
  const effectiveDate = (fm['effective_date'] as string) || '';
  const source = (fm['source'] as string) || '';

  if (typeof document === 'undefined') return null;
  return createPortal(
    <>
      <div className={styles.docDrawerBackdrop} onClick={onClose} />
      <aside className={styles.docDrawer}>
        <header className={styles.docDrawerHeader}>
          <button
            type="button"
            className={styles.docDrawerClose}
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
          <span className={styles.docDrawerCategory}>{page?.category || ''}</span>
          <h2 className={styles.docDrawerTitle}>{title}</h2>
          {source ? <p className={styles.docDrawerSource}>Source: {source}</p> : null}
        </header>

        <div className={styles.docDrawerBody}>
          {loading ? (
            <div className={styles.knowledgeStatePanel}>
              <div className={styles.loadingSpinner} />
            </div>
          ) : error ? (
            <div className={styles.knowledgeStatePanel}>
              <p>Could not load: {error}</p>
            </div>
          ) : (
            <>
              <dl className={styles.docDrawerMeta}>
                {jurisdiction ? (
                  <>
                    <dt>Jurisdiction</dt>
                    <dd>{jurisdiction}</dd>
                  </>
                ) : null}
                {effectiveDate ? (
                  <>
                    <dt>Effective</dt>
                    <dd>{effectiveDate}</dd>
                  </>
                ) : null}
                {parties.length ? (
                  <>
                    <dt>Parties</dt>
                    <dd>{parties.join(', ')}</dd>
                  </>
                ) : null}
                {subjectAreas.length ? (
                  <>
                    <dt>Subjects</dt>
                    <dd>{subjectAreas.join(', ')}</dd>
                  </>
                ) : null}
              </dl>

              <hr className={styles.docDrawerDivider} />

              <div className={styles.knowledgeMarkdown}>
                <WikiMarkdown>
                  {page?.compiled_body || page?.content || ''}
                </WikiMarkdown>
              </div>

              {(page?.annotations?.length ?? 0) > 0 ? (
                <>
                  <hr className={styles.docDrawerDivider} />
                  <h3 className={styles.docDrawerAnnotationsHeader}>
                    AI Notes
                    <span className={styles.docDrawerAnnotationsCount}>
                      {page!.annotations!.length}
                    </span>
                  </h3>
                  <ul className={styles.docDrawerAnnotations}>
                    {page!.annotations!.map((a, i) => (
                      <li key={i} className={styles.docDrawerAnnotation}>
                        <span className={styles.docDrawerAnnotationMeta}>
                          {a.author || 'ai'}
                          {a.ts ? ` · ${formatTimestamp(a.ts)}` : ''}
                        </span>
                        <p className={styles.docDrawerAnnotationText}>{a.text || ''}</p>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </>
          )}
        </div>
      </aside>
    </>,
    document.body,
  );
}

function ensureStringList(v: unknown): string[] {
  if (Array.isArray(v)) return v.filter((x): x is string => typeof x === 'string' && x.length > 0);
  if (typeof v === 'string' && v) return [v];
  return [];
}

export default KnowledgePanel;
