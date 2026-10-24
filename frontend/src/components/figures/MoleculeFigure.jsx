import React from "react"
import { asArray, atomLabel, boundsOf, makeProjector, toNum, toPoint } from "../../lib/figureSpec"
import { FigureFrame, Label, STROKE, labelWidth } from "./svg"

const WIDTH = 360
const HEIGHT = 220
const PADDING = { top: 26, right: 30, bottom: 26, left: 30 }
const FONT = 14
const BOND_GAP = 3

function parseAtoms(spec) {
  const atoms = new Map()
  for (const a of asArray(spec.atomes)) {
    if (!a || a.id == null) continue
    const pos = toPoint(a.position) || toPoint(a)
    if (!pos) continue
    const label = atomLabel(a.symbole ?? a.id)
    atoms.set(String(a.id), { id: String(a.id), pos, label, charge: a.charge, halfW: labelWidth(label, FONT) / 2 - 2 })
  }
  return atoms
}

/** Raccourcit un segment pour qu'il s'arrête au bord de l'étiquette de l'atome (boîte w × h). */
function trim(from, to, halfW, halfH = 9) {
  const dx = to[0] - from[0]
  const dy = to[1] - from[1]
  const len = Math.hypot(dx, dy) || 1
  const t = Math.min(halfW / (Math.abs(dx / len) || 1e-9), halfH / (Math.abs(dy / len) || 1e-9))
  return [from[0] + (dx / len) * Math.min(t, len / 2.2), from[1] + (dy / len) * Math.min(t, len / 2.2)]
}

function Bond({ a, b, ordre, cram }) {
  const p1 = trim(a.screen, b.screen, a.halfW)
  const p2 = trim(b.screen, a.screen, b.halfW)
  const len = Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) || 1
  const nx = -(p2[1] - p1[1]) / len
  const ny = (p2[0] - p1[0]) / len
  const line = (off, key) => (
    <line key={key} x1={p1[0] + nx * off} y1={p1[1] + ny * off} x2={p2[0] + nx * off} y2={p2[1] + ny * off}
      stroke="currentColor" strokeWidth={STROKE} strokeLinecap="round" />
  )
  if (cram === "avant") {
    const w = 4.5
    return <polygon points={`${p1[0]},${p1[1]} ${p2[0] + nx * w},${p2[1] + ny * w} ${p2[0] - nx * w},${p2[1] - ny * w}`} fill="currentColor" />
  }
  if (cram === "arriere") {
    const hashes = []
    for (let k = 1; k <= 7; k++) {
      const t = k / 7
      const w = 4.5 * t
      const cx = p1[0] + (p2[0] - p1[0]) * t
      const cy = p1[1] + (p2[1] - p1[1]) * t
      hashes.push(<line key={k} x1={cx + nx * w} y1={cy + ny * w} x2={cx - nx * w} y2={cy - ny * w} stroke="currentColor" strokeWidth={1.2} />)
    }
    return <g>{hashes}</g>
  }
  if (ordre === 2) return <g>{line(BOND_GAP, 1)}{line(-BOND_GAP, 2)}</g>
  if (ordre === 3) return <g>{line(0, 0)}{line(BOND_GAP * 1.6, 1)}{line(-BOND_GAP * 1.6, 2)}</g>
  return line(0, 0)
}

/** Directions (en radians, repère écran) les plus éloignées des liaisons d'un atome, pour y
 * placer ses doublets non liants sans chevaucher les traits. */
function freeDirections(occupied, count) {
  const candidates = Array.from({ length: 8 }, (_, k) => (k * Math.PI) / 4)
  const chosen = []
  const gap = (u, v) => { const d = Math.abs(u - v) % (2 * Math.PI); return Math.min(d, 2 * Math.PI - d) }
  for (let n = 0; n < count; n++) {
    let best = null
    let bestScore = -1
    for (const c of candidates) {
      const others = [...occupied, ...chosen]
      const score = others.length ? Math.min(...others.map((o) => gap(c, o))) : Math.PI
      if (score > bestScore + 1e-9) { best = c; bestScore = score }
    }
    chosen.push(best)
  }
  return chosen
}

/**
 * Formule développée, semi-développée ou schéma de Lewis : atomes (ou groupes « CH3 ») placés sur
 * une grille, liaisons simples/doubles/triples, représentation de Cram (coin plein « avant »,
 * hachuré « arriere »), doublets non liants et charges.
 */
export default function MoleculeFigure({ spec }) {
  const atoms = parseAtoms(spec)
  if (atoms.size === 0) return null
  const bounds = boundsOf([...atoms.values()].map((a) => a.pos))
  const { project } = makeProjector(bounds, { width: WIDTH, height: HEIGHT, padding: PADDING, equal: true, maxScale: 52 })
  for (const atom of atoms.values()) atom.screen = project(atom.pos)

  const bonds = asArray(spec.liaisons)
    .map((l) => ({ a: atoms.get(String(l?.de)), b: atoms.get(String(l?.vers)), ordre: Math.round(toNum(l?.ordre, 1)), cram: l?.cram }))
    .filter((l) => l.a && l.b && l.a !== l.b)

  const lonePairs = asArray(spec.doublets).flatMap((d, i) => {
    const atom = atoms.get(String(d?.atome))
    const count = Math.max(0, Math.min(4, Math.round(toNum(d?.nombre, 0))))
    if (!atom || count === 0) return []
    const occupied = bonds
      .filter((l) => l.a === atom || l.b === atom)
      .map((l) => { const o = l.a === atom ? l.b : l.a; return Math.atan2(o.screen[1] - atom.screen[1], o.screen[0] - atom.screen[0]) })
    return freeDirections(occupied, count).map((dir, k) => {
      const r = Math.max(atom.halfW, 8) + 5
      const cx = atom.screen[0] + Math.cos(dir) * r
      const cy = atom.screen[1] - 4 + Math.sin(dir) * r
      const tx = -Math.sin(dir) * 5
      const ty = Math.cos(dir) * 5
      return <line key={`lp-${i}-${k}`} x1={cx - tx} y1={cy - ty} x2={cx + tx} y2={cy + ty} stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" />
    })
  })

  return (
    <FigureFrame title={spec.titre} ariaLabel="Formule développée" width={WIDTH} height={HEIGHT}>
      <g className="text-base-content">
        {bonds.map((l, i) => <g key={`b-${i}`} transform="translate(0,-4)"><Bond {...l} /></g>)}
        {lonePairs}
        {[...atoms.values()].map((atom) => (
          <g key={atom.id}>
            <Label x={atom.screen[0]} y={atom.screen[1] + 1} text={atom.label} fontSize={FONT} fontWeight={600} />
            {atom.charge && (
              <text x={atom.screen[0] + atom.halfW + 2} y={atom.screen[1] - 9} fontSize={11} fontWeight={700} fill="currentColor">
                {String(atom.charge).replace("-", "−")}
              </text>
            )}
          </g>
        ))}
      </g>
    </FigureFrame>
  )
}
