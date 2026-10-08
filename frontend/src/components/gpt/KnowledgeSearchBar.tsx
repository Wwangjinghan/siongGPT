"use client";

import type { FormEvent } from "react";
import { Search, Send } from "lucide-react";

interface KnowledgeSearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading?: boolean;
}

export function KnowledgeSearchBar({ value, onChange, onSubmit, loading = false }: KnowledgeSearchBarProps) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <section aria-label="Knowledge search">
      <form onSubmit={handleSubmit} className="card-shadow flex h-[64px] items-center rounded-xl border border-line bg-white p-2 pl-4">
        <Search aria-hidden className="shrink-0 text-[#657899]" size={27} strokeWidth={1.8} />
        <label htmlFor="knowledge-query" className="sr-only">Ask Siong GPT about company knowledge</label>
        <input
          id="knowledge-query"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Ask Siong GPT about company knowledge..."
          className="focus-ring min-w-0 flex-1 rounded-md border-0 bg-transparent px-4 text-[16px] text-brand-navy outline-none placeholder:text-[#71809e]"
        />
        <button type="submit" disabled={loading} className="focus-ring flex h-12 w-14 shrink-0 items-center justify-center rounded-[10px] bg-brand-green text-white shadow-sm transition-colors hover:bg-[#1d7548] disabled:opacity-60" aria-label="Send question">
          <Send size={24} strokeWidth={1.8} />
        </button>
      </form>
      <p className="mt-2.5 text-[13px] text-muted-blue">Search SOPs, policies, forms, project documents and internal systems</p>
    </section>
  );
}
