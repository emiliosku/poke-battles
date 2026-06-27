import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { cdnUrlForSlug } from "../spriteDebugUtil";

export interface SpriteResult {
  species_id: string;
  name: string;
  types: string[];
  canonical_slug: string;
  derived_slug: string;
  canonical_hit: string | null;
  derived_hit: string | null;
}

export interface SpriteStatus {
  checked_at: number;
  count: number;
  duration_s: number;
  results: SpriteResult[];
}

type LoadState = "loading" | "ok" | "error" | "missing";

function SpriteCell({
  result,
  variant,
  loadState,
  onLoad,
  onError,
}: {
  result: SpriteResult;
  variant: "canonical" | "derived";
  loadState: LoadState;
  onLoad: () => void;
  onError: () => void;
}) {
  const slug = variant === "canonical" ? result.canonical_hit : result.derived_hit;
  const url = cdnUrlForSlug(slug);
  const label = variant === "canonical" ? "canonical" : "derived";
  return (
    <div className={`sprite-cell sprite-cell--${loadState}`}>
      <div className="sprite-cell-label">
        <code>{label}</code>
        <span>{result[`${variant}_slug`]}</span>
      </div>
      <div className="sprite-cell-art">
        {loadState === "missing" && (
          <div className="sprite-cell-missing" aria-label="404">
            404
          </div>
        )}
        {loadState === "loading" && <div className="sprite-cell-loading">…</div>}
        {(loadState === "ok" || loadState === "error") && url && (
          <img
            src={url}
            alt={`${result.name} (${label})`}
            onLoad={onLoad}
            onError={onError}
            loading="lazy"
            decoding="async"
          />
        )}
      </div>
    </div>
  );
}

function PokemonCard({
  result,
  onStatusChange,
}: {
  result: SpriteResult;
  onStatusChange: (speciesId: string, status: "ok" | "missing" | "error") => void;
}) {
  // Two independent image states: canonical slug, derived slug.
  // We report the worst of the two up to the parent so the "Only
  // failed" filter can use it.
  const [canonicalState, setCanonicalState] = useState<LoadState>(
    result.canonical_hit ? "loading" : "missing",
  );
  const [derivedState, setDerivedState] = useState<LoadState>(
    result.derived_hit ? "loading" : "missing",
  );

  useEffect(() => {
    setCanonicalState(result.canonical_hit ? "loading" : "missing");
    setDerivedState(result.derived_hit ? "loading" : "missing");
  }, [result.canonical_hit, result.derived_hit]);

  // Once both images have settled, report the combined status to the
  // parent so the global "OK / missing" counters stay in sync.
  useEffect(() => {
    if (canonicalState === "loading" || derivedState === "loading") return;
    if (canonicalState === "ok" || derivedState === "ok") {
      onStatusChange(result.species_id, "ok");
    } else if (canonicalState === "error" || derivedState === "error") {
      onStatusChange(result.species_id, "error");
    } else {
      onStatusChange(result.species_id, "missing");
    }
  }, [canonicalState, derivedState, result.species_id, onStatusChange]);

  return (
    <article className="sprite-card">
      <header className="sprite-card-head">
        <strong>{result.name}</strong>
        <code>{result.species_id}</code>
      </header>
      <div className="sprite-card-types">
        {result.types.map((t) => (
          <span key={t} className="badge">{t}</span>
        ))}
      </div>
      <div className="sprite-card-grid">
        <SpriteCell
          result={result}
          variant="canonical"
          loadState={canonicalState}
          onLoad={() => setCanonicalState("ok")}
          onError={() => setCanonicalState("error")}
        />
        <SpriteCell
          result={result}
          variant="derived"
          loadState={derivedState}
          onLoad={() => setDerivedState("ok")}
          onError={() => setDerivedState("error")}
        />
      </div>
    </article>
  );
}

function VirtualizedGrid({
  items,
  renderItem,
  rowHeight,
  overscan = 6,
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
  const [refreshing, setRefreshing] = useState(false);
  const [perSpeciesStatus, setPerSpeciesStatus] = useState<
    Record<string, "ok" | "missing" | "error">
  >({});

  const load = async (refresh = false) => {
    setLoading(true);
    setError("");
    if (refresh) setRefreshing(true);
    try {
      const url = new URL("/api/sprites/status", window.location.origin);
      if (refresh) url.searchParams.set("refresh", "true");
      const res = await fetch(url.toString());
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
    return out;
  }, [status, q, typeFilter, onlyFailed, perSpeciesStatus]);

  const stats = useMemo(() => {
    if (!status) return { total: 0, ok: 0, missing: 0, error: 0 };
    let ok = 0, missing = 0, error = 0;
    for (const r of status.results) {
      const s = perSpeciesStatus[r.species_id];
      if (s === "ok") ok += 1;
      else if (s === "error") error += 1;
      else missing += 1;
    }
    return { total: status.results.length, ok, missing, error };
  }, [status, perSpeciesStatus]);

  const handleStatus = (speciesId: string, status: "ok" | "missing" | "error") => {
    setPerSpeciesStatus((prev) => {
      if (prev[speciesId] === status) return prev;
      return { ...prev, [speciesId]: status };
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
            <span style={{ color: "#fcd34d" }}><strong>{stats.error}</strong> error</span>
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
            rowHeight={220}
            renderItem={(item) => (
              <PokemonCard result={item} onStatusChange={handleStatus} />
            )}
          />
        </section>
      )}
    </main>
  );
}
