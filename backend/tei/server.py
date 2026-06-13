import os

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI()

# Voyage 4 Nano usa 1024 dimensiones por defecto (truncando desde 2048 gracias a Matryoshka)
MODEL_NAME = os.environ.get("MODEL_ID", "voyageai/voyage-4-nano")

print(
    f"⏳ Cargando modelo {MODEL_NAME} en RAM. Esto descargará los pesos al disco externo la primera vez..."
)
# El truco: truncate_dim=1024 nos da el balance perfecto de peso/calidad
model = SentenceTransformer(MODEL_NAME, trust_remote_code=True, truncate_dim=1024)
print("✅ Modelo cargado y listo para incrustar.")


class EmbedRequest(BaseModel):
    input: list[str]
    model: str | None = None


@app.post("/v1/embeddings")
def get_embeddings(req: EmbedRequest):
    # Generamos los vectores matemáticos
    embeddings = model.encode(req.input, convert_to_tensor=False).tolist()

    # Imitamos la estructura de respuesta de OpenAI / Infinity
    data = [
        {"object": "embedding", "embedding": emb, "index": i}
        for i, emb in enumerate(embeddings)
    ]
    return {"object": "list", "data": data, "model": MODEL_NAME}


@app.get("/health")
def health():
    return {"status": "ok"}
