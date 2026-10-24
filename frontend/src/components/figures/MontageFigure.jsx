import React from "react"
import { montageModel, stripKind } from "../../lib/figureSpec"
import { Callouts, FigureFrame, STROKE } from "./svg"

// Cadre plus large que les autres schémas : le matériel occupe le centre (x ≈ 130 à 310), les
// légendes les deux colonnes latérales (alignées sur LEFT_X à droite, sur RIGHT_X à gauche).
const WIDTH = 440
const HEIGHT = 270
const LEFT_X = 122
const RIGHT_X = 318

const GLASS = { fill: "none", stroke: "currentColor", strokeWidth: STROKE, strokeLinejoin: "round", strokeLinecap: "round" }

/** Liquide : couleur d'information du thème, translucide (même rendu à l'écran et dans le PDF). */
function Liquid({ points, d }) {
  const common = { className: "text-info", fill: "currentColor", fillOpacity: 0.22, stroke: "none" }
  return d ? <path d={d} {...common} /> : <polygon points={points} {...common} />
}

/** Intérieur d'un récipient occupé par un gaz : masque ce qui est dessiné dessous. */
function GasSpace(props) {
  return <rect {...props} className="fill-base-100" stroke="none" />
}

function Rod({ x, top = 14, bottom = 250, clampY, clampTo }) {
  return (
    <g {...GLASS}>
      <line x1={x} y1={top} x2={x} y2={bottom} strokeWidth={3} />
      <rect x={x - 18} y={bottom} width={36} height={6} rx={1.5} />
      {clampY != null && <line x1={x} y1={clampY} x2={clampTo} y2={clampY} strokeWidth={2.2} />}
    </g>
  )
}

// ============================================================================
// Modèles : chacun renvoie { draw, anchors } — anchors = emplacements de légende
// { slot, at: [x, y], side, def (nom générique), optional (dessiné seulement si fourni) }.
// ============================================================================

function dosage(labels) {
  const withProbe = Boolean(labels.sonde)
  const ticks = []
  for (let y = 25; y <= 145; y += 10) ticks.push(<line key={y} x1={226} y1={y} x2={y % 20 === 5 ? 233 : 230} y2={y} />)
  return {
    draw: (
      <g>
        <Rod x={160} clampY={55} clampTo={226} />
        <Liquid points="228,35 240,35 240,150 228,150" />
        <g {...GLASS}>
          <rect x={226} y={15} width={16} height={135} rx={2} />
          <g strokeWidth={1}>{ticks}</g>
          <rect x={230} y={150} width={8} height={20} />
          <line x1={216} y1={158} x2={252} y2={158} strokeWidth={3} />
          <circle cx={234} cy={158} r={4} className="fill-base-100" />
          <polygon points="230,170 238,170 234,182" />
        </g>
        <Liquid points="196,215 198,248 270,248 272,215" />
        <path d="M194,188 L198,248 L270,248 L274,188" {...GLASS} />
        <rect x={224} y={241} width={20} height={4} rx={2} fill="currentColor" />
        <g {...GLASS}>
          <rect x={182} y={250} width={108} height={14} rx={3} />
          <circle cx={278} cy={257} r={2.5} />
        </g>
        {withProbe && (
          <g {...GLASS}>
            <line x1={262} y1={150} x2={262} y2={237} strokeWidth={2.2} />
            <circle cx={262} cy={240} r={4} />
            <path d="M262,150 Q262,112 270,112" />
            <rect x={270} y={100} width={40} height={24} rx={3} />
            <text x={290} y={116} fontSize={11} fontWeight={600} textAnchor="middle" fill="currentColor" stroke="none">pH</text>
          </g>
        )}
      </g>
    ),
    anchors: [
      { slot: "burette", at: [242, 70], side: "right", def: "Burette graduée" },
      { slot: "sonde", at: [310, 112], side: "right", def: "pH-mètre", optional: true },
      { slot: "becher", at: [197, 228], side: "left", def: "Bécher" },
      { slot: "agitateur", at: [182, 257], side: "left", def: "Agitateur magnétique" },
    ],
  }
}

function electrolyse() {
  return {
    draw: (
      <g>
        <Liquid points="135.6,132 140,215 300,215 304.4,132" />
        <GasSpace x={174} y={48} width={28} height={72} />
        <GasSpace x={238} y={48} width={28} height={40} />
        <Liquid points="174,120 202,120 202,205 174,205" />
        <Liquid points="238,88 266,88 266,205 238,205" />
        <g {...GLASS}>
          <path d="M135,118 L140,215 L300,215 L305,118" />
          <path d="M173,205 L173,55 Q188,40 203,55 L203,205" />
          <path d="M237,205 L237,55 Q252,40 267,55 L267,205" />
        </g>
        <rect x={185} y={165} width={6} height={50} fill="currentColor" />
        <rect x={249} y={165} width={6} height={50} fill="currentColor" />
        <g {...GLASS}>
          <path d="M188,215 L188,242 L200,242" />
          <path d="M252,215 L252,242 L240,242" />
          <rect x={200} y={232} width={40} height={20} rx={2} />
        </g>
        <text x={207} y={246} fontSize={12} fontWeight={700} fill="currentColor">−</text>
        <text x={229} y={246} fontSize={12} fontWeight={700} fill="currentColor">+</text>
      </g>
    ),
    anchors: [
      { slot: "gaz_cathode", at: [175, 80], side: "left", def: "Gaz (cathode)" },
      { slot: "solution", at: [150, 175], side: "left", def: "Solution électrolytique" },
      { slot: "cathode", at: [185, 200], side: "left", def: "Cathode (−)" },
      { slot: "gaz_anode", at: [265, 66], side: "right", def: "Gaz (anode)" },
      { slot: "anode", at: [255, 200], side: "right", def: "Anode (+)" },
      { slot: "generateur", at: [240, 244], side: "right", def: "Générateur" },
    ],
  }
}

