import Image from "next/image";
import { cn } from "@/lib/utils";

interface BrandLogoProps {
  className?: string;
  priority?: boolean;
}

export function BrandLogo({ className, priority = false }: BrandLogoProps) {
  return (
    <Image
      src="/siong-logo.jpg"
      width={202}
      height={64}
      alt="Siong Construction"
      className={cn("h-[64px] w-[202px] object-fill", className)}
      priority={priority}
      sizes="202px"
    />
  );
}
