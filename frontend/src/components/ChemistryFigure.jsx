import React from "react"
import { detectFigureType } from "../lib/figureSpec"
import GeometryFigure from "./GeometryFigure"
import MontageFigure from "./figures/MontageFigure"
import GraphFigure from "./figures/GraphFigure"
import ScaleFigure from "./figures/ScaleFigure"
import MoleculeFigure from "./figures/MoleculeFigure"

const RENDERERS = {
  montage: MontageFigure,
  graphique: GraphFigure,
  echelle: ScaleFigure,
  molecule: MoleculeFigure,
  geometrie: GeometryFigure,
}

/** Un schéma mal formé (JSON valide mais incohérent) ne doit jamais faire tomber tout le message
 * ou l'exercice qui le contient : il disparaît simplement, le texte reste lisible. */
class FigureBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error) {
    console.warn("[ChemistryFigure] schéma ignoré :", error)
  }

  render() {
    return this.state.failed ? null : this.props.children
  }
}

/**
 * Schéma de chimie décrit en JSON par le backend (blocs ```figure``` du chat, champ `figure`
 * des exercices et des corrections) : montage de laboratoire, graphique, échelle, molécule ou
 * figure géométrique. Le type est lu dans `spec.type` (voir lib/figureSpec.js et FIGURE_SCHEMAS
 * côté rag_system.py).
 */
export default function ChemistryFigure({ spec }) {
  const Renderer = RENDERERS[detectFigureType(spec)]
  if (!Renderer) return null
  return (
    <FigureBoundary>
      <Renderer spec={spec} />
    </FigureBoundary>
  )
}
