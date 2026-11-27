"""Gera a fonte "VT323 Smooth" a partir da VT323 (SIL OFL 1.1).

Mesmos glifos, cmap e métricas; os degraus de pixel viram contornos suaves
(rasteriza, desfoca, extrai a isolinha e reconstrói em TrueType quadrático).

Pré-requisitos: uv instalado; nenhuma dependência é adicionada ao projeto.

Uso (a partir de qualquer diretório):
    uv run --with fonttools --with pillow --with numpy --with scikit-image \
        --with scipy python scripts/fonts/smooth_vt323.py

Entrada: frontend/src/styles/fonts/VT323-Regular.ttf
Saída:   frontend/src/styles/fonts/VT323Smooth-Regular.ttf
Determinístico e idempotente: a saída depende só da entrada.
"""
import sys
from pathlib import Path

import numpy as np
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import ttProgram
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter
from skimage.measure import approximate_polygon, find_contours

FONTS_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "styles" / "fonts"
SOURCE = FONTS_DIR / "VT323-Regular.ttf"
TARGET = FONTS_DIR / "VT323Smooth-Regular.ttf"

# Parâmetros aprovados no protótipo; unidades da fonte (UPM 1000), exceto SCALE.
SIGMA_X = 24.0
SIGMA_Y = 32.0
THRESHOLD = 0.52
SCALE = 1.0  # pixels de raster por unidade
TOLERANCE = 1.2  # simplificação do polígono
CURVE_SEGMENT = 40.0  # segmentos menores que isso, com curvatura suave, viram off-curve

FAMILY = "VT323 Smooth"
FULL_NAME = "VT323 Smooth Regular"
POSTSCRIPT_NAME = "VT323Smooth-Regular"
MODIFICATION_NOTE = (
    "Derivada da VT323 (SIL OFL 1.1) com degraus de pixel suavizados; "
    "glifos, cmap e métricas preservados."
)


def flatten(recording, steps=8):
    """Converte gravação de pen em lista de polígonos (unidades da fonte)."""
    polys, cur, start = [], [], None
    for op, args in recording:
        if op == "moveTo":
            cur = [args[0]]
            start = args[0]
        elif op == "lineTo":
            cur.append(args[0])
        elif op == "qCurveTo":
            pts = list(args)
            if pts[-1] is None:  # contorno só com off-curve
                pts = pts[:-1]
                mids = [((pts[i][0] + pts[(i + 1) % len(pts)][0]) / 2,
                         (pts[i][1] + pts[(i + 1) % len(pts)][1]) / 2) for i in range(len(pts))]
                cur = [mids[-1]]
                for i, c in enumerate(pts):
                    _quad(cur, c, mids[i], steps)
                continue
            offs, end = pts[:-1], pts[-1]
            for i, c in enumerate(offs):
                nxt = end if i == len(offs) - 1 else (
                    (c[0] + offs[i + 1][0]) / 2, (c[1] + offs[i + 1][1]) / 2)
                _quad(cur, c, nxt, steps)
        elif op == "curveTo":
            p0 = cur[-1]
            c1, c2, p3 = args
            for k in range(1, steps + 1):
                t = k / steps
                mt = 1 - t
                cur.append((mt**3 * p0[0] + 3 * mt * mt * t * c1[0] + 3 * mt * t * t * c2[0] + t**3 * p3[0],
                            mt**3 * p0[1] + 3 * mt * mt * t * c1[1] + 3 * mt * t * t * c2[1] + t**3 * p3[1]))
        elif op in ("closePath", "endPath"):
            if len(cur) > 2:
                polys.append(cur)
            cur = []
    return polys


def _quad(cur, c, end, steps):
    p0 = cur[-1]
    for k in range(1, steps + 1):
        t = k / steps
        mt = 1 - t
        cur.append((mt * mt * p0[0] + 2 * mt * t * c[0] + t * t * end[0],
                    mt * mt * p0[1] + 2 * mt * t * c[1] + t * t * end[1]))


def signed_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def point_in_poly(pt, poly):
    x, y = pt
    xs, ys = poly[:, 0], poly[:, 1]
    xj, yj = np.roll(xs, 1), np.roll(ys, 1)
    cond = ((ys > y) != (yj > y)) & (x < (xj - xs) * (y - ys) / (yj - ys + 1e-12) + xs)
    return bool(np.count_nonzero(cond) % 2)


def rasterize(polys, scale, pad):
    """Even-odd não serve para TrueType com sobreposição; usa nonzero via
    composição: desenha cada contorno por orientação (externo soma, furo subtrai)."""
    pts = np.concatenate([np.asarray(p) for p in polys])
    xmin, ymin = pts.min(axis=0)
    xmax, ymax = pts.max(axis=0)
    ox, oy = xmin - pad, ymin - pad
    w = int(np.ceil((xmax - xmin + 2 * pad) * scale)) + 1
    h = int(np.ceil((ymax - ymin + 2 * pad) * scale)) + 1
    acc = np.zeros((h, w), dtype=np.int16)
    for p in polys:
        arr = np.asarray(p, dtype=float)
        a = signed_area(arr)
        if abs(a) < 1e-6:
            continue
        img = Image.new("L", (w, h), 0)
        xy = [((x - ox) * scale, (h - 1) - (y - oy) * scale) for x, y in arr]
        ImageDraw.Draw(img).polygon(xy, fill=1)
        # TrueType: horário (área < 0 em y-para-cima) = preenchido
        acc += (-1 if a > 0 else 1) * np.asarray(img, dtype=np.int16)
    mask = (acc != 0).astype(np.float32)
    return mask, ox, oy, h


