import type { ReactNode } from "react";

const iconPaths: Record<string, ReactNode> = {
  dataset: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  models: (
    <>
      <rect x="5" y="7" width="14" height="14" rx="3" />
      <path d="M12 7V4" />
      <circle cx="12" cy="3" r="1" />
      <circle cx="9" cy="13" r="1" />
      <circle cx="15" cy="13" r="1" />
    </>
  ),
  evaluate: (
    <>
      <path d="M9 11l3 3L22 4" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </>
  ),
  collect: (
    <>
      <path d="M12 3v12M7 10l5 5 5-5M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </>
  ),
  results: (
    <>
      <path d="M3 3v18h18" />
      <rect x="7" y="13" width="3" height="5" />
      <rect x="12" y="9" width="3" height="9" />
      <rect x="17" y="5" width="3" height="13" />
    </>
  ),
  analyze: (
    <>
      <path d="M3 3v18h18" />
      <path d="M7 15l4-6 3 3 5-8" />
    </>
  ),
  compare: (
    <>
      <path d="M12 4v16M5 7h14M7 7l-3 7h6L7 7M17 7l-3 7h6l-3-7M8 20h8" />
    </>
  ),
  menu: (
    <path d="M4 7h16M4 12h16M4 17h16" />
  ),
};

export function Icon({ name, size = 17 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={size >= 24 ? 1.5 : 2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {iconPaths[name] ?? null}
    </svg>
  );
}
