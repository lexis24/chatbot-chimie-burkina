/**
 * Logique pure (sans React) des schémas de chimie décrits en JSON par le backend — blocs
 * ```figure``` du chat et champ `figure` des exercices et corrections (voir FIGURE_SCHEMAS côté
 * rag_system.py). Séparée des composants de rendu (components/figures/) pour être testable sans DOM.
 */

export const FIGURE_TYPES = ["montage", "graphique", "echelle", "molecule", "geometrie"]

/** Modèles de montages dessinés par MontageFigure (même liste que MONTAGE_MODELS côté backend). */
export const MONTAGE_MODELS = ["dosage", "electrolyse", "pile", "chauffage_reflux", "recueil_gaz", "combustion", "tube_essai"]

const TYPE_ALIASES = {
  montage: "montage", experience: "montage", dispositif: "montage",
  graphique: "graphique", graph: "graphique", courbe: "graphique",
  echelle: "echelle", diagramme: "echelle", diagramme_de_predominance: "echelle", classification: "echelle",
  molecule: "molecule", formule: "molecule", formule_developpee: "molecule", lewis: "molecule",
  geometrie: "geometrie", geometry: "geometrie",
}

const MONTAGE_ALIASES = {
  chauffage: "chauffage_reflux", reflux: "chauffage_reflux", chauffage_a_reflux: "chauffage_reflux",
  recueil: "recueil_gaz", recueil_de_gaz: "recueil_gaz", deplacement_d_eau: "recueil_gaz",
  tube: "tube_essai", tube_a_essai: "tube_essai", test: "tube_essai",
  titrage: "dosage", electrolyseur: "electrolyse", pile_electrochimique: "pile",
}

function stripAccents(value) {
  return String(value).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim()
}

/** Nom d'élément normalisé (« Électrolyse » -> "electrolyse", « tube à essai » -> "tube_a_essai") :
 * le modèle n'écrit pas toujours exactement l'identifiant attendu. */
