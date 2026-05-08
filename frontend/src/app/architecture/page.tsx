import { Metadata } from 'next';
import ArchitectureClient from './ArchitectureClient';

export const metadata: Metadata = {
  title: 'Architecture | ANYLEGAL.AI — How the Agentic Loop Works',
  description: 'How AnyLegal\'s AI agent works: one agentic loop, five context layers, 12 open-source tools. Configure with agents.md, SKILL.md, and playbooks. No vendor lock-in.',
  keywords: [
    'legal AI architecture',
    'agentic loop',
    'AI agent tools',
    'legal AI open source',
    'SKILL.md',
    'agents.md',
    'contract review AI',
    'legal playbook',
    'AI context layers',
  ],
  openGraph: {
    title: 'Architecture | ANYLEGAL.AI — How the Agentic Loop Works',
    description: 'One agentic loop. Five context layers. 12 open-source tools. Your configuration, your control.',
    type: 'website',
  },
};

export default function ArchitecturePage() {
  return <ArchitectureClient />;
}
