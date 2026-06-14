# app/tei/server.py
import os

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI()

MODEL_NAME = os.getenv("MODEL_ID", "thomasht86/voyage-4-nano-ONNX")
ONNX_FILE = os.getenv("ONNX_MODEL_FILE", "onnx/model_qint8_avx512.onnx")

print(f"⏳ Cargando {MODEL_NAME} (ONNX backend)...")

model = SentenceTransformer(
    MODEL_NAME,
    backend="onnx",
    truncate_dim=1024,
    model_kwargs={"file_name": ONNX_FILE},
)

print(f"✅ Modelo ONNX listo — dimensión: {model.get_sentence_embedding_dimension()}")


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
