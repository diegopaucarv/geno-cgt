README — ESPAÑOL

# Geno: un sistema automatizado de teoría fundamentada

**Sistema automatizado para análisis cualitativo basado en la Teoría Fundamentada (CGT)**  
*Presentado en ALAS 2026*

Geno orquesta agentes LLM (vía Together.ai) y workers especializados para procesar documentos, extraer incidentes, sintetizar patrones y generar teoría desde datos cualitativos, siguiendo el método de la Teoría Fundamentada de Barney Glaser.

---

## 📦 Flujo de alto nivel

El sistema se organiza en fases secuenciales que reflejan el proceso glaseriano:

1. **Configuración del proyecto** – Definición de población y objeto de estudio.
2. **Open Coding** – Segmentación, clasificación de datos (oro/plata/bronce/anomalía), extracción de incidentes y patrones individuales por documento.
3. **Síntesis Cross‑Document** – Comparación de incidentes entre documentos, etiquetado y recuperación de evidencia textual.
4. **Detección de categoría central** – Identificación del patrón de interés y categorías emergentes.
5. **Reducción selectiva** – Filtrado y fusión de categorías relevantes al patrón de interés.
6. **Saturación** – Verificación de saturación teórica (cuatro señales) y generación de memos.
7. **Playground teórico** – Clasificación de memos con 12 códigos teóricos, elaboración de relaciones y redacción natural.
8. **Diálogo con la literatura** – Comparación con fuentes externas.
9. **Aplicabilidad** – Generación de directrices de intervención.

> El ritmo que atraviesa todo el proceso es: **PROPONER → CRITICAR → SINTETIZAR → VOLVER A CRITICAR → VOS DECIDÍS (HITL)**. Ese es el latido del sistema.[reference:0]

---

## 🧠 Lo que hace Geno (y por qué)

Geno no es un análisis temático ni una verificación de hipótesis. Es un sistema que **descubre** lo que no sabés que está ahí.[reference:1]

- **Comparación constante**: cada incidente se compara con cada otro incidente, una y otra vez, hasta que los patrones se revelan solos.[reference:2]
- **Emergencia**: las categorías, propiedades y relaciones surgen de los datos, no de tu cabeza.[reference:3]
- **Abstracción creciente**: empezás con incidentes concretos y terminás con conceptos abstractos.[reference:4]
- **Guiado por vos**: el sistema propone, critica, muestra evidencia — pero la decisión final siempre es tuya.[reference:5]

### Tipos de datos que maneja

Siguiendo a Glaser, Geno clasifica cada segmento antes de codificarlo:

- **Oro (baseline_data)**: experiencia real, espontánea. Solo esto avanza a codificación.[reference:6]
- **Plata (properline_data)**: lo que el participante cree que debe decir.[reference:7]
- **Bronce (interpreted_data)**: opinión forzada por la pregunta del entrevistador.[reference:8]
- **Anomalía (vague_data)**: evasión.[reference:9]

> Si codificás properline data creyendo que es experiencia real, tu teoría va a describir normas sociales, no comportamiento real.[reference:10]

### El patrón de interés

No es lo que los participantes dicen que les preocupa — es lo que **hacen**, lo que **sienten**, cómo **actúan** cuando no están performando.[reference:11]  
Ejemplo: "La inteligencia artificial en el periodismo" es un tema. "Manteniendo relevancia profesional ante la amenaza de obsolescencia" es un patrón de interés.[reference:12]

---

## ⚙️ Requisitos previos

- Docker y Docker Compose (recomendado)
- Una clave de API de Together.ai (gratuita con créditos iniciales)
- Python 3.10+ (opcional, solo para desarrollo local sin Docker)

---

## 🔐 Configuración del entorno (`.env`)

El sistema utiliza variables de entorno para secretos. **Nunca commitees tu `.env`** (ya está en `.gitignore`).

Tu archivo `.env` debe contener **estas tres variables obligatorias**:

JWT_SECRET=dev-jwt-secret-gt-local
HMAC_SECRET=dev-celery-hmac-gt-local
TOGETHER_API_KEY=xxxx

### Explicación de cada variable

| Variable | Propósito |
|----------|-----------|
| `JWT_SECRET` | Firma de sesiones JWT para autenticación. **En producción, cámbialo por un valor seguro**. |
| `HMAC_SECRET` | Firma de tareas internas de Celery (workers). **Cámbialo en producción**. |
| `TOGETHER_API_KEY` | Clave de API de Together.ai. Obtenela en https://api.together.ai/settings/api-keys |

