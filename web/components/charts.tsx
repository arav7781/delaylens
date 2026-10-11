"use client";

import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

/* Chart conventions (dataviz skill): one accent hue for what the title is about, everything else
   quiet grey; hairline solid grid; <=24px bars with 4px rounded data-end; 2px lines; a tooltip on
   every chart; text in ink tokens, never in the series colour. */

const AXIS = { fontSize: 11, fill: "var(--muted)" };
const tick = (v: number) => (Math.abs(v) >= 1e6 ? `${v / 1e6}M` : Math.abs(v) >= 1e3 ? `${v / 1e3}K` : `${v}`);

type TipPayload = { name?: string; value?: number | string; color?: string; dataKey?: string };

function TipBox({ active, payload, label, unit = "", digits = 1 }: {
  active?: boolean; payload?: TipPayload[]; label?: string | number; unit?: string; digits?: number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-sm">
      <div className="mb-1 text-ink-2">{label}</div>
      {payload.map((p) => (
        <div key={String(p.dataKey)} className="flex items-center gap-2">
          <span className="inline-block h-0.5 w-3" style={{ background: p.color }} />
          <span className="font-semibold text-ink tnum">
            {typeof p.value === "number" ? p.value.toLocaleString("en-US", { maximumFractionDigits: digits }) : p.value}
            {unit}
          </span>
          <span className="text-ink-2">{p.name}</span>
        </div>
      ))}
    </div>
  );
}

