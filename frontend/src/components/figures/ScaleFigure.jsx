import React from "react"
import { asArray, formatNumber, niceTicks, stackLabels, toNum } from "../../lib/figureSpec"
import { Arrow, FigureFrame, Label, SERIES_COLORS, labelWidth } from "./svg"

const WIDTH = 420

/** Échelle horizontale : échelle de pH, diagramme de prédominance (zones séparées par un pKa). */
function HorizontalScale({ spec }) {
  const zones = asArray(spec.zones)
    .map((z) => ({ de: toNum(z?.de, NaN), a: toNum(z?.a, NaN), label: z?.label }))
    .filter((z) => Number.isFinite(z.de) && Number.isFinite(z.a) && z.a !== z.de)
  const reperes = asArray(spec.reperes)
    .map((r) => ({ valeur: toNum(r?.valeur, NaN), label: r?.label }))
    .filter((r) => Number.isFinite(r.valeur))
  const values = [...zones.flatMap((z) => [z.de, z.a]), ...reperes.map((r) => r.valeur)]
  let min = toNum(spec.min, NaN)
  let max = toNum(spec.max, NaN)
  if (!Number.isFinite(min)) min = Math.min(...values, 0)
  if (!Number.isFinite(max)) max = Math.max(...values, min + 1)
  if (max - min < 1e-9) max = min + 1

  const left = 30
  const right = 380
  const axisY = 132
  const x = (v) => left + ((v - min) / (max - min)) * (right - left)

  // Zones : bandeau coloré au-dessus de l'axe ; une étiquette trop large pour sa zone passe
  // au-dessus du bandeau, en alternant deux hauteurs pour ne pas chevaucher sa voisine.
  // Bandeaux d'abord, étiquettes à la fin : les repères en pointillés passent sous les étiquettes.
  let raised = 0
  const zoneBands = []
  const zoneLabels = []
  zones.forEach((z, i) => {
    const x1 = x(Math.min(z.de, z.a))
    const x2 = x(Math.max(z.de, z.a))
    const fits = z.label && labelWidth(z.label, 11) < x2 - x1 - 4
    const labelY = fits ? 104 : 62 - (raised++ % 2) * 16
    const color = SERIES_COLORS[i % SERIES_COLORS.length]
    zoneBands.push(
      <g key={`z-${i}`} className={color}>
        <rect x={x1} y={78} width={x2 - x1} height={44} fill="currentColor" fillOpacity={0.15} />
        <line x1={x1} y1={78} x2={x2} y2={78} stroke="currentColor" strokeWidth={2.5} />
      </g>
    )
    if (z.label) zoneLabels.push(<Label key={`zl-${i}`} x={(x1 + x2) / 2} y={labelY} text={z.label} fontSize={11} fontWeight={600} className={color} />)
  })

  const ticks = niceTicks(min, max, spec.pas)
  return (
    <FigureFrame title={spec.titre} ariaLabel={`Échelle de ${spec.grandeur || "valeurs"}`} width={WIDTH} height={200}>
      {zoneBands}
      <g className="text-base-content">
        <Arrow x1={left - 8} y1={axisY} x2={right + 22} y2={axisY} width={1.5} size={8} />
        {ticks.map((t) => (
          <g key={`t-${t}`}>
            <line x1={x(t)} y1={axisY - 4} x2={x(t)} y2={axisY + 4} stroke="currentColor" strokeWidth={1.2} />
            <text x={x(t)} y={axisY + 16} fontSize={10} textAnchor="middle" fill="currentColor" fillOpacity={0.75}>{formatNumber(t)}</text>
          </g>
        ))}
        <Label x={right + 24} y={axisY + 30} text={spec.grandeur || ""} anchor="end" fontSize={12} />
        {reperes.map((r, i) => (
          <g key={`r-${i}`}>
            <line x1={x(r.valeur)} y1={72} x2={x(r.valeur)} y2={axisY + 6} stroke="currentColor" strokeDasharray="5 4" strokeWidth={1.2} />
            {r.label && <Label x={x(r.valeur)} y={axisY + 36 + (i % 2) * 16} text={r.label} fontSize={11} />}
          </g>
        ))}
      </g>
      {zoneLabels}
    </FigureFrame>
  )
}

/** Échelle verticale : classification de couples (E° des couples oxydant/réducteur, pKa des
 * couples acide/base), valeur croissante vers le haut, une espèce de chaque côté de l'axe. */
function VerticalScale({ spec }) {
  const couples = asArray(spec.couples)
    .map((c) => ({ valeur: toNum(c?.valeur, NaN), gauche: c?.gauche, droite: c?.droite }))
    .filter((c) => Number.isFinite(c.valeur))
    .sort((a, b) => b.valeur - a.valeur)
  const height = Math.max(200, 70 + couples.length * 26)
  const top = 48
  const bottom = height - 18
  const values = couples.map((c) => c.valeur)
  let min = Math.min(...values)
  let max = Math.max(...values)
  if (max - min < 1e-9) { min -= 1; max += 1 }
  const pad = (max - min) * 0.08
  const y = (v) => bottom - 8 - ((v - (min - pad)) / (max + pad - (min - pad))) * (bottom - 8 - top - 8)
  const axisX = 210
  const labelYs = stackLabels(couples.map((c) => y(c.valeur) + 4), { gap: 20, minY: top + 4, maxY: bottom })

  return (
    <FigureFrame title={spec.titre} ariaLabel={`Classification selon ${spec.grandeur || "la valeur"}`} width={WIDTH} height={height}>
      <g className="text-base-content">
        <Arrow x1={axisX} y1={bottom + 6} x2={axisX} y2={top - 12} width={1.5} size={8} />
        <Label x={axisX - 14} y={22} text={spec.gauche || ""} anchor="end" fontSize={12} />
        <Label x={axisX + 14} y={22} text={spec.droite || ""} anchor="start" fontSize={12} />
        <Label x={40} y={22} text={spec.grandeur || ""} anchor="start" fontSize={12} />
        {couples.map((c, i) => {
          const ty = y(c.valeur)
          const ly = labelYs[i]
          return (
            <g key={`c-${i}`}>
              <line x1={axisX - 5} y1={ty} x2={axisX + 5} y2={ty} stroke="currentColor" strokeWidth={1.4} />
              <text x={40} y={ly} fontSize={11} fill="currentColor" fillOpacity={0.75}>{formatNumber(c.valeur)}</text>
              <line x1={88} y1={ly - 4} x2={axisX - 8} y2={ty} stroke="currentColor" strokeOpacity={0.25} strokeWidth={0.8} />
              {c.gauche && <Label x={axisX - 14} y={ly} text={c.gauche} anchor="end" fontSize={12} className="text-primary" />}
              {c.droite && <Label x={axisX + 14} y={ly} text={c.droite} anchor="start" fontSize={12} className="text-secondary" />}
            </g>
          )
        })}
      </g>
    </FigureFrame>
  )
}

/** Échelle : verticale si le schéma décrit des couples, horizontale sinon (zones/repères). */
export default function ScaleFigure({ spec }) {
  if (asArray(spec.couples).length > 0) return <VerticalScale spec={spec} />
  if (asArray(spec.zones).length > 0 || asArray(spec.reperes).length > 0) return <HorizontalScale spec={spec} />
  return null
}
