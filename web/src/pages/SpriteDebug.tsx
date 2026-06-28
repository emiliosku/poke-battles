import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE } from "../api";
import { cdnUrlForSlug } from "../spriteDebugUtil";

// Mirror of packages/core/src/pokecore/sprite_status.py FOLDER_EXT.
// Order matters: the leftmost slot is the "preferred" sprite the
// production PokemonSprite component would try first.
const FOLDERS: Array<[string, string]> = [
  ["gen5ani", "gif"],
  ["ani", "gif"],
  ["dex", "png"],
  ["gen5", "png"],
  ["home", "png"],
  ["bw", "png"],
  ["xyani", "gif"],
];

export interface SpriteResult {
  species_id: string;
  name: string;
  types: string[];
  canonical_slug: string;
  derived_slug: string;
  canonical_hits: string[];
  derived_hits: string[];
  is_cap: boolean;
}

export interface SpriteStatus {
  checked_at: number;
  count: number;
  duration_s: number;
  results: SpriteResult[];
}

type CellState = "ok" | "missing";

// A probe hit is the literal string ``"<folder> <slug>.<ext>"`` from
// the backend. Each slot pairs a folder with whatever hit (if any)
// the probe recorded for that folder.
interface SlotDescriptor {
  folder: string;
  ext: string;
  hit: string | null;
}

// Build a per-folder lookup so each FOLDERS slot is matched to its
// own hit by folder name, not by index. The probe returns hits in
// FOLDER_EXT order but with missing folders excluded, so ``hits[i]``
// is NOT guaranteed to correspond to ``FOLDERS[i]`` — e.g. for
// aerodactyl-mega the gen5ani probe 404s, so ``hits[0]`` is the
// ``ani`` hit and indexing by position would put the ani image in
// the gen5ani slot. Looking up by folder keeps the slot label and
// the image in agreement.
export function slotsFor(slug: string, hits: string[]): SlotDescriptor[] {
  void slug;
  const byFolder = new Map<string, string>();
  for (const hit of hits) {
    const space = hit.indexOf(" ");
    if (space < 0) continue;
    const folder = hit.slice(0, space);
    const filename = hit.slice(space + 1);
    if (folder && filename) byFolder.set(folder, hit);
  }
  return FOLDERS.map(([folder, ext]) => ({
    folder,
    ext,
    hit: byFolder.get(folder) ?? null,
  }));
}

function cellStateFor(result: SpriteResult): CellState {
  if (result.canonical_hits.length > 0 || result.derived_hits.length > 0) return "ok";
  return "missing";
}

function SpriteCell({
  result,
  variant,
}: {
  result: SpriteResult;
  variant: "canonical" | "derived";
}) {
  const slug = variant === "canonical" ? result.canonical_slug : result.derived_slug;
  const hits = variant === "canonical" ? result.canonical_hits : result.derived_hits;

  // Vanilla species have derived_slug === canonical_slug. The
  // backend leaves derived_hits empty in that case; we collapse the
  // derived cell to avoid rendering the same 7-slot strip twice.
  if (variant === "derived" && result.derived_slug === result.canonical_slug) {
    return (
      <div className="sprite-cell sprite-cell--collapsed">
        <div className="sprite-cell-label">
          <code>derived</code>
          <span className="muted">(same as canonical)</span>
        </div>
      </div>
    );
  }

  const slots = slotsFor(slug, hits);
  const hitCount = slots.filter((s) => s.hit !== null).length;
  const state: CellState = hitCount > 0 ? "ok" : "missing";

  return (
    <div className={`sprite-cell sprite-cell--${state}`}>
      <div className="sprite-cell-label">
        <div className="sprite-cell-label-row">
          <code>{variant}</code>
          <span className="sprite-cell-count" data-testid="sprite-cell-count">
            {hitCount}/{slots.length}
          </span>
        </div>
        <span>{slug}</span>
      </div>
      <div className="sprite-cell-strip" data-testid="sprite-cell-strip">
        {slots.map((slot) => (
          <Slot key={slot.folder} slot={slot} speciesName={result.name} />
        ))}
      </div>
    </div>
  );
}

