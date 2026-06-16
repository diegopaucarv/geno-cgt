import enum


class RolDeUsuario(str, enum.Enum):
    INVESTIGADOR_PRINCIPAL = "INVESTIGADOR_PRINCIPAL"
    COLABORADOR = "COLABORADOR"
    ESTUDIANTE = "ESTUDIANTE"
    AUDITOR = "AUDITOR"
    VISUALIZADOR = "VISUALIZADOR"


class TipoPlanSuscripcion(str, enum.Enum):
    BASICO = "BASICO"
    PROFESIONAL = "PROFESIONAL"


class EstadoDeSaturacion(str, enum.Enum):
    ABIERTO = "ABIERTO"
    ESTABLE = "ESTABLE"
    SATURADO = "SATURADO"
    REVISION_FORZADA = "REVISION_FORZADA"


class RecategorizationAction(str, enum.Enum):
    """A5: Triada de decision para refinamiento de categorias (Recategorizacion.json)."""

    ENRICH = "ENRICH"
    SUBDIVIDE = "SUBDIVIDE"
    DIVIDE = "DIVIDE"


class AgentFamily(str, enum.Enum):
    """Familias de prompts CGT."""
    INDUCTIVE_DATA = "inductive_data"
    INDUCTIVE_CONCEPTS = "inductive_concepts"
    DESCRIPTIVE_DATA = "descriptive_data"
    EVALUATIVE = "evaluative"
    STRUCTURAL = "structural"
    ELABORATIVE = "elaborative"


class AgentPattern(str, enum.Enum):
    """Patrones agenciales soportados."""
    SELF_REFINEMENT = "self_refinement"
    REACT = "react"
    PLAN_EXECUTE = "plan_execute"
    DEBATE = "debate"
    HITL_MODIFICATION = "hitl_modification"