export function stripKind(value) {
  return stripAccents(value ?? "").replace(/[\s'-]+/g, "_")
}

/** Type de schéma reconnu, ou null si la spec est inexploitable. Une spec sans `type` mais avec
 * des `points` est une figure géométrique (format historique, toujours accepté). */
export function detectFigureType(spec) {
  if (!spec || typeof spec !== "object" || Array.isArray(spec)) return null
  if (spec.type != null) return TYPE_ALIASES[stripKind(spec.type)] || null
  return Array.isArray(spec.points) && spec.points.length > 0 ? "geometrie" : null
}

/** Modèle de montage reconnu (alias tolérés), ou null. */
export function montageModel(spec) {
  const kind = stripKind(spec?.modele)
  const model = MONTAGE_ALIASES[kind] || kind
  return MONTAGE_MODELS.includes(model) ? model : null
}

export function toNum(value, fallback = 0) {
  const n = typeof value === "string" ? Number(value.replace(",", ".")) : Number(value)
  return Number.isFinite(n) ? n : fallback
}

/** Point [x, y] ou {x, y} -> [x, y] numérique, ou null. */
export function toPoint(value) {
  if (Array.isArray(value) && value.length >= 2) {
    const x = toNum(value[0], NaN)
    const y = toNum(value[1], NaN)
    return Number.isFinite(x) && Number.isFinite(y) ? [x, y] : null
  }
  if (value && typeof value === "object" && "x" in value && "y" in value) return toPoint([value.x, value.y])
  return null
}

export function asArray(value) {
  return Array.isArray(value) ? value : []
}

/** Boîte englobante d'une liste de points [x, y], élargie si dégénérée (point unique, ligne). */
export function boundsOf(points, margin = 0) {
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const p of points) {
    if (!p) continue
    minX = Math.min(minX, p[0]); maxX = Math.max(maxX, p[0])
    minY = Math.min(minY, p[1]); maxY = Math.max(maxY, p[1])
  }
  if (!Number.isFinite(minX)) return { minX: 0, maxX: 1, minY: 0, maxY: 1 }
  if (maxX - minX < 1e-6) { minX -= 1; maxX += 1 }
  if (maxY - minY < 1e-6) { minY -= 1; maxY += 1 }
  const mx = (maxX - minX) * margin
  const my = (maxY - minY) * margin
  return { minX: minX - mx, maxX: maxX + mx, minY: minY - my, maxY: maxY + my }
}

/** Projection des coordonnées du schéma (y vers le haut) vers l'écran SVG (y vers le bas).
 * `equal` : même échelle sur les deux axes (molécules), sinon échelles indépendantes (graphiques).
 * `maxScale` plafonne l'échelle (une petite molécule ne doit pas occuper tout le cadre). */
export function makeProjector(bounds, { width, height, padding, equal = true, maxScale = Infinity }) {
  const availW = width - padding.left - padding.right
  const availH = height - padding.top - padding.bottom
  let sx = availW / (bounds.maxX - bounds.minX)
  let sy = availH / (bounds.maxY - bounds.minY)
  let offX = padding.left
  let offY = padding.top
  if (equal) {
    const s = Math.min(sx, sy, maxScale)
    offX += (availW - (bounds.maxX - bounds.minX) * s) / 2
    offY += (availH - (bounds.maxY - bounds.minY) * s) / 2
    sx = s
    sy = s
  }
  const project = ([x, y]) => [offX + (x - bounds.minX) * sx, height - offY - (y - bounds.minY) * sy]
  return { project, scaleX: sx, scaleY: sy }
}

// ============================================================================
// Étiquettes : LaTeX léger / formules chimiques -> morceaux de texte SVG (indices, exposants)
// ============================================================================

const GREEK = {
  alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ε", varepsilon: "ε", theta: "θ", lambda: "λ",
  mu: "μ", nu: "ν", pi: "π", rho: "ρ", sigma: "σ", tau: "τ", phi: "φ", varphi: "φ", omega: "ω",
  Delta: "Δ", Theta: "Θ", Lambda: "Λ", Pi: "Π", Sigma: "Σ", Phi: "Φ", Omega: "Ω",
}

/** Une espèce chimique écrite à la manière de mhchem (« SO4^2- », « 2H2O », « Cu^2+ », « H3O+ »)
 * -> syntaxe d'étiquette (« SO_4^{2-} », « 2 H_2O », « Cu^{2+} », « H_3O^{+} »). */
function ceSpeciesToLabel(token) {
  let body = token
  const coef = /^(\d+)(?=[A-Za-z([])/.exec(body)?.[1] || ""
  body = body.slice(coef.length)
  const state = /\((?:aq|s|l|g)\)$/.exec(body)?.[0] || ""
  if (state) body = body.slice(0, -state.length)
  const charge = /\^\{?([0-9]*[+-])\}?$/.exec(body) || (body.length > 1 ? /([+-])$/.exec(body) : null)
  if (charge) body = body.slice(0, charge.index)
  body = body.replace(/([A-Za-z)\]])(\d+)/g, "$1_{$2}")
  return (coef ? `${coef} ` : "") + body + (charge ? `^{${charge[1]}}` : "") + state
}

/** Contenu d'un \ce{...} -> syntaxe d'étiquette (espèces, « + », flèches). */
export function ceToLabel(content) {
  const arrows = { "<=>": "⇌", "<->": "↔", "->": "→", "<-": "←" }
  return String(content)
    .replace(/<=>|<->|->|<-/g, (a) => ` ${arrows[a]} `)
    .split(/\s+/)
    .filter(Boolean)
    .map((tok) => (tok === "+" || tok === "=" || Object.values(arrows).includes(tok) ? tok : ceSpeciesToLabel(tok)))
    .join(" ")
}

function cleanLatex(raw) {
  return String(raw)
    .replace(/\\ce\{((?:[^{}]|\{[^{}]*\})*)\}/g, (_, content) => ceToLabel(content))
    .replace(/\$/g, "")
    .replace(/\\(?:text|mathrm|textrm|mathit)\{([^{}]*)\}/g, "$1")
    .replace(/\{,\}/g, ",")
    .replace(/\^\{?\\circ\}?/g, "°")
    .replace(/\\circ/g, "°")
    .replace(/\\[,;:! ]/g, " ")
    .replace(/\\times/g, "×")
    .replace(/\\cdot/g, "·")
    .replace(/\\approx/g, "≈")
    .replace(/\\(?:d|t)?frac\{([^{}]*)\}\{([^{}]*)\}/g, "$1/$2")
    // Commande inconnue (\vec au milieu d'une étiquette, \overline...) : on garde son argument,
    // jamais le nom de la commande lui-même.
    .replace(/\\([A-Za-z]+)/g, (m, name) => GREEK[name] ?? "")
}

/**
 * Découpe une étiquette (« H_2O », « Cu^{2+} », « H_3O^+ », « pK_a = 4,8 », « 0,10\,\text{mol/L} »...)
 * en `{ vector, parts: [{ text, kind: "normal" | "sub" | "sup" }] }`. `vector` vaut true si toute
 * l'étiquette est un vecteur (\vec ou \overrightarrow) : le rendu trace alors une flèche au-dessus.
 */
export function parseLabel(raw) {
  if (raw == null) return { vector: false, parts: [] }
  let text = String(raw).trim()
  let vector = false
  const vec = /^\$?\s*\\(?:vec|overrightarrow)\{([^{}]*)\}(.*?)\s*\$?$/.exec(text)
  if (vec) {
    vector = true
    text = vec[1] + vec[2]
  }
  text = cleanLatex(text)
  const parts = []
  // Indice/exposant entre accolades, ou sinon : des chiffres seuls s'ils viennent en tête (« H_2O »
  // -> indice « 2 », pas « 2O »), charge d'ion comprise (« Cu^2+ », « H_3O^+ ») ; à défaut la suite
  // alphanumérique (« V_bE », « 10^-3 »). En texte simple, le modèle n'écrit pas toujours les accolades.
  const re = /([_^])(?:\{([^{}]*)\}|(\d+[+-]?|-?[A-Za-z0-9′']+[+-]?|[+-]))/g
  let last = 0
  let m
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push({ text: text.slice(last, m.index), kind: "normal" })
    parts.push({ text: m[2] ?? m[3], kind: m[1] === "_" ? "sub" : "sup" })
    last = re.lastIndex
  }
  if (last < text.length) parts.push({ text: text.slice(last), kind: "normal" })
  return { vector, parts: parts.filter((p) => p.text !== "").map((p) => ({ ...p, text: p.text.replace(/[{}]/g, "") })) }
}

/** Symbole d'atome ou de groupe d'une formule développée (« CH3 », « COOH », « NH_2 ») : les
 * chiffres qui suivent une lettre passent en indice, sans attendre que le modèle écrive « _ ». */
export function atomLabel(symbol) {
  const text = String(symbol ?? "").trim()
  return /[_^\\]/.test(text) ? text : text.replace(/([A-Za-z)])(\d+)/g, "$1_{$2}")
}

/** Longueur approximative (en caractères) d'une étiquette analysée, pour dimensionner son fond. */
export function labelLength(parsed) {
  return parsed.parts.reduce((n, p) => n + p.text.length * (p.kind === "normal" ? 1 : 0.75), 0)
}

/** Graduations « rondes » entre min et max (pas de 1, 2 ou 5 × 10^n), ~5 à 8 graduations. */
export function niceTicks(min, max, step) {
  let pas = toNum(step, 0)
  if (!(pas > 0)) {
    const raw = (max - min) / 6
    const pow = 10 ** Math.floor(Math.log10(raw))
    const unit = raw / pow
    pas = (unit < 1.5 ? 1 : unit < 3.5 ? 2 : unit < 7.5 ? 5 : 10) * pow
  }
  const ticks = []
  const start = Math.ceil(min / pas - 1e-9) * pas
  for (let v = start; v <= max + pas * 1e-9 && ticks.length < 40; v += pas) ticks.push(Number(v.toPrecision(12)))
  return ticks
}

/** Nombre au format français (virgule décimale), sans zéros superflus. */
export function formatNumber(value) {
  const rounded = Number(Number(value).toPrecision(6))
  return String(rounded).replace(".", ",")
}

/**
 * Place des étiquettes en colonne sans chevauchement : chaque étiquette vise la hauteur `y` de
 * son point d'ancrage, mais reste à au moins `gap` de la précédente et dans [minY, maxY].
 * Renvoie les hauteurs retenues, dans l'ordre d'entrée.
 */
export function stackLabels(ys, { gap = 17, minY = 12, maxY = 260 } = {}) {
  const order = ys.map((y, i) => ({ y, i })).sort((a, b) => a.y - b.y)
  const placed = []
  for (const item of order) {
    const prev = placed.length ? placed[placed.length - 1].y : -Infinity
    placed.push({ i: item.i, y: Math.max(item.y, prev + gap, minY) })
  }
  // Débordement en bas : on remonte la colonne d'autant, sans repasser sous minY.
  const overflow = placed.length ? placed[placed.length - 1].y - maxY : 0
  if (overflow > 0) {
    for (let k = placed.length - 1; k >= 0; k--) {
      const limit = k === placed.length - 1 ? maxY : placed[k + 1].y - gap
      placed[k].y = Math.max(minY, Math.min(placed[k].y, limit))
    }
  }
  const result = new Array(ys.length)
  for (const p of placed) result[p.i] = p.y
  return result
}
