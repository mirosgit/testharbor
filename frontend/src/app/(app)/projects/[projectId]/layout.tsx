import { ProjectGuard } from "@/components/project-guard";

export default async function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ProjectGuard projectId={Number(projectId)}>{children}</ProjectGuard>;
}
