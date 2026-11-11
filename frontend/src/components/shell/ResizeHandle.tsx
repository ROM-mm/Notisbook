/**
 * Alça de redimensionamento (divisória sólida de 3px com área de captura maior).
 * `onDrag` recebe o deslocamento TOTAL (px) desde o início do arraste no eixo
 * da alça; `onDragStart` permite ao pai fixar o tamanho-base.
 */
import { useState, type CSSProperties, type PointerEvent } from "react";

// Espaço de layout (px) da variante "gap": 1px, para não distorcer a conta do
// arraste; o vão visual vem do padding dos cartões e a captura, de `hit`.
const GAP_SIZE = 1;
const LINE_SIZE = 3;
const GAP_HIT = 7;

interface ResizeHandleProps {
  orientation: "vertical" | "horizontal";
  label: string;
  onDragStart?: () => void;
  onDrag: (delta: number) => void;
  onReset?: () => void;
  /** "gap": 1px transparente entre cartões (vão de 14px vem dos cartões), só o grip no hover. */
  variant?: "line" | "gap";
}

export function ResizeHandle({ orientation, label, onDragStart, onDrag, onReset, variant = "line" }: ResizeHandleProps) {
  const [dragging, setDragging] = useState(false);
  const [hover, setHover] = useState(false);
  const [start, setStart] = useState(0);
  const axis = (e: PointerEvent) => (orientation === "vertical" ? e.clientX : e.clientY);

  const finish = (e: PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    setDragging(false);
    document.body.style.removeProperty("user-select");
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  };

  const vertical = orientation === "vertical";
  const gap = variant === "gap";
  // Linha de 3px no lugar da borda do painel; a área de captura vem de `hit`,
  // sobreposta à linha. Estilos inline: sem CSS module próprio.
  const line: CSSProperties = {
    position: "relative",
    zIndex: 2,
    flex: "none",
    touchAction: "none",
    cursor: vertical ? "col-resize" : "row-resize",
    [vertical ? "width" : "height"]: gap ? GAP_SIZE : LINE_SIZE,
    background: gap ? "transparent" : hover || dragging ? "var(--yellow)" : "var(--ink)",
    transition: "background var(--transition-fast)",
  };
  const grip: CSSProperties = {
    position: "absolute",
    top: "50%",
    left: "50%",
    width: vertical ? 7 : 32,
    height: vertical ? 32 : 7,
    transform: "translate(-50%, -50%)",
    border: "2px solid var(--ink)",
    background: dragging ? "var(--yellow)" : "var(--color-surface)",
    boxShadow: "2px 2px 0 var(--shadow)",
  };
  const reach = gap ? GAP_HIT : 3;
  const hit: CSSProperties = { position: "absolute", inset: vertical ? `0 -${reach}px` : `-${reach}px 0` };

  return (
    <div
      role="separator"
      aria-orientation={orientation}
      aria-label={label}
      style={line}
      onPointerEnter={() => setHover(true)}
      onPointerLeave={() => setHover(false)}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        e.currentTarget.setPointerCapture(e.pointerId);
        document.body.style.userSelect = "none";
        setStart(axis(e));
        setDragging(true);
        onDragStart?.();
      }}
      onPointerMove={(e) => {
        if (dragging) onDrag(axis(e) - start);
      }}
      onPointerUp={finish}
      onPointerCancel={finish}
      onLostPointerCapture={() => {
        setDragging(false);
        document.body.style.removeProperty("user-select");
      }}
      onDoubleClick={onReset}
    >
      <span style={hit} />
      {gap && (hover || dragging) ? <span style={grip} /> : null}
    </div>
  );
}
