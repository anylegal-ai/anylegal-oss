---
name: setup
emoji: "\U0001F3D7"
description: "Guide a first-time user through workspace initialisation. Ask about their role and work, then create a personalised folder structure, anylegal.md instructions, and a starter playbook. Use when the user says /setup, asks to set up their workspace, or the workspace appears empty and they ask where to start."
requires:
  tools: [create_document, list_documents, read_document, create_folder, delete_document, delete_folder, web_search, web_fetch]
---

# Workspace Setup

## When to Use

Use this skill when:
- The user explicitly says `/setup` or "set up my workspace"
- The user asks "where do I start?" or similar first-time questions
- `list_documents` shows the workspace is empty or has no user files
- The user wants to start fresh with a new workspace structure

## Process

### Step 0 — Check for existing content

Call `list_documents` before doing anything else.

**If the workspace is empty** (no files — empty system folders like `Playbook/`, `Templates/`, `Skills/` don't count): skip this step entirely and go straight to Step 1.

**If the workspace has user-created files** (playbooks, anylegal.md, uploaded documents, user folders):

List what you found briefly, then ask:

> "Your workspace already has content: [summarise what exists — folders, playbook files, etc.].
>
> How would you like to proceed?
> **(a) Add to it** — I'll create any missing folders and update your Instructions, leaving existing files untouched
> **(b) Start fresh** — I'll clear out the old structure first, then set up a new one tailored to you
> **(c) Cancel** — leave everything as is"

Wait for the user's answer:
- **Add / supplement (a)**: proceed normally — create only what's missing, update anylegal.md
- **Start fresh (b)**:

  ⛔ **DO NOT delete anything yet.** First, show exactly what will be removed:

  > "Before I clear anything, here's what I'll delete:
  > [list each user-created folder and file found by list_documents]
  > Note: The Playbook/ folder itself is always kept, but its files and subfolders will be removed. Skills/ is never touched.
  > **Confirm: delete all of the above?** (yes / no / adjust the list)"

  Wait for an explicit "yes" before calling any delete tool.
  If the user says no or wants to adjust, revise the list and ask again.
  Only after confirmation, delete in this order:
  1. Playbook subfolders: `delete_folder("Playbook/India/")`, `delete_folder("Playbook/Singapore/")`, etc.
  2. Playbook files: `delete_document("Playbook/ndas.md")`, `delete_document("Playbook/positions.md")`, etc.
  3. Templates files: `delete_document("Templates/some-file.txt")` — delete files individually, NOT the folder
  4. User top-level folders: `delete_folder("Clients/")`, `delete_folder("Resources/")`, etc.
  5. `delete_document("anylegal.md")`

  ⛔ NEVER call `delete_folder("Playbook/")`, `delete_folder("Templates/")`, or `delete_folder("Skills/")` — these root folders are permanent and those calls will always fail.

  Then proceed with full setup.
- **Cancel (c)**: stop and tell them they can run `/setup` again any time

### Step 1 — Understand who they are

Ask ONE combined question. Do not split this into multiple messages:

> "To set up your workspace, I need to know a bit about you. Which of these best describes you?
>
> **(a) Law firm or solicitors' practice** — you advise clients on their contracts
> **(b) In-house legal team** — you're the legal function inside a company
> **(c) Commercial or procurement team** — you review contracts as part of a business role (not a lawyer)
> **(d) Solo entrepreneur or startup founder** — you're reviewing contracts for your own business
> **(e) Individual** — personal matters: tenancy, employment, consumer contracts
>
> Also briefly tell me: what kinds of contracts or legal matters do you deal with most?"

Wait for the user's response before doing anything.

### Step 1.5 — Grounding research (conditional)

Before creating any files, check whether the profile is specific enough to risk hallucination in the playbook.

**Run 1–2 targeted `web_search` calls when ALL of the following are true:**
- They named a specific industry vertical (e.g. neobank, crypto exchange, insurtech, proptech, BNPL, digital asset platform)
- AND a specific jurisdiction or region (e.g. Singapore, Indonesia, SEA, UAE, UK)
- AND they have a legal or semi-legal role where accuracy matters (law firm, in-house counsel, compliance)

**Skip this step when:**
- The profile is generic (e.g. "small business owner", "freelancer", "general commercial")
- The jurisdiction is well-covered by training data and regulations are stable (e.g. English law M&A, US SaaS contracts)
- They gave very little information and you need to act on what you have

**What to search for (keep it to 2 searches maximum):**
1. Current regulatory framework for their vertical + jurisdiction: e.g. `"neobank MAS licensing requirements 2025"` or `"OJK digital bank regulations Indonesia"`
2. Typical contract types and deal structures for that vertical: e.g. `"neobank vendor contracts sponsor bank agreement"` or `"fintech SPA investor rights SEA"`

**How to use the results:**
- Ground folder structure in actual deal stages / contract types used in that vertical
- Ground playbook clause positions in current regulatory requirements (e.g. MAS PDPA obligations, OJK capital requirements)
- Catch gaps your training data might have missed (e.g. a new licensing regime, recently changed cap table rules)

Do not narrate the search to the user. Just do it silently and use the results to improve what you generate next. If search results add nothing useful, proceed with training knowledge.

### Step 2 — Create folder structure

Based on their answer, use `create_folder` to create the appropriate folders:

| Profile | Folders to create |
|---------|-------------------|
| Law firm | `Clients/`, `Research/`, `Precedents/` |
| In-house legal | `Contracts/Vendor/`, `Contracts/Customer/`, `Policies/` |
| Commercial / procurement | `Vendor Agreements/`, `Customer Contracts/`, `NDAs/`, `Procurement/` |
| Solo entrepreneur | `Contracts/`, `Client Agreements/`, `NDAs/` |
| Individual | `Rental/`, `Employment/`, `Personal/`, `NDAs/` |

Note: `Templates/` always exists as a system folder — never call `create_folder("Templates/")`. You may create subfolders inside it (e.g. `Templates/NDAs/`, `Templates/SaaS/`) if the user's profile warrants it.

If they mentioned specific practice areas or industries, adjust accordingly — these are starting points, not rigid rules.

Say something brief as you create each folder: "Setting up your folder structure…"

### Step 3 — Write anylegal.md

Use `create_document(path="anylegal.md", ...)` to write a personalised root-level instructions file. The path MUST be exactly `"anylegal.md"` — never inside a folder (e.g. NOT `"SomeFolder/anylegal.md"`). The root `anylegal.md` is what appears as "Instructions" in the sidebar. Write it as if the user wrote it themselves — first person, their words, their context.

The file should follow this structure:

```
## About Me

[1-2 sentences: who they are, their organisation, their role]

## My Role in Contracts

[Their typical position: buyer/vendor/landlord/tenant/advisor. Risk posture if mentioned, otherwise default to "moderate".]

## Jurisdictions

[Jurisdictions they mentioned, or ask if not clear. If truly unknown, leave a placeholder.]

## How I Like to Work

[Communication style based on their profile:
- Law firm / in-house: assume legal experience, be concise and technical
- Commercial team: use plain language, explain legal terms
- Solo founder: plain language, flag unusual terms, cost-conscious
- Individual: plain language, consumer protection angle]
```

Do not write bracket placeholders — fill in real content based on what they told you.

### Step 4 — Create a starter playbook

Create `Playbook/<name>.md` with a meaningful H1 heading and 3–4 clause positions relevant to their most common contract type.

The H1 becomes the display name in the sidebar — make it descriptive:
- Law firm: `# Commercial Contracts — Standard Positions`
- In-house (as buyer): `# Vendor Agreements — Standard Positions`
- In-house (as seller): `# Customer Contracts — Standard Positions`
- Commercial / procurement: `# Procurement — Standard Positions`
- Solo founder: `# Client Agreements — Standard Positions`
- Individual: `# Standard Positions`

For each clause, use the format:
```
## [Clause Name]

- **Our position**: What you want ideally
- **Red line**: What you will not accept
- **Acceptable**: What you can live with
```

Choose clauses that actually matter for their profile. Examples:
- **Indemnification** — nearly always relevant
- **Limitation of Liability** — nearly always relevant
- **Termination** — for most commercial contracts
- **Confidentiality** — for most commercial contracts
- **Payment Terms** — for procurement / client agreements
- **IP Ownership** — for consulting / SaaS / employment

Use sensible defaults — not blank placeholders. Fill in real positions based on their profile and typical market practice.

### Step 5 — Confirm and orient

Give the user a clear summary of what was created and what to do next:

"Your workspace is set up. Here's what I created:

📁 **Folders**: [list]
✦ **Instructions** (`anylegal.md`): personalised with your context — the AI reads this before every conversation
📋 **Playbook** (`Playbook/<name>.md`): your starter negotiating positions

**What to do next:**
1. Open **Instructions** in the sidebar and review — add anything I missed, then Save
2. Upload a contract and type `/review` to run your first contract review
3. Update your Playbook as you develop your actual positions

You can run `/setup` again any time to adjust your workspace."

## Output Format

Conversational. Brief progress notes as you work ("Creating your folder structure… ✓"). End with the summary above.

## Guidelines

- Ask only what you need. One question, then act.
- Use the user's exact words when writing anylegal.md — do not over-formalise or over-engineer it.
- If they mentioned specific industries, clients, jurisdictions, or contract types, use them.
- Playbook positions should be real defaults, not `[Your position here]` placeholders.
- The whole setup should feel like talking to a smart assistant, not filling in a bureaucratic form.
- If the user says something like "I'm a startup founder building a SaaS product", their role is vendor, jurisdiction is probably their home country, and common contracts are customer agreements, NDAs, and employment/freelancer agreements — act on that without asking again.
- If jurisdiction is genuinely unclear (e.g. individual with no indication), ask as part of step 1 or add a polite note at the end: "I left jurisdiction as a placeholder in your Instructions — update it when you know."
