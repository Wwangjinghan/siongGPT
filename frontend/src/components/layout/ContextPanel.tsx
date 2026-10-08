import { cn } from "@/lib/utils";

export function ContextPanel({ className, children }: React.HTMLAttributes<HTMLElement>) {
  return <aside aria-label="Related context" className={cn("min-w-0", className)}>{children}</aside>;
}
