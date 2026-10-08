import type { LucideIcon } from "lucide-react";
import { BarChart3, FileText, UsersRound } from "lucide-react";
import { LoginCard } from "@/components/auth/LoginCard";
import { PublicOnlyRoute } from "@/components/auth/PublicOnlyRoute";
import { BrandLogo } from "@/components/layout/BrandLogo";

interface Capability {
  title: string;
  description: string;
  icon: LucideIcon;
}

const capabilities: Capability[] = [
  { title: "Find answers faster", description: "From company knowledge", icon: FileText },
  { title: "Work smarter together", description: "Across teams and projects", icon: UsersRound },
  { title: "Build a stronger tomorrow", description: "With knowledge that works", icon: BarChart3 },
];

export default function LoginPage() {
  return (
    <PublicOnlyRoute>
      <main className="relative min-h-screen overflow-hidden bg-[#f8fbfd] lg:h-dvh lg:min-h-[760px]">
      <div aria-hidden className="construction-art pointer-events-none absolute bottom-0 left-0 h-[390px] w-[665px] bg-[position:left_bottom] opacity-75" />

      <header className="relative z-10 flex h-[100px] items-center justify-between px-8 lg:px-12">
        <BrandLogo priority className="h-[68px] w-[214px]" />
        <div className="hidden text-[15px] leading-[1.45] text-muted-blue sm:block">
          <p>Knowledge for People.</p><p>Solutions for a Stronger Tomorrow.</p>
          <span className="mt-3 block h-0.5 w-9 bg-brand-green" />
        </div>
      </header>

      <div className="relative z-10 grid min-h-[calc(100vh-100px)] grid-cols-1 gap-12 px-8 pb-8 lg:grid-cols-[36%_64%] lg:items-center lg:px-12 lg:pb-8">
        <section className="max-w-[505px] px-0 lg:-mt-3 lg:pl-8">
          <p className="mb-3 text-[18px] font-semibold tracking-[.32em] text-[#8797b4]">SIONG GPT</p>
          <h2 className="text-[46px] font-extrabold leading-[1.08] tracking-[-.025em] text-brand-navy lg:text-[47px]">Enterprise<br />Knowledge<br />Workspace</h2>
          <p className="mt-5 max-w-[410px] text-[19px] leading-[1.38] text-muted-blue">Access trusted knowledge, policies,<br className="hidden xl:block" /> project information and internal expertise<br className="hidden xl:block" /> — all in one place.</p>

          <ul className="mt-7 space-y-4">
            {capabilities.map(({ title, description, icon: Icon }) => (
              <li key={title} className="flex items-center gap-5">
                <span className="flex size-[59px] shrink-0 items-center justify-center rounded-xl bg-brand-green-light text-brand-green"><Icon size={28} strokeWidth={2} /></span>
                <span><strong className="block text-[16px]">{title}</strong><span className="text-[14px] text-muted-blue">{description}</span></span>
              </li>
            ))}
          </ul>

          <div className="relative mt-14 hidden text-[11px] font-semibold tracking-[.3em] text-[#657896] lg:block">
            <p>BUILDING</p><p>A BETTER</p><p>TOMORROW</p><span className="mt-3 block h-0.5 w-12 bg-brand-green" />
          </div>
        </section>

        <div className="flex justify-center lg:justify-start lg:pl-16"><LoginCard /></div>
      </div>
      </main>
    </PublicOnlyRoute>
  );
}
