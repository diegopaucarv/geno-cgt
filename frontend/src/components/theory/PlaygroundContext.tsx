import {
  createContext, useContext, useState, useCallback, useEffect, type ReactNode,
} from "react";
import type {
  BlobData, TendrilData, GhostData, EcosystemState, Recommendation,
  RenameSuggestion, DefinitionVersion, Relationship,
} from "../../api/client";
import {
  getEcosystem, getRelationships, getGhosts, getRecommendations,
  getTheoreticalCodes, type TheoreticalCode,
} from "../../api/client";

interface PlaygroundState {
  projectId: string;
  blobs: BlobData[];
  tendrils: TendrilData[];
  ghosts: GhostData[];
  theoreticalCodes: TheoreticalCode[];
  recommendations: Recommendation[];
  selectedBlob: BlobData | null;
  selectedTendril: TendrilData | null;
  renameTarget: BlobData | null;
  renameSuggestions: RenameSuggestion[];
  definitionHistory: DefinitionVersion[];
  relationDetail: Relationship | null;
  dragState: { fromId: string; toId: string | null; type: "blob" | "ghost" } | null;
}

interface PlaygroundActions {
  setProjectId: (id: string) => void;
  refreshEcosystem: () => Promise<void>;
  selectBlob: (blob: BlobData | null) => void;
  selectTendril: (tendril: TendrilData | null) => void;
  openRename: (blob: BlobData) => void;
  closeRename: () => void;
  setDragState: (state: PlaygroundState["dragState"]) => void;
}

const PlaygroundCtx = createContext<PlaygroundState & PlaygroundActions | null>(null);

export function PlaygroundProvider({ children }: { children: ReactNode }) {
  const [projectId, setProjectId] = useState("");
  const [blobs, setBlobs] = useState<BlobData[]>([]);
  const [tendrils, setTendrils] = useState<TendrilData[]>([]);
  const [ghosts, setGhosts] = useState<GhostData[]>([]);
  const [theoreticalCodes, setTheoreticalCodes] = useState<TheoreticalCode[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [selectedBlob, setSelectedBlob] = useState<BlobData | null>(null);
  const [selectedTendril, setSelectedTendril] = useState<TendrilData | null>(null);
  const [renameTarget, setRenameTarget] = useState<BlobData | null>(null);
  const [renameSuggestions, setRenameSuggestions] = useState<RenameSuggestion[]>([]);
  const [definitionHistory, setDefinitionHistory] = useState<DefinitionVersion[]>([]);
  const [relationDetail, setRelationDetail] = useState<Relationship | null>(null);
  const [dragState, setDragState] = useState<PlaygroundState["dragState"]>(null);

  const refreshEcosystem = useCallback(async () => {
    if (!projectId) return;
    const [eco, rels, g, recs, tcs] = await Promise.all([
      getEcosystem(projectId).catch(() => null),
      getRelationships(projectId).catch(() => []),
      getGhosts(projectId).catch(() => []),
      getRecommendations(projectId).catch(() => []),
      getTheoreticalCodes(projectId).catch(() => []),
    ]);
    if (eco) { setBlobs(eco.blobs); setTendrils(eco.tendrils); }
    setGhosts(g as GhostData[]);
    setRecommendations(recs as Recommendation[]);
    setTheoreticalCodes(tcs as TheoreticalCode[]);
  }, [projectId]);

  useEffect(() => { if (projectId) refreshEcosystem(); }, [projectId]);

  return (
    <PlaygroundCtx.Provider
      value={{
        projectId, setProjectId, blobs, tendrils, ghosts, theoreticalCodes,
        recommendations, selectedBlob, selectedTendril, renameTarget,
        renameSuggestions, definitionHistory, relationDetail, dragState,
        refreshEcosystem,
        selectBlob: (b) => { setSelectedBlob(b); setSelectedTendril(null); },
        selectTendril: (t) => { setSelectedTendril(t); setSelectedBlob(null); },
        openRename: (b) => setRenameTarget(b),
        closeRename: () => setRenameTarget(null),
        setDragState,
      }}
    >
      {children}
    </PlaygroundCtx.Provider>
  );
}

export function usePlayground() {
  const ctx = useContext(PlaygroundCtx);
  if (!ctx) throw new Error("usePlayground must be inside PlaygroundProvider");
  return ctx;
}
