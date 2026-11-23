/**
 * Ícones de tecnologia lisos (vetor, uma cor só via `currentColor`), portados dos
 * `<symbol id="s-*">` da seção "VERSÃO LISA" de `frontend/icons/retro-icons.html`
 * com `viewBox="0 0 32 32"` e a mesma geometria. Tamanho padrão 14 px.
 *
 * Os ids de `<mask>`/`<clipPath>` vêm de `useId()`, então cada instância tem os
 * seus (vários ícones iguais na mesma tela não colidem).
 */
import { useId, type ReactNode, type SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

/** Tipo de qualquer componente deste módulo (para mapas nome → ícone). */
export type TechIcon = (props: IconProps) => ReactNode;

function TechSvg({ size = 14, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  );
}

/** Prefixo de id único por instância, sem os caracteres especiais de `useId()` (seguro em `url(#...)`). */
function useSvgId(): string {
  return `ti${useId().replace(/[^A-Za-z0-9_-]/g, "")}`;
}

const stroke2 = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

const LINES_13_31 = "M0 13H32M0 16H32M0 19H32M0 22H32M0 25H32M0 28H32M0 31H32";

export const SparkIcon = (p: IconProps) => (
  <TechSvg {...p}>
    <polygon
      points="20.01,1.83 20.35,13.28 29.48,16.09 20.70,19.85 21.20,30.34 14.55,22.21 5.90,24.98 10.41,17.09 4.26,9.18 13.99,11.57"
      stroke="none"
    />
  </TechSvg>
);

const ICEBERG_BODY =
  "6.00,10.00 26.50,10.00 27.00,13.00 23.00,17.00 23.00,21.50 20.00,24.00 16.00,30.00 11.00,24.50 11.00,21.00 6.00,13.00";

export const IcebergIcon = (p: IconProps) => {
  const id = useSvgId();
  return (
    <TechSvg {...p}>
      <defs>
        <clipPath id={`${id}-c-ice`}>
          <circle cx="16" cy="16" r="13.6" />
        </clipPath>
        <mask id={`${id}-m-ice`}>
          <rect width="32" height="32" fill="#fff" />
          <polygon points={ICEBERG_BODY} fill="#000" stroke="#000" strokeWidth="4" />
        </mask>
      </defs>
      <circle cx="16" cy="16" r="14.5" {...stroke2} />
      <g clipPath={`url(#${id}-c-ice)`} mask={`url(#${id}-m-ice)`}>
        <path d={LINES_13_31} stroke="currentColor" strokeWidth="1.6" fill="none" />
      </g>
      <line x1="1.5" y1="10" x2="30.5" y2="10" {...stroke2} />
      <polygon points="9,9.5 11,6.5 21,6 24,8 24.5,9.5" fill="currentColor" stroke="none" />
      <polygon points={ICEBERG_BODY} {...stroke2} />
      <path d="M16 10V18L23 17M16 18L20 24" {...stroke2} />
    </TechSvg>
  );
};

const HUDI_FRONT = "19.00,10.00 29.50,30.00 8.50,30.00";

// O HudiIcon reaproveita `LINES_13_31` (compartilhado com o IcebergIcon): a última linha,
// em y=31, fica fora do clip `HUDI_FRONT` (triângulo com y ≤ 30) e por isso não aparece.
export const HudiIcon = (p: IconProps) => {
  const id = useSvgId();
  return (
    <TechSvg {...p}>
      <defs>
        <mask id={`${id}-m-hudi`}>
          <rect width="32" height="32" fill="#fff" />
          <polygon points={HUDI_FRONT} fill="#000" />
        </mask>
        <clipPath id={`${id}-c-hudi`}>
          <polygon points={HUDI_FRONT} />
        </clipPath>
      </defs>
      <polygon points="13.00,5.00 23.00,26.00 3.00,26.00" {...stroke2} mask={`url(#${id}-m-hudi)`} />
      <g clipPath={`url(#${id}-c-hudi)`}>
        <path d={LINES_13_31} stroke="currentColor" strokeWidth="1.6" fill="none" />
      </g>
      <polygon points={HUDI_FRONT} {...stroke2} />
      <path d="M3.5 21A11 11 0 0 1 8 7.5" {...stroke2} />
      <polygon points="6,3.5 12.5,6.8 6.8,11" fill="currentColor" stroke="none" />
      <path d="M21.5 3.5A11 11 0 0 1 29.5 16" {...stroke2} />
      <polygon points="25.5,15.5 32,15 29.3,21.5" fill="currentColor" stroke="none" />
    </TechSvg>
  );
};

export const S3Icon = (p: IconProps) => (
  <TechSvg {...p}>
    <ellipse cx="16" cy="7" rx="13" ry="4" {...stroke2} />
    <path d="M3 7L6.5 27Q16 31.5 25.5 27L29 7" {...stroke2} />
    <circle cx="12" cy="17" r="1.9" fill="currentColor" stroke="none" />
    <path d="M12 17L28.5 20.8Q31.2 21.6 30.2 23.8L26.3 25.6" {...stroke2} />
  </TechSvg>
);

export const DuckdbIcon = (p: IconProps) => {
  const id = useSvgId();
  return (
    <TechSvg {...p}>
      <defs>
        <mask id={`${id}-m-duck`}>
          <rect width="32" height="32" fill="#fff" />
          <circle cx="13" cy="14" r="7" fill="#000" />
          <rect x="17" y="12.4" width="11" height="4.6" rx="2.3" fill="#000" />
          <path d="M0 23.5H32M0 26.7H32M0 29.9H32" stroke="#000" strokeWidth="1.4" />
        </mask>
      </defs>
      <circle cx="16" cy="16" r="15" fill="currentColor" stroke="none" mask={`url(#${id}-m-duck)`} />
      <circle cx="15" cy="11" r="1.4" fill="currentColor" stroke="none" />
    </TechSvg>
  );
};

export const DeltaIcon = (p: IconProps) => (
  <TechSvg {...p}>
    <path d="M16 2L28.5 21H3.5ZM16 9.5L9.3 18.5H22.7Z" fill="currentColor" stroke="none" fillRule="evenodd" />
    <path d="M3 24.5H29M6.5 27.6H25.5M10.5 30.6H21.5" {...stroke2} />
  </TechSvg>
);

export const ParquetIcon = (p: IconProps) => (
  <TechSvg {...p}>
    <g transform="rotate(-45 16 16)" fill="currentColor" stroke="none">
      <rect x="5.40" y="5.40" width="21.20" height="3" rx="0.6" />
      <rect x="5.40" y="9.95" width="7.60" height="3" rx="0.6" />
      <rect x="14.60" y="9.95" width="12.00" height="3" rx="0.6" />
      <rect x="5.40" y="14.50" width="13.10" height="3" rx="0.6" />
      <rect x="20.10" y="14.50" width="6.50" height="3" rx="0.6" />
      <rect x="5.40" y="19.05" width="4.10" height="3" rx="0.6" />
      <rect x="11.10" y="19.05" width="15.50" height="3" rx="0.6" />
      <rect x="5.40" y="23.60" width="21.20" height="3" rx="0.6" />
    </g>
  </TechSvg>
);

/** Peças do Glue: contorno + listras recortadas a partir de `stripeX` + divisória vertical. */
const GLUE_PARTS = [
  { key: "a", points: "1.50,7.00 8.50,7.00 8.50,14.00 1.50,14.00", stripeX: 5, line: { x1: 5, y1: 7, x2: 5, y2: 14 } },
  { key: "b", points: "11.50,1.00 20.50,1.00 20.50,14.00 11.50,14.00", stripeX: 16, line: { x1: 16, y1: 1, x2: 16, y2: 14 } },
  { key: "c", points: "23.50,9.00 30.50,9.00 30.50,14.00 23.50,14.00", stripeX: 27, line: { x1: 27, y1: 9, x2: 27, y2: 14 } },
  {
    key: "d",
    points: "1.50,17.00 30.50,17.00 30.50,22.00 16.00,26.50 1.50,22.00",
    stripeX: 16,
    line: { x1: 16, y1: 17, x2: 16, y2: 26.5 },
  },
  { key: "e", points: "12.50,27.50 19.50,27.50 19.50,31.00 12.50,31.00", stripeX: 16, line: { x1: 16, y1: 27.5, x2: 16, y2: 31 } },
] as const;

const GLUE_STRIPE_YS = ["0.0", "2.5", "5.0", "7.5", "10.0", "12.5", "15.0", "17.5", "20.0", "22.5", "25.0", "27.5", "30.0"];

const glueStripes = (x: number) => GLUE_STRIPE_YS.map((y) => `M${x} ${y}H32`).join("");

export const GlueIcon = (p: IconProps) => {
  const id = useSvgId();
  return (
    <TechSvg {...p}>
      {GLUE_PARTS.map(({ key, points, stripeX, line }) => (
        <g key={key}>
          <defs>
            <clipPath id={`${id}-c-glue-${key}`}>
              <polygon points={points} />
            </clipPath>
          </defs>
          <g clipPath={`url(#${id}-c-glue-${key})`}>
            <path d={glueStripes(stripeX)} stroke="currentColor" strokeWidth="1.2" />
          </g>
          <polygon points={points} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
          <line {...line} stroke="currentColor" strokeWidth="1.6" />
        </g>
      ))}
    </TechSvg>
  );
};

export const AvroIcon = (p: IconProps) => (
  <TechSvg {...p}>
    <path d="M16 8L30.5 25H1.5Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    <path d="M16 11.6L26.4 23.2H5.6Z" fill="none" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
    <path
      d="M13.3 21.6L16 15.2L18.7 21.6M14.2 19.6H17.8"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <g fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <path d="M11.6 13.2Q6.5 11.6 0.8 6.6M10.4 14.8Q6.2 13.9 2.2 10.6M9.2 16.5Q6 16 3.6 14.2" />
      <path d="M20.4 13.2Q25.5 11.6 31.2 6.6M21.6 14.8Q25.8 13.9 29.8 10.6M22.8 16.5Q26 16 28.4 14.2" />
    </g>
  </TechSvg>
);

export const OrcIcon = (p: IconProps) => {
  const id = useSvgId();
  return (
    <TechSvg {...p}>
      <defs>
        <mask id={`${id}-m-orc`}>
          <rect width="32" height="32" fill="#fff" />
          <path
            d="M5 18.2Q6.6 13.6 9.4 11.2V8.9L12.8 8.6L16 6.4L19.2 8.6L22.6 8.9V11.2Q25.4 13.6 27 18.2L22.2 20.6Q20.2 15.6 16 13.4Q11.8 15.6 9.8 20.6Z"
            fill="#000"
          />
          <path d="M16 16.8Q18.4 18.6 19.2 20.6Q18 23.6 16 26.6Q14 23.6 12.8 20.6Q13.6 18.6 16 16.8Z" fill="#000" />
        </mask>
      </defs>
      <circle cx="16" cy="16" r="15" fill="currentColor" stroke="none" mask={`url(#${id}-m-orc)`} />
    </TechSvg>
  );
};