function Slot({ slot, speciesName }: { slot: SlotDescriptor; speciesName: string }) {
  const url = slot.hit ? cdnUrlForSlug(slot.hit) : null;
  return (
    <div
      className={`sprite-slot ${slot.hit ? "sprite-slot--hit" : "sprite-slot--miss"}`}
      title={slot.hit ? `${slot.folder}.${slot.ext}` : `${slot.folder}.${slot.ext} (404)`}
      data-folder={slot.folder}
      data-state={slot.hit ? "hit" : "miss"}
    >
      <div className="sprite-slot-art">
        {url ? (
          <img
            src={url}
            alt={`${speciesName} ${slot.folder}`}
            loading="lazy"
            decoding="async"
          />
        ) : (
          <span className="sprite-slot-miss-glyph" aria-label="404">·</span>
        )}
      </div>
      <span className="sprite-slot-folder">{slot.folder}</span>
    </div>
  );
}

function PokemonCard({
  result,
  onStatusChange,
}: {
  result: SpriteResult;
  onStatusChange: (speciesId: string, status: CellState) => void;
}) {
  const state = cellStateFor(result);
  useEffect(() => {
    onStatusChange(result.species_id, state);
  }, [result.species_id, state, onStatusChange]);

  return (
    <article className="sprite-card" data-species-id={result.species_id}>
      <header className="sprite-card-head">
        <strong>{result.name}</strong>
        <code>{result.species_id}</code>
        {result.is_cap && (
          <span className="badge cap" title="Create-A-Pokémon, not in the official games">CAP</span>
        )}
      </header>
      <div className="sprite-card-types">
        {result.types.map((t) => (
          <span key={t} className="badge">{t}</span>
        ))}
      </div>
      <div className="sprite-card-grid">
        <SpriteCell result={result} variant="canonical" />
        <SpriteCell result={result} variant="derived" />
      </div>
    </article>
  );
}

