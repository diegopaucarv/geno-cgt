"""Regresión del clasificador Glaser "segment-first" (`workers/heavy/segment_classifier.py`).

Por qué existe este test
------------------------
El clasificador cambió de "codificar el documento entero" a un proceso
**classify-first**: primero se etiqueta el TEXTO completo
(`classify_text_spans`, sin crear segmentos) y después la segmentación hereda
la categoría de cada tramo (`backend/app/services/glaser_inheritance.py`).

Sobre el camino legacy de `classify_document`:

1. Con segmentadores: clasificar **cada segmento** y **fusionar sólo los
   contiguos** que comparten categoría. El caso obligatorio es

       1 baseline, 2 baseline, 3 otra, 4 baseline

   que debe producir **tres** bloques (`1-2`, `3`, `4`). Dos tramos de la misma
   categoría separados por otra categoría NO se fusionan.

2. Sin segmentadores: el LLM divide el texto **y** lo clasifica en una sola
   pasada (`fa_segment_and_classify`).

También se fijan aquí los dos fallos silenciosos detectados en la auditoría:

- El lote se numeraba con las posiciones **globales** del documento, pero el
  prompt describe una lista que empieza en 1. Si el modelo renumeraba, ninguna
  posición coincidía y el lote entero caía al prior sin avisar. Ahora se numera
  1..N por lote y se traduce de vuelta a la posición global.
- El camino fallback persistía el documento **truncado** cuando una ventana
  fallaba y aun así devolvía `status="ok"`. Ahora degrada.

El módulo sólo depende de stdlib + SQLAlchemy, así que se carga directamente del
árbol de fuentes: no requiere docker ni la pila de la API.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "workers" / "heavy" / "segment_classifier.py"
INHERITANCE_PATH = REPO_ROOT / "backend" / "app" / "services" / "glaser_inheritance.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "segment_classifier_under_test", MODULE_PATH
    )
    assert spec and spec.loader, f"no se pudo cargar {MODULE_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_inheritance():
    spec = importlib.util.spec_from_file_location(
        "glaser_inheritance_under_test", INHERITANCE_PATH
    )
    assert spec and spec.loader, f"no se pudo cargar {INHERITANCE_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sc = _load_module()
gi = _load_inheritance()


# ── Dobles del cliente LLM ─────────────────────────────────────────────


class _Output:
    """Sustituto de ``AgentOutput`` del worker."""

    def __init__(self, data=None, success=True, error=None):
        self.data = data
        self.success = success
        self.error = error


class _RecordingLLM:
    """Cliente falso que delega la respuesta en ``responder`` y guarda las llamadas."""

    def __init__(self, responder):
        self.calls: list[dict] = []
        self._responder = responder

    def run_agent(self, **kwargs):
        self.calls.append(kwargs)
        return self._responder(kwargs)


def _classify_by_text(kwargs):
    """Clasifica cada línea del lote leyendo el ordinal y el texto del usuario."""
    entries = []
    for line in kwargs["user_content"].split("\n\n"):
        ordinal, _, text = line.partition(". ")
        category = "vague_data" if text == "s44" else "baseline_data"
        entries.append(
            {"segment_id": int(ordinal), "category": category, "confidence": "HIGH"}
        )
    return _Output({"classifications": entries})


# ── Taxonomía canónica ─────────────────────────────────────────────────


def test_only_five_canonical_classes_exist():
    assert sc.CLASSES_GLASER == (
        "baseline_data",
        "properline_data",
        "interpreted_data",
        "vague_data",
        "document_context",
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("baseline_data", "baseline_data"),
        ("<baseline_data>", "baseline_data"),
        ("Baseline", "baseline_data"),
        ("proper line", "properline_data"),
        ("Interpreted Data", "interpreted_data"),
        ("interviewer", "document_context"),
        ("interviewer_context", "document_context"),
        ("document_context", "document_context"),
        # Tags del clasificador legacy: se mapean, nunca se propagan.
        ("processual_data", "baseline_data"),
        ("contextual_data", "vague_data"),
        ("", "baseline_data"),
        ("etiqueta inventada", "baseline_data"),
    ],
)
def test_normalize_never_leaks_a_non_canonical_class(raw, expected):
    result = sc._normalizar_clase(raw)
    assert result == expected
    assert result in sc.CLASSES_GLASER


def test_default_class_is_baseline():
    assert sc.DEFAULT_CLASS == "baseline_data"


# ── Fusión por contigüidad (el requisito central) ──────────────────────


def test_merge_splits_same_class_when_not_contiguous():
    clasificaciones = [
        {"position": 1, "category": "baseline_data", "confidence": "HIGH"},
        {"position": 2, "category": "baseline_data", "confidence": "HIGH"},
        {"position": 3, "category": "interpreted_data", "confidence": "MEDIUM"},
        {"position": 4, "category": "baseline_data", "confidence": "HIGH"},
    ]
    textos = {1: "uno", 2: "dos", 3: "tres", 4: "cuatro"}

    blocks = sc.merge_adjacent_segments(clasificaciones, textos)

    assert [(b["class"], b["start_pos"], b["end_pos"]) for b in blocks] == [
        ("baseline_data", 1, 2),
        ("interpreted_data", 3, 3),
        ("baseline_data", 4, 4),
    ]
    assert blocks[0]["segment_positions"] == [1, 2]
    assert blocks[0]["text"] == "uno dos"


def test_merge_does_not_bridge_a_position_gap():
    clasificaciones = [
        {"position": 1, "category": "baseline_data", "confidence": "HIGH"},
        {"position": 2, "category": "baseline_data", "confidence": "HIGH"},
        {"position": 4, "category": "baseline_data", "confidence": "HIGH"},
    ]
    blocks = sc.merge_adjacent_segments(clasificaciones, {1: "a", 2: "b", 4: "d"})
    assert [(b["start_pos"], b["end_pos"]) for b in blocks] == [(1, 2), (4, 4)]


def test_merge_is_order_independent():
    clasificaciones = [
        {"position": 4, "category": "baseline_data", "confidence": "HIGH"},
        {"position": 1, "category": "baseline_data", "confidence": "HIGH"},
        {"position": 2, "category": "baseline_data", "confidence": "HIGH"},
        {"position": 3, "category": "baseline_data", "confidence": "HIGH"},
    ]
    blocks = sc.merge_adjacent_segments(clasificaciones, {})
    assert [(b["start_pos"], b["end_pos"]) for b in blocks] == [(1, 4)]


def test_block_confidence_is_the_weakest_member():
    clasificaciones = [
        {"position": 1, "category": "baseline_data", "confidence": "HIGH"},
        {"position": 2, "category": "baseline_data", "confidence": "LOW"},
        {"position": 3, "category": "baseline_data", "confidence": "HIGH"},
    ]
    blocks = sc.merge_adjacent_segments(clasificaciones, {})
    assert len(blocks) == 1
    assert blocks[0]["confidence"] == "LOW"


def test_blocks_to_xml_uses_real_tags():
    xml = sc.blocks_to_xml(
        [
            {"class": "baseline_data", "text": "hola"},
            {"class": "vague_data", "text": "no sé"},
        ]
    )
    assert (
        xml == "<baseline_data>hola</baseline_data>\n\n<vague_data>no sé</vague_data>"
    )


# ── Camino 1: clasificar segmentos existentes ──────────────────────────


def test_batch_is_rendered_with_local_ordinals():
    batch = [{"position": 41, "text": "a"}, {"position": 42, "text": "b"}]
    assert sc._render_batch(batch) == "1. a\n\n2. b"


def test_local_ordinals_map_back_to_global_positions():
    """El modelo numera 1..N por lote; la posición global se restaura."""
    llm = _RecordingLLM(
        lambda _kwargs: _Output(
            {
                "classifications": [
                    {"segment_id": 1, "category": "vague_data", "confidence": "HIGH"},
                    {
                        "segment_id": 2,
                        "category": "baseline_data",
                        "confidence": "HIGH",
                    },
                ]
            }
        )
    )

    out = sc.classify_segments_json_schema(
        [{"position": 41, "text": "a"}, {"position": 42, "text": "b"}], "proj-1", llm
    )

    assert [o["position"] for o in out] == [41, 42]
    assert [o["category"] for o in out] == ["vague_data", "baseline_data"]
    # El lote viaja en el mensaje del usuario; el prefijo estático no.
    assert llm.calls[0]["cache_key"] == "proj-1"
    assert "a" in llm.calls[0]["user_content"]


def test_global_positions_from_the_model_are_also_accepted():
    llm = _RecordingLLM(
        lambda _kwargs: _Output(
            {
                "classifications": [
                    {"segment_id": 41, "category": "vague_data", "confidence": "HIGH"},
                    {
                        "segment_id": 42,
                        "category": "baseline_data",
                        "confidence": "HIGH",
                    },
                ]
            }
        )
    )

    out = sc.classify_segments_json_schema(
        [{"position": 41, "text": "a"}, {"position": 42, "text": "b"}], "proj-1", llm
    )
    assert [o["position"] for o in out] == [41, 42]


def test_batching_preserves_contiguity_across_batches():
    """45 segmentos → 2 lotes; la fusión ignora las fronteras del lote."""
    segmentos = [{"position": i, "text": f"s{i}"} for i in range(1, 46)]
    llm = _RecordingLLM(_classify_by_text)

    out = sc.classify_segments_json_schema(segmentos, "proj-1", llm)

    assert [o["position"] for o in out] == list(range(1, 46))
    assert out[43]["category"] == "vague_data"
    assert all(o["category"] in sc.CLASSES_GLASER for o in out)
    assert len(llm.calls) == 2

    blocks = sc.merge_adjacent_segments(
        out, {s["position"]: s["text"] for s in segmentos}
    )
    assert [(b["class"], b["start_pos"], b["end_pos"]) for b in blocks] == [
        ("baseline_data", 1, 43),
        ("vague_data", 44, 44),
        ("baseline_data", 45, 45),
    ]


def test_unusable_batches_degrade_instead_of_silently_using_the_prior():
    llm = _RecordingLLM(
        lambda _kwargs: _Output(
            {"classifications": [{"segment_id": 999, "category": "baseline_data"}]}
        )
    )
    with pytest.raises(RuntimeError):
        sc.classify_segments_json_schema([{"position": 1, "text": "a"}], "proj-1", llm)


def test_omitted_positions_are_recovered_by_the_low_temperature_retry():
    calls = {"n": 0}

    def responder(_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Output(
                {"classifications": [{"segment_id": 1, "category": "vague_data"}]}
            )
        return _Output(
            {"classifications": [{"segment_id": 1, "category": "interpreted_data"}]}
        )

    llm = _RecordingLLM(responder)
    out = sc.classify_segments_json_schema(
        [{"position": 1, "text": "a"}, {"position": 2, "text": "b"}], "proj-1", llm
    )

    assert [o["category"] for o in out] == ["vague_data", "interpreted_data"]
    assert llm.calls[1]["temperature"] == 0.0


# ── Camino 2: el LLM segmenta y clasifica ──────────────────────────────


def test_fallback_raises_when_a_window_fails():
    raw = "\n\n".join(f"parrafo {i} " + "x" * 400 for i in range(40))
    assert len(sc._windows(raw)) >= 2

    class _FirstWindowOnly:
        def __init__(self):
            self.calls = 0

        def run_agent(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return _Output(
                    {
                        "segments": [
                            {
                                "text": "parrafo 0",
                                "category": "baseline_data",
                                "confidence": "HIGH",
                            }
                        ]
                    }
                )
            return _Output(success=False, error="ventana rota")

    with pytest.raises(RuntimeError):
        sc.llm_segment_and_classify(raw, "proj-1", _FirstWindowOnly())


def test_fallback_keeps_unlocated_segments_in_place():
    raw = "Uno. Dos. Tres."

    class _Paraphrasing:
        def run_agent(self, **_kwargs):
            return _Output(
                {
                    "segments": [
                        {
                            "text": "Uno.",
                            "category": "baseline_data",
                            "confidence": "HIGH",
                        },
                        {
                            "text": "resumen inventado",
                            "category": "vague_data",
                            "confidence": "LOW",
                        },
                        {
                            "text": "Tres.",
                            "category": "baseline_data",
                            "confidence": "HIGH",
                        },
                    ]
                }
            )

    out = sc.llm_segment_and_classify(raw, "proj-1", _Paraphrasing())

    assert [o["text"] for o in out] == ["Uno.", "resumen inventado", "Tres."]
    assert out[1]["is_exact_match"] is False
    assert out[1]["start_char"] is None


def test_located_offsets_match_the_stored_text():
    raw = "  Hola mundo.  Chau."
    located = sc._locate_offsets(raw, [{"text": "Hola mundo."}, {"text": "Chau."}])

    for item in located:
        assert item["is_exact_match"] is True
        assert raw[item["start_char"] : item["end_char"]] == item["text"]


# ── Puente con el worker ───────────────────────────────────────────────


def test_classify_document_accepts_segments_and_persists_blocks():
    """Extremo a extremo con una sesión falsa: 3 bloques y metadata escrita."""

    class _Result:
        def __init__(self, rows=None):
            self._rows = rows or []

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return self._rows

    class _Session:
        def __init__(self, rows):
            self.rows = rows
            self.sql: list[str] = []
            self.params: list[dict] = []

        def execute(self, statement, params=None):
            sql = str(statement)
            self.sql.append(sql)
            self.params.append(params or {})
            if "SELECT id, texto, posicion FROM segmentos" in sql:
                return _Result(self.rows)
            if "SELECT metadatos FROM documentos" in sql:
                return _Result([('{"texto_extraido": "x"}',)])
            return _Result()

    rows = [
        ("s1", "uno", 1),
        ("s2", "dos", 2),
        ("s3", "tres", 3),
        ("s4", "cuatro", 4),
    ]
    session = _Session(rows)
    llm = _RecordingLLM(
        lambda kwargs: _Output(
            {
                "classifications": [
                    {
                        "segment_id": int(line.partition(". ")[0]),
                        "category": (
                            "interpreted_data"
                            if line.partition(". ")[2] == "tres"
                            else "baseline_data"
                        ),
                        "confidence": "HIGH",
                    }
                    for line in kwargs["user_content"].split("\n\n")
                ]
            }
        )
    )

    result = sc.classify_document("doc-1", "proj-1", session, llm)

    assert result["status"] == "ok"
    assert result["used_fallback"] is False
    assert [(b["class"], b["start_pos"], b["end_pos"]) for b in result["blocks"]] == [
        ("baseline_data", 1, 2),
        ("interpreted_data", 3, 3),
        ("baseline_data", 4, 4),
    ]
    assert result["baseline_tags_count"] == 2
    # El clasificador escribe tipo_dato_glaser por segmento y los metadatos.
    updates = [sql for sql in session.sql if "tipo_dato_glaser" in sql]
    assert len(updates) == len(rows)
    patch = [p for p in session.params if "glaser_blocks" in str(p)]
    assert patch, "no se persistieron glaser_blocks"


# ── Restos de la taxonomía vieja ───────────────────────────────────────


def test_guard_counts_out_of_taxonomy_labels_as_unclassified():
    """Una etiqueta legacy no es ``NULL``, pero tampoco está clasificada.

    Si el guard sólo mira los ``NULL``, un documento con
    ``processual_data``/``contextual_data`` nunca se vuelve a clasificar y sus
    segmentos quedan fuera de la extracción de incidentes (que sólo lee
    ``baseline_data``).
    """

    class _Result:
        def __init__(self, rows=None):
            self._rows = rows or []

        def fetchone(self):
            return self._rows[0] if self._rows else None

    class _Session:
        def __init__(self):
            self.sql: list[str] = []

        def execute(self, statement, params=None):
            self.sql.append(str(statement))
            return _Result([(5, 2)])

    session = _Session()
    total, sin_clasificar = sc.contar_segmentos_sin_clasificar(session, "doc-1")

    assert (total, sin_clasificar) == (5, 2)
    sql = session.sql[0]
    assert "tipo_dato_glaser IS NULL" in sql
    assert "NOT IN" in sql
    for clase in sc.CLASSES_GLASER:
        assert f"'{clase}'" in sql, f"el guard no reconoce {clase} como canónica"
    assert "processual_data" not in sql
    assert "contextual_data" not in sql


class _ScriptedSession:
    """Sesión mínima que responde según el SQL y registra lo que recibe."""

    def __init__(self, selects):
        self.selects = selects
        self.sql: list[str] = []
        self.params: list[dict] = []

    class _Result:
        def __init__(self, rows=None):
            self._rows = rows or []

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return self._rows

    def execute(self, statement, params=None):
        sql = str(statement)
        self.sql.append(sql)
        self.params.append(params or {})
        for needle, rows in self.selects.items():
            if needle in sql:
                return self._Result(rows)
        return self._Result()


def test_legacy_labels_are_normalized_and_view_rebuilt():
    """``processual_data``/``contextual_data`` se traducen sin llamar al LLM."""
    session = _ScriptedSession(
        {
            "SELECT id, tipo_dato_glaser FROM segmentos": [
                ("s1", "baseline_data"),
                ("s2", "processual_data"),
                ("s3", "contextual_data"),
            ],
            "SELECT metadatos FROM documentos": [
                (
                    '{"texto_clasificado": '
                    '"<baseline_data>uno</baseline_data>'
                    '<processual_data>dos</processual_data>"}',
                )
            ],
            "SELECT id, texto, posicion FROM segmentos": [
                ("s1", "uno", 1),
                ("s2", "dos", 2),
                ("s3", "tres", 3),
            ],
        }
    )

    result = sc.normalizar_etiquetas_legacy(session, "doc-1")

    assert result == {"changed": 2, "rebuilt": True, "total": 3}
    updates = [
        p for p in session.params if "tipo" in p and "sid" in p and p["sid"] is not None
    ]
    assert {"tipo": "baseline_data", "sid": "s2"} in updates
    assert {"tipo": "vague_data", "sid": "s3"} in updates

    patch = json.loads(next(p["patch"] for p in session.params if "patch" in p))
    blocks = patch["glaser_blocks"]
    assert [(b["class"], b["start_pos"], b["end_pos"]) for b in blocks] == [
        ("baseline_data", 1, 2),
        ("vague_data", 3, 3),
    ]
    xml = patch["texto_clasificado"]
    assert "<baseline_data>" in xml
    assert "<vague_data>" in xml
    assert "processual_data" not in xml
    assert "contextual_data" not in xml


def test_legacy_normalization_does_not_rebuild_with_unclassified_segments():
    """Si queda algún ``NULL`` manda el camino del LLM: no se reconstruye nada."""
    session = _ScriptedSession(
        {
            "SELECT id, tipo_dato_glaser FROM segmentos": [
                ("s1", "processual_data"),
                ("s2", None),
            ],
            "SELECT metadatos FROM documentos": [("{}",)],
            "SELECT id, texto, posicion FROM segmentos": [
                ("s1", "uno", 1),
                ("s2", "dos", 2),
            ],
        }
    )

    result = sc.normalizar_etiquetas_legacy(session, "doc-1")

    assert result == {"changed": 1, "rebuilt": False, "total": 2}
    assert not [p for p in session.params if "patch" in p]


# ═══════════════════════════════════════════════════════════════════════
# Herencia de tags: classify-first (texto → segmentos)
# ═══════════════════════════════════════════════════════════════════════


def _blocks_with_offsets(full_text, entries, pos=0):
    blocks = []
    for text, clase in entries:
        start = full_text.index(text, pos)
        blocks.append(
            {
                "class": clase,
                "text": text,
                "start_char": start,
                "end_char": start + len(text),
            }
        )
        pos = start + len(text)
    return blocks


def test_inherit_tags_assigns_the_block_covering_each_segment():
    """Cada segmento hereda la categoría del tramo de texto del que salió."""
    full_text = "Uno baseline. Dos interpretado. Tres contexto."
    blocks = _blocks_with_offsets(
        full_text,
        [
            ("Uno baseline.", "baseline_data"),
            ("Dos interpretado.", "interpreted_data"),
            ("Tres contexto.", "document_context"),
        ],
    )

    tags = gi.inherit_tags(
        ["Uno baseline.", "Dos interpretado.", "Tres contexto."],
        blocks,
        full_text,
    )

    assert tags == ["baseline_data", "interpreted_data", "document_context"]


def test_inherit_tags_returns_none_for_unmatched_segments():
    """Un segmento que no se puede situar queda en ``None``, nunca baseline."""
    full_text = "Uno baseline. Dos interpretado."
    blocks = _blocks_with_offsets(
        full_text,
        [
            ("Uno baseline.", "baseline_data"),
            ("Dos interpretado.", "interpreted_data"),
        ],
    )

    tags = gi.inherit_tags(
        ["Uno baseline.", "fragmento que no existe en el texto"],
        blocks,
        full_text,
    )

    assert tags[0] == "baseline_data"
    assert tags[1] is None, (
        "un segmento sin match debe quedar en None para que el detector de "
        "inconsistencias lo vea; nunca se rellena con baseline_data"
    )


def test_inherit_tags_tolerates_preprocessed_quotes():
    """El segmentador pasa las comillas dobles a simples; la herencia también."""
    full_text = 'Ella dijo "no voy" y se fue.'
    blocks = _blocks_with_offsets(
        full_text, [('Ella dijo "no voy" y se fue.', "baseline_data")]
    )

    tags = gi.inherit_tags(["Ella dijo 'no voy' y se fue."], blocks, full_text)

    assert tags == ["baseline_data"]


def test_inherit_tags_returns_one_entry_per_segment():
    tags = gi.inherit_tags(["a", "b", "c"], [], "a b c")
    assert tags == [None, None, None]


def test_blocks_from_metadatos_drops_malformed_blocks():
    blocks = gi.blocks_from_metadatos(
        {
            "glaser_blocks": [
                {
                    "class": "baseline_data",
                    "text": "ok",
                    "start_char": 0,
                    "end_char": 2,
                },
                {"class": None, "text": "sin clase"},
                "no es un dict",
            ]
        }
    )
    assert blocks == [
        {"class": "baseline_data", "text": "ok", "start_char": 0, "end_char": 2}
    ]
    assert gi.blocks_from_metadatos(None) == []


# ── classify_text_spans NO debe crear / borrar segmentos ───────────────


class _MetadatosSession:
    """Sesión falsa que sirve ``metadatos`` y registra el SQL ejecutado."""

    class _Result:
        def __init__(self, rows=None):
            self._rows = rows or []

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return self._rows

    def __init__(self, meta):
        self.meta = meta
        self.sql: list[str] = []
        self.params: list[dict] = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.sql.append(sql)
        self.params.append(params or {})
        if "SELECT metadatos FROM documentos" in sql:
            return self._Result([(self.meta,)])
        return self._Result()


def test_classify_text_spans_does_not_call_segment_persistence():
    """Ancla estática: la función no debe escribir en ``segmentos``."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    node = next(
        n
        for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.FunctionDef) and n.name == "classify_text_spans"
    )
    # Sin el docstring: el texto puede nombrar la función que NO se llama.
    statements = node.body
    if statements and isinstance(statements[0], ast.Expr):
        first = statements[0].value
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            statements = statements[1:]
    body = "\n".join(ast.get_source_segment(src, s) or "" for s in statements)

    assert "_persistir_segmentos_fallback" not in body, (
        "classify_text_spans es el camino classify-first: NO debe crear segmentos"
    )
    assert "INSERT INTO segmentos" not in body
    assert "DELETE FROM segmentos" not in body


