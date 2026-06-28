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

// The "home" sprites (HOME style — the clean, modern art Showdown uses
// in the teambuilder / battle UI). Some species lack a home image
// (e.g. CAP, very new releases) so consumers still need a fallback.
const HOME_FOLDERS: Array<[string, string]> = [["home", "png"]];

function urlsForSlug(slug: string, folders: Array<[string, string]> = FOLDERS): string[] {
  if (!slug) return [];
  return folders.map(([folder, ext]) => `https://play.pokemonshowdown.com/sprites/${folder}/${slug}.${ext}`);
}

// Variant picks which folder chain to try. ``"default"`` is the full
// pixel-art → animated → static chain used in battle. ``"home"``
// prefers the modern HOME sprite and falls back to the default chain
// if a species has no HOME image, so we never render an empty orb for
// a real (e.g. CAP) species.
export type SpriteVariant = "default" | "home";

function foldersForVariant(variant: SpriteVariant): Array<[string, string]> {
  if (variant === "home") return HOME_FOLDERS;
  return FOLDERS;
}

// Build the ordered URL list for a species. We try the canonical
// species_id first (the pokedex key the engine uses) and then fall
// back to the form-aware sprite_id (e.g. "slowking-galar" instead of
// "slowkinggalar"). For each slug, the folder chain is walked in
// preference order (gen5ani pixel art → newer animated → static).
export function spriteUrls(
  ...args: Array<string | null | undefined | { variant: SpriteVariant }>
): string[] {
  let variant: SpriteVariant = "default";
  const slugs: Array<string | null | undefined> = [];
  for (const arg of args) {
    if (arg && typeof arg === "object" && "variant" in arg) {
      variant = arg.variant;
    } else {
      slugs.push(arg as string | null | undefined);
    }
  }
  const folders = foldersForVariant(variant);
  const fallbackFolders = variant === "home" ? FOLDERS : null;
  const out: string[] = [];
  for (const slug of slugs) {
    if (!slug) continue;
    for (const url of urlsForSlug(slug, folders)) {
      if (!out.includes(url)) out.push(url);
    }
    // For variant="home" we also append the default chain so a
    // missing home image (e.g. CAP) still resolves to something.
    if (fallbackFolders) {
      for (const url of urlsForSlug(slug, fallbackFolders)) {
        if (!out.includes(url)) out.push(url);
      }
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
  variant: SpriteVariant = "default",
): void {
  if (typeof window === "undefined") return;
  for (const { canonical, derived } of speciesList) {
    const key = `${variant}|${warmedKey([canonical ?? "", derived ?? ""])}`;
    if (!canonical && !derived) continue;
    if (warmedSpecies.has(key)) continue;
    warmedSpecies.add(key);
    for (const url of spriteUrls(canonical, derived, { variant })) {
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
  variant = "default",
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
  /** ``"home"`` prefers the modern HOME sprite; if the species has
   *  none (e.g. CAP), the default chain is tried as a fallback. */
  variant?: SpriteVariant;
}) {
  const urls = spriteUrls(primaryId, fallbackId, { variant });
  const [idx, setIdx] = useState(0);
  const [allFailed, setAllFailed] = useState(false);
  useEffect(() => {
    setIdx(0);
    setAllFailed(false);
  }, [primaryId, fallbackId, variant]);
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