function VirtualizedGrid({
  items,
  renderItem,
  rowHeight,
  overscan = 4,
}: {
  items: SpriteResult[];
  renderItem: (item: SpriteResult, index: number) => React.ReactNode;
  rowHeight: number;
  overscan?: number;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(800);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => setScrollTop(el.scrollTop);
    el.addEventListener("scroll", onScroll, { passive: true });
    const ro = new ResizeObserver(() => setViewportHeight(el.clientHeight));
    ro.observe(el);
    setViewportHeight(el.clientHeight);
    return () => {
      el.removeEventListener("scroll", onScroll);
      ro.disconnect();
    };
  }, []);

  const startIdx = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
  const endIdx = Math.min(
    items.length,
    Math.ceil((scrollTop + viewportHeight) / rowHeight) + overscan,
  );
  const visible = items.slice(startIdx, endIdx);
  const totalHeight = items.length * rowHeight;
  const offsetY = startIdx * rowHeight;

  return (
    <div ref={scrollRef} className="sprite-grid-scroll" data-testid="sprite-grid">
      <div style={{ height: totalHeight, position: "relative" }}>
        <div style={{ position: "absolute", top: offsetY, left: 0, right: 0 }}>
          {visible.map((item, i) => (
            <div key={item.species_id} style={{ minHeight: rowHeight }}>
              {renderItem(item, startIdx + i)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function SpriteDebug() {
  const [status, setStatus] = useState<SpriteStatus | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [hideCap, setHideCap] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [perSpeciesStatus, setPerSpeciesStatus] = useState<Record<string, CellState>>({});

  const load = async (refresh = false) => {
    setLoading(true);
    setError("");
    if (refresh) setRefreshing(true);
    try {
      const url = `${API_BASE}/sprites/status${refresh ? "?refresh=true" : ""}`;
      const res = await fetch(url, { credentials: "include" });
      if (!res.ok) throw new Error(`status ${res.status}`);
      const data = (await res.json()) as SpriteStatus;
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const allTypes = useMemo(() => {
    if (!status) return [] as string[];
    const set = new Set<string>();
    for (const r of status.results) for (const t of r.types) set.add(t);
    return Array.from(set).sort();
  }, [status]);

  const filtered = useMemo(() => {
    if (!status) return [] as SpriteResult[];
    let out = status.results;
    if (q) {
      const needle = q.toLowerCase();
      out = out.filter(
        (r) => r.species_id.toLowerCase().includes(needle) || r.name.toLowerCase().includes(needle),
      );
    }
    if (typeFilter) {
      const needle = typeFilter.toLowerCase();
      out = out.filter((r) => r.types.some((t) => t.toLowerCase() === needle));
    }
    if (onlyFailed) {
      out = out.filter((r) => perSpeciesStatus[r.species_id] !== "ok");
    }
    if (hideCap) {
      out = out.filter((r) => !r.is_cap);
    }
    return out;
  }, [status, q, typeFilter, onlyFailed, hideCap, perSpeciesStatus]);

  const stats = useMemo(() => {
    if (!status) return { total: 0, ok: 0, missing: 0, totalSlots: 0 };
    let ok = 0;
    let missing = 0;
    let totalSlots = 0;
    for (const r of status.results) {
      const s = perSpeciesStatus[r.species_id];
      if (s === "ok") ok += 1;
      else missing += 1;
      // Each species contributes up to 2 cells; canonical always
      // renders, derived only when it differs from canonical.
      totalSlots += r.canonical_hits.length + r.derived_hits.length;
    }
    return { total: status.results.length, ok, missing, totalSlots };
  }, [status, perSpeciesStatus]);

  const handleStatus = (speciesId: string, st: CellState) => {
    setPerSpeciesStatus((prev) => {
      if (prev[speciesId] === st) return prev;
      return { ...prev, [speciesId]: st };
    });
  };

  const checkedAt = status
    ? new Date(status.checked_at * 1000).toLocaleString()
    : "";

  return (
    <main className="page sprite-debug">
      <section className="hero">
        <span className="eyebrow">Dev tools</span>
        <h1>Sprite coverage</h1>
        <p>
          For every species in the bundled Pokédex, the engine asks
          "does the Showdown CDN serve a sprite for this species, under
          either the canonical <code>species_id</code> or the derived
          <code>sprite_id</code>?". This page renders the answer side
          by side so you can spot the gaps at a glance. Dev-only —
          the route and the probe are stripped from production builds.
        </p>
      </section>

      {error && <div className="notice error" aria-live="polite">{error}</div>}

      <section className="card stack">
        <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
            <input
              className="field-input"
              type="search"
              placeholder="Filter by name or species id…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <select
              className="field-input"
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              aria-label="Type filter"
            >
              <option value="">All types</option>
              {allTypes.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <label className="row" style={{ gap: 6 }}>
              <input
                type="checkbox"
                checked={onlyFailed}
                onChange={(e) => setOnlyFailed(e.target.checked)}
              />
              <span>Only show failed</span>
            </label>
            <label className="row" style={{ gap: 6 }}>
              <input
                type="checkbox"
                checked={hideCap}
                onChange={(e) => setHideCap(e.target.checked)}
              />
              <span>Hide CAP</span>
            </label>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button
              className="button secondary"
              type="button"
              onClick={() => void load(true)}
              disabled={refreshing}
            >
              {refreshing ? "Re-probing CDN…" : "Refresh from CDN"}
            </button>
          </div>
        </div>
        <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
          <div className="row" style={{ gap: 12, flexWrap: "wrap" }}>
            <span><strong>{stats.total}</strong> total</span>
            <span style={{ color: "#86efac" }}><strong>{stats.ok}</strong> ok</span>
            <span style={{ color: "#fca5a5" }}><strong>{stats.missing}</strong> missing</span>
            <span className="muted">
              <strong>{stats.totalSlots}</strong> sprite hits across all folders
            </span>
          </div>
          {status && (
            <span className="muted">
              Probed in {status.duration_s.toFixed(1)}s · {checkedAt}
            </span>
          )}
        </div>
      </section>

      {loading && !status && <p className="muted">Probing Showdown CDN…</p>}

      {status && (
        <section className="card stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h2>{filtered.length} of {status.results.length} shown</h2>
            <span className="muted">Virtualized; only visible cards load sprites.</span>
          </div>
          <VirtualizedGrid
            items={filtered}
            rowHeight={320}
            renderItem={(item) => (
              <PokemonCard result={item} onStatusChange={handleStatus} />
            )}
          />
        </section>
      )}
    </main>
  );
}
