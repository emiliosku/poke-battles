import { useEffect, useState } from "react";

export function spriteUrls(speciesId: string): string[] {
  if (!speciesId) return [];
  return [
    `https://play.pokemonshowdown.com/sprites/gen5ani/${speciesId}.gif`,
    `https://play.pokemonshowdown.com/sprites/ani/${speciesId}.gif`,
    `https://play.pokemonshowdown.com/sprites/dex/${speciesId}.png`,
  ];
}

// Pre-warm the browser's image cache by kicking off fetches for every
// fallback URL of every species, as soon as we know the team roster.
// By the time the PokemonSprite components mount, the URLs are already
// in flight (or cached), so the first paint is much less likely to land
// on an empty sprite orb.
//
// We dedupe per species so switching cards or re-rendering the preview
// does not trigger another batch of HTTP requests.
const warmedSpecies = new Set<string>();

export function prefetchSprites(speciesIds: string[]): void {
  if (typeof window === "undefined") return;
  for (const id of speciesIds) {
    if (!id || warmedSpecies.has(id)) continue;
    warmedSpecies.add(id);
    for (const url of spriteUrls(id)) {
      const img = new Image();
      img.decoding = "async";
      img.src = url;
    }
  }
}

export function PokemonSprite({
  speciesId,
  label,
  className,
}: {
  speciesId: string;
  label: string;
  className?: string;
}) {
  const urls = spriteUrls(speciesId);
  const [idx, setIdx] = useState(0);
  const [allFailed, setAllFailed] = useState(false);
  useEffect(() => {
    setIdx(0);
    setAllFailed(false);
  }, [speciesId]);
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
