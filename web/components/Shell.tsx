"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import {
  Bot, Boxes, Database, Gauge, Globe2, MessageSquare, PackageSearch, Route, Truck, X,
} from "lucide-react";
import { useApi } from "@/lib/api";
import Copilot from "@/components/Copilot";

const NAV = [
  { href: "/", label: "Overview", icon: Gauge },
  { href: "/regions", label: "Regions & markets", icon: Globe2 },
  { href: "/shipping", label: "Shipping modes", icon: Truck },
  { href: "/products", label: "Products & traffic", icon: Boxes },
  { href: "/scenarios", label: "Promise what-if", icon: Route },
  { href: "/orders", label: "Open orders at risk", icon: PackageSearch },
  { href: "/pipeline", label: "Big Data pipeline", icon: Database },
  { href: "/copilot", label: "Copilot", icon: Bot },
];

type Health = { mongo: boolean; hadoop: boolean; llm_model: string };

function Dot({ ok, label }: { ok: boolean | undefined; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
      <span
        className="inline-block h-2 w-2 rounded-full"
        style={{ background: ok === undefined ? "var(--muted)" : ok ? "var(--good)" : "var(--critical)" }}
        aria-hidden
      />
      {label}
      <span className="sr-only">{ok ? "online" : "offline"}</span>
    </span>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const { data: health } = useApi<Health>("/api/health");

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-border bg-surface px-3 py-5 md:flex">
        <Link href="/" className="mb-6 flex items-center gap-2 px-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-sm font-bold text-white">DL</span>
          <span>
            <span className="block text-sm font-semibold">DelayLens</span>
            <span className="block text-[11px] text-muted">DataCo delivery intelligence</span>
          </span>
        </Link>
        <nav className="flex flex-col gap-0.5">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm ${
                  active ? "bg-surface-2 font-medium text-ink" : "text-ink-2 hover:bg-surface-2"
                }`}
              >
                <Icon size={16} strokeWidth={1.75} />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto flex flex-col gap-1.5 border-t border-border px-2 pt-4">
          <Dot ok={health?.hadoop} label="Hadoop 3.5 (HDFS + YARN)" />
          <Dot ok={health?.mongo} label="MongoDB 7" />
          <Dot ok={health ? true : undefined} label={health?.llm_model ?? "LLM gateway"} />
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-border bg-page/90 px-4 py-2.5 backdrop-blur md:hidden">
          <span className="text-sm font-semibold">DelayLens</span>
          <select
            className="ml-auto rounded-md border border-border bg-surface px-2 py-1 text-sm"
            value={path}
            onChange={(e) => (window.location.href = e.target.value)}
            aria-label="Navigate"
          >
            {NAV.map((n) => (
              <option key={n.href} value={n.href}>
                {n.label}
              </option>
            ))}
          </select>
        </header>
        <main className="mx-auto max-w-[1280px] px-4 py-6 md:px-8">{children}</main>
      </div>

      {path !== "/copilot" && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-5 right-5 z-30 flex items-center gap-2 rounded-full bg-accent px-4 py-3 text-sm font-medium text-white shadow-lg"
        >
          <MessageSquare size={16} /> Ask Copilot
        </button>
      )}
      {open && (
        <div className="fixed inset-0 z-40 flex justify-end bg-black/20" onClick={() => setOpen(false)}>
          <div
            className="flex h-full w-full max-w-[520px] flex-col border-l border-border bg-surface"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <span className="flex items-center gap-2 text-sm font-semibold">
                <Bot size={16} /> DelayLens Copilot
              </span>
              <button onClick={() => setOpen(false)} aria-label="Close copilot" className="text-ink-2">
                <X size={18} />
              </button>
            </div>
            <Copilot compact />
          </div>
        </div>
      )}
    </div>
  );
}
