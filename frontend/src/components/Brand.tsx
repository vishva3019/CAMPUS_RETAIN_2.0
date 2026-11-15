import { useId } from "react";

/** The paper plane, without its tile: used by the report/claim flight animations. */
export function PlaneGlyph({ className = "size-10" }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden>
      <path d="M37 3L2 18.5l13.3 4.7L19 37.5l5.7-9.5 9.5 5.7z" fill="#ffffff" />
      <path d="M15.3 23.2L37 3 24.7 28" fill="#c7d2fe" />
    </svg>
  );
}

/** Campus Retain logo: a paper plane carrying lost things back to their owners. */
export function BrandMark({ className = "size-9" }: { className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <defs>
        <linearGradient id={`bm${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#38bdf8" /><stop offset="1" stopColor="#4f46e5" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="18" fill={`url(#bm${id})`} />
      <path d="M50 14L13 30l14 5 4 15 6-10 10 6z" fill="#ffffff" />
      <path d="M27 35l23-21-13 26" fill="#c7d2fe" />
      <path d="M12 48c4 4 9 5 13 2" fill="none" stroke="#ffffff" strokeWidth="2.5" strokeLinecap="round" strokeDasharray="2 4" />
    </svg>
  );
}
