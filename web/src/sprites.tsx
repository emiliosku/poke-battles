import { useEffect, useState } from "react";

const FOLDERS: Array<[string, string]> = [
  ["gen5ani", "gif"],
  ["ani", "gif"],
  ["dex", "png"],
  ["gen5", "png"],
  ["home", "png"],
  ["bw", "png"],
  ["xyani", "gif"],
];

function urlsForSlug(slug: string): string[] {
  if (!slug) return [];
  return FOLDERS.map(([folder, ext]) => `https://play.pokemonshowdown.com/sprites/${folder}/${slug}.${ext}`);
}

// Build the ordered URL list for a species. We try the canonical
// species_id first (the pokedex key the engine uses) and then fall
// back to the form-aware sprite_id (e.g. "slowking-galar" instead of
// "slowkinggalar"). For each slug, the folder chain is walked in
// preference order (gen5ani pixel art → newer animated → static).
export function spriteUrls(...slugs: Array<string | null | undefined>): string[] {
  const out: string[] = [];
  for (const slug of slugs) {
    if (!slug) continue;
    for (const url of urlsForSlug(slug)) {
      if (!out.includes(url)) out.push(url);
    }
  }
  return out;
}

// Pre-warm the browser's image cache by kicking off fetches for every
// fallback URL of every species, as soon as we know the team roster.
// By the time the PokemonSprite components mount, the URLs are already
// in flight (or cached), so the first paint is much less likely to land
// on an empty sprite orb.
//
// We dedupe per species so switching cards or re-rendering the preview
// does not trigger another batch of HTTP requests.
const warmedKey = (slugs: string[]) => slugs.filter(Boolean).join("|");
const warmedSpecies = new Set<string>();

export function prefetchSprites(
  speciesList: Array<{ canonical?: string | null; derived?: string | null }>,
): void {
  if (typeof window === "undefined") return;
  for (const { canonical, derived } of speciesList) {
    const key = warmedKey([canonical ?? "", derived ?? ""]);
    if (!key || warmedSpecies.has(key)) continue;
    warmedSpecies.add(key);
    for (const url of spriteUrls(canonical, derived)) {
      const img = new Image();
      img.decoding = "async";
      img.src = url;
    }
  }
}

export function PokemonSprite({
  primaryId,
  fallbackId,
  label,
  className,
}: {
  /** The slug to try first. Pass the API's ``sprite_id`` field — it's
   *  the form-aware slug the server generated for this species
   *  (e.g. "slowking-galar"), which is what the CDN actually serves
   *  for megas / regionals / dotted-name Pokemon. */
  primaryId: string;
  /** Tried only if every URL from ``primaryId`` 404s. Typically the
   *  canonical Showdown species_id (e.g. "slowkinggalar") — for
   *  base-form species it matches primaryId. */
  fallbackId?: string;
  label: string;
  className?: string;
}) {
  const urls = spriteUrls(primaryId, fallbackId);
  const [idx, setIdx] = useState(0);
  const [allFailed, setAllFailed] = useState(false);
  useEffect(() => {
    setIdx(0);
    setAllFailed(false);
  }, [primaryId, fallbackId]);
  const url = urls[idx];
  if (!url) {
    return (
      <div className={`sprite-orb empty ${className || ""}`} title={label}>
        <span className="sprite-orb-name">{label}</span>
      </div>
    );
  }
  if (allFailed) {
    return (
      <div className={`sprite-orb fallback ${className || ""}`} title={label}>
        <span className="sprite-orb-name">{label}</span>
      </div>
    );
  }
  return (
    <img
      className={`pokemon-sprite ${className || ""}`}
      src={url}
      alt={label}
      loading="eager"
      decoding="async"
      onError={() => {
        if (idx + 1 < urls.length) {
          setIdx(idx + 1);
        } else {
          setAllFailed(true);
        }
      }}
    />
  );
}

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(id);
  }, [value, delayMs]);
  return debounced;
}
