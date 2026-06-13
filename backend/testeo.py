# backend/test_tei.py
import asyncio

from app.core.tei_client import TEIClient


async def probar_voyage():
    cliente = TEIClient()

    print("⏳ Conectando con contenedor Infinity (Cargando voyage-4-nano en RAM)...")

    documentos = [
        "El marco metodológico de la Grounded Theory exige muestreo teórico continuo.",
        "El participante mostró ansiedad al hablar de su entorno laboral.",
    ]
    query = "¿Qué metodología se utiliza?"

    try:
        docs_emb = await cliente.embed_documents(documentos)
        print(f"✅ Documentos procesados: {len(docs_emb)} vectores.")
        print(f"📏 Dimensión del vector devuelto: {len(docs_emb[0])}")

        query_emb = await cliente.embed_query(query)
        print(f"✅ Query procesada. Dimensión: {len(query_emb)}")

        print("\n🚀 ¡Cliente de Embeddings funcionando a la perfección!")
        print(
            "⚠️ IMPORTANTE: Si la dimensión devuelta es 2048, debes cambiar 'Vector(1536)' a 'Vector(2048)' en SQLAlchemy."
        )

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(probar_voyage())
