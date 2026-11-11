/** Ícones dos controles do kernel (paths Tabler, viewBox 24, traço 2.25 com pontas retas; `currentColor`). */
import type { ReactNode } from "react";

function Svg({ children }: { children: ReactNode }) {
  return (
    <svg
      width={14}
      height={14}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.25}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export const CheckSmallIcon = () => (
  <Svg>
    <path d="M5 12l5 5l10 -10" />
  </Svg>
);

export const CrossSmallIcon = () => (
  <Svg>
    <path d="M18 6l-12 12M6 6l12 12" />
  </Svg>
);
