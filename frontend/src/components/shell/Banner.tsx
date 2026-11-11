/** Faixa de marca no topo do shell: ícone, wordmark, frase e decoração de fluxo (puramente visual). */
import styles from "./Banner.module.css";
import { BrandMark } from "./icons";

export function Banner() {
  return (
    <header className={styles.banner} aria-label="Notisbook">
      <BrandMark size={32} />
      <span className={styles.wordmark}>notisbook</span>
      <span className={styles.separator} aria-hidden="true" />
      <span className={styles.tagline}>Explore. Code. Transform.</span>
      <svg
        className={styles.flow}
        viewBox="0 0 320 56"
        preserveAspectRatio="xMaxYMid slice"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M0 40 C 50 40, 60 16, 110 16 S 170 40, 220 40 S 280 16, 320 16" />
        <path d="M0 48 C 60 48, 90 28, 150 28 S 250 48, 320 30" />
        <g fill="currentColor" stroke="none">
          <circle cx="110" cy="16" r="3" />
          <circle cx="220" cy="40" r="3" />
          <circle cx="150" cy="28" r="2.5" />
          <circle cx="290" cy="22" r="3" />
        </g>
      </svg>
    </header>
  );
}
