// ── Pipeline stage & agent display config ──────────────────────────
// Arquitectura pre-selective-coding:
//   data_management: por documento (secuencial)
//   open_coding:     cada 3 documentos (acumulativo, con HITL gate unificado)
//
// Principios:
//   - glaser classifier corre PRE-segmentación (tags markdown) — filtra antes de segmentar
//   - A2 (fa_prime_mover_extractor) extrae patrón de interés por documento desde baseline
//   - A3 (fa_population_context) se acumula cada 3 docs, lanza propuestas cada 3
//   - fc_main_concern_proposer/critic corren elaborativamente cada 3 docs
//   - HITL gate UNIFICADO al final de open_coding: concern, población, códigos, core category, hipótesis
//   - {chosen_concern} y {chosen_population} se inyectan condicionalmente en prompts downstream
//
// Agentes ignorados (duplicados): fa_process_identifier, fa_sense_maker,
//   fb_indicators_extractor, fb_pattern_labeler, fa_document_pattern_extractor

export interface AgentDef {
  id: string;
  label: string;
  tier: "PRO" | "FLASH" | "NLP";
  dependencies: string[];
  chain?: string;
  chainOrder?: number;
  independent?: boolean;
  iterationKey?: string;
}

export interface ChainDef {
  /** Canonical chain identifier — matches chain_runs.chain_id */
  id: string;
  /** Display label (i18n key) */
  label: string;
  /** Agents in this chain, in execution order */
  agents: AgentDef[];
  /** If true, this chain runs in parallel with other chains in the same stage */
  parallel?: boolean;
  /** Agent ID that synchronizes parallel chains before proceeding */
  sync_agent_id?: string;
  /** Default max retries for agents in this chain */
  default_max_retries?: number;
  /** Default timeout in seconds */
  default_timeout_seconds?: number;
}

export interface StageDef {
  key: string;
  icon: string;
  label: string;
  agents: AgentDef[];
  /** NEW: Named chains of agents. If present, agents in chains are separate from stage.agents */
  chains?: ChainDef[];
  /** If true, this stage triggers a HITL gate after completion */
  hasHITL?: boolean;
  /** If true, this stage runs once per batch (every 3 docs), not per document */
  batchTrigger?: boolean;
  /** Minimum docs needed before this stage can run */
  minDocs?: number;
}

export const FAMILY_COLORS: Record<string, string> = {
  PRO: "#A371F7",
  FLASH: "#3FB950",
  NLP: "#58A6FF",
};

