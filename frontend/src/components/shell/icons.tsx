/**
 * Ícones SVG inline (paths Tabler, viewBox 24, traço 2.25 com pontas retas); herdam `currentColor`.
 * Exceção: PanelLeft, PanelRight, Focus e o "N" das marcas são desenhos em pixel preenchidos
 * (`shape-rendering: crispEdges`), não paths Tabler com traço. As marcas (`BrandMark`,
 * `HomeBrandMark`) usam cores fixas ou tokens de tema. `FolderIcon` é o desenho liso `s-folder` de
 * `frontend/icons/retro-icons.html` (viewBox 32, traço 2 com pontas redondas); `FileCsvIcon`,
 * `FileJsonIcon` e `FileTextIcon` são os desenhos lisos `s-csv`, `s-json` e `s-txt` do mesmo arquivo.
 */
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
  <Svg viewBox="0 0 32 32" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" {...p}>
    <path d="M3 26V8Q3 7 4 7H11.5L14 10H28Q29 10 29 11V26Q29 27 28 27H4Q3 27 3 26ZM3 13.5H29" />
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

export const EraserIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M19 20h-10.5l-4.21 -4.3a1 1 0 0 1 0 -1.41l10 -10a1 1 0 0 1 1.41 0l5 5a1 1 0 0 1 0 1.41l-9.2 9.3" />
    <path d="M18 13.3l-6.3 -6.3" />
  </Svg>
);

export const RefreshIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 11a8.1 8.1 0 0 0 -15.5 -2m-.5 -4v4h4" />
    <path d="M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4" />
  </Svg>
);

type MarkColors = { shadow: string; fill: string; ink: string; star: string };

/** Geometria N-Block compartilhada pelas marcas; as cores chegam por props. */
function BrandMarkShape({ size, colors, ...rest }: IconProps & { size: number; colors: MarkColors }) {
  const { shadow, fill, ink, star } = colors;
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" focusable="false" {...rest}>
      <rect x="11" y="11" width="48" height="48" fill={shadow} />
      <rect
        x="6"
        y="6"
        width="48"
        height="48"
        fill={fill}
        stroke={ink}
        strokeWidth="3.5"
        strokeLinejoin="miter"
        strokeLinecap="square"
      />
      <path shapeRendering="crispEdges" fill={ink} d="M12 14h12v32h-12zM36 14h12v32h-12zM24 14h8v16h-8zM28 30h8v16h-8z" />
      <polygon
        points="53.0,1.0 56.2,7.8 63.0,11.0 56.2,14.2 53.0,21.0 49.8,14.2 43.0,11.0 49.8,7.8"
        fill={star}
        stroke={ink}
        strokeWidth="2.5"
        strokeLinejoin="miter"
      />
    </svg>
  );
}

const BRAND_COLORS: MarkColors = {
  shadow: "var(--brand-mark-shadow)",
  fill: "var(--color-bg)",
  ink: "var(--color-text)",
  star: "var(--color-bg)",
};

const HOME_COLORS: MarkColors = {
  shadow: "var(--home-mark-shadow)",
  fill: "#BBF7D0",
  ink: "#000",
  star: "#FDE68A",
};

/** Marca N-Block monocromática: monograma N com faísca, em `--color-text` sobre `--color-bg` (invertida no escuro). A sombra deslocada usa `--brand-mark-shadow`. */
export function BrandMark({ size = 32, ...rest }: IconProps) {
  return <BrandMarkShape size={size} colors={BRAND_COLORS} {...rest} />;
}

/** Marca da tela inicial com as cores do favicon; a sombra segue o tema via `--home-mark-shadow`. */
export function HomeBrandMark({ size = 112, ...rest }: IconProps) {
  return <BrandMarkShape size={size} colors={HOME_COLORS} {...rest} />;
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

const FILE_SHEET = "M7 4Q7 3 8 3H20L26 9V28Q26 29 25 29H8Q7 29 7 28ZM20 3V9H26";

const FileSheetSvg = ({ children, ...p }: IconProps & { children: ReactNode }) => (
  <Svg viewBox="0 0 32 32" strokeLinecap="butt" strokeLinejoin="miter" {...p}>
    <path d={FILE_SHEET} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    {children}
  </Svg>
);

export const FileCsvIcon = (p: IconProps) => (
  <FileSheetSvg {...p}>
    <rect x="10" y="12" width="13" height="14" rx="0.6" fill="none" stroke="currentColor" strokeWidth="1.5" />
    <path d="M10 16H23" stroke="currentColor" strokeWidth="2.4" fill="none" />
    <path d="M10 21H23M14.3 12V26M18.7 12V26" stroke="currentColor" strokeWidth="1.3" fill="none" />
  </FileSheetSvg>
);

export const FileJsonIcon = (p: IconProps) => (
  <FileSheetSvg {...p}>
    <path
      d="M14 12.5Q11.6 12.5 11.6 14.8V17.2Q11.6 18.6 10 19.2Q11.6 19.8 11.6 21.2V23.6Q11.6 25.9 14 25.9M19 12.5Q21.4 12.5 21.4 14.8V17.2Q21.4 18.6 23 19.2Q21.4 19.8 21.4 21.2V23.6Q21.4 25.9 19 25.9"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle cx="16.5" cy="19.2" r="1.1" fill="currentColor" stroke="none" />
  </FileSheetSvg>
);

export const FileTextIcon = (p: IconProps) => (
  <FileSheetSvg {...p}>
    <path
      d="M10.5 13H22.5M10.5 16.5H22.5M10.5 20H20M10.5 23.5H17"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      fill="none"
    />
  </FileSheetSvg>
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

export const PanelLeftIcon = (p: IconProps) => (
  <Svg shapeRendering="crispEdges" stroke="none" fill="currentColor" {...p}>
    <path fillRule="evenodd" d="M6 4h12v2h2v12h-2v2h-12v-2h-2v-12h2zM6 6v12h12v-12z" />
    <path d="M6 6h4v12h-4z" />
  </Svg>
);

export const PanelRightIcon = (p: IconProps) => (
  <Svg shapeRendering="crispEdges" stroke="none" fill="currentColor" {...p}>
    <path fillRule="evenodd" d="M6 4h12v2h2v12h-2v2h-12v-2h-2v-12h2zM6 6v12h12v-12z" />
    <path d="M14 6h4v12h-4z" />
  </Svg>
);

export const FocusIcon = (p: IconProps) => (
  <Svg shapeRendering="crispEdges" stroke="none" fill="currentColor" {...p}>
    <path d="M4 4h6v2h-4v4h-2zM14 4h6v6h-2v-4h-4zM4 14h2v4h4v2h-6zM18 14h2v6h-6v-2h4zM10 10h4v4h-4z" />
  </Svg>
);