def smooth_glyph(polys):
    pad = 4 * max(SIGMA_X, SIGMA_Y) + 10
    mask, ox, oy, h = rasterize(polys, SCALE, pad)
    blur = gaussian_filter(mask, sigma=(SIGMA_Y * SCALE, SIGMA_X * SCALE))
    contours = find_contours(blur, THRESHOLD)
    out = []
    for c in contours:
        if len(c) < 4:
            continue
        # (linha, coluna) -> unidades da fonte
        pts = np.column_stack([c[:, 1] / SCALE + ox, ((h - 1) - c[:, 0]) / SCALE + oy])
        if np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]
        pts = approximate_polygon(np.vstack([pts, pts[:1]]), tolerance=TOLERANCE)[:-1]
        if len(pts) < 3 or abs(signed_area(pts)) < 4:
            continue
        out.append(pts)
    # orientação: profundidade de aninhamento par = externo (horário), ímpar = furo
    oriented = []
    for i, p in enumerate(out):
        depth = sum(point_in_poly(p[0], q) for j, q in enumerate(out) if j != i)
        a = signed_area(p)
        want_cw = depth % 2 == 0
        if (a > 0) == want_cw:  # área > 0 = anti-horário
            p = p[::-1]
        oriented.append(p)
    return oriented


def to_ttglyph(contours, glyphset):
    pen = TTGlyphPen(glyphset)
    for p in contours:
        n = len(p)
        pts = [(int(round(x)), int(round(y))) for x, y in p]
        # remove duplicados consecutivos após arredondamento
        clean = [pts[i] for i in range(n) if pts[i] != pts[(i + 1) % n]]
        if len(clean) < 3:
            continue
        m = len(clean)
        on = []
        for i in range(m):
            a, b, c = np.array(clean[i - 1]), np.array(clean[i]), np.array(clean[(i + 1) % m])
            u, v = b - a, c - b
            lu, lv = np.hypot(*u), np.hypot(*v)
            cosang = float(np.dot(u, v) / (lu * lv + 1e-9))
            # vértice vira off-curve (curva suave) se ambos os segmentos forem
            # curtos e a curvatura moderada; trechos retos longos ficam on-curve
            smooth = lu < CURVE_SEGMENT and lv < CURVE_SEGMENT and cosang > 0.3
            on.append(not smooth)
        if not any(on):
            pen.qCurveTo(*clean, None)
            pen.closePath()
            continue
        k = on.index(True)
        seq = clean[k:] + clean[:k]
        flags = on[k:] + on[:k]
        pen.moveTo(seq[0])
        offs = []
        for pt, f in zip(seq[1:] + seq[:1], flags[1:] + flags[:1]):
            if f:
                if offs:
                    pen.qCurveTo(*offs, pt)
                    offs = []
                else:
                    pen.lineTo(pt)
            else:
                offs.append(pt)
        pen.closePath()
    return pen.glyph()


def rename(font):
    """Troca os nomes de família/arquivo; a VT323 não declara Reserved Font Name."""
    for rec in font["name"].names:
        if rec.nameID in (1, 16):
            rec.string = FAMILY
        elif rec.nameID == 4:
            rec.string = FULL_NAME
        elif rec.nameID == 6:
            rec.string = POSTSCRIPT_NAME
        elif rec.nameID == 3:
            rec.string = f"{rec.toUnicode()};smooth"
    for platform, enc, lang in ((1, 0, 0), (3, 1, 0x409)):
        font["name"].setName(MODIFICATION_NOTE, 10, platform, enc, lang)


def drop_obsolete_hinting(font):
    """O hinting original referencia pontos que deixam de existir."""
    for tag in ("fpgm", "prep", "cvt ", "DSIG", "hdmx", "LTSH", "VDMX"):
        if tag in font:
            del font[tag]
    if "gasp" in font:
        font["gasp"].gaspRange = {0xFFFF: 0x000F}
    maxp = font["maxp"]
    for attr in ("maxTwilightPoints", "maxStorage", "maxFunctionDefs",
                 "maxInstructionDefs", "maxStackElements", "maxSizeOfInstructions"):
        setattr(maxp, attr, 0)
    maxp.maxZones = 1


def main():
    font = TTFont(SOURCE, recalcTimestamp=False)  # preserva head.modified: saída reprodutível
    glyphset = font.getGlyphSet()
    glyf, hmtx = font["glyf"], font["hmtx"]
    converted, failures, empty, composites = 0, [], 0, 0
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if glyph.isComposite():
            composites += 1
            glyph.program = ttProgram.Program()
            glyph.program.fromBytecode(b"")
            continue
        if glyph.numberOfContours == 0:
            empty += 1
            continue
        pen = DecomposingRecordingPen(glyphset)
        glyphset[name].draw(pen)
        try:
            contours = smooth_glyph(flatten(pen.value))
            if not contours:
                raise ValueError("nenhum contorno após o limiar")
            new_glyph = to_ttglyph(contours, glyphset)
            new_glyph.recalcBounds(glyf)
        except ValueError as exc:
            failures.append(f"{name}: {exc}")  # mantém o glifo original
            continue
        glyf[name] = new_glyph
        hmtx[name] = (hmtx[name][0], new_glyph.xMin)
        converted += 1

    # Componentes suavizados mudam de xMin; o LSB dos compostos precisa acompanhar
    # (mantém head.flags bit 1: lsb == xMin). Advances permanecem intactos.
    for name in font.getGlyphOrder():
        if glyf[name].isComposite():
            glyf[name].recalcBounds(glyf)
            hmtx[name] = (hmtx[name][0], getattr(glyf[name], "xMin", 0))

    drop_obsolete_hinting(font)
    rename(font)
    font.save(TARGET)
    print(f"convertidos={converted} falhos={len(failures)} vazios={empty} compostos_mantidos={composites}")
    for failure in failures:
        print("  FALHA", failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