function pile(labels, spec) {
  const device = stripKind(spec.appareil || "V")
  const letter = device.startsWith("a") ? "A" : device.startsWith("l") ? null : "V"
  return {
    draw: (
      <g>
        <Liquid points="141,165 144,240 204,240 207,165" />
        <Liquid points="233,165 236,240 296,240 299,165" />
        <g {...GLASS}>
          <path d="M140,140 L144,240 L204,240 L208,140" />
          <path d="M232,140 L236,240 L296,240 L300,140" />
        </g>
        <path d="M190,215 L190,120 Q190,105 205,105 L235,105 Q250,105 250,120 L250,215" fill="none"
          stroke="currentColor" strokeWidth={11} strokeLinejoin="round" />
        <path d="M190,215 L190,120 Q190,105 205,105 L235,105 Q250,105 250,120 L250,215" fill="none"
          className="stroke-base-100" strokeWidth={7} strokeLinejoin="round" />
        <rect x={164} y={95} width={8} height={125} className="text-secondary" fill="currentColor" />
        <rect x={264} y={95} width={8} height={125} className="text-accent" fill="currentColor" />
        <g {...GLASS}>
          <path d="M168,95 L168,60 L203,60" />
          <path d="M268,95 L268,60 L237,60" />
          <circle cx={220} cy={60} r={17} className="fill-base-100" />
          {letter == null && (
            <>
              <line x1={208} y1={48} x2={232} y2={72} />
              <line x1={232} y1={48} x2={208} y2={72} />
            </>
          )}
        </g>
        {letter && <text x={220} y={65} fontSize={15} fontWeight={700} textAnchor="middle" fill="currentColor">{letter}</text>}
      </g>
    ),
    anchors: [
      { slot: "electrode_gauche", at: [164, 112], side: "left", def: "Électrode" },
      { slot: "solution_gauche", at: [146, 205], side: "left", def: "Solution" },
      { slot: "appareil", at: [203, 52], side: "left", def: null, optional: true },
      { slot: "pont_salin", at: [250, 128], side: "right", def: "Pont salin" },
      { slot: "electrode_droite", at: [272, 112], side: "right", def: "Électrode" },
      { slot: "solution_droite", at: [294, 205], side: "right", def: "Solution" },
    ],
  }
}

function chauffageReflux() {
  return {
    draw: (
      <g>
        <Rod x={160} clampY={70} clampTo={206} />
        {/* Ballon : arc de rayon 32 attaché au col en (212, 168) et (228, 168), centre en y ≈ 199. */}
        <Liquid d="M188.6,205 A32,32 0 0 0 251.4,205 Z" />
        <g {...GLASS}>
          <rect x={206} y={20} width={28} height={100} rx={4} />
          <rect x={214} y={10} width={12} height={112} />
          <line x1={234} y1={105} x2={256} y2={105} strokeWidth={3} />
          <line x1={206} y1={35} x2={184} y2={35} strokeWidth={3} />
          <rect x={212} y={122} width={16} height={46} />
          <path d="M212,168 A32,32 0 1 0 228,168" />
          <path d="M178,212 L178,252 L262,252 L262,212" strokeWidth={2.2} />
          <path d="M178,212 Q220,262 262,212" strokeWidth={1.2} strokeDasharray="3 3" />
        </g>
      </g>
    ),
    anchors: [
      { slot: "eau_sortie", at: [184, 35], side: "left", def: "Sortie d'eau" },
      { slot: "ballon", at: [196, 204], side: "left", def: "Mélange réactionnel" },
      { slot: "chauffe_ballon", at: [178, 240], side: "left", def: "Chauffe-ballon" },
      { slot: "refrigerant", at: [234, 60], side: "right", def: "Réfrigérant à eau" },
      { slot: "eau_entree", at: [256, 105], side: "right", def: "Entrée d'eau" },
    ],
  }
}