export const PIPELINE_STAGES: StageDef[] = [
  // ═══ 1. DATA MANAGEMENT — Por documento (secuencial) ═══
  // Orden: Punctuator → Clasificador Glaser (tags markdown) → Segmentador (solo baseline) 
  {
    key: "data_management",
    icon: "📥",
    label: "pipeline.stage.data_management",
    agents: [
      {
        id: "util_punctuator",
        label: "pipeline.agent.util_punctuator",
        tier: "PRO",
        dependencies: [],
        independent: true,
        iterationKey: "data_mgmt",
      },
      {
        id: "fa_glaser_data_classifier",
        label: "pipeline.agent.clasificador_datos",
        tier: "PRO",
        dependencies: ["util_punctuator"],
        independent: true,
        iterationKey: "data_mgmt",
      },
      {
        id: "segmentar_documento",
        label: "pipeline.agent.segmentar_documento",
        tier: "NLP",
        dependencies: ["fa_glaser_data_classifier"],
        independent: true,
        iterationKey: "data_mgmt",
      },

    ],
    chains: [{
      id: "data_management_main",
      label: "pipeline.chain.data_management",
      agents: [
        {
          id: "util_punctuator",
          label: "pipeline.agent.util_punctuator",
          tier: "PRO",
          dependencies: [],
          independent: true,
          iterationKey: "data_mgmt",
        },
        {
          id: "fa_glaser_data_classifier",
          label: "pipeline.agent.clasificador_datos",
          tier: "PRO",
          dependencies: ["util_punctuator"],
          independent: true,
          iterationKey: "data_mgmt",
        },
        {
          id: "segmentar_documento",
          label: "pipeline.agent.segmentar_documento",
          tier: "NLP",
          dependencies: ["fa_glaser_data_classifier"],
          independent: true,
          iterationKey: "data_mgmt",
        },

      ],
      default_max_retries: 3,
      default_timeout_seconds: 600,
    }],
  },

  // ═══ 2. OPEN CODING — Cada 3 documentos (acumulativo) ═══
  // Disparador: ≥3 documentos con data_management completo
  // Flujo:
  //   A3 (population_context) — acumulativo cada 3
  //   B1 (incident_grouper) → B2 (code_generator) → B3 (label_critic)
  //   S1 (category_synthesizer) — merge con previos
  //   HYP (hypothesis_generator) → EV (evidence_classifier) → S2 (hypothesis_synthesizer)
  //   CFG (config_critic) — opcional
  //   ─── HITL GATE UNIFICADO ───
  //   fc_main_concern_proposer → fc_main_concern_critic
  //   El usuario decide: concern, población, core category candidate, revisa códigos/hipótesis
  {
    key: "open_coding",
    icon: "🧠",
    label: "pipeline.stage.open_coding",
    batchTrigger: true,
    minDocs: 3,
    agents: [
      // ── A3: Contexto poblacional acumulativo ──
      {
        id: "fa_population_context",
        label: "pipeline.agent.fa_population_context",
        tier: "PRO",
        dependencies: ["segmentar_documento"],
        independent: true,
        iterationKey: "open_coding",
      },
      // ── B1: Agrupador de incidentes (todos los docs) ──
      {
        id: "fb_incident_grouper",
        label: "pipeline.agent.fb_incident_grouper",
        tier: "PRO",
        dependencies: ["fa_population_context"],
        chain: "B1 → Códigos → S1",
        chainOrder: 1,
        iterationKey: "open_coding",
      },
      // ── B2: Generador de códigos desde grupos ──
      {
        id: "fb_code_generator",
        label: "pipeline.agent.fb_code_generator",
        tier: "PRO",
        dependencies: ["fb_incident_grouper"],
        chain: "B1 → Códigos → S1",
        chainOrder: 2,
        iterationKey: "open_coding",
      },
      // ── B3: Crítico de etiquetas (por código, FLASH) ──
      {
        id: "fb_label_critic",
        label: "pipeline.agent.fb_label_critic",
        tier: "FLASH",
        dependencies: ["fb_code_generator"],
        chain: "B1 → Códigos → S1",
        chainOrder: 3,
        iterationKey: "open_coding",
      },
      // ── S1: Sintetizador de categorías ──
      {
        id: "fd_category_synthesizer",
        label: "pipeline.agent.fd_category_synthesizer",
        tier: "PRO",
        dependencies: ["fb_label_critic"],
        chain: "S1 — Síntesis",
        chainOrder: 1,
        iterationKey: "open_coding",
      },
      // ── Línea paralela: Hipótesis ──
      {
        id: "fb_hypothesis_generator",
        label: "pipeline.agent.fb_hypothesis_generator",
        tier: "PRO",
        dependencies: ["fb_code_generator"],
        chain: "Hipótesis → S2",
        chainOrder: 1,
        iterationKey: "open_coding",
      },
      {
        id: "fb_evidence_classifier",
        label: "pipeline.agent.fb_evidence_classifier",
        tier: "FLASH",
        dependencies: ["fb_hypothesis_generator"],
        chain: "Hipótesis → S2",
        chainOrder: 2,
        iterationKey: "open_coding",
      },
      // ── S2: Sintetizador de hipótesis (NUEVO) ──
      {
        id: "fd_hypothesis_synthesizer",
        label: "pipeline.agent.fd_hypothesis_synthesizer",
        tier: "PRO",
        dependencies: ["fb_evidence_classifier"],
        chain: "Hipótesis → S2",
        chainOrder: 3,
        iterationKey: "open_coding",
      },
      // ── CFG: Crítico de configuración (opcional) ──
      {
        id: "fd_config_critic",
        label: "pipeline.agent.fd_config_critic",
        tier: "PRO",
        dependencies: ["fd_category_synthesizer", "fd_hypothesis_synthesizer"],
        independent: true,
        iterationKey: "open_coding",
      },
      // ── HITL: Concern Proposer → Concern Critic ──
      {
        id: "fc_main_concern_proposer",
        label: "pipeline.agent.fc_main_concern_proposer",
        tier: "PRO",
        dependencies: ["fd_category_synthesizer"],
        chain: "HITL — Concern",
        chainOrder: 1,
        iterationKey: "open_coding",
      },
      {
        id: "fc_main_concern_critic",
        label: "pipeline.agent.fc_main_concern_critic",
        tier: "PRO",
        dependencies: ["fc_main_concern_proposer"],
        chain: "HITL — Concern",
        chainOrder: 2,
        iterationKey: "open_coding",
      },
      {
        id: "population_generalizer",
        label: "pipeline.agent.population_generalizer",
        tier: "FLASH",
        dependencies: ["fc_main_concern_critic"],
        independent: true,
        iterationKey: "open_coding",
      },
    ],
    chains: [
      {
        id: "open_coding_main",
        label: "pipeline.chain.open_coding_main",
        agents: [
          {
            id: "fb_incident_grouper",
            label: "pipeline.agent.fb_incident_grouper",
            tier: "PRO",
            dependencies: ["fa_population_context"],
            chain: "B1 → Códigos → S1",
            chainOrder: 1,
            iterationKey: "open_coding",
          },
          {
            id: "fb_code_generator",
            label: "pipeline.agent.fb_code_generator",
            tier: "PRO",
            dependencies: ["fb_incident_grouper"],
            chain: "B1 → Códigos → S1",
            chainOrder: 2,
            iterationKey: "open_coding",
          },
          {
            id: "fb_label_critic",
            label: "pipeline.agent.fb_label_critic",
            tier: "FLASH",
            dependencies: ["fb_code_generator"],
            chain: "B1 → Códigos → S1",
            chainOrder: 3,
            iterationKey: "open_coding",
          },
          {
            id: "fd_category_synthesizer",
            label: "pipeline.agent.fd_category_synthesizer",
            tier: "PRO",
            dependencies: ["fb_label_critic"],
            chain: "S1 — Síntesis",
            chainOrder: 1,
            iterationKey: "open_coding",
          },
        ],
        default_max_retries: 3,
        default_timeout_seconds: 900,
      },
      {
        id: "open_coding_hypotheses",
        label: "pipeline.chain.open_coding_hypotheses",
        parallel: true,
        agents: [
          {
            id: "fb_hypothesis_generator",
            label: "pipeline.agent.fb_hypothesis_generator",
            tier: "PRO",
            dependencies: ["fb_code_generator"],
            chain: "Hipótesis → S2",
            chainOrder: 1,
            iterationKey: "open_coding",
          },
          {
            id: "fb_evidence_classifier",
            label: "pipeline.agent.fb_evidence_classifier",
            tier: "FLASH",
            dependencies: ["fb_hypothesis_generator"],
            chain: "Hipótesis → S2",
            chainOrder: 2,
            iterationKey: "open_coding",
          },
          {
            id: "fd_hypothesis_synthesizer",
            label: "pipeline.agent.fd_hypothesis_synthesizer",
            tier: "PRO",
            dependencies: ["fb_evidence_classifier"],
            chain: "Hipótesis → S2",
            chainOrder: 3,
            iterationKey: "open_coding",
          },
        ],
        default_max_retries: 2,
        default_timeout_seconds: 600,
      },
    ],
  },

  // ═══ 3. Selective Coding ═══
  {
    key: "selective_coding",
    icon: "🎯",
    label: "pipeline.stage.selective_coding",
    agents: [
      {
        id: "fc_core_category_proposer",
        label: "pipeline.agent.fc_core_category_proposer",
        tier: "PRO",
        dependencies: ["fc_main_concern_critic"],
        chain: "Core Category",
        chainOrder: 1,
        iterationKey: "selective_1",
      },
      {
        id: "fc_core_emergence_critic",
        label: "pipeline.agent.fc_core_emergence_critic",
        tier: "FLASH",
        dependencies: ["fc_core_category_proposer"],
        chain: "Core Category",
        chainOrder: 2,
        iterationKey: "selective_1",
      },
      {
        id: "fd_selective_reduction_proposer",
        label: "pipeline.agent.fd_selective_reduction_proposer",
        tier: "PRO",
        dependencies: ["fc_core_emergence_critic"],
        chain: "Reducción Selectiva",
        chainOrder: 1,
        iterationKey: "selective_2",
      },
      {
        id: "fd_selective_reduction_critic",
        label: "pipeline.agent.fd_selective_reduction_critic",
        tier: "PRO",
        dependencies: ["fd_selective_reduction_proposer"],
        chain: "Reducción Selectiva",
        chainOrder: 2,
        iterationKey: "selective_2",
      },
      {
        id: "fe_core_saturation_proposer",
        label: "pipeline.agent.fe_core_saturation_proposer",
        tier: "PRO",
        dependencies: ["fd_selective_reduction_critic"],
        chain: "Saturación",
        chainOrder: 1,
        iterationKey: "selective_3",
      },
      {
        id: "fe_core_saturation_critic",
        label: "pipeline.agent.fe_core_saturation_critic",
        tier: "FLASH",
        dependencies: ["fe_core_saturation_proposer"],
        chain: "Saturación",
        chainOrder: 2,
        iterationKey: "selective_3",
      },
      {
        id: "ff_database_a_proposer",
        label: "pipeline.agent.ff_database_a_proposer",
        tier: "PRO",
        dependencies: ["fe_core_saturation_critic"],
        chain: "Database A",
        chainOrder: 1,
        iterationKey: "selective_4",
      },
      {
        id: "ff_database_a_critic",
        label: "pipeline.agent.ff_database_a_critic",
        tier: "PRO",
        dependencies: ["ff_database_a_proposer"],
        chain: "Database A",
        chainOrder: 2,
        iterationKey: "selective_4",
      },
      {
        id: "ff_database_b_proposer",
        label: "pipeline.agent.ff_database_b_proposer",
        tier: "PRO",
        dependencies: ["ff_database_a_critic"],
        chain: "Database B",
        chainOrder: 1,
        iterationKey: "selective_5",
      },
      {
        id: "ff_database_b_critic",
        label: "pipeline.agent.ff_database_b_critic",
        tier: "PRO",
        dependencies: ["ff_database_b_proposer"],
        chain: "Database B",
        chainOrder: 2,
        iterationKey: "selective_5",
      },
    ],
    chains: [
      {
        id: "selective_main_concern",
        label: "pipeline.chain.selective_main_concern",
        agents: [
          {
            id: "fc_main_concern_proposer",
            label: "pipeline.agent.fc_main_concern_proposer",
            tier: "PRO",
            dependencies: ["fd_category_synthesizer"],
            iterationKey: "selective_1",
          },
          {
            id: "fc_main_concern_critic",
            label: "pipeline.agent.fc_main_concern_critic",
            tier: "PRO",
            dependencies: ["fc_main_concern_proposer"],
            iterationKey: "selective_1",
          },
        ],
        default_max_retries: 3,
        default_timeout_seconds: 600,
      },
      {
        id: "selective_core_emergence",
        label: "pipeline.chain.selective_core_emergence",
        agents: [
          {
            id: "fc_core_category_proposer",
            label: "pipeline.agent.fc_core_category_proposer",
            tier: "PRO",
            dependencies: ["fc_main_concern_critic"],
            chain: "Core Category",
            chainOrder: 1,
            iterationKey: "selective_1",
          },
          {
            id: "fc_core_emergence_critic",
            label: "pipeline.agent.fc_core_emergence_critic",
            tier: "FLASH",
            dependencies: ["fc_core_category_proposer"],
            chain: "Core Category",
            chainOrder: 2,
            iterationKey: "selective_1",
          },
        ],
        default_max_retries: 3,
        default_timeout_seconds: 600,
      },
      {
        id: "selective_reduction",
        label: "pipeline.chain.selective_reduction",
        agents: [
          {
            id: "fd_selective_reduction_proposer",
            label: "pipeline.agent.fd_selective_reduction_proposer",
            tier: "PRO",
            dependencies: ["fc_core_emergence_critic"],
            chain: "Reducción Selectiva",
            chainOrder: 1,
            iterationKey: "selective_2",
          },
          {
            id: "fd_selective_reduction_critic",
            label: "pipeline.agent.fd_selective_reduction_critic",
            tier: "PRO",
            dependencies: ["fd_selective_reduction_proposer"],
            chain: "Reducción Selectiva",
            chainOrder: 2,
            iterationKey: "selective_2",
          },
        ],
        default_max_retries: 3,
        default_timeout_seconds: 600,
      },
      {
        id: "selective_saturation",
        label: "pipeline.chain.selective_saturation",
        agents: [
          {
            id: "fe_core_saturation_proposer",
            label: "pipeline.agent.fe_core_saturation_proposer",
            tier: "PRO",
            dependencies: ["fd_selective_reduction_critic"],
            chain: "Saturación",
            chainOrder: 1,
            iterationKey: "selective_3",
          },
          {
            id: "fe_core_saturation_critic",
            label: "pipeline.agent.fe_core_saturation_critic",
            tier: "FLASH",
            dependencies: ["fe_core_saturation_proposer"],
            chain: "Saturación",
            chainOrder: 2,
            iterationKey: "selective_3",
          },
        ],
        default_max_retries: 3,
        default_timeout_seconds: 600,
      },
      {
        id: "selective_database_a",
        label: "pipeline.chain.selective_database_a",
        agents: [
          {
            id: "ff_database_a_proposer",
            label: "pipeline.agent.ff_database_a_proposer",
            tier: "PRO",
            dependencies: ["fe_core_saturation_critic"],
            chain: "Database A",
            chainOrder: 1,
            iterationKey: "selective_4",
          },
          {
            id: "ff_database_a_critic",
            label: "pipeline.agent.ff_database_a_critic",
            tier: "PRO",
            dependencies: ["ff_database_a_proposer"],
            chain: "Database A",
            chainOrder: 2,
            iterationKey: "selective_4",
          },
        ],
        default_max_retries: 3,
        default_timeout_seconds: 600,
      },
      {
        id: "selective_database_b",
        label: "pipeline.chain.selective_database_b",
        agents: [
          {
            id: "ff_database_b_proposer",
            label: "pipeline.agent.ff_database_b_proposer",
            tier: "PRO",
            dependencies: ["ff_database_a_critic"],
            chain: "Database B",
            chainOrder: 1,
            iterationKey: "selective_5",
          },
          {
            id: "ff_database_b_critic",
            label: "pipeline.agent.ff_database_b_critic",
            tier: "PRO",
            dependencies: ["ff_database_b_proposer"],
            chain: "Database B",
            chainOrder: 2,
            iterationKey: "selective_5",
          },
        ],
        default_max_retries: 3,
        default_timeout_seconds: 600,
      },
    ],
  },

  // ═══ 4. Theoretical Coding ═══
  {
    key: "theoretical_coding",
    icon: "🎨",
    label: "pipeline.stage.theoretical_coding",
    agents: [
      {
        id: "f6b_ghost_blob_mapper",
        label: "pipeline.agent.f6b_ghost_blob_mapper",
        tier: "PRO",
        dependencies: ["ff_database_b_critic"],
        independent: true,
        iterationKey: "theory_1",
      },
      {
        id: "f6b_memo_theoretical_tagger",
        label: "pipeline.agent.f6b_memo_theoretical_tagger",
        tier: "FLASH",
        dependencies: ["ff_database_b_critic"],
        independent: true,
        iterationKey: "theory_2",
      },
      {
        id: "f6b_ecosystem_gap_detector",
        label: "pipeline.agent.f6b_ecosystem_gap_detector",
        tier: "PRO",
        dependencies: ["ff_database_b_critic"],
        independent: true,
        iterationKey: "theory_3",
      },
      {
        id: "f6b_conceptual_elaborator",
        label: "pipeline.agent.f6b_conceptual_elaborator",
        tier: "PRO",
        dependencies: ["ff_database_b_critic"],
        independent: true,
        iterationKey: "theory_4",
      },
      {
        id: "f6b_definition_writer",
        label: "pipeline.agent.f6b_definition_writer",
        tier: "PRO",
        dependencies: ["ff_database_b_critic"],
        independent: true,
        iterationKey: "theory_5",
      },
      {
        id: "f6b_incident_elaborator",
        label: "pipeline.agent.f6b_incident_elaborator",
        tier: "PRO",
        dependencies: ["ff_database_b_critic"],
        independent: true,
        iterationKey: "theory_6",
      },
    ],
    chains: [{
      id: "theoretical_coding",
      label: "pipeline.chain.theoretical_coding",
      agents: [
        {
          id: "f6b_ghost_blob_mapper",
          label: "pipeline.agent.f6b_ghost_blob_mapper",
          tier: "PRO",
          dependencies: ["ff_database_b_critic"],
          independent: true,
          iterationKey: "theory_1",
        },
        {
          id: "f6b_memo_theoretical_tagger",
          label: "pipeline.agent.f6b_memo_theoretical_tagger",
          tier: "FLASH",
          dependencies: ["ff_database_b_critic"],
          independent: true,
          iterationKey: "theory_2",
        },
        {
          id: "f6b_ecosystem_gap_detector",
          label: "pipeline.agent.f6b_ecosystem_gap_detector",
          tier: "PRO",
          dependencies: ["ff_database_b_critic"],
          independent: true,
          iterationKey: "theory_3",
        },
        {
          id: "f6b_conceptual_elaborator",
          label: "pipeline.agent.f6b_conceptual_elaborator",
          tier: "PRO",
          dependencies: ["ff_database_b_critic"],
          independent: true,
          iterationKey: "theory_4",
        },
        {
          id: "f6b_definition_writer",
          label: "pipeline.agent.f6b_definition_writer",
          tier: "PRO",
          dependencies: ["ff_database_b_critic"],
          independent: true,
          iterationKey: "theory_5",
        },
        {
          id: "f6b_incident_elaborator",
          label: "pipeline.agent.f6b_incident_elaborator",
          tier: "PRO",
          dependencies: ["ff_database_b_critic"],
          independent: true,
          iterationKey: "theory_6",
        },
      ],
      default_max_retries: 2,
      default_timeout_seconds: 900,
    }],
  },

  // ═══ 5. Writing ═══
  {
    key: "writing",
    icon: "📝",
    label: "pipeline.stage.writing",
    agents: [
      {
        id: "f6a_natural_writer",
        label: "pipeline.agent.f6a_natural_writer",
        tier: "PRO",
        dependencies: ["ff_database_b_critic"],
        chain: "Writer→Critic→Gap",
        chainOrder: 1,
        iterationKey: "writing_1",
      },
      {
        id: "f6a_writing_critic",
        label: "pipeline.agent.f6a_writing_critic",
        tier: "PRO",
        dependencies: ["f6a_natural_writer"],
        chain: "Writer→Critic→Gap",
        chainOrder: 2,
        iterationKey: "writing_1",
      },
      {
        id: "f6a_gap_feeler",
        label: "pipeline.agent.f6a_gap_feeler",
        tier: "FLASH",
        dependencies: ["f6a_writing_critic"],
        chain: "Writer→Critic→Gap",
        chainOrder: 3,
        iterationKey: "writing_1",
      },
    ],
    chains: [{
      id: "writing_main",
      label: "pipeline.chain.writing",
      agents: [
        {
          id: "f6a_natural_writer",
          label: "pipeline.agent.f6a_natural_writer",
          tier: "PRO",
          dependencies: ["ff_database_b_critic"],
          chain: "Writer→Critic→Gap",
          chainOrder: 1,
          iterationKey: "writing_1",
        },
        {
          id: "f6a_writing_critic",
          label: "pipeline.agent.f6a_writing_critic",
          tier: "PRO",
          dependencies: ["f6a_natural_writer"],
          chain: "Writer→Critic→Gap",
          chainOrder: 2,
          iterationKey: "writing_1",
        },
        {
          id: "f6a_gap_feeler",
          label: "pipeline.agent.f6a_gap_feeler",
          tier: "FLASH",
          dependencies: ["f6a_writing_critic"],
          chain: "Writer→Critic→Gap",
          chainOrder: 3,
          iterationKey: "writing_1",
        },
      ],
      default_max_retries: 3,
      default_timeout_seconds: 900,
    }],
  },
];

// ── Helpers ─────────────────────────────────────────────────

export function canRunAgent(
  agentId: string,
  completedAgents: Set<string>,
): boolean {
  for (const stage of PIPELINE_STAGES) {
    const agent = stage.agents.find((a) => a.id === agentId);
    if (!agent) continue;
    return agent.dependencies.every((dep) => completedAgents.has(dep));
  }
  return false;
}

export function areAllAgentsDone(
  stageKey: string,
  completedAgents: Set<string>,
): boolean {
  const stage = PIPELINE_STAGES.find((s) => s.key === stageKey);
  if (!stage) return false;
  return stage.agents.every((a) => completedAgents.has(a.id));
}

export function getStageChains(stageKey: string): ChainDef[] {
  const stage = PIPELINE_STAGES.find(s => s.key === stageKey);
  return stage?.chains || [];
}

export function getChainById(chainId: string): ChainDef | undefined {
  for (const stage of PIPELINE_STAGES) {
    if (stage.chains) {
      const chain = stage.chains.find(c => c.id === chainId);
      if (chain) return chain;
    }
  }
  return undefined;
}
