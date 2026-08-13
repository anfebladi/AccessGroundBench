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
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" />
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
      <rect x="5" y="2" width="14" height="20" rx="2" />
      <path d="M9 18h.01M9 6h6" />
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
      <rect x="3" y="4" width="8" height="16" rx="1.5" />
      <rect x="13" y="4" width="8" height="16" rx="1.5" />
      <path d="M7 9v6M17 9v6" />
    </>
  ),
  command: (
    <path d="M9 3a3 3 0 0 0-3 3v12a3 3 0 1 0 3-3h6a3 3 0 1 0-3 3V6a3 3 0 1 0 3 3H9a3 3 0 1 0 3-3z" />
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
