/** Recuo por nível das árvores do painel de dados (Catalog e Notislake). */
import type { CSSProperties } from "react";

/** Recuo de cada nível da árvore, em px. */
export const INDENT_PX = 14;

/**
 * Estilo inline do nível: recuo da linha e variáveis das linhas-guia dos ancestrais
 * (`.treeGuides`): `--tree-indent` (passo) e `--tree-guides` (largura total).
 */
export const treeIndent = (level: number): CSSProperties =>
  ({
    paddingLeft: `${level * INDENT_PX}px`,
    "--tree-indent": `${INDENT_PX}px`,
    "--tree-guides": `${(level - 1) * INDENT_PX}px`,
  }) as CSSProperties;
