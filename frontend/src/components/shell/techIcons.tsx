/**
 * Ícones de tecnologia lisos (vetor, uma cor só via `currentColor`), portados dos
 * `<symbol id="s-*">` da seção "VERSÃO LISA" de `frontend/icons/retro-icons.html`
 * com `viewBox="0 0 32 32"` e a mesma geometria. Tamanho padrão 14 px.
 *
 * Os ids de `<mask>`/`<clipPath>` vêm de `useId()`, então cada instância tem os
 * seus (vários ícones iguais na mesma tela não colidem).
 *
 * Cor: cada parte pinta por estilo com `var(--ico-<parte>, currentColor)` (não por atributo
 * de apresentação). As variáveis só existem sob `[data-icons="colorized"]` (`tokens.css`);
 * fora dele tudo cai no `currentColor` e o ícone fica mono. As camadas extras do DuckDB
 * (listras, cabeça/bico, contorno) e da ORC (orca, contorno) usam fallback `transparent`/`none`
 * e ficam invisíveis fora do colorized.
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

const SPARK_STROKE = { stroke: "var(--ico-spark, currentColor)" };

/** Forma do logo do Apache Spark: estrela assimétrica e inclinada, oca, com traço grosso e pontas arredondadas. */
export const SparkIcon = (p: IconProps) => (
  <TechSvg {...p}>
    <path
      d="M14.3 3.3L19.3 9.4L28.1 7.5L22.8 15.3L25.6 22.8L17.8 21.3L10.3 28.7L10.6 18.8L3.8 15L11.9 11.9Z"
      fill="none"
      strokeWidth="3"
      strokeLinejoin="round"
      strokeLinecap="round"
      style={SPARK_STROKE}
    />
  </TechSvg>
);

const ICEBERG_BODY =
  "6.00,10.00 26.50,10.00 27.00,13.00 23.00,17.00 23.00,21.50 20.00,24.00 16.00,30.00 11.00,24.50 11.00,21.00 6.00,13.00";

const ICEBERG_STROKE = { stroke: "var(--ico-iceberg, currentColor)" };
const ICEBERG_FILL = { fill: "var(--ico-iceberg, currentColor)" };
const ICEBERG_WATER_STROKE = { stroke: "var(--ico-iceberg-water, currentColor)" };

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
      <circle cx="16" cy="16" r="14.5" {...stroke2} style={ICEBERG_STROKE} />
      <g clipPath={`url(#${id}-c-ice)`} mask={`url(#${id}-m-ice)`}>
        <path d={LINES_13_31} strokeWidth="1.6" fill="none" style={ICEBERG_WATER_STROKE} />
      </g>
      <line x1="1.5" y1="10" x2="30.5" y2="10" {...stroke2} style={ICEBERG_STROKE} />
      <polygon points="9,9.5 11,6.5 21,6 24,8 24.5,9.5" stroke="none" style={ICEBERG_FILL} />
      <polygon points={ICEBERG_BODY} {...stroke2} style={ICEBERG_STROKE} />
      <path d="M16 10V18L23 17M16 18L20 24" {...stroke2} style={ICEBERG_STROKE} />
    </TechSvg>
  );
};

const HUDI_FRONT = "19.00,10.00 29.50,30.00 8.50,30.00";
const HUDI_STROKE = { stroke: "var(--ico-hudi, currentColor)" };
const HUDI_FILL = { fill: "var(--ico-hudi, currentColor)" };
const HUDI_BACK_STROKE = { stroke: "var(--ico-hudi-back, currentColor)" };
const HUDI_BACK_FILL = { fill: "var(--ico-hudi-back, currentColor)" };

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
      <polygon points="13.00,5.00 23.00,26.00 3.00,26.00" {...stroke2} mask={`url(#${id}-m-hudi)`} style={HUDI_BACK_STROKE} />
      <g clipPath={`url(#${id}-c-hudi)`}>
        <path d={LINES_13_31} strokeWidth="1.6" fill="none" style={HUDI_STROKE} />
      </g>
      <polygon points={HUDI_FRONT} {...stroke2} style={HUDI_STROKE} />
      <path d="M3.5 21A11 11 0 0 1 8 7.5" {...stroke2} style={HUDI_BACK_STROKE} />
      <polygon points="6,3.5 12.5,6.8 6.8,11" stroke="none" style={HUDI_BACK_FILL} />
      <path d="M21.5 3.5A11 11 0 0 1 29.5 16" {...stroke2} style={HUDI_STROKE} />
      <polygon points="25.5,15.5 32,15 29.3,21.5" stroke="none" style={HUDI_FILL} />
    </TechSvg>
  );
};

