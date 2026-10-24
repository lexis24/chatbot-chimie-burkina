import { describe, it, expect } from "vitest"
import {
  detectFigureType, montageModel, toPoint, stripKind, parseLabel, ceToLabel, atomLabel, niceTicks, formatNumber,
  makeProjector, boundsOf, stackLabels,
} from "./figureSpec"

const text = (raw) => parseLabel(raw).parts.map((p) => p.text).join("")

describe("detectFigureType", () => {
  it("reads the explicit type, accents and aliases included", () => {
    expect(detectFigureType({ type: "montage" })).toBe("montage")
    expect(detectFigureType({ type: "Échelle" })).toBe("echelle")
    expect(detectFigureType({ type: "molécule" })).toBe("molecule")
    expect(detectFigureType({ type: "formule développée" })).toBe("molecule")
    expect(detectFigureType({ type: "courbe" })).toBe("graphique")
    expect(detectFigureType({ type: "Géométrie" })).toBe("geometrie")
  })

  it("treats a typeless spec with points as a geometry figure (historical format)", () => {
    expect(detectFigureType({ points: [{ id: "A", x: 0, y: 0 }] })).toBe("geometrie")
  })

  it("rejects unknown types and unusable values", () => {
    expect(detectFigureType({ type: "circuit" })).toBeNull()
    expect(detectFigureType({})).toBeNull()
    expect(detectFigureType(null)).toBeNull()
    expect(detectFigureType([1, 2])).toBeNull()
  })
})

describe("montageModel", () => {
  it("accepts the known models, accents and aliases included", () => {
    expect(montageModel({ modele: "dosage" })).toBe("dosage")
    expect(montageModel({ modele: "Électrolyse" })).toBe("electrolyse")
    expect(montageModel({ modele: "chauffage à reflux" })).toBe("chauffage_reflux")
    expect(montageModel({ modele: "tube à essai" })).toBe("tube_essai")
    expect(montageModel({ modele: "titrage" })).toBe("dosage")
  })

  it("rejects an unknown or missing model", () => {
    expect(montageModel({ modele: "distillation" })).toBeNull()
    expect(montageModel({})).toBeNull()
  })
})

describe("toPoint / stripKind", () => {
  it("accepts [x, y], {x, y} and French decimal strings", () => {
    expect(toPoint([1, 2])).toEqual([1, 2])
    expect(toPoint({ x: "1,5", y: 0 })).toEqual([1.5, 0])
    expect(toPoint(["a", 2])).toBeNull()
    expect(toPoint(undefined)).toBeNull()
  })

  it("normalizes names written loosely by the model", () => {
    expect(stripKind("Électrode gauche")).toBe("electrode_gauche")
    expect(stripKind("pont-salin")).toBe("pont_salin")
  })
})

describe("parseLabel — chemical formulas", () => {
  it("splits subscripts and ion charges", () => {
    expect(parseLabel("H_2O").parts).toEqual([
      { text: "H", kind: "normal" }, { text: "2", kind: "sub" }, { text: "O", kind: "normal" },
    ])
    expect(parseLabel("Cu^{2+}").parts).toEqual([{ text: "Cu", kind: "normal" }, { text: "2+", kind: "sup" }])
    expect(parseLabel("Cu^2+").parts).toEqual([{ text: "Cu", kind: "normal" }, { text: "2+", kind: "sup" }])
    expect(parseLabel("H_3O^+").parts).toEqual([
      { text: "H", kind: "normal" }, { text: "3", kind: "sub" }, { text: "O", kind: "normal" }, { text: "+", kind: "sup" },
    ])
    expect(parseLabel("CH_3COO^-").parts.at(-1)).toEqual({ text: "-", kind: "sup" })
  })

  it("keeps the physics-style labels working", () => {
    expect(parseLabel("10^-3").parts).toEqual([{ text: "10", kind: "normal" }, { text: "-3", kind: "sup" }])
    expect(parseLabel("pK_a = 4,8").parts).toEqual([
      { text: "pK", kind: "normal" }, { text: "a", kind: "sub" }, { text: " = 4,8", kind: "normal" },
    ])
    expect(text("$0{,}10\\,\\text{mol/L}$")).toBe("0,10 mol/L")
    expect(text("$25^{\\circ}\\text{C}$")).toBe("25°C")
  })

  it("accepts \\ce{...} written by mistake in a label", () => {
    expect(text("$\\ce{SO4^2-}$")).toBe("SO42-")
    expect(parseLabel("\\ce{SO4^2-}").parts).toEqual([
      { text: "SO", kind: "normal" }, { text: "4", kind: "sub" }, { text: "2-", kind: "sup" },
    ])
    expect(ceToLabel("2H2 + O2 -> 2H2O")).toBe("2 H_{2} + O_{2} → 2 H_{2}O")
  })
})

describe("atomLabel", () => {
  it("subscripts the digits of a group written plainly", () => {
    expect(atomLabel("CH3")).toBe("CH_{3}")
    expect(atomLabel("COOH")).toBe("COOH")
    expect(atomLabel("NH_2")).toBe("NH_2")
  })
})

describe("niceTicks / formatNumber", () => {
  it("uses the requested step when given", () => {
    expect(niceTicks(0, 14, 2)).toEqual([0, 2, 4, 6, 8, 10, 12, 14])
  })

  it("picks a round step otherwise", () => {
    expect(niceTicks(0, 30)).toEqual([0, 5, 10, 15, 20, 25, 30])
  })

  it("formats with a French decimal comma", () => {
    expect(formatNumber(4.8)).toBe("4,8")
    expect(formatNumber(-0.76)).toBe("-0,76")
  })
})

describe("makeProjector / boundsOf", () => {
  it("maps y upwards to SVG y downwards with an equal scale, capped by maxScale", () => {
    const { project, scaleX } = makeProjector(boundsOf([[0, 0], [1, 0]]), {
      width: 200, height: 100, padding: { top: 0, right: 0, bottom: 0, left: 0 }, maxScale: 40,
    })
    expect(scaleX).toBe(40)
    const [, yLow] = project([0, -1])
    const [, yHigh] = project([0, 1])
    expect(yHigh).toBeLessThan(yLow)
  })
})

describe("stackLabels", () => {
  it("keeps labels apart and in range, preserving input order", () => {
    expect(stackLabels([50, 52, 120], { gap: 17, minY: 10, maxY: 200 })).toEqual([50, 67, 120])
    expect(stackLabels([190, 195], { gap: 17, minY: 10, maxY: 200 })).toEqual([183, 200])
    expect(stackLabels([5], { gap: 17, minY: 10, maxY: 200 })).toEqual([10])
  })
})
