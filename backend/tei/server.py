import os

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI()

# Leemos la variable de entorno o usamos el default
MODEL_NAME = os.environ.get("MODEL_ID", "voyageai/voyage-4-nano")

print(f"⏳ Cargando modelo {MODEL_NAME} en RAM. Esto puede tardar la primera vez...")
# trust_remote_code=True es el pase mágico para la arquitectura Qwen3
model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
print("✅ Modelo cargado y listo para incrustar.")


class EmbedRequest(BaseModel):
    input: list[str]


@app.post("/v1/embeddings")
def get_embeddings(req: EmbedRequest):
    # encode() genera los vectores matemáticos
    embeddings = model.encode(req.input, convert_to_tensor=False).tolist()

    # Formateamos la respuesta exactamente como OpenAI/Infinity para no romper tu cliente
    data = [
        {"object": "embedding", "embedding": emb, "index": i}
        for i, emb in enumerate(embeddings)
    ]
    return {"object": "list", "data": data, "model": MODEL_NAME}


@app.get("/health")
def health():
    return {"status": "ok"}
