import os

# --- compatibility shim: fixes naming mismatch between old voyage-4-nano
#     model code (input_embeds) and current transformers (inputs_embeds)
import transformers.masking_utils as _mu

_orig_ccm = _mu.create_causal_mask


def _compat_ccm(*args, input_embeds=None, **kwargs):
    if input_embeds is not None and "inputs_embeds" not in kwargs:
        kwargs["inputs_embeds"] = input_embeds
    return _orig_ccm(*args, **kwargs)


_mu.create_causal_mask = _compat_ccm
# --- end shim

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

app = FastAPI()

MODEL_NAME = os.environ.get("MODEL_ID", "voyageai/voyage-4-nano")
print(f"⏳ Cargando modelo {MODEL_NAME}...")
model = SentenceTransformer(
    MODEL_NAME,
    trust_remote_code=True,
    truncate_dim=1024,
    model_kwargs={"attn_implementation": "sdpa"},
)
print("✅ Modelo cargado y listo para incrustar.")


class EmbedRequest(BaseModel):
    input: list[str]
    model: str | None = None


@app.post("/v1/embeddings")
def get_embeddings(req: EmbedRequest):
    embeddings = model.encode(req.input, convert_to_tensor=False).tolist()
    data = [
        {"object": "embedding", "embedding": emb, "index": i}
        for i, emb in enumerate(embeddings)
    ]
    return {"object": "list", "data": data, "model": MODEL_NAME}


@app.get("/health")
def health():
    return {"status": "ok"}
