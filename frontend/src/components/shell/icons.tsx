/** Ícones SVG inline (paths Tabler, viewBox 24, traço 2.25 com pontas retas); herdam `currentColor`. */
import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 16, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.25}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const FolderIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 4h4l3 3h7a2 2 0 0 1 2 2v8a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-11a2 2 0 0 1 2 -2" />
  </Svg>
);

export const NotebookIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 4h11a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-11a1 1 0 0 1 -1 -1v-14a1 1 0 0 1 1 -1m3 0v18" />
    <path d="M13 8l2 0" />
    <path d="M13 12l2 0" />
  </Svg>
);

export const FileIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 3v4a1 1 0 0 0 1 1h4" />
    <path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2" />
  </Svg>
);

export const PlusIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 5l0 14" />
    <path d="M5 12l14 0" />
  </Svg>
);

export const PencilIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 20h4l10.5 -10.5a2.828 2.828 0 1 0 -4 -4l-10.5 10.5v4" />
    <path d="M13.5 6.5l4 4" />
  </Svg>
);

export const ChevronRightIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M9 6l6 6l-6 6" />
  </Svg>
);

export const RefreshIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 11a8.1 8.1 0 0 0 -15.5 -2m-.5 -4v4h4" />
    <path d="M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4" />
  </Svg>
);

/** Marca N-Block monocromática: monograma N com faísca, em `--color-text` sobre `--color-bg` (invertida no escuro). A sombra deslocada usa `--brand-mark-shadow`. */
export function BrandMark({ size = 32, ...rest }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false" {...rest}>
      <rect x="11" y="11" width="48" height="48" fill="var(--brand-mark-shadow)" />
      <rect
        x="6"
        y="6"
        width="48"
        height="48"
        fill="var(--color-bg)"
        stroke="var(--color-text)"
        strokeWidth="3.5"
        strokeLinejoin="miter"
        strokeLinecap="square"
      />
      <rect x="15" y="16" width="8" height="30" fill="var(--color-text)" />
      <rect x="37" y="16" width="8" height="30" fill="var(--color-text)" />
      <polygon points="15,16 23,16 45,46 37,46" fill="var(--color-text)" />
      <polygon
        points="53.0,1.0 56.2,7.8 63.0,11.0 56.2,14.2 53.0,21.0 49.8,14.2 43.0,11.0 49.8,7.8"
        fill="var(--color-bg)"
        stroke="var(--color-text)"
        strokeWidth="2.5"
        strokeLinejoin="miter"
      />
    </svg>
  );
}

export const DatabaseIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 6a8 3 0 1 0 16 0a8 3 0 1 0 -16 0" />
    <path d="M4 6v6a8 3 0 0 0 16 0v-6" />
    <path d="M4 12v6a8 3 0 0 0 16 0v-6" />
  </Svg>
);

export const TableIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 5a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v14a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-14" />
    <path d="M3 10h18" />
    <path d="M10 3v18" />
  </Svg>
);

export const CloseIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M18 6l-12 12" />
    <path d="M6 6l12 12" />
  </Svg>
);

export const MoreVerticalIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M11 12a1 1 0 1 0 2 0a1 1 0 1 0 -2 0" />
    <path d="M11 19a1 1 0 1 0 2 0a1 1 0 1 0 -2 0" />
    <path d="M11 5a1 1 0 1 0 2 0a1 1 0 1 0 -2 0" />
  </Svg>
);

export const PlayFilledIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 4v16l13 -8l-13 -8" fill="currentColor" />
  </Svg>
);

export const StopFilledIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="5" y="5" width="14" height="14" fill="currentColor" />
  </Svg>
);

export const SymlinkIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 21v-4a3 3 0 0 1 3 -3h5" />
    <path d="M9 17l3 -3l-3 -3" />
    <path d="M14 3v4a1 1 0 0 0 1 1h4" />
    <path d="M5 11v-6a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2h-9.5" />
  </Svg>
);

export const FileParquetIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 3v4a1 1 0 0 0 1 1h4" />
    <path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2" />
    <path d="M9 17l0 -5" />
    <path d="M12 17l0 -1" />
    <path d="M15 17l0 -3" />
  </Svg>
);

export const FileCsvIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M14 3v4a1 1 0 0 0 1 1h4" />
    <path d="M5 12v-7a2 2 0 0 1 2 -2h7l5 5v4" />
    <path d="M7 16.5a1.5 1.5 0 0 0 -3 0v3a1.5 1.5 0 0 0 3 0" />
    <path d="M10 20.25c0 .414 .336 .75 .75 .75h1.25a1 1 0 0 0 1 -1v-1a1 1 0 0 0 -1 -1h-1a1 1 0 0 1 -1 -1v-1a1 1 0 0 1 1 -1h1.25a.75 .75 0 0 1 .75 .75" />
    <path d="M16 15l2 6l2 -6" />
  </Svg>
);

export const FileJsonIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M7 4a2 2 0 0 0 -2 2v3a2 3 0 0 1 -2 3a2 3 0 0 1 2 3v3a2 2 0 0 0 2 2" />
    <path d="M17 4a2 2 0 0 1 2 2v3a2 3 0 0 0 2 3a2 3 0 0 0 -2 3v3a2 2 0 0 1 -2 2" />
  </Svg>
);

export const ViewIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10 12a2 2 0 1 0 4 0a2 2 0 0 0 -4 0" />
    <path d="M21 12c-2.4 4 -5.4 6 -9 6c-3.6 0 -6.6 -2 -9 -6c2.4 -4 5.4 -6 9 -6c3.6 0 6.6 2 9 6" />
  </Svg>
);

export const ExternalTableIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 21h-7a2 2 0 0 1 -2 -2v-12a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v5" />
    <path d="M3 10h18" />
    <path d="M10 3v18" />
    <path d="M16 22l5 -5" />
    <path d="M21 21.5v-4.5h-4.5" />
  </Svg>
);

export const TempTableIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 5a2 2 0 0 1 2 -2h14a2 2 0 0 1 2 2v14a2 2 0 0 1 -2 2h-14a2 2 0 0 1 -2 -2v-14" strokeDasharray="3 3" />
    <path d="M3 10h18" />
    <path d="M10 3v18" />
  </Svg>
);

export const ColumnIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 3h8v18h-8z" />
    <path d="M8 8h8" />
  </Svg>
);

export const VariablesIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 4c-2.5 5 -2.5 10 0 16m14 -16c2.5 5 2.5 10 0 16m-10 -11h1c1 0 1 1 2.016 3.527c.984 2.473 .984 3.473 1.984 3.473h1" />
    <path d="M8 16c1.5 0 3 -2 4 -3.5s2.5 -3.5 4 -3.5" />
  </Svg>
);

export const PanelLeftIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <path d="M9 4v16" />
  </Svg>
);

export const PanelRightIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <path d="M15 4v16" />
  </Svg>
);

export const FocusIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 8v-2a2 2 0 0 1 2 -2h2" />
    <path d="M4 16v2a2 2 0 0 0 2 2h2" />
    <path d="M16 4h2a2 2 0 0 1 2 2v2" />
    <path d="M16 20h2a2 2 0 0 0 2 -2v-2" />
    <path d="M10 12a2 2 0 1 0 4 0a2 2 0 0 0 -4 0" />
  </Svg>
);