> El resto de la configuración (base de datos, MinIO, Redis, rutas) ya tiene valores por defecto en `config.py` y `docker-compose.yml`.

### Pasos para crear tu `.env`

1. Copia el ejemplo o crea el archivo: `cp .env.example .env`
2. Abrí `.env` y pegá el contenido de arriba.
3. Sustituí `xxxx` por tu `TOGETHER_API_KEY` real.

---

## 🐳 Levantar el sistema con Docker (recomendado)

Construir imágenes (solo la primera vez):
docker-compose build

Levantar todos los servicios (API, workers, Redis, DB, MinIO):
docker-compose up -d

Ver logs en tiempo real:
docker-compose logs -f

Detener los servicios:
docker-compose down

Una vez levantado, la API estará disponible en `http://localhost:8000` (por defecto).

---

## 💻 Desarrollo local (sin Docker)

Si preferís ejecutar sin Docker para depuración:

1. Crear y activar entorno virtual:
   python -m venv venv
   source venv/bin/activate      # Linux/Mac
   venv\Scripts\activate         # Windows

2. Instalar dependencias:
   pip install -r requirements.txt

3. Asegurate de tener Redis y PostgreSQL corriendo localmente (o usá docker-compose solo para esos servicios).

4. Exportar las variables de entorno (o cargar .env):
   export JWT_SECRET=dev-jwt-secret-gt-local
   export HMAC_SECRET=dev-celery-hmac-gt-local
   export TOGETHER_API_KEY=xxxx

5. Ejecutar migraciones (si usás Django/Flask + ORM):
   python manage.py migrate

6. Iniciar el servidor de desarrollo:
   python manage.py runserver

---

## 🧪 Comandos útiles

- `make test` – Ejecutar suite de pruebas
- `make lint` – Revisar estilo de código (flake8, black)
- `docker-compose exec api bash` – Acceder al contenedor de la API
- `docker-compose exec worker bash` – Acceder al contenedor del worker de Celery
- `docker-compose logs -f worker` – Ver logs del worker en tiempo real

---

## 📁 Documentación adicional

