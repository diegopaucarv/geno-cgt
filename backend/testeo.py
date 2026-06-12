# backend/test_db.py
import asyncio
import os

from app.models.domain.category import Categoria, DocCode
from app.models.domain.document import Documento
from app.models.domain.project import Proyecto
from app.models.domain.segment import Segmento

# Importamos nuestros modelos recién creados
from app.models.domain.user import Usuario
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# 1. Cargar configuración
load_dotenv()
db_url = str(os.environ.get("DATABASE_URL"))

# 2. Configurar el motor asíncrono de SQLAlchemy
engine = create_async_engine(db_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def run_test():
    async with AsyncSessionLocal() as session:
        try:
            print("⏳ Iniciando test de inserción de datos...")

            # --- A. Crear un Usuario ---
            nuevo_usuario = Usuario(
                nombre="Investigador Principal",
                correo="test@gt-automation.local",
                rol="INVESTIGADOR_PRINCIPAL",
            )
            session.add(nuevo_usuario)
            await (
                session.flush()
            )  # Flush asigna el ID (UUID) sin hacer commit definitivo

            # --- B. Crear un Proyecto vinculado al Usuario ---
            nuevo_proyecto = Proyecto(
                nombre="Estudio sobre Rigidez Cognitiva",
                ruta_de_codificacion="ABDUCTIVA_CGT",
                creador_id=nuevo_usuario.id,
            )
            session.add(nuevo_proyecto)
            await session.flush()

            # --- C. Crear un Documento (con ruta a un MinIO imaginario) ---
            nuevo_documento = Documento(
                proyecto_id=nuevo_proyecto.id,
                titulo="Entrevista_Sujeto_01",
                tipo_de_fuente="AUDIO_VIDEO",
                ruta_s3="s3://corpus/entrevista_01.mp4",
            )
            session.add(nuevo_documento)
            await session.flush()

            # --- D. Crear un Segmento con PgVector ---
            vector_falso = [
                0.1
            ] * 1536  # Un array de 1536 dimensiones (simulando BGE-small/OpenAI)
            nuevo_segmento = Segmento(
                documento_id=nuevo_documento.id,
                texto="El sujeto mostró una clara resistencia al cambio de esquema.",
                posicion=1,
                embedding=vector_falso,
            )
            session.add(nuevo_segmento)
            await session.flush()

            # --- E. Crear una Categoría de Grounded Theory ---
            nueva_categoria = Categoria(
                proyecto_id=nuevo_proyecto.id,
                nombre="Resistencia al Esquema",
                definicion="Incapacidad inicial para adaptar modelos mentales.",
                estado_saturacion="ABIERTO",
            )
            session.add(nueva_categoria)
            await session.flush()

            # --- F. Vincular Documento y Categoría (DocCode) ---
            nuevo_doc_code = DocCode(
                documento_id=nuevo_documento.id,
                categoria_id=nueva_categoria.id,
                estado="presente",
                resumen_evidencia="Se detectó en el primer tercio de la entrevista.",
            )
            session.add(nuevo_doc_code)

            # --- GUARDAR TODO EN LA BD ---
            await session.commit()
            print(
                "✅ ¡Test exitoso! Todos los datos fueron guardados con sus relaciones y vectores."
            )

            # --- COMPROBACIÓN (LECTURA) ---
            print("\n🔍 Leyendo desde PostgreSQL:")
            stmt = select(Categoria).where(Categoria.nombre == "Resistencia al Esquema")
            resultado = await session.execute(stmt)
            categoria_guardada = resultado.scalar_one()

            print(
                f"-> Categoría recuperada: '{categoria_guardada.nombre}' (ID: {categoria_guardada.id})"
            )

        except Exception as e:
            await session.rollback()
            print(f"❌ Error durante el test: {e}")
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_test())
