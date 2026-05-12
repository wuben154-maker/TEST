import { createContext, useContext, type ReactNode } from 'react';
import { useProjects } from '@/hooks/useProjects';

export type WorkspaceProjectsApi = ReturnType<typeof useProjects>;

const WorkspaceProjectsContext = createContext<WorkspaceProjectsApi | null>(null);

export function WorkspaceProjectsProvider({ children }: { children: ReactNode }) {
  const value = useProjects();
  return (
    <WorkspaceProjectsContext.Provider value={value}>{children}</WorkspaceProjectsContext.Provider>
  );
}

export function useWorkspaceProjects(): WorkspaceProjectsApi {
  const ctx = useContext(WorkspaceProjectsContext);
  if (!ctx) {
    throw new Error('useWorkspaceProjects must be used within WorkspaceProjectsProvider');
  }
  return ctx;
}
