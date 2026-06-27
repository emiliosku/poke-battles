/** Helper utilities for the dev-only sprite coverage page. Extracted
 *  into a separate module so the helpers can be unit-tested without
 *  pulling in the React component graph. */

/** Convert the backend's "<folder> <name>.<ext>" hit descriptor into
 *  a real URL the <img> tag can use. Returns null if the descriptor
 *  is missing or malformed. */
export function cdnUrlForSlug(slug: string | null): string | null {
  if (!slug) return null;
  const [folder, filename] = slug.split(" ");
  if (!folder || !filename) return null;
  return `https://play.pokemonshowdown.com/sprites/${folder}/${filename}`;
}
