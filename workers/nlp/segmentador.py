import gc
import logging
import os
import re
import unicodedata
from typing import Optional

import numpy as np
import spacy
import stanza
from embedding_client import EmbeddingClient
from rapidfuzz import fuzz
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from spacy.language import Language

# ── GPU / CPU switch ──────────────────────────────────────────────────────────
_USE_GPU = os.getenv("USE_GPU", "false").lower() in ("1", "true", "yes")
if _USE_GPU:
    spacy.require_gpu()
    _stanza_gpu = True
else:
    _stanza_gpu = False

# ── Stanza coref bug-fix ──────────────────────────────────────────────────────
try:
    from stanza.models.coref.config import Config as _StanzaCorefCfg

    if not hasattr(_StanzaCorefCfg, "_coref_patched_flag"):
        _StanzaCorefCfg._coref_original_init = _StanzaCorefCfg.__init__

        def _coref_patched_init(self, *args, **kwargs):
            kwargs.setdefault("plateau_epochs", 10)
            _StanzaCorefCfg._coref_original_init(self, *args, **kwargs)

        _StanzaCorefCfg.__init__ = _coref_patched_init
        _StanzaCorefCfg._coref_patched_flag = True
        print("[PATCH] Stanza coref Config parcheado correctamente.")
except ImportError:
    pass


@Language.component("conversational_sbd")
def conversational_sbd(doc):
    pivots = {
        "entonces",
        "bueno",
        "o sea",
        "además",
        "pero",
        "porque",
        "luego",
        "así que",
    }
    for i in range(len(doc) - 2):
        token = doc[i]
        if (
            token.lower_ in pivots
            and doc[i + 1].text == ","
            and doc[i + 2].pos_ == "VERB"
        ):
            doc[i].is_sent_start = True
        elif token.lower_ in {"bueno", "o sea", "entonces"}:
            doc[i].is_sent_start = True
    return doc


# ── Simple token counter (no model weights needed) ─────────────────────────────


def _count_tokens(text: str) -> int:
    """Rough BPE token estimate: ~1.3 tokens per Spanish word."""
    words = len(text.split())
    return max(1, int(words * 1.3))


# ═══════════════════════════════════════════════════════════════════════════════
# AttentionShiftDetector
# ═══════════════════════════════════════════════════════════════════════════════


class AttentionShiftDetector:
    def __init__(self):
        self.device = -1  # CPU only

    def get_attention_weights(self, text):
        # Placeholder — no transformer loaded
        return None

    def compare_attention(self, attn1, attn2):
        return 0.0

    def detect_topic_shift(self, seg1, seg2):
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# ClassicSegmenter — embedding-aware, no NLI model
# ═══════════════════════════════════════════════════════════════════════════════


