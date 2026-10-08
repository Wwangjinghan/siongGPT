"use client";

import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export function Checkbox({ className, ...props }: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root className={cn("focus-ring peer flex size-7 shrink-0 items-center justify-center rounded-md border border-line bg-white data-[state=checked]:border-brand-green data-[state=checked]:bg-brand-green data-[state=checked]:text-white", className)} {...props}>
      <CheckboxPrimitive.Indicator><Check size={18} strokeWidth={2.8} /></CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