const S3_STROKE = { stroke: "var(--ico-s3, currentColor)" };
const S3_FILL = { fill: "var(--ico-s3, currentColor)" };

export const S3Icon = (p: IconProps) => (
  <TechSvg {...p}>
    <ellipse cx="16" cy="7" rx="13" ry="4" {...stroke2} style={S3_STROKE} />
    <path d="M3 7L6.5 27Q16 31.5 25.5 27L29 7" {...stroke2} style={S3_STROKE} />
    <circle cx="12" cy="17" r="1.9" stroke="none" style={S3_FILL} />
    <path d="M12 17L28.5 20.8Q31.2 21.6 30.2 23.8L26.3 25.6" {...stroke2} style={S3_STROKE} />
  </TechSvg>
);

/**
 * Recortes do disco do DuckDB (cabeça, bico e listras d'água): furos no `<mask>` e, com as mesmas
 * medidas, preenchimento/traço da camada extra do colorized.
 */
const DUCKDB_HEAD = { cx: 13, cy: 14, r: 7 } as const;
const DUCKDB_BEAK = { x: 17, y: 12.4, width: 11, height: 4.6, rx: 2.3 } as const;
const DUCKDB_STRIPES = "M0 23.5H32M0 26.7H32M0 29.9H32";
const DUCKDB_FILL = { fill: "var(--ico-duckdb, currentColor)" };
const DUCKDB_DUCK_FILL = { fill: "var(--ico-duckdb-duck, transparent)" };
const DUCKDB_EYE_FILL = { fill: "var(--ico-duckdb-eye, currentColor)" };
const DUCKDB_STRIPE_STROKE = { stroke: "var(--ico-duckdb-stripe, transparent)" };
const DUCKDB_RING_STROKE = { stroke: "var(--ico-duckdb-ring, none)" };

export const DuckdbIcon = (p: IconProps) => {
  const id = useSvgId();
  return (
    <TechSvg {...p}>
      <defs>
        <mask id={`${id}-m-duck`}>
          <rect width="32" height="32" fill="#fff" />
          <circle {...DUCKDB_HEAD} fill="#000" />
          <rect {...DUCKDB_BEAK} fill="#000" />
          <path d={DUCKDB_STRIPES} stroke="#000" strokeWidth="1.4" />
        </mask>
        <clipPath id={`${id}-c-duck`}>
          <circle cx="16" cy="16" r="15" />
        </clipPath>
      </defs>
      {/* Camada extra (só colorized): listras d'água sob os recortes do disco, recortadas ao disco. */}
      <g clipPath={`url(#${id}-c-duck)`}>
        <path d={DUCKDB_STRIPES} fill="none" strokeWidth="2" style={DUCKDB_STRIPE_STROKE} />
      </g>
      {/* Camada extra (só colorized): preenche os recortes da cabeça e do bico. */}
      <g stroke="none" style={DUCKDB_DUCK_FILL}>
        <circle {...DUCKDB_HEAD} />
        <rect {...DUCKDB_BEAK} />
      </g>
      <circle cx="16" cy="16" r="15" stroke="none" mask={`url(#${id}-m-duck)`} style={DUCKDB_FILL} />
      <circle cx="15" cy="11" r="1.4" stroke="none" style={DUCKDB_EYE_FILL} />
      {/* Camada extra (só colorized): contorno por dentro da silhueta. */}
      <circle cx="16" cy="16" r="14.4" fill="none" strokeWidth="1.2" style={DUCKDB_RING_STROKE} />
    </TechSvg>
  );
};

const DELTA_FILL = { fill: "var(--ico-delta, currentColor)" };
const DELTA_WAVE_STROKE = { stroke: "var(--ico-delta-wave, currentColor)" };