class ClassicSegmenter:
    def __init__(self, embedding_client: EmbeddingClient, spacy_model: str):
        self.nlp = spacy.load(spacy_model)
        self.embedding_client = embedding_client
        self.embedding_cache: dict[str, np.ndarray] = {}

    def semantic_cohesion_score(self, segment1: str, segment2: str) -> float:
        doc1 = self.nlp(segment1)
        doc2 = self.nlp(segment2)
        ents1 = {ent.text for ent in doc1.ents}
        ents2 = {ent.text for ent in doc2.ents}
        if not (ents1 or ents2):
            return 0.0
        intersection = ents1 & ents2
        union = ents1 | ents2
        return len(intersection) / len(union)

    def compute_semantic_shift(self, segment1: str, segment2: str) -> float:
        """Cosine distance via TEI embeddings (replaces NLI bart-large-mnli)."""
        try:
            if not segment1 or not segment2:
                return 1.0
            seg1_tail = segment1[-1000:] if len(segment1) > 1000 else segment1
            emb1 = self._get_cached_embedding(seg1_tail)
            emb2 = self._get_cached_embedding(segment2)
            return float(1.0 - cosine_similarity([emb1], [emb2])[0][0])
        except Exception as e:
            print(f"[ClassicSeg] Error computing semantic shift: {e}")
            return 1.0

    def compute_boundary_score(self, segment1: str, segment2: str) -> float:
        doc2 = self.nlp(segment2)
        content_pos = {"VERB", "NOUN", "ADJ", "ADV"}

        if sum(1 for t in doc2 if t.pos_ in content_pos) < 4:
            return -1.0

        emb1 = self._get_cached_embedding(segment1)
        emb2 = self._get_cached_embedding(segment2)

        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)

        if norm1 == 0 or norm2 == 0:
            similarity = 0.0
        else:
            similarity = float(np.dot(emb1, emb2) / (norm1 * norm2))

        cohesion = self.semantic_cohesion_score(segment1, segment2)
        return 0.5 * (1.0 - similarity) + 0.5 * (1.0 - cohesion)

    def _get_cached_embedding(self, text: str) -> np.ndarray:
        if text not in self.embedding_cache:
            self.embedding_cache[text] = self.embedding_client.encode_single(text)
        return self.embedding_cache[text]

    def robust_sentence_split(self, text: str) -> list[dict]:
        doc = self.nlp(text)
        return [
            {"text": sent.text.strip(), "start": sent.start_char, "end": sent.end_char}
            for sent in doc.sents
        ]

    def segment_sentences(
        self, sentences: list[dict], threshold: float = 0.8
    ) -> list[list[dict]]:
        segments = [[sentences[0]]]
        for i in range(1, len(sentences)):
            current_sentence = sentences[i]["text"]
            last_segment_text = " ".join([s["text"] for s in segments[-1]])
            if (
                self.compute_boundary_score(last_segment_text, current_sentence)
                < threshold
            ):
                segments[-1].append(sentences[i])
            else:
                segments.append([sentences[i]])
        return segments

    def segment_text(
        self, text: str, max_segments: int = 10, threshold: float = 0.5
    ) -> list[str]:
        sentences = self.robust_sentence_split(text)
        if not sentences:
            return [text]
        grouped = self.segment_sentences(sentences, threshold)

        boundary_scores = [
            self.compute_boundary_score(
                " ".join(s["text"] for s in grouped[i]),
                " ".join(s["text"] for s in grouped[i + 1]),
            )
            for i in range(len(grouped) - 1)
        ]

        while len(grouped) > max_segments:
            merge_idx = int(np.argmin(boundary_scores))
            grouped[merge_idx] += grouped.pop(merge_idx + 1)
            boundary_scores.pop(merge_idx)
            if merge_idx < len(boundary_scores):
                boundary_scores[merge_idx] = (
                    self.compute_boundary_score(
                        " ".join(s["text"] for s in grouped[merge_idx]),
                        " ".join(s["text"] for s in grouped[merge_idx + 1]),
                    )
                    if merge_idx + 1 < len(grouped)
                    else float("inf")
                )

        return [" ".join(s["text"] for s in seg) for seg in grouped]


# ═══════════════════════════════════════════════════════════════════════════════
# ProgressiveSegmenter — TEI-powered, no local embedding model
# ═══════════════════════════════════════════════════════════════════════════════


