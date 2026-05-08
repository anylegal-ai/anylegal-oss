"use client";

import React from "react";
import Link from "next/link";
import styles from "../landing.module.css";

export default function ArchitectureClient() {
  return (
    <div className={styles.landing}>
      {/* Navigation */}
      <nav className={styles.nav}>
        <div className={styles.navContainer}>
          <Link href="/" className={styles.logo}>
            <span className={styles.logoText}>
              ANYLEGAL<span className={styles.logoAi}>.ai</span>
            </span>
          </Link>
          <div className={styles.navButtons}>
            <a
              href="https://anylegal.ai"
              target="_blank"
              rel="noopener noreferrer"
              className={styles.btnPrimary}
            >
              Hosted product →
            </a>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className={`${styles.section}`} style={{ paddingTop: '120px' }}>
        <span className={styles.sectionTitle}>Architecture</span>
        <h1 className={styles.sectionHeading}>How AnyLegal&apos;s Agent Works</h1>
        <p className={styles.coworkSubtitle}>
          One agentic loop. Five context layers. Your configuration, your control.
        </p>
      </section>

      {/* The Agentic Loop */}
      <section className={`${styles.section}`}>
        <h2 className={styles.sectionHeading}>The Agentic Loop</h2>
        <div style={{ maxWidth: '720px', margin: '0 auto', textAlign: 'left', lineHeight: 1.8 }}>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
            Unlike simple chatbots that respond in one shot, AnyLegal runs an <strong>agentic loop</strong>.
            The LLM receives your message along with a set of tools and autonomously decides which tools to call,
            in what order, and how many times. It keeps working until the task is complete.
          </p>
          <div style={{
            background: 'var(--bg-card, #f8fafc)',
            border: '1px solid var(--border-subtle, #e2e8f0)',
            borderRadius: '12px',
            padding: '24px',
            fontFamily: 'monospace',
            fontSize: '13px',
            lineHeight: 1.7,
            whiteSpace: 'pre-wrap',
            marginBottom: '32px',
            color: 'var(--text-primary)'
          }}>
{`User Message
    ↓
┌───────────────────────────────────────┐
│  System Prompt (5 context layers)     │
│  + Available Tools (filtered by skill)│
│  + Conversation History               │
└───────────────────────────────────────┘
    ↓
┌───────────────────────────────────────┐
│  LLM decides: respond or use a tool  │
│                                       │
│  → If tool call: execute tool,        │
│    feed result back, loop again       │
│  → If text: stream response to user   │
└───────────────────────────────────────┘
    ↓
Workspace Mode: Editor updates + side chat
Chat Mode: Full-width chat + artifact cards`}
          </div>
          <p style={{ color: 'var(--text-secondary)' }}>
            The agent might read a document, search the web for relevant case law, compare clauses against
            your playbook, and draft an edit &mdash; all from a single user message. You see each step as
            numbered progress items in the chat.
          </p>
        </div>
      </section>

      {/* Five Context Layers */}
      <section className={`${styles.section} ${styles.featuresSection}`}>
        <span className={styles.sectionTitle}>Progressive Disclosure</span>
        <h2 className={styles.sectionHeading}>Five Context Layers</h2>
        <p className={styles.coworkSubtitle}>
          The system prompt is assembled from five layers, each adding more context.
          You control layers 1&ndash;3. The platform handles the rest.
        </p>

        <div style={{ maxWidth: '800px', margin: '40px auto 0' }}>
          <table className={styles.comparisonTable}>
            <thead>
              <tr>
                <th>Layer</th>
                <th>Name</th>
                <th>Source</th>
                <th>Who Controls It</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>L0</strong></td>
                <td>Platform Prompt</td>
                <td><code>system_prompt.md</code></td>
                <td>AnyLegal (hardcoded)</td>
              </tr>
              <tr>
                <td><strong>L1</strong></td>
                <td className={styles.comparisonHighlight}>agents.md</td>
                <td className={styles.comparisonHighlight}>Your <code>agents.md</code> file</td>
                <td className={styles.comparisonHighlight}>You</td>
              </tr>
              <tr>
                <td><strong>L2</strong></td>
                <td className={styles.comparisonHighlight}>Skill Instructions</td>
                <td className={styles.comparisonHighlight}><code>SKILL.md</code> body</td>
                <td className={styles.comparisonHighlight}>You (customizable)</td>
              </tr>
              <tr>
                <td><strong>L3</strong></td>
                <td className={styles.comparisonHighlight}>Playbook</td>
                <td className={styles.comparisonHighlight}><code>positions.md</code></td>
                <td className={styles.comparisonHighlight}>You</td>
              </tr>
              <tr>
                <td><strong>L4</strong></td>
                <td>Session Context</td>
                <td>Documents, active file, conversation</td>
                <td>Automatic</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* agents.md */}
      <section className={`${styles.section}`}>
        <h2 className={styles.sectionHeading}>agents.md &mdash; Your Agent Configuration</h2>
        <div style={{ maxWidth: '720px', margin: '0 auto', textAlign: 'left', lineHeight: 1.8 }}>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
            The <code>agents.md</code> file is your personal configuration for the AI agent. It sits at the
            top of the workspace file tree and is injected into every conversation as Layer 1 context.
            Think of it as &ldquo;who the agent is&rdquo; for your workspace.
          </p>
          <div style={{
            background: 'var(--bg-card, #f8fafc)',
            border: '1px solid var(--border-subtle, #e2e8f0)',
            borderRadius: '12px',
            padding: '24px',
            fontFamily: 'monospace',
            fontSize: '13px',
            lineHeight: 1.7,
            whiteSpace: 'pre-wrap',
            marginBottom: '32px',
            color: 'var(--text-primary)'
          }}>
{`# Agent Configuration

## Identity
You are a legal assistant for a mid-size commercial law firm.

## Preferences
- Default jurisdiction: UAE (DIFC)
- Default language: English
- Citation format: [[N]](URL) with source name
- Always flag unlimited liability and uncapped indemnity

## Default Representing Party
Buyer / Tenant / Licensee (unless instructed otherwise)

## Review Focus
- Limitation of liability
- Indemnification
- Termination for convenience
- IP assignment vs license
- Governing law and dispute resolution`}
          </div>
          <p style={{ color: 'var(--text-secondary)' }}>
            Edit this file anytime from the workspace sidebar. Changes take effect on the next message.
            The agent will follow your preferences, represent your default party, and focus on the areas
            you care about.
          </p>
        </div>
      </section>

      {/* How layers interplay */}
      <section className={`${styles.section}`}>
        <h2 className={styles.sectionHeading}>How the Layers Interplay</h2>
        <div style={{ maxWidth: '720px', margin: '0 auto', textAlign: 'left', lineHeight: 1.8 }}>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
            When you type a message, the system assembles the prompt from all applicable layers:
          </p>
          <div style={{
            background: 'var(--bg-card, #f8fafc)',
            border: '1px solid var(--border-subtle, #e2e8f0)',
            borderRadius: '12px',
            padding: '24px',
            fontFamily: 'monospace',
            fontSize: '13px',
            lineHeight: 1.7,
            whiteSpace: 'pre-wrap',
            marginBottom: '32px',
            color: 'var(--text-primary)'
          }}>
{`Example: User types "/review this NDA"

System prompt assembled:
├── L0: Platform prompt (anti-hallucination rules,
│       citation format, tool usage patterns)
├── L1: agents.md ("represent Buyer, focus on
│       indemnity and liability caps")
├── L2: review SKILL.md body ("read the document,
│       flag risks, compare against playbook...")
├── L3: positions.md ("Indemnity: cap at contract
│       value. Liability: mutual cap at 12 months...")
└── L4: Session context
    ├── Documents: NDA.docx (DOCX, 12KB)
    ├── Active document: NDA.docx
    └── Conversation history

→ The LLM now knows WHO it represents (L1),
  HOW to review (L2), WHAT positions to enforce (L3),
  and WHICH document to read (L4).`}
          </div>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '16px' }}>
            <strong>Why this matters:</strong> Every layer is a file you can read, edit, and version-control.
            No hidden prompts, no opaque configuration databases, no vendor lock-in. If you switch platforms,
            your <code>agents.md</code>, <code>SKILL.md</code> files, and <code>positions.md</code> come with you.
          </p>
        </div>
      </section>

      {/* Playbook */}
      <section className={`${styles.section}`}>
        <h2 className={styles.sectionHeading}>Playbook &mdash; Your Positions</h2>
        <div style={{ maxWidth: '720px', margin: '0 auto', textAlign: 'left', lineHeight: 1.8 }}>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
            The playbook (<code>positions.md</code>) is where you define your firm&apos;s or organization&apos;s
            standard positions on common contract clauses. The agent loads it as Layer 3 context when
            performing reviews, comparisons, or drafting.
          </p>
          <div style={{
            background: 'var(--bg-card, #f8fafc)',
            border: '1px solid var(--border-subtle, #e2e8f0)',
            borderRadius: '12px',
            padding: '24px',
            fontFamily: 'monospace',
            fontSize: '13px',
            lineHeight: 1.7,
            whiteSpace: 'pre-wrap',
            marginBottom: '32px',
            color: 'var(--text-primary)'
          }}>
{`# Standard Positions

## Limitation of Liability
- Preferred: Mutual cap at 12 months of fees paid
- Acceptable: Mutual cap at contract value
- Unacceptable: Unlimited liability for either party
- Flag: Any carve-out that effectively removes the cap

## Indemnification
- Preferred: Mutual indemnification, capped
- Acceptable: Asymmetric if we're the buyer
- Unacceptable: Uncapped indemnity obligations

## Termination
- Preferred: Either party, 30 days written notice
- Acceptable: 60-90 day notice period
- Flag: No termination for convenience clause`}
          </div>
          <p style={{ color: 'var(--text-secondary)' }}>
            This is a plain markdown file. Define it once, and every review, comparison, and draft will
            enforce your positions consistently. Share it across your team by copying a file.
          </p>
        </div>
      </section>

      {/* Open Tools */}
      <section className={`${styles.section}`}>
        <h2 className={styles.sectionHeading}>Open Source Tools</h2>
        <div style={{ maxWidth: '720px', margin: '0 auto', textAlign: 'left', lineHeight: 1.8 }}>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
            The tools the agent uses &mdash; document reading, editing, web search, comparison, DOCX track
            changes &mdash; are all open source on GitHub. You can audit exactly how your contracts are processed.
          </p>
          <table className={styles.comparisonTable}>
            <thead>
              <tr>
                <th>Category</th>
                <th>Tools</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Document Management</td>
                <td><code>list_documents</code>, <code>read_document</code>, <code>create_document</code>, <code>edit_document</code></td>
              </tr>
              <tr>
                <td>Web Research</td>
                <td><code>web_search</code> (120+ jurisdictions), <code>web_fetch</code></td>
              </tr>
              <tr>
                <td>Comparison</td>
                <td><code>compare</code>, <code>create_redlined_docx</code></td>
              </tr>
              <tr>
                <td>DOCX Track Changes</td>
                <td><code>accept_revisions</code>, <code>reject_revisions</code>, <code>get_revision_stats</code>, <code>export_docx</code></td>
              </tr>
            </tbody>
          </table>
          <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginTop: '16px' }}>
            Skills define which tools the agent can access. The <code>/review</code> skill gets document tools;
            the <code>/research</code> skill gets web tools. This keeps the agent focused and efficient.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className={styles.ctaSection}>
        <h2 className={styles.ctaTitle}>See It in Action</h2>
        <p className={styles.ctaSubtitle}>
          Start a free trial and explore the workspace file tree &mdash;
          edit <code>agents.md</code>, customize your playbook, activate skills.
        </p>
        <div className={styles.ctaButtons}>
          <Link href="/skills" className={styles.btnGhost}>
            View Skills →
          </Link>
          <a
            href="https://anylegal.ai"
            target="_blank"
            rel="noopener noreferrer"
            className={`${styles.btnPrimary} ${styles.btnLarge}`}
          >
            Hosted product →
          </a>
        </div>
      </section>

      {/* Minimal Footer */}
      <footer className={styles.footer}>
        <div className={styles.footerContent}>
          <div className={styles.footerBottom}>
            <div className={styles.footerCompliance}>
              <span className={styles.footerComplianceItem}>Privacy by Design</span>
              <span className={styles.footerComplianceItem}>Open Source Tools</span>
              <span className={styles.footerComplianceItem}>Portable Structure</span>
            </div>
            <div className={styles.footerCopyright}>
              © 2026 AnyLegal.ai &middot; <Link href="/">Home</Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
