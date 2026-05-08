"use client";

import React from "react";
import Link from "next/link";
import styles from "../landing.module.css";

export default function SkillsClient() {
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
        <span className={styles.sectionTitle}>Open Skills</span>
        <h1 className={styles.sectionHeading}>How Skills Work in AnyLegal</h1>
        <p className={styles.coworkSubtitle}>
          Skills are portable, open instruction files that tell the AI agent how to perform specialized legal tasks.
          No vendor lock-in &mdash; take them anywhere.
        </p>
      </section>

      {/* What is a Skill */}
      <section className={`${styles.section}`}>
        <h2 className={styles.sectionHeading}>What is a SKILL.md?</h2>
        <div style={{ maxWidth: '720px', margin: '0 auto', textAlign: 'left', lineHeight: 1.8 }}>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
            A <strong>SKILL.md</strong> file is a markdown document that defines how an AI agent should
            perform a specific task. It includes the skill&apos;s name, description, which tools it needs,
            and detailed instructions for the LLM.
          </p>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '24px' }}>
            This format is inspired by the OpenSkills standard &mdash; portable across agents, version-controllable
            with Git, and readable by humans. No proprietary configuration. No vendor lock-in.
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
{`---
name: review
description: Review a contract against a playbook
tools:
  - read_document
  - edit_document
  - compare
  - list_documents
trigger:
  slash: /review
  keywords: [review, analyze, check, flag, risks]
---

# Review Skill

You are a contract review specialist.

## Instructions
1. Read the active document using read_document
2. Identify key clauses and risk areas
3. Compare against the user's playbook positions
4. Flag missing or problematic clauses
5. Suggest specific edits using edit_document

## Output Format
- Use structured headings for each clause area
- Rate risk as HIGH / MEDIUM / LOW
- Always cite the specific clause text`}
          </div>

          <h3 style={{ fontSize: '18px', marginBottom: '16px', color: 'var(--text-primary)' }}>Key Properties</h3>
          <table className={styles.comparisonTable} style={{ marginBottom: '40px' }}>
            <thead>
              <tr>
                <th>Field</th>
                <th>Purpose</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><code>name</code></td>
                <td>Unique identifier for the skill</td>
              </tr>
              <tr>
                <td><code>description</code></td>
                <td>One-line summary shown in menus and tool tips</td>
              </tr>
              <tr>
                <td><code>tools</code></td>
                <td>Which tools the agent can use when this skill is active (tool filtering)</td>
              </tr>
              <tr>
                <td><code>trigger.slash</code></td>
                <td>Slash command that activates the skill (e.g. <code>/review</code>)</td>
              </tr>
              <tr>
                <td><code>trigger.keywords</code></td>
                <td>Natural language keywords for automatic detection</td>
              </tr>
              <tr>
                <td>Body (markdown)</td>
                <td>Full instructions injected into the system prompt when the skill is active</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Available Skills */}
      <section className={`${styles.section} ${styles.featuresSection}`}>
        <span className={styles.sectionTitle}>Built-in Skills</span>
        <h2 className={styles.sectionHeading}>Four Skills, Ready to Use</h2>

        <div className={styles.featuresGrid}>
          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <path d="M9 15l2 2 4-4"/>
              </svg>
            </div>
            <h3 className={styles.featureTitle}>/review</h3>
            <p className={styles.featureDescription}>
              Review a contract against your playbook. Flags risks, missing clauses, and problematic terms.
              Uses <code>read_document</code>, <code>edit_document</code>, <code>compare</code>.
            </p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="11" cy="11" r="8"/>
                <path d="M21 21l-4.35-4.35"/>
              </svg>
            </div>
            <h3 className={styles.featureTitle}>/research</h3>
            <p className={styles.featureDescription}>
              Research a legal question across 120+ jurisdictions. Returns answers with inline citations
              in <code>[[N]](URL)</code> format.
              Uses <code>web_search</code>, <code>web_fetch</code>.
            </p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M16 3h5v5M8 3H3v5M3 16v5h5M16 21h5v-5"/>
                <path d="M21 3L14 10M3 21l7-7"/>
              </svg>
            </div>
            <h3 className={styles.featureTitle}>/compare</h3>
            <p className={styles.featureDescription}>
              Compare two documents or text versions. Returns structured diff, similarity percentage,
              and redline output. Uses <code>compare</code>, <code>read_document</code>, <code>create_redlined_docx</code>.
            </p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIcon}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
            </div>
            <h3 className={styles.featureTitle}>/draft</h3>
            <p className={styles.featureDescription}>
              Draft a new document from scratch or from a template. NDAs, service agreements, notices,
              and more. Uses <code>create_document</code>, <code>read_document</code>, <code>list_documents</code>.
            </p>
          </div>
        </div>
      </section>

      {/* How Skills Are Loaded */}
      <section className={`${styles.section}`}>
        <h2 className={styles.sectionHeading}>Progressive Disclosure</h2>
        <p className={styles.coworkSubtitle}>
          Skills aren&apos;t loaded all at once. The agent loads only what it needs, when it needs it.
        </p>
        <div style={{ maxWidth: '640px', margin: '32px auto 0', textAlign: 'left' }}>
          <table className={styles.comparisonTable}>
            <thead>
              <tr>
                <th>Level</th>
                <th>What&apos;s Loaded</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><strong>L1 &mdash; Metadata</strong></td>
                <td>Name, description, trigger keywords</td>
                <td>Always (listed in slash command menu)</td>
              </tr>
              <tr>
                <td><strong>L2 &mdash; Full Body</strong></td>
                <td>Complete SKILL.md instructions</td>
                <td>When skill is activated (slash command or auto-detected)</td>
              </tr>
              <tr>
                <td><strong>L3 &mdash; Playbook</strong></td>
                <td>User&apos;s playbook positions relevant to this skill</td>
                <td>When the skill needs organizational context</td>
              </tr>
            </tbody>
          </table>
          <p style={{ color: 'var(--text-muted)', fontSize: '14px', marginTop: '16px' }}>
            This keeps the system prompt lean. A research query doesn&apos;t load review instructions.
            A review doesn&apos;t load drafting templates. Token budget stays focused.
          </p>
        </div>
      </section>

      {/* Portability */}
      <section className={`${styles.section}`}>
        <h2 className={styles.sectionHeading}>Portable by Design</h2>
        <div style={{ maxWidth: '720px', margin: '0 auto', textAlign: 'left', lineHeight: 1.8 }}>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '16px' }}>
            SKILL.md files are plain markdown with YAML frontmatter. This means:
          </p>
          <ul style={{ color: 'var(--text-secondary)', paddingLeft: '20px', marginBottom: '24px' }}>
            <li><strong>Version control</strong> &mdash; track changes to your skills in Git</li>
            <li><strong>Share with teams</strong> &mdash; copy a file, share a skill</li>
            <li><strong>No vendor lock-in</strong> &mdash; skills work with any agent that reads the format</li>
            <li><strong>Customize freely</strong> &mdash; edit instructions, add tools, change triggers</li>
            <li><strong>Open source</strong> &mdash; all built-in skills are on GitHub</li>
          </ul>
          <p style={{ color: 'var(--text-secondary)' }}>
            Compare this to proprietary skill systems where your configurations are locked in a vendor&apos;s
            cloud database. With AnyLegal, your skills are files you own.
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className={styles.ctaSection}>
        <h2 className={styles.ctaTitle}>Try Skills in Action</h2>
        <p className={styles.ctaSubtitle}>
          Type <code>/review</code>, <code>/research</code>, <code>/compare</code>, or <code>/draft</code> in the chat to activate a skill.
        </p>
        <div className={styles.ctaButtons}>
          <a
            href="https://anylegal.ai"
            target="_blank"
            rel="noopener noreferrer"
            className={`${styles.btnPrimary} ${styles.btnLarge}`}
          >
            Hosted product →
          </a>
          <a
            href="https://github.com/wouldbe12/lexwiki"
            target="_blank"
            rel="noopener noreferrer"
            className={styles.btnGhost}
          >
            View Skills on GitHub →
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
