import { Check, SquareCheckBig } from "lucide-react";

export function RecommendedActions({ actions }: { actions: string[] }) {
  return (
    <section className="flex gap-5 border-t border-line px-7 py-3 sm:px-8">
      <div className="flex size-12 shrink-0 items-center justify-center rounded-full bg-[#eaf1fb] text-brand-navy"><SquareCheckBig size={23} /></div>
      <div className="pt-0.5 text-[13px]">
        <h3 className="mb-2 text-[14px] font-bold">Recommended Actions</h3>
        <ul className="space-y-1.5">
          {actions.map((action) => (
            <li key={action} className="flex items-center gap-3">
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-[#e7f0ff] text-action"><Check size={13} strokeWidth={2.6} /></span>
              {action}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
