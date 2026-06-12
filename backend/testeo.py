import asyncio

from app.core.tei_client import TEIClient


async def test_voyage():
    cliente = TEIClient()

    print("⏳ Conectando con contenedor TEI (voyage-4-nano)...")

    documentos = [
        "El marco metodológico de la Grounded Theory exige muestreo teórico continuo.",
        "El participante mostró ansiedad al hablar de su entorno laboral.",
    ]
    query = "¿Qué metodología se utiliza?"

    try:
        # Probamos codificación de documentos
        docs_emb = await cliente.embed_documents(documentos)
        print(f"✅ Documentos procesados: {len(docs_emb)} vectores.")
        print(f"📏 Dimensión del vector 1: {len(docs_emb[0])} (Debe ser 1024 o 2048)")

        # Probamos codificación de query (prefijo distinto)
        query_emb = await cliente.embed_query(query)
        print(f"✅ Query procesada. Dimensión: {len(query_emb)}")

        print("\n🚀 ¡Cliente TEI y modelo Voyage-4-nano funcionando a la perfección!")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_voyage())