/** Ranked horizontal bars in plain HTML: label, bar, value at the tip. */
export function BarList({
  rows, max, unit = "%", digits = 1, highlight = [], reference, referenceLabel, sub,
}: {
  rows: { label: string; value: number; note?: string }[];
  max?: number;
  unit?: string;
  digits?: number;
  highlight?: string[];
  reference?: number;
  referenceLabel?: string;
  sub?: (label: string) => string | undefined;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const top = max ?? Math.max(...rows.map((r) => r.value), reference ?? 0) * 1.05;
  return (
    <div>
      <ul className="flex flex-col gap-1">
        {rows.map((r) => {
          const on = highlight.includes(r.label);
          return (
            <li
              key={r.label}
              className="grid items-center gap-2 rounded text-xs"
              style={{ gridTemplateColumns: "minmax(0,36fr) minmax(0,52fr) minmax(0,12fr)", background: hover === r.label ? "var(--surface-2)" : undefined }}
              onMouseEnter={() => setHover(r.label)}
              onMouseLeave={() => setHover(null)}
              title={`${r.label}: ${r.value.toFixed(digits)}${unit}${r.note ? ` · ${r.note}` : ""}`}
              tabIndex={0}
            >
              <span className={`min-w-0 py-0.5 leading-tight ${on ? "font-semibold text-ink" : "text-ink-2"}`}>
                <span className="block">{r.label}</span>
                {sub?.(r.label) && <span className="block text-[10.5px] font-normal text-muted">{sub(r.label)}</span>}
              </span>
              <span className="relative h-4">
                <span
                  className="absolute left-0 top-0.5 h-3 rounded-r"
                  style={{ width: `${Math.max(0.5, (r.value / top) * 100)}%`, background: on ? "var(--accent)" : "var(--gray-mark)" }}
                />
                {reference !== undefined && (
                  <span className="absolute -bottom-0.5 -top-0.5 w-px" style={{ left: `${(reference / top) * 100}%`, background: "var(--ink-2)" }} />
                )}
              </span>
              <span className={`text-right tnum ${on ? "font-semibold" : "text-ink-2"}`}>
                {(Math.round(r.value * 10 ** digits + 1e-9) / 10 ** digits).toFixed(digits)}
                {unit}
              </span>
            </li>
          );
        })}
      </ul>
      {reference !== undefined && (
        <div className="mt-2 flex items-center gap-1.5 text-[11px] text-ink-2">
          <span className="inline-block h-3 w-px" style={{ background: "var(--ink-2)" }} />
          {referenceLabel ?? "reference"} {reference.toFixed(digits)}
          {unit}
        </div>
      )}
    </div>
  );
}

/** Single- or multi-series line over time (one y axis only). */
export function TrendLine({
  data, x, series, unit = "", height = 240, digits = 1, yDomain, refY, refLabel, yTicks,
}: {
  data: Record<string, unknown>[];
  x: string;
  series: { key: string; name: string; color?: string }[];
  unit?: string;
  height?: number;
  digits?: number;
  yDomain?: [number | "auto", number | "auto"];
  refY?: number;
  refLabel?: string;
  yTicks?: number[];
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey={x} tick={AXIS} tickLine={false} axisLine={{ stroke: "var(--axis)" }} minTickGap={24} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} domain={yDomain ?? ["auto", "auto"]} ticks={yTicks} tickFormatter={(v) => `${tick(v)}${unit}`} width={52} />
          <Tooltip content={<TipBox unit={unit} digits={digits} />} cursor={{ stroke: "var(--axis)" }} />
          {refY !== undefined && (
            <ReferenceLine y={refY} stroke="var(--ink-2)" strokeWidth={1}
              label={{ value: refLabel, position: "insideTopRight", fontSize: 10, fill: "var(--ink-2)" }} />
          )}
          {series.length > 1 && <Legend iconType="plainline" wrapperStyle={{ fontSize: 11 }} formatter={(v) => <span style={{ color: "var(--ink-2)" }}>{v}</span>} />}
          {series.map((s, i) => (
            <Line key={s.key} type="monotone" dataKey={s.key} name={s.name} stroke={s.color ?? (i === 0 ? "var(--accent)" : "var(--gray-mark)")}
              strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface)" }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Vertical columns; colour per bar from `colorOf` (accent vs grey). */
export function Columns({
  data, x, y, name, unit = "", height = 220, colorOf, digits = 1, series,
}: {
  data: Record<string, unknown>[];
  x: string;
  y?: string;
  name?: string;
  unit?: string;
  height?: number;
  digits?: number;
  colorOf?: (row: Record<string, unknown>) => string;
  series?: { key: string; name: string; color: string }[];
}) {
  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -8 }} barGap={2}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis dataKey={x} tick={AXIS} tickLine={false} axisLine={{ stroke: "var(--axis)" }} interval="preserveStartEnd" minTickGap={12} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={(v) => `${tick(v)}${unit}`} width={52} />
          <Tooltip content={<TipBox unit={unit} digits={digits} />} cursor={{ fill: "var(--surface-2)" }} />
          {series ? (
            <>
              <Legend iconType="square" wrapperStyle={{ fontSize: 11 }} formatter={(v) => <span style={{ color: "var(--ink-2)" }}>{v}</span>} />
              {series.map((s) => (
                <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false} />
              ))}
            </>
          ) : (
            <Bar dataKey={y!} name={name} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}
              shape={(props: unknown) => {
                const p = props as { x: number; y: number; width: number; height: number; payload: Record<string, unknown> };
                const fill = colorOf ? colorOf(p.payload) : "var(--accent)";
                const r = Math.min(4, p.height);
                return (
                  <path fill={fill}
                    d={`M${p.x},${p.y + p.height}V${p.y + r}Q${p.x},${p.y} ${p.x + r},${p.y}H${p.x + p.width - r}Q${p.x + p.width},${p.y} ${p.x + p.width},${p.y + r}V${p.y + p.height}Z`} />
                );
              }} />
          )}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Sequential single-hue heatmap (blue), value labels inside cells with contrast-picked ink. */
export function Heatmap({
  rows, cols, value, rowLabel, colLabel, unit = "%", min, max, note,
}: {
  rows: string[];
  cols: string[];
  value: (r: string, c: string) => { v: number; n: number } | undefined;
  rowLabel: string;
  colLabel: string;
  unit?: string;
  min: number;
  max: number;
  note?: string;
}) {
  const shade = (v: number) => {
    const t = Math.max(0, Math.min(1, (v - min) / (max - min)));
    return { bg: `color-mix(in oklab, #cde2fb ${Math.round((1 - t) * 100)}%, #0d366b)`, ink: t > 0.5 ? "#ffffff" : "#0b0b0b" };
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate text-xs" style={{ borderSpacing: 2 }}>
        <thead>
          <tr>
            <th className="px-2 py-1 text-left font-medium text-ink-2">{rowLabel} \ {colLabel}</th>
            {cols.map((c) => (
              <th key={c} className="px-1 py-1 text-center font-medium text-ink-2">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody className="tnum">
          {rows.map((r) => (
            <tr key={r}>
              <td className="whitespace-nowrap px-2 py-1 text-ink-2">{r}</td>
              {cols.map((c) => {
                const cell = value(r, c);
                if (!cell) return <td key={c} className="rounded text-center text-muted">–</td>;
                const s = shade(cell.v);
                return (
                  <td key={c} className="rounded px-1 py-1 text-center" style={{ background: s.bg, color: s.ink }}
                    title={`${r} · ${c}: ${cell.v.toFixed(1)}${unit} late (${cell.n.toLocaleString()} orders)`}>
                    {cell.v.toFixed(0)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 flex items-center gap-2 text-[11px] text-ink-2">
        <span>{min}{unit}</span>
        <span className="h-2 w-32 rounded" style={{ background: "linear-gradient(90deg,#cde2fb,#0d366b)" }} />
        <span>{max}{unit}</span>
        {note && <span className="ml-2 text-muted">{note}</span>}
      </div>
    </div>
  );
}

/** 100% stacked bar per row: delivery outcome mix. Status colours with a legend. */
export function OutcomeMix({ rows }: { rows: { label: string; late: number; on_time: number; advance: number; canceled: number }[] }) {
  const parts = [
    { key: "late", name: "Late", color: "var(--critical)" },
    { key: "on_time", name: "On time", color: "var(--s1)" },
    { key: "advance", name: "Early (advance)", color: "var(--s3)" },
    { key: "canceled", name: "Canceled", color: "var(--gray-mark)" },
  ] as const;
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-3 text-[11px] text-ink-2">
        {parts.map((p) => (
          <span key={p.key} className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: p.color }} />
            {p.name}
          </span>
        ))}
      </div>
      <div className="flex flex-col gap-2">
        {rows.map((r) => {
          const total = r.late + r.on_time + r.advance + r.canceled;
          return (
            <div key={r.label} className="grid items-center gap-2 text-xs" style={{ gridTemplateColumns: "30% 70%" }}>
              <span className="text-ink-2">{r.label}</span>
              <div className="flex h-5 gap-[2px] overflow-hidden rounded">
                {parts.map((p) => {
                  const v = r[p.key];
                  const pct = (100 * v) / total;
                  if (pct <= 0) return null;
                  return (
                    <div key={p.key} className="flex items-center justify-center text-[10px] font-medium"
                      style={{ width: `${pct}%`, background: p.color, color: p.key === "advance" || p.key === "canceled" ? "#0b0b0b" : "#fff" }}
                      title={`${r.label} · ${p.name}: ${pct.toFixed(1)}% (${v.toLocaleString()} orders)`}>
                      {pct >= 9 ? `${pct.toFixed(0)}%` : ""}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
