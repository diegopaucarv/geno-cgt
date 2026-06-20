// ── Pipeline stage & agent display config ──────────────────────────
// Basado en secuencia_cgt.mermaid y los prompt.md reales.
// Solo para display en el frontend. La ejecución la maneja el orchestrator.

export interface AgentDef {
  id: string;
  label: string;
  tier: "PRO" | "FLASH" | "NLP";
  dependencies: string[]; // agent IDs that must complete before this one
  chain?: string; // chain label for grouping
  chainOrder?: number; // position within chain
  independent?: boolean;
  iterationKey?: string; // key for tracking iterations
}

export interface StageDef {
  key: string;
  icon: string;
  label: string;
  agents: AgentDef[];
}

// ── Family colors ─────────────────────────────────────────────────

export const FAMILY_COLORS: Record<string, string> = {
  PRO: "#A371F7",
  FLASH: "#3FB950",
  NLP: "#58A6FF",
};

// ── 5 fases con sus agentes reales ────────────────────────────────

export const PIPELINE_STAGES: StageDef[] = [
  // ═══ 1. Gestión de datos (por documento) ═══
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
        id: "segmentar_documento",
        label: "pipeline.agent.segmentar_documento",
        tier: "NLP",
        dependencies: ["util_punctuator"],
        independent: true,
        iterationKey: "data_mgmt",
      },
      {
        id: "fa_glaser_data_classifier",
        label: "pipeline.agent.fa_glaser_data_classifier",
        tier: "FLASH",
        dependencies: ["segmentar_documento"],
        independent: true,
        iterationKey: "data_mgmt",
      },
      {
        id: "fa_document_pattern_extractor",
        label: "pipeline.agent.fa_document_pattern_extractor",
        tier: "PRO",
        dependencies: ["fa_glaser_data_classifier"],
        independent: true,
        iterationKey: "data_mgmt",
      },
      {
        id: "incident_extractor",
        label: "pipeline.agent.incident_extractor",
        tier: "PRO",
        dependencies: ["fa_document_pattern_extractor"],
        independent: true,
        iterationKey: "data_mgmt",
      },
    ],
  },

  // ═══ 2. Open Coding (cada 3 docs) ═══
  {
    key: "open_coding",
    icon: "🧠",
    label: "pipeline.stage.open_coding",
    agents: [
      // ── Auxiliares (non-blocking, per doc) ──
      {
        id: "fa_population_context",
        label: "pipeline.agent.fa_population_context",
        tier: "PRO",
        dependencies: ["incident_extractor"],
        chain: "A1→A2",
        chainOrder: 1,
        iterationKey: "open_coding",
      },
      {
        id: "fa_process_identifier",
        label: "pipeline.agent.fa_process_identifier",
        tier: "PRO",
        dependencies: ["fa_population_context"],
        chain: "A1→A2",
        chainOrder: 2,
        iterationKey: "open_coding",
      },
      // ── A3: Sense-making (needs incidents from all docs) ──
      {
        id: "fa_sense_maker",
        label: "pipeline.agent.fa_sense_maker",
        tier: "PRO",
        dependencies: ["incident_extractor"],
        independent: true,
        iterationKey: "open_coding",
      },
      // ── Chain B1→B2→B3: Grouper → Labeler → Critic (cross-doc) ──
      {
        id: "fb_incident_grouper",
        label: "pipeline.agent.fb_incident_grouper",
        tier: "PRO",
        dependencies: ["incident_extractor"],
        chain: "B1→B2→B3",
        chainOrder: 1,
        iterationKey: "open_coding",
      },
      {
        id: "fb_pattern_labeler",
        label: "pipeline.agent.fb_pattern_labeler",
        tier: "PRO",
        dependencies: ["fb_incident_grouper"],
        chain: "B1→B2→B3",
        chainOrder: 2,
        iterationKey: "open_coding",
      },
      {
        id: "fb_label_critic",
        label: "pipeline.agent.fb_label_critic",
        tier: "FLASH",
        dependencies: ["fb_pattern_labeler"],
        chain: "B1→B2→B3",
        chainOrder: 3,
        iterationKey: "open_coding",
      },
      // ── Chain B2a→B2b: Indicadores → Códigos ──
      {
        id: "fb_indicators_extractor",
        label: "pipeline.agent.fb_indicators_extractor",
        tier: "FLASH",
        dependencies: ["fb_label_critic"],
        chain: "Indicadores → Códigos",
        chainOrder: 1,
        iterationKey: "open_coding",
      },
      {
        id: "fb_code_generator",
        label: "pipeline.agent.fb_code_generator",
        tier: "PRO",
        dependencies: ["fb_indicators_extractor"],
        chain: "Indicadores → Códigos",
        chainOrder: 2,
        iterationKey: "open_coding",
      },
      // ── Chain B3: Hipótesis → Evidence ──
      {
        id: "fb_hypothesis_generator",
        label: "pipeline.agent.fb_hypothesis_generator",
        tier: "PRO",
        dependencies: ["fb_code_generator"],
        chain: "Hipótesis → Evidence",
        chainOrder: 1,
        iterationKey: "open_coding",
      },
      {
        id: "fb_evidence_classifier",
        label: "pipeline.agent.fb_evidence_classifier",
        tier: "FLASH",
        dependencies: ["fb_hypothesis_generator"],
        chain: "Hipótesis → Evidence",
        chainOrder: 2,
        iterationKey: "open_coding",
      },
      // ── Chain S1→S2→S3: Synthesizers + Config Critic (post all batches) ──
      {
        id: "fd_category_synthesizer",
        label: "pipeline.agent.fd_category_synthesizer",
        tier: "PRO",
        dependencies: ["fb_evidence_classifier"],
        chain: "Síntesis S1→S2→S3",
        chainOrder: 1,
        iterationKey: "open_coding",
      },
      {
        id: "fd_hypothesis_synthesizer",
        label: "pipeline.agent.fd_hypothesis_synthesizer",
        tier: "PRO",
        dependencies: ["fd_category_synthesizer"],
        chain: "Síntesis S1→S2→S3",
        chainOrder: 2,
        iterationKey: "open_coding",
      },
      {
        id: "fd_config_critic",
        label: "pipeline.agent.fd_config_critic",
        tier: "PRO",
        dependencies: ["fd_hypothesis_synthesizer"],
        chain: "Síntesis S1→S2→S3",
        chainOrder: 3,
        iterationKey: "open_coding",
      },
    ],
  },

  // ═══ 3. Selective Coding ═══
  {
    key: "selective_coding",
    icon: "🎯",
    label: "pipeline.stage.selective_coding",
    agents: [
      // ── Acto 1: Main Concern (needs ALL open coding done) ──
      {
        id: "fc_main_concern_proposer",
        label: "pipeline.agent.fc_main_concern_proposer",
        tier: "PRO",
        dependencies: ["fd_config_critic"],
        chain: "Main Concern",
        chainOrder: 1,
        iterationKey: "selective_1",
      },
      {
        id: "fc_main_concern_critic",
        label: "pipeline.agent.fc_main_concern_critic",
        tier: "PRO",
        dependencies: ["fc_main_concern_proposer"],
        chain: "Main Concern",
        chainOrder: 2,
        iterationKey: "selective_1",
      },
      // ── Acto 2: Core Category ──
      {
        id: "fc_core_category_proposer",
        label: "pipeline.agent.fc_core_category_proposer",
        tier: "PRO",
        dependencies: ["fc_main_concern_critic"],
        chain: "Core Category",
        chainOrder: 1,
        iterationKey: "selective_2",
      },
      {
        id: "fc_core_emergence_critic",
        label: "pipeline.agent.fc_core_emergence_critic",
        tier: "FLASH",
        dependencies: ["fc_core_category_proposer"],
        chain: "Core Category",
        chainOrder: 2,
        iterationKey: "selective_2",
      },
      // ── Acto 3: Selective Reduction ──
      {
        id: "fd_selective_reduction_proposer",
        label: "pipeline.agent.fd_selective_reduction_proposer",
        tier: "PRO",
        dependencies: ["fc_core_emergence_critic"],
        chain: "Reducción Selectiva",
        chainOrder: 1,
        iterationKey: "selective_3",
      },
      {
        id: "fd_selective_reduction_critic",
        label: "pipeline.agent.fd_selective_reduction_critic",
        tier: "PRO",
        dependencies: ["fd_selective_reduction_proposer"],
        chain: "Reducción Selectiva",
        chainOrder: 2,
        iterationKey: "selective_3",
      },
      // ── Acto 4: Core Saturation ──
      {
        id: "fe_core_saturation_proposer",
        label: "pipeline.agent.fe_core_saturation_proposer",
        tier: "PRO",
        dependencies: ["fd_selective_reduction_critic"],
        chain: "Saturación",
        chainOrder: 1,
        iterationKey: "selective_4",
      },
      {
        id: "fe_core_saturation_critic",
        label: "pipeline.agent.fe_core_saturation_critic",
        tier: "FLASH",
        dependencies: ["fe_core_saturation_proposer"],
        chain: "Saturación",
        chainOrder: 2,
        iterationKey: "selective_4",
      },
      // ── Acto 5: Database A/B ──
      {
        id: "ff_database_a_proposer",
        label: "pipeline.agent.ff_database_a_proposer",
        tier: "PRO",
        dependencies: ["fe_core_saturation_critic"],
        chain: "Database A",
        chainOrder: 1,
        iterationKey: "selective_5",
      },
      {
        id: "ff_database_a_critic",
        label: "pipeline.agent.ff_database_a_critic",
        tier: "PRO",
        dependencies: ["ff_database_a_proposer"],
        chain: "Database A",
        chainOrder: 2,
        iterationKey: "selective_5",
      },
      {
        id: "ff_database_b_proposer",
        label: "pipeline.agent.ff_database_b_proposer",
        tier: "PRO",
        dependencies: ["ff_database_a_critic"],
        chain: "Database B",
        chainOrder: 1,
        iterationKey: "selective_6",
      },
      {
        id: "ff_database_b_critic",
        label: "pipeline.agent.ff_database_b_critic",
        tier: "PRO",
        dependencies: ["ff_database_b_proposer"],
        chain: "Database B",
        chainOrder: 2,
        iterationKey: "selective_6",
      },
    ],
  },

  // ═══ 4. Theoretical Coding (playground) ═══
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
  },

  // ═══ 5. Redacción ═══
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
  },
];

// ── Helper: check if an agent can run ──
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

// ── Helper: check if all agents in a stage are done ──
export function areAllAgentsDone(
  stageKey: string,
  completedAgents: Set<string>,
): boolean {
  const stage = PIPELINE_STAGES.find((s) => s.key === stageKey);
  if (!stage) return false;
  return stage.agents.every((a) => completedAgents.has(a.id));
}
