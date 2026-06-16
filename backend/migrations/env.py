import os
import sys
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# 1. Añadimos la carpeta raíz de tu backend al sistema para que encuentre tus clases
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# 2. Cargamos tus contraseñas y rutas desde el archivo secreto .env
load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 3. Le inyectamos a Alembic la URL de tu base de datos
db_url = str(os.environ.get("DATABASE_URL"))
if db_url and db_url.startswith("postgresql+asyncpg"):
    # Truco: Alembic prefiere el driver síncrono. Lo cambiamos al vuelo solo para las migraciones.
    db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

config.set_main_option("sqlalchemy.url", db_url)


# 4. AQUÍ IMPORTAS TUS CLASES (La traducción de tu diagrama UML)
from app.models.base import Base
from app.models.domain.canvas import (
    BordeDeLienzo,
    LienzoDelPlanDeAnalisis,
    NodoDeLienzo,
)
from app.models.domain.category import Categoria, CodigoSegmento, DocCode
from app.models.domain.document import Documento
from app.models.domain.document_process import DocumentProcess
from app.models.domain.hitl_decision import HitlDecision
from app.models.domain.memo import Memo
from app.models.domain.pipeline_run import (
    PipelineRun,
    PipelineTask,
    TaskStepCheckpoint,
)
from app.models.domain.population_context import PopulationContext
from app.models.domain.project import Proyecto
from app.models.domain.segment import Segmento
from app.models.domain.synthesis import (
    CodeDocumentSummary,
    CodeGlobalSummary,
    CodePrototype,
    GraphEntity,
    GraphRelation,
    Hypothesis,
    ParadigmState,
    ProcessingState,
    SaturationMetrics,
)
from app.models.domain.user import Usuario
from app.models.domain.workflow import Fase
from app.models.exec_log import RegistroEjecucionAgente
from app.models.langgraph_checkpoints import LangGraphCheckpoint

# 5. Le decimos a Alembic que vigile estas clases
target_metadata = Base.metadata

# ====================================================================
# ESTO ES LO QUE FALTABA: EL MOTOR DE EJECUCIÓN DE ALEMBIC
# ====================================================================


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.
    This configures the context with just a URL
    and not an Engine.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
