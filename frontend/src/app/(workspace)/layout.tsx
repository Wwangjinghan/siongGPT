import { AppShell } from "@/components/layout/AppShell";
import { ProtectedWorkspace } from "@/components/auth/ProtectedWorkspace";

export default function WorkspaceLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <ProtectedWorkspace>
      <AppShell>{children}</AppShell>
    </ProtectedWorkspace>
  );
}
