import * as React from "react";
import { cn } from "@/lib/utils";

export function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn("focus-ring h-12 w-full rounded-lg border border-line bg-white px-4 text-brand-navy placeholder:text-[#8b99b3]", className)}
      {...props}
    />
  );
}
