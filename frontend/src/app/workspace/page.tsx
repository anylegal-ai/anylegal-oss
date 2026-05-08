import { Metadata } from 'next';
import { Suspense } from 'react';
import WorkspaceClient from './WorkspaceClient';

export const metadata: Metadata = {
  title: 'Workspace | ANYLEGAL.AI',
  description: 'Your Legal AI Operating System - Research, Review, Revise, and Draft legal documents.',
  robots: {
    index: false,
    follow: false,
    googleBot: {
      index: false,
      follow: false,
      'max-image-preview': 'none',
      'max-snippet': 0,
    },
  },
};

export default function WorkspacePage() {
  return (
    <Suspense>
      <WorkspaceClient />
    </Suspense>
  );
}