export const DeltaIcon = (p: IconProps) => (
  <TechSvg {...p}>
    <path d="M16 2L28.5 21H3.5ZM16 9.5L9.3 18.5H22.7Z" stroke="none" fillRule="evenodd" style={DELTA_FILL} />
    <path d="M3 24.5H29M6.5 27.6H25.5M10.5 30.6H21.5" {...stroke2} style={DELTA_WAVE_STROKE} />
  </TechSvg>
);

const PARQUET_FILL = { fill: "var(--ico-parquet, currentColor)" };

export const ParquetIcon = (p: IconProps) => (
  <TechSvg {...p}>
    <g transform="rotate(-45 16 16)" stroke="none" style={PARQUET_FILL}>
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

const GLUE_STROKE = { stroke: "var(--ico-glue, currentColor)" };
const GLUE_STRIPE_STROKE = { stroke: "var(--ico-glue-stripe, currentColor)" };

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
            <path d={glueStripes(stripeX)} strokeWidth="1.2" style={GLUE_STRIPE_STROKE} />
          </g>
          <polygon points={points} fill="none" strokeWidth="1.6" strokeLinejoin="round" style={GLUE_STROKE} />
          <line {...line} strokeWidth="1.6" style={GLUE_STROKE} />
        </g>
      ))}
    </TechSvg>
  );
};

const AVRO_STROKE = { stroke: "var(--ico-avro, currentColor)" };

export const AvroIcon = (p: IconProps) => (
  <TechSvg {...p}>
    <path d="M16 8L30.5 25H1.5Z" fill="none" strokeWidth="1.8" strokeLinejoin="round" style={AVRO_STROKE} />
    <path d="M16 11.6L26.4 23.2H5.6Z" fill="none" strokeWidth="1.1" strokeLinejoin="round" style={AVRO_STROKE} />
    <path
      d="M13.3 21.6L16 15.2L18.7 21.6M14.2 19.6H17.8"
      fill="none"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={AVRO_STROKE}
    />
    <g fill="none" strokeWidth="1.6" strokeLinecap="round" style={AVRO_STROKE}>
      <path d="M11.6 13.2Q6.5 11.6 0.8 6.6M10.4 14.8Q6.2 13.9 2.2 10.6M9.2 16.5Q6 16 3.6 14.2" />
      <path d="M20.4 13.2Q25.5 11.6 31.2 6.6M21.6 14.8Q25.8 13.9 29.8 10.6M22.8 16.5Q26 16 28.4 14.2" />
    </g>
  </TechSvg>
);

const ORC_BODY =
  "M5 18.2Q6.6 13.6 9.4 11.2V8.9L12.8 8.6L16 6.4L19.2 8.6L22.6 8.9V11.2Q25.4 13.6 27 18.2L22.2 20.6Q20.2 15.6 16 13.4Q11.8 15.6 9.8 20.6Z";
const ORC_BELLY = "M16 16.8Q18.4 18.6 19.2 20.6Q18 23.6 16 26.6Q14 23.6 12.8 20.6Q13.6 18.6 16 16.8Z";
const ORC_FILL = { fill: "var(--ico-orc, currentColor)" };
const ORC_MARK_FILL = { fill: "var(--ico-orc-mark, transparent)" };
const ORC_RING_STROKE = { stroke: "var(--ico-orc-ring, none)" };

export const OrcIcon = (p: IconProps) => {
  const id = useSvgId();
  return (
    <TechSvg {...p}>
      <defs>
        <mask id={`${id}-m-orc`}>
          <rect width="32" height="32" fill="#fff" />
          <path d={ORC_BODY} fill="#000" />
          <path d={ORC_BELLY} fill="#000" />
        </mask>
      </defs>
      {/* Camada extra (só colorized): preenche os recortes da orca. */}
      <g stroke="none" style={ORC_MARK_FILL}>
        <path d={ORC_BODY} />
        <path d={ORC_BELLY} />
      </g>
      <circle cx="16" cy="16" r="15" stroke="none" mask={`url(#${id}-m-orc)`} style={ORC_FILL} />
      {/* Camada extra (só colorized): contorno por dentro da silhueta. */}
      <circle cx="16" cy="16" r="14.4" fill="none" strokeWidth="1.2" style={ORC_RING_STROKE} />
    </TechSvg>
  );
};
