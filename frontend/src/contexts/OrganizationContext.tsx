'use client';

import { createContext, useContext, ReactNode } from 'react';

type Organization = null;

type OrganizationContextShape = {
  organization: Organization;
  isDemo: boolean;
  isOrgUser: boolean;
};

const defaultValue: OrganizationContextShape = {
  organization: null,
  isDemo: false,
  isOrgUser: false,
};

const OrganizationContext = createContext<OrganizationContextShape>(defaultValue);

export function OrganizationProvider({ children }: { children: ReactNode }) {
  return <OrganizationContext.Provider value={defaultValue}>{children}</OrganizationContext.Provider>;
}

export function useOrganization() {
  return useContext(OrganizationContext);
}