- [`kb.md`](https://github.com/diegopaucarv/gt/blob/main/Documentacion/cgt_alignment/kb.md) – Guía narrativa del proceso CGT glaseriano.
- [`4-Patrones_de_desarrollo.md`](https://github.com/diegopaucarv/gt/blob/main/Documentacion/cgt_alignment/4-Patrones_de_desarrollo.md) – Detalles técnicos (transiciones, checkpoints, cancelabilidad).
- [`5-Adaptacion_Sistema_Agencial.md`](https://github.com/diegopaucarv/gt/blob/main/Documentacion/cgt_alignment/5-Adaptacion_Sistema_Agencial.md) – Arquitectura de agentes y workers.

---

## ⚠️ Consideraciones de seguridad

- Los valores `dev-*` para JWT y HMAC son **solo para desarrollo local**.
- Nunca expongas tu `TOGETHER_API_KEY` en logs o repositorios públicos.
- El archivo `.env` ya está en `.gitignore`; verificá que no se haya commiteado.

---

## 🆘 Soporte

Si encontrás errores al levantar el sistema, verificá que:
- Docker esté corriendo y tenga suficientes recursos (mínimo 4 GB de RAM recomendados).
- Tu `TOGETHER_API_KEY` sea válida y tenga créditos disponibles.
- Los puertos 8000, 5432, 6379 y 9000 no estén ocupados.

README — ENGLISH

# Geno: an automated grounded theory system

**Automated qualitative analysis system based on Grounded Theory (CGT)**  
*Presented at ALAS 2026*

Geno orchestrates LLM agents (via Together.ai) and specialized workers to process documents, extract incidents, synthesize patterns, and generate theory from qualitative data, following Barney Glaser's Grounded Theory method.

---

## 📦 High-level flow

The system is organized into sequential phases that reflect the Glaserian process:

1. **Project setup** – Definition of population and object of study.
2. **Open Coding** – Segmentation, data classification (gold/silver/bronze/anomaly), incident extraction, and individual pattern detection per document.
3. **Cross‑Document Synthesis** – Comparison of incidents across documents, labeling, and textual evidence retrieval.
4. **Core category detection** – Identification of the pattern of interest and emerging categories.
5. **Selective reduction** – Filtering and merging of categories relevant to the pattern of interest.
6. **Saturation** – Theoretical saturation verification (four signals) and memo generation.
7. **Theoretical playground** – Memo classification using 12 theoretical codes, relationship building, and natural writing.
8. **Dialogue with the literature** – Comparison with external sources.
9. **Applicability** – Generation of intervention guidelines.

> The rhythm that runs through the entire process is: **PROPOSE → CRITIQUE → SYNTHESIZE → CRITIQUE AGAIN → YOU DECIDE (HITL)**. That is the system's heartbeat.[reference:13]

---

## 🧠 What Geno does (and why)

Geno is not a thematic analysis or a hypothesis test. It is a system that **discovers** what you don't know is there.[reference:14]

- **Constant comparison**: each incident is compared with every other incident, again and again, until patterns reveal themselves.[reference:15]
- **Emergence**: categories, properties, and relationships arise from the data, not from your head.[reference:16]
- **Increasing abstraction**: you start with concrete incidents and end with abstract concepts.[reference:17]
- **Guided by you**: the system proposes, critiques, shows evidence — but the final decision is always yours.[reference:18]

### Data types it handles

Following Glaser, Geno classifies each segment before coding it:

- **Gold (baseline_data)**: real, spontaneous experience. Only this moves forward to coding.[reference:19]
- **Silver (properline_data)**: what the participant believes they should say.[reference:20]
- **Bronze (interpreted_data)**: opinion forced by the interviewer's question.[reference:21]
- **Anomaly (vague_data)**: evasion.[reference:22]

> If you code properline data thinking it's real experience, your theory will describe social norms, not actual behavior.[reference:23]

### The pattern of interest

It's not what participants say concerns them — it's what they **do**, what they **feel**, how they **act** when they're not performing.[reference:24]  
Example: "Artificial intelligence in journalism" is a topic. "Maintaining professional relevance in the face of obsolescence threat" is a pattern of interest.[reference:25]

---

## ⚙️ Prerequisites

- Docker and Docker Compose (recommended)
- A Together.ai API key (free with initial credits)
- Python 3.10+ (optional, only for local development without Docker)

---

## 🔐 Environment setup (`.env`)

The system uses environment variables for secrets. **Never commit your `.env`** (it is already in `.gitignore`).

Your `.env` file must contain **these three mandatory variables**:

JWT_SECRET=dev-jwt-secret-gt-local
HMAC_SECRET=dev-celery-hmac-gt-local
TOGETHER_API_KEY=xxxx

### Explanation of each variable

| Variable | Purpose |
|----------|---------|
| `JWT_SECRET` | JWT session signing for authentication. **In production, replace with a secure value**. |
| `HMAC_SECRET` | Internal Celery task signing (workers). **Change in production**. |
| `TOGETHER_API_KEY` | Together.ai API key. Get it at https://api.together.ai/settings/api-keys |

> The rest of the configuration (database, MinIO, Redis, paths) already has default values in `config.py` and `docker-compose.yml`.

### Steps to create your `.env`

1. Copy the example or create the file: `cp .env.example .env`
2. Open `.env` and paste the content above.
3. Replace `xxxx` with your actual `TOGETHER_API_KEY`.

---

## 🐳 Running the system with Docker (recommended)

Build images (only the first time):
docker-compose build

Start all services (API, workers, Redis, DB, MinIO):
docker-compose up -d

View logs in real time:
docker-compose logs -f

Stop services:
docker-compose down

Once started, the API will be available at `http://localhost:8000` (by default).

---

## 💻 Local development (without Docker)

If you prefer to run without Docker for debugging:

1. Create and activate a virtual environment:
   python -m venv venv
   source venv/bin/activate      # Linux/Mac
   venv\Scripts\activate         # Windows

2. Install dependencies:
   pip install -r requirements.txt

3. Make sure Redis and PostgreSQL are running locally (or use docker-compose only for those services).

4. Export the environment variables (or load .env):
   export JWT_SECRET=dev-jwt-secret-gt-local
   export HMAC_SECRET=dev-celery-hmac-gt-local
   export TOGETHER_API_KEY=xxxx

5. Run migrations (if using Django/Flask + ORM):
   python manage.py migrate

6. Start the development server:
   python manage.py runserver

---

## 🧪 Useful commands

- `make test` – Run the test suite
- `make lint` – Check code style (flake8, black)
- `docker-compose exec api bash` – Access the API container
- `docker-compose exec worker bash` – Access the Celery worker container
- `docker-compose logs -f worker` – View worker logs in real time

---

## 📁 Additional documentation

- [`kb.md`](https://github.com/diegopaucarv/gt/blob/main/Documentacion/cgt_alignment/kb.md) – Narrative guide to the Glaserian CGT process.
- [`4-Patrones_de_desarrollo.md`](https://github.com/diegopaucarv/gt/blob/main/Documentacion/cgt_alignment/4-Patrones_de_desarrollo.md) – Technical details (transitions, checkpoints, cancelability).
- [`5-Adaptacion_Sistema_Agencial.md`](https://github.com/diegopaucarv/gt/blob/main/Documentacion/cgt_alignment/5-Adaptacion_Sistema_Agencial.md) – Agent and worker architecture.

---

## ⚠️ Security considerations

- The `dev-*` values for JWT and HMAC are **for local development only**.
- Never expose your `TOGETHER_API_KEY` in logs or public repositories.
- The `.env` file is already in `.gitignore`; verify it hasn't been committed.

---

## 🆘 Support

If you encounter errors when starting the system, verify that:
- Docker is running and has enough resources (at least 4 GB of RAM recommended).
- Your `TOGETHER_API_KEY` is valid and has available credits.
- Ports 8000, 5432, 6379, and 9000 are not occupied.

README — PORTUGUÊS

# Geno: um sistema automatizado de teoria fundamentada

**Sistema automatizado para análise qualitativa baseado na Teoria Fundamentada (CGT)**  
*Apresentado no ALAS 2026*

Geno orquestra agentes LLM (via Together.ai) e workers especializados para processar documentos, extrair incidentes, sintetizar padrões e gerar teoria a partir de dados qualitativos, seguindo o método da Teoria Fundamentada de Barney Glaser.

---

## 📦 Fluxo de alto nível

O sistema é organizado em fases sequenciais que refletem o processo glaseriano:

1. **Configuração do projeto** – Definição da população e objeto de estudo.
2. **Codificação aberta (Open Coding)** – Segmentação, classificação de dados (ouro/prata/bronze/anomalia), extração de incidentes e padrões individuais por documento.
3. **Síntese entre documentos** – Comparação de incidentes entre documentos, rotulagem e recuperação de evidência textual.
4. **Detecção da categoria central** – Identificação do padrão de interesse e categorias emergentes.
5. **Redução seletiva** – Filtragem e fusão de categorias relevantes ao padrão de interesse.
6. **Saturação** – Verificação da saturação teórica (quatro sinais) e geração de memos.
7. **Playground teórico** – Classificação de memos com 12 códigos teóricos, elaboração de relações e redação natural.
8. **Diálogo com a literatura** – Comparação com fontes externas.
9. **Aplicabilidade** – Geração de diretrizes de intervenção.

> O ritmo que atravessa todo o processo é: **PROPOR → CRITICAR → SINTETIZAR → CRITICAR NOVAMENTE → VOCÊ DECIDE (HITL)**. Esse é o batimento do sistema.[reference:26]

---

## 🧠 O que Geno faz (e por quê)

Geno não é uma análise temática nem uma verificação de hipóteses. É um sistema que **descobre** o que você não sabe que está lá.[reference:27]

- **Comparação constante**: cada incidente é comparado com cada outro incidente, repetidamente, até que os padrões se revelem.[reference:28]
- **Emergência**: as categorias, propriedades e relações surgem dos dados, não da sua cabeça.[reference:29]
- **Abstração crescente**: você começa com incidentes concretos e termina com conceitos abstratos.[reference:30]
- **Guiado por você**: o sistema propõe, critica, mostra evidência — mas a decisão final é sempre sua.[reference:31]

### Tipos de dados que ele manuseia

Seguindo Glaser, Geno classifica cada segmento antes de codificá-lo:

- **Ouro (baseline_data)**: experiência real, espontânea. Só isso avança para a codificação.[reference:32]
- **Prata (properline_data)**: o que o participante acredita que deve dizer.[reference:33]
- **Bronze (interpreted_data)**: opinião forçada pela pergunta do entrevistador.[reference:34]
- **Anomalia (vague_data)**: evasão.[reference:35]

> Se você codificar properline_data achando que é experiência real, sua teoria vai descrever normas sociais, não comportamento real.[reference:36]

### O padrão de interesse

Não é o que os participantes dizem que os preocupa — é o que eles **fazem**, o que **sentem**, como **agem** quando não estão performando.[reference:37]  
Exemplo: "A inteligência artificial no jornalismo" é um tópico. "Mantendo relevância profissional diante da ameaça de obsolescência" é um padrão de interesse.[reference:38]

---

## ⚙️ Pré-requisitos

- Docker e Docker Compose (recomendado)
- Uma chave de API da Together.ai (gratuita com créditos iniciais)
- Python 3.10+ (opcional, apenas para desenvolvimento local sem Docker)

---

## 🔐 Configuração do ambiente (`.env`)

O sistema utiliza variáveis de ambiente para segredos. **Nunca commite o seu `.env`** (ele já está no `.gitignore`).

Seu arquivo `.env` deve conter **estas três variáveis obrigatórias**:

JWT_SECRET=dev-jwt-secret-gt-local
HMAC_SECRET=dev-celery-hmac-gt-local
TOGETHER_API_KEY=xxxx

### Explicação de cada variável

| Variável | Finalidade |
|----------|------------|
| `JWT_SECRET` | Assinatura de sessões JWT para autenticação. **Em produção, troque por um valor seguro**. |
| `HMAC_SECRET` | Assinatura de tarefas internas do Celery (workers). **Troque em produção**. |
| `TOGETHER_API_KEY` | Chave de API da Together.ai. Obtenha em https://api.together.ai/settings/api-keys |

> O restante da configuração (banco de dados, MinIO, Redis, caminhos) já possui valores padrão em `config.py` e `docker-compose.yml`.

### Passos para criar seu `.env`

1. Copie o exemplo ou crie o arquivo: `cp .env.example .env`
2. Abra o `.env` e cole o conteúdo acima.
3. Substitua `xxxx` pela sua `TOGETHER_API_KEY` real.

---

## 🐳 Executando o sistema com Docker (recomendado)

Construir as imagens (somente na primeira vez):
docker-compose build

Iniciar todos os serviços (API, workers, Redis, DB, MinIO):
docker-compose up -d

Ver logs em tempo real:
docker-compose logs -f

Parar os serviços:
docker-compose down

Uma vez iniciado, a API estará disponível em `http://localhost:8000` (por padrão).

---

## 💻 Desenvolvimento local (sem Docker)

Se preferir executar sem Docker para depuração:

1. Criar e ativar um ambiente virtual:
   python -m venv venv
   source venv/bin/activate      # Linux/Mac
   venv\Scripts\activate         # Windows

2. Instalar dependências:
   pip install -r requirements.txt

3. Certifique-se de que Redis e PostgreSQL estejam rodando localmente (ou use docker-compose apenas para esses serviços).

4. Exportar as variáveis de ambiente (ou carregar .env):
   export JWT_SECRET=dev-jwt-secret-gt-local
   export HMAC_SECRET=dev-celery-hmac-gt-local
   export TOGETHER_API_KEY=xxxx

5. Executar migrações (se usar Django/Flask + ORM):
   python manage.py migrate

6. Iniciar o servidor de desenvolvimento:
   python manage.py runserver

---

## 🧪 Comandos úteis

- `make test` – Executar a suíte de testes
- `make lint` – Verificar estilo do código (flake8, black)
- `docker-compose exec api bash` – Acessar o container da API
- `docker-compose exec worker bash` – Acessar o container do worker Celery
- `docker-compose logs -f worker` – Ver logs do worker em tempo real

---

## 📁 Documentação adicional

- [`kb.md`](https://github.com/diegopaucarv/gt/blob/main/Documentacion/cgt_alignment/kb.md) – Guia narrativa do processo CGT glaseriano.
- [`4-Patrones_de_desarrollo.md`](https://github.com/diegopaucarv/gt/blob/main/Documentacion/cgt_alignment/4-Patrones_de_desarrollo.md) – Detalhes técnicos (transições, checkpoints, cancelabilidade).
- [`5-Adaptacion_Sistema_Agencial.md`](https://github.com/diegopaucarv/gt/blob/main/Documentacion/cgt_alignment/5-Adaptacion_Sistema_Agencial.md) – Arquitetura de agentes e workers.

---

## ⚠️ Considerações de segurança

- Os valores `dev-*` para JWT e HMAC são **apenas para desenvolvimento local**.
- Nunca exponha sua `TOGETHER_API_KEY` em logs ou repositórios públicos.
- O arquivo `.env` já está no `.gitignore`; verifique se ele não foi commitado.

---

## 🆘 Suporte

Se encontrar erros ao iniciar o sistema, verifique se:
- O Docker está rodando e tem recursos suficientes (mínimo de 4 GB de RAM recomendados).
- Sua `TOGETHER_API_KEY` é válida e tem créditos disponíveis.
- As portas 8000, 5432, 6379 e 9000 não estão ocupadas.