def test_classify_text_spans_persists_metadata_only():
    raw = "Uno. Dos."

    def responder(_kwargs):
        return _Output(
            {
                "segments": [
                    {"text": "Uno.", "category": "baseline_data", "confidence": "HIGH"},
                    {
                        "text": "Dos.",
                        "category": "interpreted_data",
                        "confidence": "HIGH",
                    },
                ]
            }
        )

    session = _MetadatosSession({"texto_extraido": raw})
    result = sc.classify_text_spans(
        session, "doc-1", "proj-1", _RecordingLLM(responder)
    )

    assert result["status"] == "ok"
    assert [b["class"] for b in result["blocks"]] == [
        "baseline_data",
        "interpreted_data",
    ]
    assert result["baseline_tags_count"] == 1
    # Los bloques conservan el rango original: lo necesita la herencia de tags.
    assert result["blocks"][0]["start_char"] == 0
    assert all("INSERT INTO segmentos" not in sql for sql in session.sql)
    assert any("glaser_blocks" in str(params) for params in session.params)


def test_classify_text_spans_degrades_without_text():
    session = _MetadatosSession({})
    result = sc.classify_text_spans(
        session, "doc-1", "proj-1", _RecordingLLM(lambda _k: _Output({}))
    )

    assert result["status"] == "degraded"
    assert result["reason"] == "document has no text to classify"
    assert result["blocks"] == []


def test_classify_text_spans_degrades_when_the_llm_raises(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("provider caído")

    monkeypatch.setattr(sc, "llm_segment_and_classify", boom)
    session = _MetadatosSession({"texto_extraido": "Hola."})
    result = sc.classify_text_spans(session, "doc-1", "proj-1", object())

    assert result["status"] == "degraded"
    assert "provider caído" in result["reason"], (
        "el motivo real de la degradación debe llegar al llamador, que decide "
        "si marca 'error' o reintenta"
    )
    assert not [p for p in session.params if "patch" in p], (
        "un clasificado degradado no debe escribir metadatos"
    )
