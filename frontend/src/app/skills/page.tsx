import { Metadata } from 'next';
import SkillsClient from './SkillsClient';

export const metadata: Metadata = {
  title: 'Skills | ANYLEGAL.AI — Portable AI Task Instructions',
  description: 'SKILL.md: portable, version-controlled instruction files for legal AI tasks. Review contracts, research law, compare documents, draft agreements. Open format, no vendor lock-in.',
  keywords: [
    'SKILL.md',
    'legal AI skills',
    'portable AI instructions',
    'contract review skill',
    'legal research skill',
    'document comparison',
    'legal drafting AI',
    'open source legal AI',
    'AI task automation',
  ],
  openGraph: {
    title: 'Skills | ANYLEGAL.AI — Portable AI Task Instructions',
    description: 'Portable, open instruction files that tell the AI agent how to perform specialized legal tasks. No vendor lock-in.',
    type: 'website',
  },
};

export default function SkillsPage() {
  return <SkillsClient />;
}
