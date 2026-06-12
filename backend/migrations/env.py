import os
import sys
from logging.config import fileConfig

from alembic import context
from app.models.base import Base
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# 1. Añadimos la carpeta raíz de tu backend al sistema para que encuentre tus clases
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# 2. Cargamos tus contraseñas y rutas desde el archivo secreto .env
load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# 3. Le inyectamos a Alembic la URL de tu base de datos
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgresql+asyncpg") and type(db_url) is str:
    # Truco: Alembic prefiere el driver síncrono. Lo cambiamos al vuelo solo para las migraciones.
    db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

config.set_main_option("sqlalchemy.url", db_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 4. AQUÍ IMPORTAS TUS CLASES (La traducción de tu diagrama UML)
# Primero importas la Base:

# Luego importas los modelos que vayas creando (por ejemplo, para el análisis de Grounded Theory):
# from app.models.analisis import Documento, Categoria

# 5. Le decimos a Alembic que vigile estas clases
target_metadata = Base.metadata
