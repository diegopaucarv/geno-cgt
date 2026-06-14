# app/tei/server.py
import os

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI()

# ── GPU / CPU switch ──────────────────────────────────────────────────────────
USE_GPU = os.getenv("USE_GPU", "false").lower() in ("1", "true", "yes")

MODEL_NAME = os.getenv("MODEL_ID", "thomasht86/voyage-4-nano-ONNX")

if USE_GPU:
    # GPU: modelo full-precision (el qint8_avx512 NO funciona en CUDA)
    ONNX_FILE = os.getenv("ONNX_MODEL_FILE", "onnx/model.onnx")
    print(f"⏳ Cargando {MODEL_NAME} (ONNX → CUDAExecutionProvider)...")
    model_kwargs = {
        "file_name": ONNX_FILE,
        "provider": "CUDAExecutionProvider",
    }
else:
    # CPU: int8 cuantizado dinámico + AVX512 (más rápido, menor RAM)
    ONNX_FILE = os.getenv("ONNX_MODEL_FILE", "onnx/model_qint8_avx512.onnx")
    print(f"⏳ Cargando {MODEL_NAME} (ONNX → CPUExecutionProvider, int8 AVX512)...")
    model_kwargs = {
        "file_name": ONNX_FILE,
        "provider": "CPUExecutionProvider",
    }

model = SentenceTransformer(
    MODEL_NAME,
    backend="onnx",
    truncate_dim=1024,
    model_kwargs=model_kwargs,
)

print(f"✅ Modelo ONNX listo — dimensión: {model.get_sentence_embedding_dimension()}")
print(f"   Archivo: {ONNX_FILE}")
print(f"   GPU: {USE_GPU}")


class EmbedRequest(BaseModel):
    input: list[str]
    model: str | None = None
    prompt_name: str | None = None


@app.post("/v1/embeddings")
def get_embeddings(req: EmbedRequest):
    embeddings = model.encode(
        req.input,
        prompt_name=req.prompt_name,
        convert_to_tensor=False,
    ).tolist()

    data = [
        {"object": "embedding", "embedding": emb, "index": i}
        for i, emb in enumerate(embeddings)
    ]
    return {"object": "list", "data": data, "model": MODEL_NAME}


@app.get("/health")
def health():
    return {"status": "ok"}
