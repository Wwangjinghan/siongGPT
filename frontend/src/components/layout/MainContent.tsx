import { cn } from "@/lib/utils";

export function MainContent({ className, children }: React.HTMLAttributes<HTMLElement>) {
  return <main className={cn("min-w-0", className)}>{children}</main>;
}