function recueilGaz() {
  return {
    draw: (
      <g>
        <Liquid points="137.5,210 130,240 200,240 192.5,210" />
        <Liquid points="215.8,182 218,245 320,245 322.2,182" />
        <GasSpace x={256} y={103} width={28} height={67} />
        <Liquid points="256,170 284,170 284,236 256,236" />
        <g {...GLASS}>
          <path d="M150,130 L150,160 L130,240 L200,240 L180,160 L180,130" />
          <rect x={147} y={122} width={36} height={10} rx={1.5} />
          <path d="M215,168 L218,245 L320,245 L323,168" />
          <path d="M255,236 L255,110 Q270,95 285,110 L285,236" />
          <path d="M165,122 L165,92 L232,92 L232,240 L268,240 L268,226" strokeWidth={2.4} />
        </g>
        <g fill="none" stroke="currentColor" strokeWidth={1}>
          <circle cx={268} cy={214} r={3} />
          <circle cx={271} cy={198} r={2.4} />
          <circle cx={266} cy={184} r={2} />
        </g>
      </g>
    ),
    anchors: [
      { slot: "tube_degagement", at: [180, 92], side: "left", def: "Tube à dégagement" },
      { slot: "reactifs", at: [140, 226], side: "left", def: "Réactifs" },
      { slot: "gaz", at: [284, 135], side: "right", def: "Gaz recueilli" },
      { slot: "cuve", at: [318, 215], side: "right", def: "Cuve à eau" },
    ],
  }
}

function combustion(labels) {
  const withLiquid = Boolean(labels.liquide)
  return {
    draw: (
      <g>
        {withLiquid && <Liquid points="151,215 289,215 289,239 151,239" />}
        <g {...GLASS}>
          <path d="M175,92 L175,108 Q150,118 150,140 L150,240 L290,240 L290,140 Q290,118 265,108 L265,92" />
          <line x1={165} y1={90} x2={275} y2={90} strokeWidth={3} />
          <line x1={220} y1={30} x2={220} y2={175} strokeWidth={2} />
          <path d="M206,175 Q220,192 234,175 Z" />
        </g>
        <path d="M212,174 Q211,158 220,146 Q229,158 228,174 Q224,165 220,168 Q216,165 212,174 Z"
          className="text-warning" fill="currentColor" fillOpacity={0.85} />
      </g>
    ),
    anchors: [
      { slot: "gaz", at: [160, 135], side: "left", def: "Dioxygène" },
      { slot: "combustible", at: [208, 180], side: "left", def: "Combustible" },
      { slot: "cuillere", at: [220, 60], side: "right", def: "Cuillère à combustion" },
      { slot: "liquide", at: [289, 228], side: "right", def: null, optional: true },
    ],
  }
}

function tubeEssai(labels) {
  const withPrecipitate = Boolean(labels.observation)
  const grains = []
  if (withPrecipitate) {
    for (let i = 0; i < 14; i++) grains.push(<circle key={i} cx={205 + ((i * 7) % 20)} cy={212 + ((i * 5) % 14)} r={1.6} />)
  }
  return {
    draw: (
      <g>
        <Liquid d="M201,160 L201,215 A14,14 0 0 0 229,215 L229,160 Z" />
        <path d="M200,60 L200,215 A15,15 0 0 0 230,215 L230,60" {...GLASS} />
        {withPrecipitate && <g className="text-secondary" fill="currentColor">{grains}</g>}
        <g {...GLASS}>
          <rect x={209} y={14} width={12} height={28} rx={2} />
          <ellipse cx={215} cy={12} rx={9} ry={7} className="fill-base-100" />
          <polygon points="211,42 219,42 215,50" />
        </g>
        <circle cx={215} cy={58} r={2.8} className="text-info" fill="currentColor" fillOpacity={0.6} />
      </g>
    ),
    anchors: [
      { slot: "ajout", at: [221, 28], side: "right", def: "Réactif ajouté" },
      { slot: "contenu", at: [201, 185], side: "left", def: "Solution testée" },
      { slot: "observation", at: [229, 218], side: "right", def: null, optional: true },
    ],
  }
}

const MODELS = {
  dosage,
  electrolyse,
  pile,
  chauffage_reflux: chauffageReflux,
  recueil_gaz: recueilGaz,
  combustion,
  tube_essai: tubeEssai,
}

/**
 * Montage de laboratoire choisi parmi des modèles prédéfinis (voir MONTAGE_MODELS) : le backend
 * fournit le modèle et les étiquettes, le dessin place lui-même la verrerie. Une étiquette absente
 * garde le nom générique du matériel ; un élément facultatif (pH-mètre, eau de chaux, précipité)
 * n'est dessiné que si son étiquette est fournie.
 */
export default function MontageFigure({ spec }) {
  const model = montageModel(spec)
  if (!model) return null
  const labels = spec.etiquettes && typeof spec.etiquettes === "object" ? spec.etiquettes : {}
  const { draw, anchors } = MODELS[model](labels, spec)
  const items = anchors
    .map((a) => {
      const given = labels[a.slot]
      if (a.optional && !given) return null
      return { at: a.at, side: a.side, text: given != null && given !== "" ? String(given) : a.def }
    })
    .filter(Boolean)
  return (
    <FigureFrame title={spec.titre} ariaLabel={`Montage : ${model.replace("_", " ")}`} width={WIDTH} height={HEIGHT}>
      <g className="text-base-content/80">{draw}</g>
      <Callouts items={items} leftX={LEFT_X} rightX={RIGHT_X} height={HEIGHT} />
    </FigureFrame>
  )
}
