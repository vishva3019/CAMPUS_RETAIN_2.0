export function dateLabel(iso: string | null | undefined) {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function dateTimeLabel(iso: string | null | undefined) {
  if (!iso) return "";
  return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** Notification links point at the classic pages; map them to app routes. */
export function appLink(link: string | null): string | null {
  if (!link) return null;
  if (link === "/app" || link.startsWith("/app/") || link.startsWith("/app?")) return link.slice(4) || "/";
  if (link === "/me") return "/activity";
  if (link.startsWith("/dashboard")) return "/" + (link.split("?")[1] ? "?" + link.split("?")[1] : "");
  return null;
}
