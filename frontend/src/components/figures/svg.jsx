import React from "react"
import { parseLabel, labelLength, stackLabels } from "../../lib/figureSpec"

export const VIEW_WIDTH = 360
export const VIEW_HEIGHT = 260
export const STROKE = 1.75

/** Couleurs des séries/zones successives : classes de thème (clair/sombre) appliquées via
 * `currentColor`, comme le reste du schéma — c'est ce que l'export PDF (html2canvas) reproduit. */
export const SERIES_COLORS = ["text-primary", "text-secondary", "text-accent", "text-error", "text-success"]

// Style en ligne plutôt qu'une classe utilitaire : il l'emporte toujours sur ce que le <pre>
// parent impose (police à chasse fixe, white-space: pre), quel que soit l'ordre des feuilles CSS.
export const FIGURE_TEXT_STYLE = { fontFamily: '"Source Sans 3", system-ui, -apple-system, "Segoe UI", sans-serif', whiteSpace: "normal" }

/** Cadre SVG commun : viewBox fixe, largeur fluide jusqu'à sa taille de conception (comme
 * GeometryFigure, voir RAPPORT_MOBILE.md §8), légende facultative sous le schéma. Police et
 * espacements forcés : un schéma du chat est rendu à l'intérieur du <pre> du bloc ```figure```,
 * dont il hériterait sinon la police à chasse fixe. */
export function FigureFrame({ title, ariaLabel, children, width = VIEW_WIDTH, height = VIEW_HEIGHT }) {
  return (
    <figure className="my-2 flex flex-col items-center" style={FIGURE_TEXT_STYLE}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        className="h-auto w-full overflow-visible text-base-content/80"
        style={{ maxWidth: width }}
        role="img"
        aria-label={title || ariaLabel}
      >
        {children}
      </svg>
      {title && <figcaption className="mt-1 text-center text-xs text-base-content/60">{title}</figcaption>}
    </figure>
  )
}

/** Pointe de flèche pleine en (x2, y2), orientée de (x1, y1) vers (x2, y2). Polygone explicite
 * plutôt qu'un <marker> SVG : les markers sont mal reproduits par html2canvas (export PDF). */
export function ArrowHead({ x1, y1, x2, y2, size = 8, className }) {
  const len = Math.hypot(x2 - x1, y2 - y1) || 1
  const ux = (x2 - x1) / len
  const uy = (y2 - y1) / len
  const bx = x2 - ux * size
  const by = y2 - uy * size
  const w = size * 0.45
  const pts = [[x2, y2], [bx - uy * w, by + ux * w], [bx + uy * w, by - ux * w]]
  return <polygon points={pts.map((p) => p.join(",")).join(" ")} fill="currentColor" className={className} />
}

export function Arrow({ x1, y1, x2, y2, width = STROKE, size = 8, dashed = false, className }) {
  const len = Math.hypot(x2 - x1, y2 - y1) || 1
  // Le trait s'arrête à la base de la pointe : sinon son extrémité dépasse sous la pointe.
  const ex = x2 - ((x2 - x1) / len) * size * 0.8
  const ey = y2 - ((y2 - y1) / len) * size * 0.8
  return (
    <g className={className}>
      <line x1={x1} y1={y1} x2={ex} y2={ey} stroke="currentColor" strokeWidth={width} strokeDasharray={dashed ? "5 4" : undefined} />
      <ArrowHead x1={x1} y1={y1} x2={x2} y2={y2} size={size} />
    </g>
  )
}

/** Largeur approximative d'une étiquette à la taille de police donnée (fond, alignements). */
export function labelWidth(text, fontSize = 12) {
  const parsed = parseLabel(text)
  return Math.max(labelLength(parsed) * fontSize * 0.6, fontSize * 0.7) + 6
}

/**
 * Étiquette avec fond légèrement opaque (lisible posée sur un trait), indices/exposants en
 * <tspan> décalés (formules chimiques : H₂O, Cu²⁺) et petite flèche au-dessus pour un vecteur
 * (voir parseLabel).
 */
export function Label({ x, y, text, anchor = "middle", fontSize = 12, fontWeight = 600, className, vector = false, box = true }) {
  const parsed = parseLabel(text)
  if (vector) parsed.vector = true
  if (parsed.parts.length === 0) return null
  const width = Math.max(labelLength(parsed) * fontSize * 0.6, fontSize * 0.7) + 6
  const boxX = anchor === "middle" ? x - width / 2 : anchor === "end" ? x - width : x
  const top = y - fontSize * (parsed.vector ? 1.45 : 1.0)
  const height = y + fontSize * 0.45 - top
  const arrowY = y - fontSize * 1.05
  let shift = 0
  return (
    <g className={className}>
      {box && <rect x={boxX} y={top} width={width} height={height} rx={3} className="fill-base-100" fillOpacity={0.85} />}
      <text x={x} y={y} fontSize={fontSize} fontWeight={fontWeight} textAnchor={anchor} fill="currentColor">
        {parsed.parts.map((p, i) => {
          const target = p.kind === "sub" ? 0.3 : p.kind === "sup" ? -0.4 : 0
          const dy = (target - shift) * fontSize
          shift = target
          return (
            <tspan key={i} dy={dy || undefined} fontSize={p.kind === "normal" ? undefined : fontSize * 0.72}>
              {/* Vrai signe moins en exposant (charges SO₄²⁻, puissances de dix) : un trait d'union y est illisible. */}
              {p.kind === "sup" ? p.text.replace(/-/g, "−") : p.text}
            </tspan>
          )
        })}
      </text>
      {parsed.vector && (
        <Arrow x1={boxX + 4} y1={arrowY} x2={boxX + width - 3} y2={arrowY} width={1.1} size={4.5} />
      )}
    </g>
  )
}

/**
 * Étiquettes de légende d'un montage, rangées en deux colonnes (gauche/droite) sans
 * chevauchement (voir stackLabels), chacune reliée à son point d'ancrage par un trait de rappel.
 * `items` : [{ at: [x, y], side: "left" | "right", text }].
 */
export function Callouts({ items, leftX, rightX, height, fontSize = 11 }) {
  const render = []
  for (const side of ["left", "right"]) {
    const column = items.filter((it) => it.side === side && it.text)
    const ys = stackLabels(column.map((it) => it.at[1] + 4), { gap: fontSize + 7, minY: 14, maxY: height - 6 })
    column.forEach((it, k) => {
      const y = ys[k]
      const x = side === "left" ? leftX : rightX
      const lineEnd = side === "left" ? x + 3 : x - 3
      render.push(
        <g key={`${side}-${k}`}>
          <polyline
            points={`${it.at[0]},${it.at[1]} ${lineEnd},${y - 4}`}
            fill="none" stroke="currentColor" strokeWidth={0.9} strokeOpacity={0.7}
          />
          <circle cx={it.at[0]} cy={it.at[1]} r={1.6} fill="currentColor" />
          <Label x={x} y={y} text={it.text} anchor={side === "left" ? "end" : "start"} fontSize={fontSize} fontWeight={500} />
        </g>
      )
    })
  }
  return <g className="text-base-content">{render}</g>
}