class ProgressiveSegmenter:
    def __init__(
        self,
        spacy_model: str = "es_core_news_lg",
        stanza_lang: str = "es",
        similarity_threshold: float = 0.6,
        max_depth: int = 3,
        window_size: int = 3,
        tei_url: str | None = None,
        debug_coref: bool = True,
    ):
        self.similarity_threshold = similarity_threshold
        self.max_depth = max_depth
        self.window_size = window_size
        self.stanza_lang = stanza_lang
        self.stanza_use_gpu = _stanza_gpu
        self.debug_coref = debug_coref

        # Embedding client → TEI (Voyage-4 ONNX, 1024-dim)
        self.embedding_client = EmbeddingClient(base_url=tei_url)

        # Classic segmenter (also uses TEI via embedding client)
        self.classicseg = ClassicSegmenter(self.embedding_client, spacy_model)

        # spaCy pipeline
        self.nlp = spacy.load(spacy_model)
        if "conversational_sbd" not in self.nlp.pipe_names:
            self.nlp.add_pipe("conversational_sbd", before="parser")
        if "conversational_sbd" not in self.classicseg.nlp.pipe_names:
            self.classicseg.nlp.add_pipe("conversational_sbd", before="parser")

        self.tfidf_vectorizer = TfidfVectorizer()
        self._stanza_pipeline = None
        logging.info(
            f"[Init] GPU: {_stanza_gpu}, TEI: {self.embedding_client.base_url}"
        )

    # ── debug helper ──────────────────────────────────────────────────────────
    def _dprint(self, msg: str) -> None:
        if self.debug_coref:
            print(f"[COREF] {msg}")

    # ── Stanza lazy-load ──────────────────────────────────────────────────────
    def get_stanza(self) -> Optional[stanza.Pipeline]:
        if self._stanza_pipeline is None:
            print("[COREF] Stanza pipeline not loaded — iniciando carga...")
            try:
                stanza.download(
                    self.stanza_lang,
                    processors="tokenize,pos,lemma,depparse,constituency,coref",
                    verbose=False,
                )
                self._stanza_pipeline = stanza.Pipeline(
                    self.stanza_lang,
                    processors="tokenize,pos,lemma,depparse,constituency,coref",
                    use_gpu=self.stanza_use_gpu,
                    verbose=False,
                )
                print("[COREF] ✓ Stanza coref pipeline cargado correctamente.")
            except Exception as e:
                print(
                    f"[COREF] ✗ Error cargando Stanza: {e}. Correferencias deshabilitadas."
                )
                self._stanza_pipeline = None
        else:
            self._dprint("Pipeline ya en memoria — reutilizando.")
        return self._stanza_pipeline

    # ── Preprocessing ─────────────────────────────────────────────────────────
    def preprocess_text(self, text: str, min_chars: int = 3) -> list[str]:
        if not text:
            return []

        text = unicodedata.normalize("NFKC", text)
        text = re.sub(r"[“”«»]", '"', text)
        text = re.sub(r"[‘’`]", "'", text)
        text = text.replace(',"', "'").replace('""', "'").replace('"', "'")
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text).strip()

        original_max = self.nlp.max_length
        self.nlp.max_length = max(original_max, len(text) + 100)

        try:
            doc = self.nlp(text)
            sentences = []
            for sent in doc.sents:
                clean_sent = sent.text.strip()
                if len(clean_sent) >= min_chars:
                    sentences.append(clean_sent)
        finally:
            self.nlp.max_length = original_max

        logging.info(
            f"[Preprocess] {len(sentences)} oraciones extraídas de {len(text)} caracteres."
        )
        return sentences

    # ── Embeddings (via TEI) ───────────────────────────────────────────────────
    def generate_embeddings(self, sentences: list[str]) -> np.ndarray:
        if not sentences:
            return np.empty((0, 1024), dtype=np.float32)
        return self.embedding_client.encode(sentences)

    def compute_similarities(self, embeddings: np.ndarray) -> np.ndarray:
        return cosine_similarity(embeddings)

    def contextual_coherence(
        self, embeddings: np.ndarray, sentences: list[str]
    ) -> np.ndarray:
        if len(sentences) <= 1:
            return np.array([])
        similarity_matrix = cosine_similarity(embeddings)
        return similarity_matrix.diagonal(offset=1)

    # ── Hierarchical clustering ───────────────────────────────────────────────
    def hierarchical_clustering(self, similarities: np.ndarray) -> np.ndarray:
        num_elements = similarities.shape[0]
        distance_matrix = 1.0 - similarities
        if num_elements > 1000:
            condensed_distance = squareform(distance_matrix, checks=False)
        else:
            condensed_distance = distance_matrix
        linkage_matrix = linkage(condensed_distance, method="ward")
        clusters = fcluster(
            linkage_matrix, t=self.similarity_threshold, criterion="distance"
        )
        boundaries = np.where(np.diff(clusters) != 0)[0] + 1
        logging.info(f"[HierClust] {len(boundaries)} límites detectados.")
        return boundaries

    # ── Recursive segmentation ─────────────────────────────────────────────────
    def recursive_segmentation(self, sentences: list[str], depth: int = 0) -> list[str]:
        if depth > self.max_depth or len(sentences) <= 1:
            return [" ".join(sentences)]

        if len(sentences) > 500:
            self._dprint(
                f"[RecSeg] {len(sentences)} sentences at depth {depth} — switching to windowed."
            )
            return self._windowed_segmentation(sentences)

        embeddings = self.generate_embeddings(sentences)

        if len(sentences) > 200:
            sim_matrix = self._windowed_similarity(embeddings, window=10)
        else:
            sim_matrix = cosine_similarity(embeddings)

        dist_matrix = 1.0 - np.clip(sim_matrix, 0, 1)
        condensed = squareform(dist_matrix, checks=False)
        Z = linkage(condensed, method="ward")
        cut_height = np.percentile(Z[:, 2], 60)
        labels = fcluster(Z, t=cut_height, criterion="distance")
        boundaries = np.where(np.diff(labels) != 0)[0] + 1

        segments, start = [], 0
        for b in boundaries:
            segments.append(self.recursive_segmentation(sentences[start:b], depth + 1))
            start = b
        segments.append(self.recursive_segmentation(sentences[start:], depth + 1))
        return [item for sub in segments for item in sub]

    # ── Windowed similarity ────────────────────────────────────────────────────
    def _windowed_similarity(
        self, embeddings: np.ndarray, window: int = 10
    ) -> np.ndarray:
        n = len(embeddings)
        sim = np.zeros((n, n), dtype=np.float32)
        for i in range(n):
            start = max(0, i - window)
            end = min(n, i + window + 1)
            chunk = embeddings[start:end]
            sims = cosine_similarity(embeddings[i : i + 1], chunk)[0]
            sim[i, start:end] = sims
            sim[start:end, i] = sims
        np.fill_diagonal(sim, 1.0)
        return sim

    def _windowed_segmentation(
        self, sentences: list[str], window: int = 20
    ) -> list[str]:
        """Linear-pass fallback. Pre-encodes all sentences once to avoid N HTTP calls."""
        if not sentences:
            return []

        # Pre-encode all sentences
        all_emb = self.generate_embeddings(sentences)

        segments = [[sentences[0]]]
        for i in range(1, len(sentences)):
            window_sentences = segments[-1][-window:]
            # Get pre-computed embeddings for the window
            window_start = max(0, i - len(window_sentences))
            window_emb = all_emb[window_start:i]
            current_emb = all_emb[i : i + 1]

            mean_window = window_emb.mean(axis=0, keepdims=True)
            sim = cosine_similarity(mean_window, current_emb)[0][0]

            if sim >= self.similarity_threshold:
                segments[-1].append(sentences[i])
            else:
                segments.append([sentences[i]])

        return [" ".join(seg) for seg in segments]

    # ── Topic shift detection (via TEI) ────────────────────────────────────────
    def detect_topic_shift(
        self,
        segment1: str,
        segment2: str,
        last_n: int = 3,
        min_content_tokens: int = 4,
    ) -> bool:
        import math
        from collections import Counter

        if not hasattr(self, "similarity_history"):
            self.similarity_history = []
            self.syntactic_diff_history = []
            self.lex_sim_history = []

        seg1_tail = segment1[-500:] if len(segment1) > 500 else segment1
        first_period = seg1_tail.find(".")
        if first_period != -1 and len(seg1_tail) > 300:
            seg1_tail = seg1_tail[first_period + 1 :].strip()

        # 1. Substance filter
        doc1 = self.nlp(seg1_tail)
        doc2 = self.nlp(segment2)

        content_pos = {"VERB", "NOUN", "ADJ", "ADV"}
        content_count1 = sum(1 for token in doc1 if token.pos_ in content_pos)
        content_count2 = sum(1 for token in doc2 if token.pos_ in content_pos)

        if content_count1 < min_content_tokens or content_count2 < min_content_tokens:
            self.similarity_history.append(1.0)
            self.syntactic_diff_history.append(0.0)
            self.lex_sim_history.append(1.0)
            return False

        # 2. Embedding similarity via TEI (replaces local SentenceTransformer)
        emb1 = self.embedding_client.encode_single(seg1_tail)
        emb2 = self.embedding_client.encode_single(segment2)
        similarity = float(cosine_similarity([emb1], [emb2])[0][0])

        try:
            tfidf1 = self.tfidf_vectorizer.transform([seg1_tail])
            tfidf2 = self.tfidf_vectorizer.transform([segment2])
            lex_sim = float(cosine_similarity(tfidf1, tfidf2)[0][0])
        except Exception:
            lex_sim = 0.0

        dep_counts1 = Counter([token.dep_ for token in doc1])
        dep_counts2 = Counter([token.dep_ for token in doc2])
        all_labels = set(dep_counts1.keys()).union(set(dep_counts2.keys()))
        vec1 = [
            dep_counts1[label] / len(doc1) if len(doc1) > 0 else 0
            for label in all_labels
        ]
        vec2 = [
            dep_counts2[label] / len(doc2) if len(doc2) > 0 else 0
            for label in all_labels
        ]
        dot_product = sum(v1 * v2 for v1, v2 in zip(vec1, vec2))
        mag1 = math.sqrt(sum(v**2 for v in vec1))
        mag2 = math.sqrt(sum(v**2 for v in vec2))
        syntactic_diff = (
            1.0 if mag1 == 0 or mag2 == 0 else 1.0 - (dot_product / (mag1 * mag2))
        )

        MAX_HISTORY = 200
        if len(self.similarity_history) > MAX_HISTORY:
            self.similarity_history = self.similarity_history[-MAX_HISTORY:]
            self.syntactic_diff_history = self.syntactic_diff_history[-MAX_HISTORY:]
            self.lex_sim_history = self.lex_sim_history[-MAX_HISTORY:]

        self.similarity_history.append(similarity)
        self.syntactic_diff_history.append(syntactic_diff)
        self.lex_sim_history.append(lex_sim)

        return (similarity < 0.6) or (syntactic_diff > 0.4)

    # ── Progressive clustering ─────────────────────────────────────────────────
    def progressive_clustering(self, segments: list[str]) -> list[str]:
        if not segments:
            return segments

        merged_segments = [segments[0]]

        for i in range(1, len(segments)):
            last_segment = merged_segments[-1]
            current_segment = segments[i]

            if not self.detect_topic_shift(last_segment, current_segment, last_n=3):
                merged_segments[-1] += " " + current_segment
            else:
                merged_segments.append(current_segment)

            MAX_HISTORY = 200
            for attr in (
                "similarity_history",
                "syntactic_diff_history",
                "lex_sim_history",
            ):
                hist = getattr(self, attr, None)
                if hist is not None and len(hist) > MAX_HISTORY:
                    setattr(self, attr, hist[-MAX_HISTORY:])

        return merged_segments

    def compute_syntactic_difference(self, doc1, doc2) -> float:
        dep_diff = sum(
            1 for token1, token2 in zip(doc1, doc2) if token1.dep_ != token2.dep_
        )
        return dep_diff / max(len(doc1), len(doc2))

    def final_clustering(self, segments: list[str]) -> list[str]:
        clustered_segments = self.progressive_clustering(segments)
        logging.info(
            f"[FinalClust] {len(clustered_segments)} segmentos tras clustering."
        )
        return clustered_segments

    # ── Offset mapper (for coref) ──────────────────────────────────────────────
    class OffsetMapper:
        def __init__(self, global_offset: int):
            self.global_offset = global_offset

        def to_global(self, local_start: int, local_end: int) -> tuple[int, int]:
            return local_start + self.global_offset, local_end + self.global_offset

    # ── Fuzzy matching ─────────────────────────────────────────────────────────
    def _fuzzy_match(self, text1: str, text2: str) -> bool:
        stop = self.nlp.Defaults.stop_words

        def clean(t):
            return " ".join([w for w in t.lower().split() if w not in stop])

        norm1, norm2 = clean(text1), clean(text2)
        if not norm1 or not norm2:
            return text1.lower().strip() == text2.lower().strip()

        return fuzz.token_set_ratio(norm1, norm2) >= 85

    # ── Subject extraction ─────────────────────────────────────────────────────
    def find_subjects_for_roots(self, text: str) -> list[str]:
        subjects = []
        try:
            stanza_pipe = self.get_stanza()
            if not stanza_pipe:
                return []

            doc = stanza_pipe(text)
            for sentence in doc.sentences:
                tree = sentence.constituency
                root_ids = [word.id for word in sentence.words if word.head == 0]

                for word in sentence.words:
                    if word.head in root_ids and "nsubj" in word.deprel:
                        phrase_found = False
                        try:
                            leaf = tree.get_leaf_for_index(word.id - 1)
                            curr = leaf
                            while curr.parent is not None:
                                if curr.label == "NP":
                                    subjects.append(" ".join(curr.leaf_labels()))
                                    phrase_found = True
                                    break
                                curr = curr.parent
                        except Exception:
                            phrase_found = False

                        if not phrase_found:
                            subjects.append(word.text)

            return list(set([s.strip() for s in subjects if s]))
        except Exception as e:
            logging.error(f"[COREF] Subject extraction failure: {e}")
            return []

    # ── Global coref chain extraction ──────────────────────────────────────────
    def _extract_global_chains(
        self, segments_info: list[dict], full_doc_text: str, context_units: int = 2
    ) -> list[dict]:
        global_chains: list[dict] = []
        seen_chain_keys: set[tuple] = set()
        buffer: list[tuple[int, int]] = []
        stanza_pipe = self.get_stanza()
        total_uces = len(segments_info)

        self._dprint(
            f"Iniciando extracción de cadenas globales sobre {total_uces} UCEs "
            f"(ventana deslizante de {context_units} UCEs)."
        )

        if stanza_pipe is None:
            self._dprint("✗ Stanza no disponible — saltando extracción de cadenas.")
            return global_chains

        for uce_idx, uce in enumerate(segments_info):
            buffer.append((uce["start"], uce["end"]))
            if len(buffer) > context_units + 1:
                buffer.pop(0)

            window_start = buffer[0][0]
            window_end = buffer[-1][1]
            window_text = full_doc_text[window_start:window_end]
            window_char_len = window_end - window_start

            MAX_WINDOW_CHARS = 4000
            if window_char_len > MAX_WINDOW_CHARS and len(buffer) > 1:
                shrunk_buffer = buffer[1:]
                while (
                    shrunk_buffer
                    and len(full_doc_text[shrunk_buffer[0][0] : shrunk_buffer[-1][1]])
                    > MAX_WINDOW_CHARS
                ):
                    shrunk_buffer = shrunk_buffer[1:]
                if shrunk_buffer:
                    effective_start = shrunk_buffer[0][0]
                    effective_end = shrunk_buffer[-1][1]
                    window_text = full_doc_text[effective_start:effective_end]

            try:
                doc = stanza_pipe(window_text)
            except MemoryError:
                self._dprint(
                    f"    MemoryError en ventana UCE {uce_idx + 1} — saltando."
                )
                gc.collect()
                continue
            except Exception as e:
                logging.error(f"[COREF] Stanza window error: {e}")
                continue

            mapper = self.OffsetMapper(window_start)
            for chain in doc.coref:
                mentions = []
                for mention in chain.mentions:
                    s_idx = (
                        mention.sentence[0]
                        if isinstance(mention.sentence, (tuple, list))
                        else mention.sentence
                    )
                    sw_idx = (
                        mention.start_word[0]
                        if isinstance(mention.start_word, (tuple, list))
                        else mention.start_word
                    )
                    ew_idx = (
                        mention.end_word[-1]
                        if isinstance(mention.end_word, (tuple, list))
                        else mention.end_word
                    )

                    sent = doc.sentences[s_idx]
                    first_word = sent.words[sw_idx]
                    last_word = sent.words[ew_idx - 1]

                    m_start_local = first_word.start_char
                    if m_start_local is None and getattr(first_word, "parent", None):
                        m_start_local = first_word.parent.start_char

                    m_end_local = last_word.end_char
                    if m_end_local is None and getattr(last_word, "parent", None):
                        m_end_local = last_word.parent.end_char

                    if m_start_local is None or m_end_local is None:
                        continue

                    m_start_global, m_end_global = mapper.to_global(
                        m_start_local, m_end_local
                    )
                    mentions.append(
                        {
                            "text": window_text[m_start_local:m_end_local],
                            "start_char": m_start_global,
                            "end_char": m_end_global,
                        }
                    )

                if not mentions:
                    continue

                chain_key = tuple(
                    sorted((m["start_char"], m["end_char"]) for m in mentions)
                )
                if chain_key in seen_chain_keys:
                    continue
                seen_chain_keys.add(chain_key)
                global_chains.append({"mentions": mentions})

        self._dprint(
            f"Extracción global completada: {len(global_chains)} cadenas únicas."
        )
        return global_chains

    # ── Coref-based merge decision ─────────────────────────────────────────────
    def van_unidos(
        self,
        seg1_info: dict,
        seg2_info: dict,
        global_chains: list[dict],
        precomputed_roots: set | None = None,
    ) -> tuple[bool, bool]:
        if precomputed_roots is not None:
            los_roots = precomputed_roots
        else:
            text1 = seg1_info["text"]
            boundary_context = text1[-500:] if len(text1) > 500 else text1
            los_roots = set(self.find_subjects_for_roots(boundary_context))

        if not los_roots:
            if precomputed_roots is not None:
                has_spanning = any(
                    any(
                        seg1_info["start"] <= m["start_char"] < seg1_info["end"]
                        for m in chain["mentions"]
                    )
                    and any(
                        seg2_info["start"] <= m["start_char"] < seg2_info["end"]
                        for m in chain["mentions"]
                    )
                    for chain in global_chains
                )
                return False, has_spanning
            return False, False

        has_any_spanning = False
        for chain in global_chains:
            has_seg1_root = False
            has_seg2_mention = False
            has_mention_in_1 = False

            for mention in chain["mentions"]:
                if seg1_info["start"] <= mention["start_char"] < seg1_info["end"]:
                    has_mention_in_1 = True
                    if any(
                        self._fuzzy_match(mention["text"], root) for root in los_roots
                    ):
                        has_seg1_root = True
                elif seg2_info["start"] <= mention["start_char"] < seg2_info["end"]:
                    has_seg2_mention = True

                if has_seg1_root and has_seg2_mention:
                    return True, True

            if has_mention_in_1 and has_seg2_mention:
                has_any_spanning = True

        return False, has_any_spanning

    # ── Coreference resolution pass ────────────────────────────────────────────
    def resolve_coreferences(self, segments: list[str]) -> list[str]:
        self._dprint(
            f"\n{'=' * 60}\nresolve_coreferences() iniciado con {len(segments)} segmentos.\n{'=' * 60}"
        )

        if not segments or not isinstance(segments, list) or not self.get_stanza():
            self._dprint(
                "Condición de salida temprana: lista vacía o Stanza no disponible."
            )
            return segments

        full_doc_text = ""
        segments_info = []
        current_offset = 0
        for i, seg in enumerate(segments):
            start = current_offset
            end = start + len(seg)
            segments_info.append({"text": seg, "start": start, "end": end})
            full_doc_text += seg + " "
            current_offset = end + 1

        self._dprint("Fase 1: extrayendo cadenas coref globales...")
        global_chains = self._extract_global_chains(segments_info, full_doc_text)
        self._dprint(f"Fase 1 completada: {len(global_chains)} cadenas únicas.\n")

        self._dprint("Fase 2: pasada de merge greedy con van_unidos()...")
        merged_segments = []
        current_seg_info = segments_info[0]
        merges_total = 0

        for i in range(1, len(segments_info)):
            next_seg_info = segments_info[i]
            should_merge, _ = self.van_unidos(
                current_seg_info, next_seg_info, global_chains
            )
            if should_merge:
                current_seg_info["text"] += " " + next_seg_info["text"]
                current_seg_info["end"] = next_seg_info["end"]
                merges_total += 1
            else:
                merged_segments.append(current_seg_info["text"])
                current_seg_info = next_seg_info

        merged_segments.append(current_seg_info["text"])

        self._dprint(
            f"\nFase 2 completada: {merges_total} merges aplicados. "
            f"{len(merged_segments)} UCEs finales (de {len(segments)} originales).\n{'=' * 60}\n"
        )
        return merged_segments

    # ── Token-gated segment processing ─────────────────────────────────────────
    def process_segment(self, text: str, max_tokens: int) -> list[str]:
        token_count = _count_tokens(text)
        if token_count > max_tokens:
            print(
                f"[SegText] Segmento muy largo ({token_count} tokens) → enviando a ClassicSegmenter."
            )
            return self.classicseg.segment_text(text)
        return [text]

    # ── Main entry point ───────────────────────────────────────────────────────
    def segment_text(self, text: str, max_tokens: int = 1024) -> list[str]:
        print(f"\n[SegText] Iniciando segmentación. Texto: {len(text)} chars.")
        sentences = self.preprocess_text(text)
        print(f"[SegText] {len(sentences)} oraciones tras preprocesado.")

        all_segments = self.recursive_segmentation(sentences)
        print(f"[SegText] {len(all_segments)} segmentos tras segmentación recursiva.")

        self.tfidf_vectorizer.fit(sentences)
        print(f"[SegText] TF-IDF ajustado sobre {len(sentences)} oraciones crudas.")

        clustered_segments = self.final_clustering(all_segments)
        print(f"[SegText] {len(clustered_segments)} segmentos tras clustering final.")

        print(f"[SegText] Iniciando resolución de correferencias...")
        clustered_segments = self.resolve_coreferences(clustered_segments)
        print(
            f"[SegText] {len(clustered_segments)} UCEs tras resolución de correferencias."
        )

        segmentos = []
        overflow_count = 0
        for seg in clustered_segments:
            token_count = _count_tokens(seg)

            if token_count > max_tokens:
                overflow_count += 1
                num_required_splits = (token_count // max_tokens) + 1
                print(
                    f"[SegText] Overflow UCE ({token_count} tokens) → Corte quirúrgico en {num_required_splits} fragmento(s)."
                )
                safe_segments = self.classicseg.segment_text(
                    seg,
                    max_segments=num_required_splits,
                    threshold=-1.0,
                )
                segmentos.extend(safe_segments)
            else:
                segmentos.append(seg)

        print(
            f"[SegText] Segmentación completada: {len(segmentos)} UCEs finales "
            f"({overflow_count} desbordamientos resueltos con cortes quirúrgicos)."
        )
        return segmentos
