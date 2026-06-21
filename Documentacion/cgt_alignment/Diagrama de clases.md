# Diagrama de clases

# 3. Diagrama de Clases Unificado

```
@startuml IQAS_DiagramaClases_v6_ES
!theme plain
skinparam classAttributeIconSize 0
skinparam classFontSize 9
skinparam packageFontSize 10
skinparam packageBackgroundColor #FAFAFA
skinparam classBackgroundColor #FFFFF0
skinparam abstractClassBackgroundColor #FFF0F0
skinparam interfaceBackgroundColor #F0FFFF
skinparam enumBackgroundColor #F0FFF0
hide empty members
left to right direction

' ═══════════════════════════════════════
'  LEYENDA DE REVISIONES
'  [v5] = cambios de versión 5 (robustez + seguridad)
'  [v6] = cambios nuevos en esta versión:
'         + ConfiguraciónDeSaturaciónGlobal   (§2.2)
'         + RegistroEjecuciónAgente           (§2.5)
'         + incidentesMotivadores en DiffRec  (§2.9)
' ═══════════════════════════════════════

' ═══════════════════════════════════════
'  ENUMERACIONES
' ═══════════════════════════════════════
package "Enumeraciones" #F5F5F5 {
  enum RolDeUsuario { INVESTIGADOR_PRINCIPAL; COLABORADOR; ESTUDIANTE; AUDITOR; VISUALIZADOR }
  enum RutaDeCodificación { DEDUCTIVA; ABDUCTIVA_CGT; INDUCTIVA }
  enum TipoDePreguntaInvestigación { DESCRIPTIVA; INTERPRETATIVA; EXPLICATIVA; RELACIONAL }
  enum TipoDeFuente {
    ENCUESTA_DB; WEB_SCRAPING; REDES_SOCIALES; AUDIO_VIDEO
    BIBLIOGRAFÍA; INFORME_CUANTITATIVO; GRUPO_FOCAL; IMAGEN
  }
  enum TipoDeDatoGlaser {
    DATO_BASE; DATO_PROPIO; DATO_INTERPRETADO; DATO_VAGO
  }
  enum TipoDeMemo { HIPÓTESIS; PROPIEDAD; RELACIÓN; METODOLÓGICO; MUESTREO }
  enum EstadoDeMemo { ABIERTO; SAT; MOD; FORZADO }
  enum EstadoDeSaturación { ABIERTO; ESTABLE; SATURADO; REVISIÓN_FORZADA }
  enum TipoDeRelación {
    JERARQUÍA; CAUSAL; TIPOLOGÍA; ETAPA_DE_PROCESO; OPOSICIÓN; COOCURRENCIA
  }
  enum TipoDeInterésAbductivo {
    HIPÓTESIS_CAUSAL; PROCESO_SOCOCOGNITIVO
    PROCESO_CENTRAL_LONGITUDINAL; DEFINIDO_POR_INVESTIGADOR
  }
  enum PosturaInterpretativa {
    EXPLORADOR; ABOGADO_DEL_DIABLO; ETNÓGRAFO_VIRTUAL
    TEÓRICO_CRÍTICO; EDITOR; POSTURA_DE_AUDITOR; DIALÉCTICA
  }
  enum FamiliaDeOrdenamiento {
    TEMÁTICA; CAUSAL; PROCESO_TEMPORAL; JERÁRQUICA
    TIPOLÓGICA; SEIS_CS; PROCESO_SOCIAL_BÁSICO; MATRIZ_DOS_POR_DOS
  }
  enum EsqueletoNarrativo {
    ESTUDIO_DE_CASO; COMPARACIÓN; CRONOLÓGICO; SUSPENSO; EMBLEMA_MICRO_MACRO
  }
  enum EstrategiaDeVolumenDeTokens {
    BAJO_MEDIO_COMPLETO; ALTO_NO_CONVERSACIONAL_LOTE; ALTO_CONVERSACIONAL_HILADO
  }
  enum RazónDeBorradoDeMemoria { SATURACIÓN_FALLIDA_TRAS_BORRADO; TRANSICIÓN_DE_FASE; REINICIO_MANUAL }
  enum TipoDePlantilla {
    GT_CLÁSICA; GT_CONSTRUCTIVISTA; ANÁLISIS_SITUACIONAL
    AD_FOUCAULDIANO; ACD; AD_RETÓRICO; IPA; NARRATIVA; MÉTODOS_MIXTOS
  }
  enum TipoDeNodoDeLienzo {
    FUENTE_DE_DATOS; FASE; HERRAMIENTA_DE_ANÁLISIS; PUERTA_DE_DECISIÓN; SALIDA; ANOTACIÓN
  }
  enum EstadoDeNodoDeLienzo { NO_INICIADO; EJECUTÁNDOSE; COMPLETO; NECESITA_REVISIÓN; ERROR; OMITIDO }
  enum NivelDeModelo { RÁPIDO_ECONÓMICO; EQUILIBRADO; RAZONAMIENTO_POTENTE }
  enum VeredictoDelCrítico { APROBADO; NECESITA_REVISIÓN; ALUCINACIÓN_DETECTADA; VIOLACIÓN_METODOLÓGICA }
  enum TipoDeCapaDeOrientación { TOOLTIP; TARJETA_PRIMARIA; TUTORIAL; ASISTENTE; PLANTILLA }
  enum EstadoDeMódulo { ACTIVO; DESHABILITADO; CARGANDO; ERROR }
  enum TipoModelo { LLM; ONNX_EMBEDDING }
  enum RiesgoPrompt { BAJO; MEDIO; ALTO; CUARENTENA }
  enum EstadoTareaCelery { PENDIENTE; EJECUTANDO; COMPLETADA; FALLIDA; DUPLICADA_BLOQUEADA }
  enum MotivoLogSeguridad {
    AUTH_FALLIDA; ACCESO_DENEGADO; INYECCION_PROMPT; MALWARE_DETECTADO
    DISCREPANCIA_HASH_MODELO; CAMBIO_PERMISO_CRITICO; BORRADO_GDPR
  }
  enum TipoPlanSuscripción { BASICO; PROFESIONAL }
}

' ═══════════════════════════════════════
'  INTERFACES DE MÓDULOS
' ═══════════════════════════════════════
package "Interfaces de Módulos" #E8EAF6 {
  interface IMóduloNLP {
    +ejecutar(corpus, config) : ResultadoVersionado
    +puedeEjecutarConRuta(r : RutaDeCodificación) : booleano
    +entradasRequeridas() : cadena[]
    +nivelDeComplejidadEstimado() : NivelDeModelo
    +estadoDelMódulo() : EstadoDeMódulo
  }
  interface IAgente {
    +ejecutar(entrada) : Objeto
    +etiquetasDeCapacidad() : cadena[]
    +nivelDeModeloPreferido() : NivelDeModelo
    +aceptaContexto(ctx : ContextoDeAgente) : booleano
    +manejarError(reintentos : Entero) : void
  }
  interface IAdaptadorDeAlmacenamiento {
    +obtener(id : UUID) : Objeto
    +consultar(filtro : Mapa) : Objeto[]
    +insertarOActualizar(entidad : Objeto) : void
    +eliminar(id : UUID) : void
    +inserciónMasiva(entidades : Objeto[]) : void
  }
  interface IRenderizadorDeVisualización {
    +renderizar(datos, config) : CargaÚtilDeArtefacto
    +soporta(tipoDeArtefacto : cadena) : booleano
    +exportarComo(formato : cadena) : Objeto
  }
  interface IPlantillaMetodológica {
    +obtenerTopologíaDelLienzo() : NodoDeLienzo[]
    +obtenerRosterDeAgentesPorDefecto() : ConfiguraciónDeAgente[]
    +obtenerUmbralesPorDefecto() : ConfiguraciónDeUmbral
    +obtenerContenidoDeOrientación() : PaqueteDeOrientación
    +obtenerTipoDePlantilla() : TipoDePlantilla
  }
  interface IProveedorDeOrientación {
    +obtenerTooltip(claveDeContexto : cadena) : TooltipDeOrientación
    +obtenerTutorial(idDeFase : cadena) : Tutorial
    +obtenerTarjetaPrimaria(idDeFase : cadena) : TarjetaPrimariaDeFase
  }
  interface ILLMClient {
    +generar(mensajes, modelo, opciones) : RespuestaLLM
    +generarStream(mensajes, modelo, opciones) : Stream
  }
  interface IProveedorSecretos {
    +obtener(clave : cadena) : cadena
    +rotar(clave : cadena) : void
  }
}

' ═══════════════════════════════════════
'  GESTIÓN DE USUARIOS Y PERMISOS
' ═══════════════════════════════════════
package "Gestión de Usuarios y Permisos" #E3F2FD {
  class Usuario {
    +id : UUID
    +nombre : cadena
    +correo : cadena
    +rol : RolDeUsuario
    +plan : TipoPlanSuscripción
    +tokensMensualesUsados : Entero
    --
    +tienePermiso(acción, recurso) : Booleano
    +obtenerPerfilEfectivo() : PerfilDePermiso
  }
  class PerfilDeEstudiante { +permisoDeCodificación; +accesoAMemos; +fasesPermitidas : cadena[] }
  class PerfilDePermisoDeColaborador {
    +id : UUID
    +puedeVerDatosPersonales : Booleano
    +permisoDeCodificación; +accesoAMemos; +puedeExportar : Booleano
    +accesoAAnalíticas; +fasesPermitidas : cadena[]
    --
    +aplicarASolicitud(solicitud) : RespuestaFiltrada
  }
  class PerfilDeAuditor {
    +puedeLeerRegistroDeAuditoría : Booleano = true
    +puedeLeerHistorialDeCambios : Booleano = true
    +puedeLeerTodosLosMemos : Booleano = true
    +puedeExportarInformeDeAuditoría : Booleano = true
    +puedeEscribir : Booleano = false
  }
  class PerfilDeVisualizador {
    +puedeLeerInformes : Booleano = true
    +accesoAAnalíticas
    +puedeEscribir : Booleano = false
  }
  class ÁmbitoDeAccesoADocumentos {
    +idsDeDocumentosPermitidos : UUID[]
    +etiquetasDeDocumentosPermitidos : cadena[]
    +permitirTodos : Booleano
  }
  class PolíticaDeEnmascaramientoDeSegmentos {
    +enmascararNombresPersonales : Booleano
    +enmascararUbicaciones : Booleano
    +enmascararFechas : Booleano
    +patronesDeEnmascaramientoPersonalizados : cadena[]
  }
  class PolíticaDeAccesoAAnalíticas {
    +accesoReinert; +accesoBERTopic; +accesoIncrustaciones
    +accesoRF_SHAP; +accesoMCA; +accesoKWIC : Booleano
  }
  class RegistroDeAuditoríaDePermisos {
    +idUsuario : UUID; +acción : cadena; +recurso : cadena
    +fueConcedido : Booleano; +marcaDeTiempo : DateTime; +razónDeDenegación : cadena
  }
  class FiltroDeAccesoADatos {
    +idUsuario : UUID
    --
    +aplicarA(consulta, perfil) : ResultadoFiltrado
    +enmascararSegmentos(segs, política) : Segmento[]
    +filtrarAnalíticas(resultados, política) : Objeto
  }
}

' ═══════════════════════════════════════
'  SEGURIDAD TRANSVERSAL
' ═══════════════════════════════════════
package "Seguridad Transversal" #FFD0D0 {
  class AdaptadorGestorSecretos implements IProveedorSecretos {
    +tipoProveedor : cadena
    -cachéLocalCifrado : Mapa
    +obtener(clave) : cadena
    +rotar(clave) : void
  }
  class ListaNegraJWT {
    -redisCaché : DB_CACHE
    +agregar(token, ttlSegundos) : void
    +estáRevocado(token) : booleano
  }
  class FirmadorTareasCelery {
    -claveHMAC : cadena
    +firmar(tipoTarea, payload) : cadena
    +verificar(tipoTarea, payload, firma) : booleano
  }
  class GestorRetencionGDPR {
    +programarBorrado(usuarioId, políticaDías) : void
    +anonimizarTotal(idRegistro, tabla) : void
    +registrarConformidad(operacion, firmante) : void
  }
  class GeneradorSBOM {
    +generar(imagenDocker) : Objeto
    +firmar(sbom, claveCosign) : cadena
  }
  class LoggerEstructurado {
    +nivel : cadena
    +registrar(evento, contexto) : void
    +redactarPII(mensaje) : cadena
  }
}

' ═══════════════════════════════════════
'  PUERTA DE ENLACE Y CONTROL DE ACCESO
' ═══════════════════════════════════════
package "Puerta de Enlace y Control de Acceso" #FFCCBC {
  class FiltroCORS {
    +dominiosPermitidos : cadena[]
    +permitirCredenciales : Booleano
  }
  class FiltroCSRF {
    +validarToken(token, cookie) : booleano
  }
  class LimitadorTasa {
    -redis : DB_CACHE
    +permitir(ip, usuario, endpoint) : booleano
  }
  class InyectarCabecerasSeguridad {
    +aplicar(respuesta) : void
  }
  class SanitizadorErrores {
    +sanitizar(excepcion, entorno) : Mapa
  }
  class PuertaEnlaceAPI {
    +enrutar(solicitud) : Respuesta
  }
  class ServicioAutenticación {
    +autenticarJWT(token) : Usuario
    +refrescarToken(refresh) : Token
  }
  class ServicioAplicaciónPermisos {
    +aplicar(usuario, recurso, acción) : Booleano
  }
}

' ═══════════════════════════════════════
'  SISTEMA DE ORIENTACIÓN Y PLANTILLAS
' ═══════════════════════════════════════
package "Sistema de Orientación y Plantillas" #FFF8E1 {
  class SistemaDeOrientación {
    +singleton : SistemaDeOrientación
    +urlBaseCMS : cadena
    +urlRegistroDePlantillas : cadena
    --
    +obtenerProveedor(capa : TipoDeCapaDeOrientación) : IProveedorDeOrientación
    +observarEventoDeEstado(evento : cadena) : void
    +cargarPaqueteDePlantilla(tipo : TipoDePlantilla) : IPlantillaMetodológica
  }
  abstract class PlantillaMetodológica implements IPlantillaMetodológica {
    +id : UUID
    +tipo : TipoDePlantilla
    +versión : cadena
    +metadatosDeAutor : cadena
    +hashDeFirma : cadena
    +referenciasBibliográficasIncrustadas : cadena[]
    --
    +validar() : booleano
    +esCompatibleConRuta(r : RutaDeCodificación) : booleano
  }
  class PlantillaGTClásica extends PlantillaMetodológica
  class PlantillaGTConstructivista extends PlantillaMetodológica
  class PlantillaAnálisisSituacional extends PlantillaMetodológica
  abstract class PlantillaAnálisisDiscurso extends PlantillaMetodológica
  class PlantillaADFoucaultiano extends PlantillaAnálisisDiscurso
  class PlantillaACD extends PlantillaAnálisisDiscurso
  class PlantillaADRetórico extends PlantillaAnálisisDiscurso
  class PlantillaIPA extends PlantillaMetodológica
  class PlantillaAnálisisNarrativo extends PlantillaMetodológica
  class PlantillaMétodosMixtos extends PlantillaMetodológica
  class Tutorial {
    +id : UUID; +claveDeFase : cadena; +título : cadena
    +contenido : cadena; +justificaciónMetodológica : cadena
    +erroresComunes : cadena[]; +excepciónSeleccionada : cadena
    +ejemploDeLiteratura : cadena; +últimaActualización : DateTime
  }
  class TooltipDeOrientación {
    +claveDeContexto : cadena; +textoCorto : cadena
    +idTutorialRelacionado : UUID; +idNodoDeLienzoVinculado : UUID
  }
  class TarjetaPrimariaDeFase {
    +idDeFase : cadena; +titular : cadena
    +quéSucede : cadena; +decisionesClave : cadena[]
    +cuándoDesviarse : cadena; +estáDescartada : Booleano
  }
  class SesiónDelAsistenteDeInvestigación {
    +id : UUID; +idProyecto : UUID; +idUsuario : UUID
    +instantáneaDeContexto : cadena; +registroDeInteracciones : Objeto[]
    +idsDeMemosReflexivos : UUID[]
    --
    +preguntar(pregunta : cadena) : cadena
    +explicarNodo(idNodo : UUID) : cadena
    +proponerMemo(idCategoría : UUID) : Memo
    +resaltarNodoDelLienzo(idNodo : UUID) : void
  }
}

' ═══════════════════════════════════════
'  LIENZO DEL PLAN DE ANÁLISIS
' ═══════════════════════════════════════
package "Lienzo del Plan de Análisis" #FFFDE7 {
  class LienzoDelPlanDeAnálisis {
    +id : UUID; +idProyecto : UUID
    +versiónDelLienzo : Entero; +estáBloqueado : Booleano
    +últimaModificación : DateTime
    --
    +agregarNodo(n : NodoDeLienzo) : void
    +conectar(idOrigen : UUID, idDestino : UUID, tipoDeBorde : cadena) : void
    +cargarPlantilla(t : IPlantillaMetodológica) : void
    +validarTopología() : ResultadoDeValidación
    +exportarComoDiagramaMetodológico(formato : cadena) : ExportaciónDeLienzo
    +convertirAEspecificaciónDeEjecución() : EspecificaciónDeEjecución
  }
  class NodoDeLienzo {
    +id : UUID; +tipo : TipoDeNodoDeLienzo; +etiqueta : cadena
    +estado : EstadoDeNodoDeLienzo; +posX : Flotante; +posY : Flotante
    +parámetrosDeConfiguración : Mapa; +idDeFaseAsociada : cadena
    +claveTooltipDeOrientación : cadena; +idTutorial : UUID
    +esObligatorio : Booleano; +esPersonalizado : Booleano
    --
    +configurar(parámetros : Mapa) : void
    +omitir(razón : cadena) : void
    +obtenerInsigniaDeEstado() : cadena
  }
  class BordeDeLienzo {
    +id : UUID; +idNodoOrigen : UUID; +idNodoDestino : UUID
    +tipoDeDato : cadena; +esCondicional : Booleano
    +expresiónCondicional : cadena; +etiqueta : cadena
  }
  class ExportaciónDeLienzo {
    +id : UUID; +formato : cadena
    +contenido : Objeto; +generadoEn : DateTime
    +estáListoParaPublicación : Booleano
  }
  class EspecificaciónDeEjecución {
    +idsDeFaseOrdenados : cadena[]
    +idsDeFaseOmitidos : cadena[]
    +ramasCondicionales : Mapa
    +sobrescriturasDeRosterDeAgentes : Mapa
  }
}

' ═══════════════════════════════════════
'  CONFIGURACIÓN DEL PROYECTO
'  [v6] ConfiguraciónDeSaturaciónGlobal añadida (§2.2)
' ═══════════════════════════════════════
package "Configuración del Proyecto" #EDE7F6 {
  class Proyecto {
    +id : UUID; +nombre : cadena
    +rutaDeCodificación : RutaDeCodificación; +estado : cadena
    +creadoEn : DateTime; +tipoDePlantillaActiva : TipoDePlantilla
    --
    +seleccionarRuta(ruta); +activar()
    +asignarColaborador(usuario, perfil)
    +cargarPlantilla(tipo : TipoDePlantilla) : void
    +validarDependenciasDeRuta()
  }
  class PreguntaDeInvestigación {
    +id : UUID; +texto : cadena; +tipo : TipoDePreguntaInvestigación
    +planesDeAnálisis : cadena[]; +esReformulada : Booleano
    +justificaciónDeReformulación : cadena
    --
    +reformular(nuevoTexto, justificación)
    +vincularVariable(v)
  }
  class MarcoTeórico {
    +id : UUID; +alcance : cadena; +explicaciónFalsable : cadena
    --
    +criticar(); +validar()
  }
  class Constructo {
    +id : UUID; +nombre : cadena
    +definición : cadena; +operacionalización : cadena
    +idsDeConstructosRelacionados : UUID[]
  }
  class GrupoDeVariables {
    +id : UUID; +esDinámico : Booleano = true
    --
    +agregarVariable(v); +anotarCambio(nota)
    +vincularACategoría(v, c); +agregarNotaReflexiva(nota)
  }
  class Variable {
    +id : UUID; +nombre : cadena; +fuente : cadena
    +tipo : cadena; +derivadaDe : cadena
    +estáBinarizada : Booleano; +reglaDeBinarización : cadena
  }
  class NotaReflexivaDeGrupoDeVariables {
    +id : UUID; +eventoDesencadenante : cadena; +idCategoría : UUID
    +nota : cadena; +conectaAVariable : Booleano; +marcaDeTiempo : DateTime
  }
  class ConfiguraciónDePruebaDeHipótesis {
    +nDocsMin : Entero = 3; +porcentajeMínimoCorpus : Flotante = 0.20
    +umbralDeFuerza : Flotante = 0.70
    +porcentajeMáximoContraejemplo : Flotante = 0.10
    +máximoCandidatos : Entero = 20
    +umbralDeEjemploCompartidoDeFusión : Flotante = 0.80
  }
  ' ── [v6] NUEVA CLASE §2.2 ─────────────────────────────
  class ConfiguraciónDeSaturaciónGlobal {
    ' Umbrales por tipo de entidad (Tabla 1 del documento)
    +umbralIncidente : Entero = 3
    +umbralCategoría : Entero = 3
    +umbralRelación : Entero = 5
    +umbralFaseSelectiva : Entero = 5
    +umbralGlobal : Entero = 3
    +guardiaGlobalBucle : Entero = 20
    ' Guardia de iteraciones globales por fase
    +máxIteracionesGlobalPorFase : Entero = 100
    +iteracionesActualesPorFase : Mapa
    ' Condición compuesta para Fase 5b:
    ' todasCategoríasRelevancia≥4 saturadas
    ' AND todas relaciones postuladas saturadas
    +condiciónTerminaciónFase5b : cadena
    --
    +esFaseSaturada(idFase : cadena) : Booleano
    +registrarIteración(idFase : cadena) : void
    +verificarGuardiaGlobal(idFase : cadena) : Booleano
    +resetearContadorFase(idFase : cadena) : void
  }
  ' ──────────────────────────────────────────────────────
  class InterésAbductivo {
    +id : UUID; +tipo : TipoDeInterésAbductivo
    +descripción : cadena; +textoDefinidoPorInvestigador : cadena
    --
    +validar()
  }
  class PlanDeSuscripción {
    +tipo : TipoPlanSuscripción
    +limiteMensualTokens : Entero
    +precioMensualCentavos : Entero
  }
}

' ═══════════════════════════════════════
'  SERVICIO DE BIBLIOGRAFÍA
' ═══════════════════════════════════════
package "Servicio de Bibliografía" #F3E5F5 {
  class ReferenciaBibliográfica {
    +id : UUID; +claveBibTeX : cadena; +título : cadena
    +autores : cadena[]; +año : Entero
    +rutaPDF : cadena; +seUsaComoDato : Booleano
  }
  class ÍndiceRAGBibliográfico {
    +nombreDelÍndice : cadena; +dimensiónDeVector : Entero
    --
    +consultar(texto, topK) : ReferenciaBibliográfica[]
    +insertar(ref)
  }
}

' ═══════════════════════════════════════
'  CORPUS
' ═══════════════════════════════════════
package "Corpus" #E8F5E9 {
  class Documento {
    +id : UUID; +título : cadena; +tipoDeFuente : TipoDeFuente
    +textoCrudo : cadena; +textoLimpio : cadena; +paráfrasis : cadena
    +tipoDeTranscripción : cadena; +interlocutoresSeparados : Booleano
    +estrategiaDeVolumenDeTokens : EstrategiaDeVolumenDeTokens
    +marcasDelModerador : cadena[]; +etiquetasDeSensibilidad : cadena[]
    +idLoteDeProcesamiento : UUID
    +urlS3 : cadena
    --
    +anonimizar(); +generarÍndiceEstructural(); +generarParáfrasis()
  }
  class ÍndiceEstructuralDeDocumento {
    +secciones : Mapa; +etiquetasDePreguntas : Mapa
    +idsDeTurnosDeEntrevistador : UUID[]; +idsDeTurnosDeParticipante : UUID[]
  }
  class MetadatosDeDocumento {
    +etiquetasDeCategoría : cadena[]; +resumenIA : cadena
    +estadoDeInclusión : cadena; +idPreguntaInvestigaciónPrimaria : UUID
    +puntajeDeProfundidadContextual : cadena
  }
  class InformeDeAdecuaciónDeDocumento {
    +idsPreguntasInvestigaciónMejorAjustadas : UUID[]; +profundidadContextual : cadena
    +preguntasContrafácticas : cadena[]
    +posicionamientosEmergentes : cadena[]
    +tipologíasEmergentes : cadena[]
    +metáforasEmergentes : cadena[]
    +sugerenciasDeMemo : UUID[]
  }
  class InformeDeCríticaDeDocumento {
    +análisisDeSesgo : cadena; +intertextualidad : cadena
    +relacionesDeActores : cadena; +coherenciaEntreDocumentos : cadena
    +mensajeReflexivo : cadena; +mapaGlaserDeSegmentos : Mapa
    +sugerenciasDeMemo : UUID[]
  }
  class MotorPrimario {
    +id : UUID; +descripción : cadena
    +idDocumento : UUID; +idSegmento : UUID; +tipo : cadena
  }
  class SugerenciaDeAnotación {
    +referenciaDePasaje : UUID; +tipoDeMemoSugerido : TipoDeMemo
    +razón : cadena; +aceptada : Booleano; +aceptadaPorIdUsuario : UUID
  }
   class Segmento {
    +id : UUID; +texto : cadena; +textoEnmascarado : cadena
    +paráfrasis : cadena; +posición : Entero
    +tipoGlaser : TipoDeDatoGlaser
    +pesoDeDiferenciación : Flotante; +pesoDeAyuda : Flotante
    +esResiduo : Booleano; +contieneDatosPersonales : Booleano
    +conteoDeTokens : Entero; +esAnomalía : Booleano
    +notaDePreservaciónDeAnomalía : cadena
    ' [v7] vector de embeddings para búsqueda semántica (pgvector)
    +embedding : vector(1536)
    --
    +enriquecer(); +marcarComoResiduo(); +obtenerEnmascarado(política) : cadena
    +marcarComoAnomalía(nota : cadena) : void
  }
  ' resto de clases (Oración, BufferDeResiduos, etc.) igual que v6
}

  class Oración { +id : UUID; +texto : cadena; +conteoDeTokens : Entero }
  class BufferDeResiduos {
    +tamañoMáximo : Entero = 500; +umbralDeArchivo : Entero = 500
    --
    +agregar(s); +reclasificar(s, maxIntentos : Entero = 3)
    +archivar(); +purgarExceso()
  }
  class EscánerMalware {
    +clamAVHost : cadena
    +reglasYARA : cadena[]
    +analizar(archivoBinario) : ResultadoMalware
    +ponerEnCuarentena(idDocumento) : void
  }
  class SanitizadorArchivos {
    +validarMagicBytes(archivo, tipoDeclarado) : booleano
    +eliminarMetadatos(archivo) : archivoLimpio
    +limitarTamaño(tamañoMaxMb) : booleano
  }
}

' ═══════════════════════════════════════
'  ANÁLISIS NLP
' ═══════════════════════════════════════
package "Análisis NLP" #FFF3E0 {
  class CachéDeIncrustacionesCompartidas {
    +versiónDelCaché : Entero
    +dimensiónDeVector : Entero
    +conteoDeAciertos : Entero; +conteoDeFallos : Entero
    --
    +obtenerOCalcular(idSegmento : UUID) : Flotante[]
    +invalidar(idSegmento : UUID) : void
    +cargaMasiva(idsSegmento : UUID[]) : Mapa
  }
  class AnálisisReinert implements IMóduloNLP {
    +id : UUID; +idEjecución : UUID; +versión : Entero
    --
    +ejecutarAnálisis(); +obtenerClasePorPalabra(palabra) : ClaseReinert
  }
  class InformeLexicométrico {
    +datosDiagramaVenn : Objeto; +datosPersistenciaDeClústeres : Objeto
    +datosGráficoDeSedimentación : Objeto; +datosComparaciónInterclase : Objeto
    +matrizDeTransiciónDiscursiva : Objeto; +datosConfusiónSemántica : Objeto
    --
    +generar()
  }
  class ClaseReinert {
    +idDeClase : Entero; +palabras : cadena[]
    +conteoUC : Entero; +conteoUCE : Entero
    +distribuciónPorDocumento : Mapa; +transicionesDiscursivas : cadena[]
  }
  class InformeDeSíntesisDeClase {
    +idClaseReinert : Entero; +resumenLéxico : cadena
    +resumenSemántico : cadena; +resumenSociolingüístico : cadena
    +puntajeDeCalidad : Flotante; +generadoEn : DateTime
  }
  class ResultadoBERTopic implements IMóduloNLP {
    +idTema : Entero; +palabras : cadena[]
    +pesos : Flotante[]; +idEjecución : UUID; +versión : Entero
  }
  class ResultadoDeIncrustación {
    +id : UUID; +tipoDeEntidad : cadena
    +vector : Flotante[]; +coordsReducidas : Flotante[]; +versión : Entero
    +provieneDeCaché : Booleano
  }
  class InformeSociolingüístico {
    +ordenDeVariablesRF_SHAP : cadena[]; +coordenadasMCA : Objeto
    +prediccionesDeVariables : Objeto; +datosDeCalidadML : Objeto
    --
    +priorizarVariables() : cadena[]
  }
  class ResultadoRF_SHAP implements IMóduloNLP {
    +importanciasDeVariables : Mapa; +versión : Entero
    --
    +ejecutarSelección()
  }
  class ResultadoMCA implements IMóduloNLP {
    +dimensiones : Mapa; +coordenadas : Mapa; +versión : Entero
  }
  class ResultadoKWIC { +término : cadena; +aciertos : cadena[]; +referenciasDeSegmento : UUID[] }
  class ResultadoNER { +entidades : Mapa; +idSegmento : UUID }
  class FiguraRetórica { +tipo : cadena; +ejemplo : cadena; +idClase : Entero }
  class IncrustadorONNX implements IMóduloNLP {
    +rutaModeloONNX : cadena
    +hashSHA : cadena
    +dimensiónVector : Entero = 1024
    +ejecutar(corpus, config) : ResultadoVersionado
    +cargarModeloOffline() : void
  }
}

' ═══════════════════════════════════════
'  SISTEMA DE CODIFICACIÓN
'  [v6] incidentesMotivadores añadido a RegistroDeCambioDeDiferencias (§2.9)
' ═══════════════════════════════════════
package "Sistema de Codificación" #FCE4EC {
  class Categoría {
    +id : UUID; +nombre : cadena; +definición : cadena
    +límites : cadena; +ejemplosTípicos : cadena[]
    +ejemplosAtípicos : cadena[]; +estadoDeSaturación : EstadoDeSaturación
    +puntajeDeRelevancia : Entero; +versión : Entero
    +esCentral : Booleano; +idsPreguntaInvestigaciónVinculados : UUID[]
    --
    +dividir(razón) : Categoría[]
    +refinar(propiedad); +fusionar(otra) : Categoría
    +verificarSaturación() : Booleano
    +verificarIntercambiabilidad(incidencias) : Booleano
    +obtenerResumen() : cadena
  }
  class PropiedadDeCategoría {
    +nombre : cadena; +dimensiones : cadena[]; +rangoDeValores : cadena
    +perfiles : cadena[]; +esLímite : Booleano; +esRelacional : Booleano
  }
  class AsignaciónDeCódigo {
    +id : UUID; +asignadoEn : DateTime; +confianza : Flotante
    +esReasignado : Booleano; +razónDeReasignación : cadena
    +faseDeAsignación : cadena; +asignadoPorIdUsuario : UUID
  }
  class RelaciónDeCategoría {
    +tipoDeRelación : TipoDeRelación; +h0 : cadena; +h1 : cadena
    +h1Aceptada : Booleano; +documentosConEvidencia : Entero
    +fuerza : Flotante; +conteoDeContraejemplos : Entero
    +nDocsMin : Entero; +umbralDeFuerza : Flotante
    +porcentajeMáximoContraejemplo : Flotante
    --
    +validar(); +aplicarUmbrales(config : ConfiguraciónDePruebaDeHipótesis)
  }
  class CandidatoAFusión {
    +porcentajeDeEjemploCompartido : Flotante; +puntajeDeSolapamientoSemántico : Flotante
    +frecuenciaDeCoocurrencia : Entero; +conteoDeMencionesEnMemo : Entero
    +rangoDePrioridad : Entero; +estado : cadena; +señalesDeFuente : cadena[]
  }
  class CandidatoARelación {
    +fuentes : cadena[]; +rangoDePrioridad : Entero
    +estado : cadena; +tiposDeRelaciónPropuestos : TipoDeRelación[]
    --
    +aceptar(); +rechazar()
  }
  class RastreadorDeSaturación {
    +iteracionesConsecutivas : Entero
    +umbralDeCategoría : Entero = 3
    +umbralRelacional : Entero = 5
    +maxIteraciones : Entero = 20
    +contraejemplosEncontrados : Entero
    --
    +reiniciar(razón); +incrementar(); +estáSaturado() : Booleano; +forzarRevisión()
  }
  class EventoDeBorradoDeMemoria {
    +razón : RazónDeBorradoDeMemoria; +idCategoría : UUID
    +definiciónPreservada : cadena; +declaraciónDePreocupaciónPreservada : cadena
    +marcaDeTiempo : DateTime
  }
  class BucleDeComparaciónConstante {
    +idCategoría : UUID; +idVariable : UUID
    +conteoDeIteraciones : Entero; +totalIteracionesDeFase : Entero
    +estado : cadena
    --
    +ejecutar(documentos : Documento[])
    +activarBorradoDeMemoria(); +verificarLímiteGlobal(max : Entero)
  }
  class ResultadoDeAnálisisParalelo {
    +patronesDeComportamiento : cadena; +propiedades : cadena
    +causasEstructurales : cadena; +causasContingentes : cadena
    +consecuencias : cadena; +patronesPensamientoVsAcción : cadena
    +memoSintetizado : cadena; +tablasDeVariación : Objeto
    +matricesTipológicas : Objeto
  }
  class RegistroDePreservaciónDeAnomalías {
    +id : UUID; +idsDeSegmento : UUID[]
    +razónDePreservación : cadena
    +resumenDeVozDivergente : cadena
    +notaDePerspectivaMinoritaria : cadena
    +conteoDeFusionesPrevenidas : Entero
    +marcadoParaRevisiónDelInvestigador : Booleano
    --
    +resaltar() : void
    +generarInformeDeDivergencia() : cadena
  }
  class MotorDeComparaciónSecuencial {
    +últimoIdDeIncidenteProcesado : UUID
    +índiceDeSecuencia : Entero
    +esEstricto : Booleano
    --
    +compararSiguiente(incidente, categoríasExistentes) : ResultadoDeComparación
    +aplicarSecuencia(incidentes : Objeto[]) : void
    +detectarPerspicaciaInterruptiva() : booleano
    +activarMemoSobrePerspicacia(perspicacia : cadena) : Memo
  }
  ' ── [v6] incidentesMotivadores añadido (§2.9) ─────────
  class RegistroDeCambioDeDiferencias {
    +id : UUID; +tipoDeEntidad : cadena; +idEntidad : UUID
    +parcheDeDiferencias : cadena; +resumenLegible : cadena
    +tipoDeCambio : cadena; +cambiadoPorIdUsuario : UUID
    +marcaDeTiempo : DateTime
    ' [v6] referencia a los segmentos que motivaron la decisión
    +incidentesMotivadores : UUID[]
    --
    +reconstruir(versiónObjetivo : Entero) : Objeto
  }
  class DocCode {
    +documentoId : UUID
    +codeId : UUID
    +status : cadena  -- 'presente', 'ausente', 'no_evaluado'
    +evidenceSummary : cadena
    +updatedAt : DateTime
    --
    +primaryKey (documentoId, codeId)
  }

  class CodePrototype {
    +codeId : UUID
    +segmentIds : UUID[]  -- hasta 3 segmentos ejemplares
    +updatedAt : DateTime
  }

  class CodeEmbeddingCache {
    +codeId : UUID
    +embedding : vector(1536)  -- embedding del nombre+descripción
    +updatedAt : DateTime
  }

  class CodeDocumentSummary {
    +codeId : UUID
    +documentId : UUID
    +summary : cadena  -- síntesis intra-documento
    +updatedAt : DateTime
    --
    +primaryKey (codeId, documentId)
  }

  class CodeGlobalSummary {
    +codeId : UUID
    +summary : cadena   -- síntesis inter-documento consolidada
    +version : Entero
    +updatedAt : DateTime
  }

  class Hypothesis {
    +id : UUID
    +projectId : UUID
    +codeId : UUID (opcional)
    +text : cadena
    +level : cadena  -- 'general', 'specific', 'emergent'
    +confidence : Flotante
    +status : cadena  -- 'candidate', 'accepted', 'rejected', 'modified'
    +parentHypothesisId : UUID (para árbol de pensamientos)
    +createdAt : DateTime
  }

  class HypothesisDecision {
    +id : UUID
    +hypothesisId : UUID
    +decision : cadena  -- 'accept', 'reject', 'modify'
    +rationale : cadena
    +userNotes : cadena
    +decidedAt : DateTime
  }

  class ProcessingState {
    +entityType : cadena  -- 'document', 'segment', 'code'
    +entityId : UUID
    +step : cadena       -- 'segmented', 'coded', 'synthesized', 'hypothesized'
    +completedAt : DateTime
    --
    +primaryKey (entityType, entityId, step)
  }

  class SaturationMetrics {
    +codeId : UUID
    +centroid : vector(1536)      -- embedding promedio de resúmenes recientes
    +rollingStd : Flotante
    +lastUpdated : DateTime
    +saturationStatus : cadena    -- 'unsaturated', 'saturated', 'insufficient_data'
    +documentsSinceChange : Entero
  }

  class GraphEntity {
    +id : UUID
    +projectId : UUID
    +name : cadena
    +type : cadena   -- 'person', 'concept', 'event'
    +frequency : Entero
  }

  class GraphRelation {
    +sourceId : UUID
    +targetId : UUID
    +relationType : cadena
    +strength : Flotante
    --
    +primaryKey (sourceId, targetId, relationType)
  }


  ' ──────────────────────────────────────────────────────
}

package "Procesamiento Eficiente" #E0F2F1 {
  class SemanticChunker {
    +modelName : cadena = "bert-base-multilingual-cased"
    +windowSize : Entero = 3
    +similarityThreshold : Flotante = 0.7
    --
    +segmentar(texto : cadena) : Segmento[]
    +calcularEmbeddingLote(textos : cadena[]) : vector[]
  }

  class BatchLLMProcessor {
    +batchSize : Entero = 20
    +modelEndpoint : cadena
    --
    +procesarLote(segmentos : Segmento[]) : AsignaciónDeCódigo[]
    +generarPromptEstructurado(segmentos) : cadena
    +parsearRespuesta(jsonRaw : cadena) : Mapa
  }

  class BiEncoderModel {
    +modelPath : cadena
    +threshold : Flotante = 0.85
    +cache : CodeEmbeddingCache
    --
    +codificarTexto(texto : cadena) : vector
    +codificarCódigo(codigo : Categoría) : vector
    +esEquivalente(segmento : Segmento, codigo : Categoría) : Booleano
    +buscarCódigoSimilar(segmento : Segmento, topK : Entero) : Categoría[]
  }

  class HybridVectorIndex {
    +pgvectorIndex : cadena
    +bm25Index : cadena
    +rrfK : Entero = 60
    --
    +buscar(consulta : cadena, topK : Entero) : Segmento[]
    +fusionarRankings(resultadosVector, resultadosBM25) : Segmento[]
    +actualizar(segmento : Segmento) : void
  }

  class MaterializedViewManager {
    +vistaCodeDocumentSummary : cadena
    +vistaCodeFrequency : cadena
    --
    +refrescarIncremental(tablasAfectadas : cadena[]) : void
    +refrescarCompleto(nombreVista : cadena) : void
    +programarRefresco(intervaloMinutos : Entero) : void
  }

  class IncrementalSaturationCalculator {
    +windowSize : Entero = 5
    +entropyThreshold : Flotante = 0.1
    --
    +actualizarCentroide(codeId : UUID, nuevoResumen : cadena) : void
    +calcularEntropía(codeId : UUID) : Flotante
    +evaluarSaturación(codeId : UUID) : EstadoDeSaturación
  }
}

' ═══════════════════════════════════════
'  SISTEMA DE MEMOS
' ═══════════════════════════════════════
package "Sistema de Memos" #E0F7FA {
  class BancoDeMemos {
    +id : UUID
    --
    +agregarMemo(m); +obtenerMemosPorTipo(t) : Memo[]
    +obtenerMemosPorCategoría(c) : Memo[]
    +deduplicarMemos(); +finalizarAMemosFinales() : MemosFinales
  }
  class Memo {
    +id : UUID; +tipo : TipoDeMemo; +estado : EstadoDeMemo
    +contenido : cadena; +esConfidencial : Booleano
    +idAutor : UUID; +creadoEn : DateTime
    +historialDeVersiones : Objeto; +hashDeTema : cadena
    --
    +actualizar(nuevoContenido); +marcarComo(estado : EstadoDeMemo); +establecerConfidencial(flag)
  }
  class MemosFinales { +id : UUID; --; +organizarPorTema() }
  class GrupoTemático { +id : UUID; +nombre : cadena }
}

' ═══════════════════════════════════════
'  TALLER DE INTERPRETACIÓN
' ═══════════════════════════════════════
package "Taller de Interpretación" #E8F5FD {
  class SesiónInterpretativa {
    +id : UUID; +idProyecto : UUID
    +posturaActiva : PosturaInterpretativa; +creadoEn : DateTime
    --
    +establecerPostura(p); +aplicarGesto(tipoDeGesto, idFragmento) : GestoInterpretativo
  }
  class GestoInterpretativo {
    +tipoDeGesto : cadena; +categoríaDeGesto : cadena
    +idFragmentoObjetivo : UUID; +respuestaDelSistema : cadena
    +idMemoResultante : UUID; +marcaDeTiempo : DateTime
  }
  class AnálisisDeSilencios {
    +palabrasFaltantes : cadena[]; +combinacionesClaseTemaVacías : Objeto
    +temasNoCapturados : UUID[]; +categoríasDeBajaCentralidad : UUID[]
    +vistaJerárquica : Objeto
  }
  class SugerenciaDeExpansiónExterna {
    +nivelDeAnálisis : cadena; +fuentesSugeridas : cadena[]
    +gruposAContrastar : cadena[]; +experimentoContrafáctico : cadena
    +justificación : cadena
  }
  class InformeDeGeneralización {
    +dominiosTransferibles : Objeto; +mapaDeTérminosComparativos : Objeto
    +análisisDeSensibilidad : Objeto; +casosParalelos : Objeto
  }
}

' ═══════════════════════════════════════
'  VISUALIZACIÓN
' ═══════════════════════════════════════
package "Visualización" #FFFDE7 {
  abstract class ArtefactoDeVisualización implements IRenderizadorDeVisualización {
    +id : UUID; +título : cadena; +generadoEn : DateTime
    +idsDeCategoría : UUID[]; +idsDeVariable : UUID[]
    +{abstract} renderizar() : Objeto
  }
  class ViñetaNarrativa { +estilo : cadena; +modoPoético : Booleano }
  class MapaRadialDeDistribución { +idCategoríaCentral : UUID }
  class VisualizaciónDeLíneaDeTiempo { +campoTemporal : cadena }
  class DiagramaDeProceso { +pasos : cadena[]; +esInductivo : Booleano }
  class GrafoDeCoocurrencia { +campoDePesoDeBorde : cadena; +filtrarPorVariable : UUID }
  class DiagramaSankey { +secuenciaDeFlujo : cadena[] }
  class DendrogramaDeClústeres { +nClústeres : Entero; +guardadoComoVariable : Booleano }
  class ResultadoDeTablaCruzada {
    +variables : cadena[]; +valorChiCuadrado : Flotante
    +pValor : Flotante; +interpretaciónEnLenguajeClaro : cadena
  }
  class MapaDePosiciones {
    +etiquetaEjeX : cadena; +etiquetaEjeY : cadena; +terceraVariable : cadena
  }
}

' ═══════════════════════════════════════
'  CAPA DE ARQUITECTURA DE IA
'  [v6] RegistroEjecuciónAgente añadido (§2.5)
' ═══════════════════════════════════════
package "Capa de Arquitectura de IA" #FFE0B2 {
  class AgenteCoordinador implements IAgente {
    +id : cadena; +intenciónEstratégica : cadena
    +objetivoDeFaseActual : cadena
    +registroDeCoherenciaEntreAgentes : Objeto[]
    --
    +evaluarProgresoDeFase() : cadena
    +resolverConflictoEntreAgentes(salidas : Objeto[]) : Objeto
    +establecerEstrategiaDeDelegación(estrategia : cadena) : void
  }
  class AgenteDelegador implements IAgente {
    +id : cadena; +registroDeAgentes : Mapa
    +cargaActual : Mapa
    --
    +enrutarTarea(tarea : TareaDeAgente) : cadena
    +seleccionarAgente(etiquetaDeCapacidad : cadena, nivel : NivelDeModelo) : IAgente
    +rebalancearCarga() : void
    +registrarAgente(a : IAgente) : void
  }
  class AgenteCrítico implements IAgente {
    +id : cadena; +historialDeVeredictos : VeredictoDelCrítico[]
    +maxCiclosDeRevisión : Entero = 3
    --
    +evaluar(salida : Objeto, contexto : ContextoDeAgente) : VeredictoDelCrítico
    +identificarAlucinaciones(texto : cadena) : cadena[]
    +verificarRestriccionesMetodológicas(salida : Objeto) : cadena[]
    +solicitarRevisión(idProductor : cadena, retroalimentación : cadena) : void
  }
  class AgenteEnrutador implements IAgente {
    +id : cadena; +tablaDeEnrutamiento : Mapa
    --
    +clasificarTarea(tarea : TareaDeAgente) : NivelDeModelo
    +despachar(tarea : TareaDeAgente, nivel : NivelDeModelo) : Objeto
    +obtenerEndpointModeloRápido() : cadena
    +obtenerEndpointModeloPotente() : cadena
  }
  class BucleGeneradorCrítico {
    +id : UUID; +idProductor : cadena; +idCrítico : cadena
    +maxCiclos : Entero = 3; +cicloActual : Entero
    +veredictoFinal : VeredictoDelCrítico
    --
    +ejecutar(tarea : TareaDeAgente) : Objeto
    +estáCompleto() : booleano
    +escalarAInvestigador(razón : cadena) : void
  }
  class AplicadorDePolíticasIA {
    +id : UUID; +reglasActivas : cadena[]
    --
    +examinar(salidaDeAgente : Objeto) : ResultadoDePolítica
    +verificarAntiAlucinación(texto : cadena) : booleano
    +verificarRestriccionesÉticas(texto : cadena) : booleano
    +verificarPrivacidadDeDatos(texto : cadena) : booleano
    +bloquearYMarcar(salida : Objeto, razón : cadena) : void
  }
  class ConfiguraciónDeEnrutamientoDeModelos {
    +endpointModeloRápido : cadena; +endpointModeloEquilibrado : cadena
    +endpointModeloPotente : cadena
    +reglasTareaANivel : Mapa
    +presupuestoDeCostoUsdPorSesión : Flotante
    +costoDeSesiónActual : Flotante
  }
  class ConstructorDeContextoDeAgente {
    +presupuestoMaxTokens : Entero = 4000
    --
    +construirPara(idAgente : cadena, idFase : cadena) : ContextoDeAgente
    +inyectarContextoRodante(rcwm : Objeto) : void
    +inyectarDefinicionesDeCategoría(gatos : Categoría[]) : void
    +inyectarPreocupaciónPrincipal(preocupación : cadena) : void
    +estimarConteoDeTokens(ctx : ContextoDeAgente) : Entero
  }
  class ContextoDeAgente {
    +resumenDeContextoRodante : cadena
    +definicionesDeCategoría : cadena
    +declaraciónDePreocupaciónPrincipal : cadena
    +instrucciónDeFase : cadena
    +conteoDeTokensEstimado : Entero
  }
  class Anti_RepeticiónDeBuclesDeRetroalimentación {
    +períodoDeEnfriamientoMs : Entero = 30000
    +mapaDeÚltimoDisparo : Mapa
    --
    +debeDisparar(idBucle : cadena) : booleano
    +registrarDisparo(idBucle : cadena) : void
    +reiniciar(idBucle : cadena) : void
  }
  class EjecutorPorLotesDeAPI {
    +tamañoDeLote : Entero = 10
    +tareasPendientes : TareaDeAgente[]
    --
    +encolar(tarea : TareaDeAgente) : void
    +vaciarLote() : Objeto[]
    +agruparPorNivelDeModelo() : Mapa
  }
  class ProxyLiteLLM implements ILLMClient {
    -proveedores : cadena[]
    -timeoutSegundos : Entero = 30
    -maxReintentos : Entero = 3
    +generar(mensajes, modelo, opciones) : RespuestaLLM
    -fallback(proveedorFallido) : void
  }
  class GestorVersionesModelo {
    -tablaVersiones : DB_MODEL_VER
    +hashAutorizado(tipoModelo, nombreModelo) : cadena
    +validarHash(modeloReal, hashEsperado) : booleano
    +alertarDiscrepancia(hashObtenido, hashEsperado) : void
  }
  class DetectorInyeccionPrompt {
    -patrones : cadena[]
    -normalizadorUnicode : Normalizador
    +analizar(texto) : RiesgoPrompt
    +sanitizar(texto) : cadena
  }
  ' ── [v6] NUEVA CLASE §2.5 ─────────────────────────────
  class RegistroEjecuciónAgente {
    ' Trazabilidad completa por cada invocación de agente
    +id : UUID
    +idAgente : cadena
    +idFase : cadena
    +versiónPrompt : cadena
    +modeloLLMUtilizado : cadena
    +proveedorLLM : cadena
    +hashEntrada : cadena
    +hashSalida : cadena
    +fecha : DateTime
    +costoTokensUsd : Flotante
    +veredictoDelCrítico : VeredictoDelCrítico
    --
    +reconstruirTrazabilidad() : cadena
  }
  ' ──────────────────────────────────────────────────────
}

' ═══════════════════════════════════════
'  FLUJO DE TRABAJO Y AGENTES
' ═══════════════════════════════════════
package "Flujo de Trabajo y Agentes" #EFEBE9 {
  class OrquestadorDeFlujoDeTrabajo {
    +id : UUID
    --
    +avanzar(); +activarRetroalimentación(evento)
    +leerEspecificaciónDeEjecución(espec : EspecificaciónDeEjecución) : void
    +notificarInvestigador(msg)
  }
  class AdministradorDeVentanaDeContextoRodante {
    +tamañoDeVentana : Entero = 3
    +idsDeDocumentoActuales : UUID[]
    +resumenAcumulado : cadena
    --
    +refrescar(nuevoIdDoc); +obtenerContexto() : cadena; +almacenarEnBancoDeMemos()
  }
  class Fase {
    +id : UUID; +número : cadena; +nombre : cadena; +estado : cadena
    --
    +iniciar(); +completar(); +estáCompleta() : Booleano
  }
  class BucleDeRetroalimentación {
    +id : UUID; +eventoDesencadenante : cadena
    +númeroDeFaseFuente : cadena; +númeroDeFaseDestino : cadena
    +acciónAutomática : cadena; +requiereConfirmación : Booleano
    --
    +ejecutar()
  }
  class PlanDeMuestreo {
    +estrategia : cadena; +reglaDeBinarización : cadena
    +casosContraste : UUID[]; +casosExtremos : UUID[]; +casosConsistentes : UUID[]
  }
  ' Subclases concretas de Agente (implementan IAgente)
  class CodificadorAbierto implements IAgente
  class Resegmentador implements IAgente
  class AgrupadorDocumento implements IAgente
  class AgrupadorInterDocumento implements IAgente
  class ProponenteDeMemo implements IAgente
  class ProbadorDeMemo implements IAgente
  class AgrupadorGeneral implements IAgente
  class ConsolidadorDeHipótesis implements IAgente
  class AgenteReCodificador implements IAgente
  class AgenteLibroDeCódigosDeVariables implements IAgente
  class AgenteAgrupadorDePerspicacias implements IAgente
  class AgenteDeAgrupamientoTemático implements IAgente
  class AgenteDePruebaDeHipótesis implements IAgente
  class SensorDePreocupaciónPrincipal implements IAgente
  class DetectorDeEmergenciaCentral implements IAgente
  class ProbadorDeIntercambiabilidad implements IAgente
  class MuestreadorTeórico implements IAgente
  class ComparadorDeDocumentos implements IAgente
  class DetectadorDeVacíos implements IAgente
  class EscritorNatural implements IAgente
  class AgenteDeOrdenamiento implements IAgente
  class ComparadorDeLiteratura implements IAgente
  class SintetizadorDeMemos implements IAgente
  class ExtractorRetórico implements IAgente
  class AgenteMultiSintetizador implements IAgente
  class RecomendadorDeRelaciones implements IAgente
  class PreservadorDeAnomalías implements IAgente
}

' ═══════════════════════════════════════
'  WORKERS ASÍNCRONOS
' ═══════════════════════════════════════
package "Workers Asíncronos (Celery)" #FFFACD {
  class CeleryApp {
    +taskSerializer : cadena = "json"
    +resultSerializer : cadena = "json"
    +acceptContent : cadena[] = ["json"]
    +enviarTarea(tipo, payload, firma) : cadena
  }
  class TareaDocumento {
    +id : UUID
    +tipo : cadena
    +estado : EstadoTareaCelery
    +ejecutar() : Resultado
  }
  class NotificadorWebSocket {
    +enviar(usuarioId, evento, datos) : void
  }
  class RegistroIdempotenciaTarea {
    +taskId : cadena
    +createdAt : DateTime
    +tipoTarea : cadena
    +estado : EstadoTareaCelery
  }
}

' ═══════════════════════════════════════
'  INFRAESTRUCTURA DE BD
' ═══════════════════════════════════════
package "Infraestructura de Conexión BD" #F0FFF0 {
  class PgBouncerPool {
    +modoTransacción : Booleano
    +autenticación : cadena = "scram-sha-256"
    +limiteConexionesPorServicio : Entero
    +obtenerPool() : Pool
  }
}

' ═══════════════════════════════════════
'  SALIDA Y REDACCIÓN
' ═══════════════════════════════════════
package "Salida y Redacción" #F3E5F5 {
  class RegistroDeOrdenamiento { +id : UUID; --; +generar(familia : FamiliaDeOrdenamiento) }
  class IteraciónDeOrdenamiento {
    +familia : FamiliaDeOrdenamiento; +memoResultante : cadena
    +idsDeMemoSinHogar : UUID[]; +pilasDelgadas : UUID[]; +marcaDeTiempo : DateTime
  }
  class GrupoTeórico {
    +etiqueta : cadena; +justificación : cadena
    +esEstable : Booleano; +apareceEnFamilias : FamiliaDeOrdenamiento[]
  }
  class RegistroDeVacío {
    +descripción : cadena; +tipoDeVacío : cadena
    +esInterno : Booleano; +resolución : cadena
  }
  class ReglaDeRedacción {
    +códigoDeRegla : cadena; +nombre : cadena
    +descripción : cadena; +estáActiva : Booleano
  }
  class Informe {
    +id : UUID; +audiencia : cadena; +objetivo : cadena
    +esqueletoNarrativo : EsqueletoNarrativo
    +personaDeRedacción : cadena; +enfoqueDeEstilo : cadena
    --
    +generar(); +aplicarFiltroDeEstilo(); +aplicarReglasDeRedacción(); +exportarComo(formato)
  }
  class SecciónDeInforme {
    +título : cadena; +contenido : cadena
    +tieneVacíoDeEvidencia : Booleano; +afirmacionesNoSoportadas : cadena[]
  }
  class InformeDeLíneasFuturas {
    +vacíosDetectados : cadena[]; +preguntasInvestigaciónPropuestas : cadena[]
    +sugerenciasMetodológicas : cadena[]; +ordenDePrioridad : cadena[]
  }
  class InformeDeAuditabilidad {
    +listaVerificaciónCOREQ : Mapa; +listaVerificaciónLincolnGuba : Mapa
    +diagramaDeEvoluciónDeCategorías : Objeto; +respuestasReflexivas : Objeto
    +decisionesDocumentadas : Entero; +generadoEn : DateTime
  }
}

' ═══════════════════════════════════════
'  AUDITORÍA Y LOGS INMUTABLES
' ═══════════════════════════════════════
package "Auditoría y Logs Inmutables" #F5F5F5 {
  class RegistroIdempotenciaWebhook {
    +stripeEventId : cadena
    +procesadoEn : DateTime
    +payloadJson : Objeto
  }
  class RegistroSeguridadInmutable {
    +id : UUID
    +timestamp : DateTime
    +motivo : MotivoLogSeguridad
    +hashAnterior : cadena
    +hashActual : cadena
    +detalles : Mapa
    +firmante : cadena
  }
  class VersiónModeloAutorizada {
    +tipo : TipoModelo
    +nombreModelo : cadena
    +hashSHA : cadena
    +autorizadoPor : cadena
    +fechaAutorizacion : DateTime
  }
}

' ═══════════════════════════════════════
'  RELACIONES
' ═══════════════════════════════════════

' -- Usuarios y Permisos --
Usuario "1" -- "0..1" PerfilDeEstudiante
Usuario "1" -- "0..1" PerfilDePermisoDeColaborador
Usuario "1" -- "0..1" PerfilDeAuditor
Usuario "1" -- "0..1" PerfilDeVisualizador
PerfilDePermisoDeColaborador *-- ÁmbitoDeAccesoADocumentos
PerfilDePermisoDeColaborador *-- PolíticaDeEnmascaramientoDeSegmentos
PerfilDePermisoDeColaborador *-- PolíticaDeAccesoAAnalíticas
FiltroDeAccesoADatos ..> PolíticaDeEnmascaramientoDeSegmentos
FiltroDeAccesoADatos ..> PolíticaDeAccesoAAnalíticas
Usuario --> PlanDeSuscripción

' -- Configuración del Proyecto --
Proyecto *-- "1..*" PreguntaDeInvestigación
Proyecto *-- GrupoDeVariables
Proyecto *-- BancoDeMemos
Proyecto *-- OrquestadorDeFlujoDeTrabajo
Proyecto *-- BufferDeResiduos
Proyecto o-- "0..1" MarcoTeórico                           : "omitir si CGT"
Proyecto o-- "0..1" InterésAbductivo                       : "solo CGT"
Proyecto *-- "0..1" ConfiguraciónDePruebaDeHipótesis
Proyecto --> "0..1" LienzoDelPlanDeAnálisis
Proyecto --> "0..1" PlantillaMetodológica                  : "plantillaActiva"
' [v6] §2.2 — condición de término por fase coordinada aquí
Proyecto *-- "0..1" ConfiguraciónDeSaturaciónGlobal
MarcoTeórico *-- "1..*" Constructo
MarcoTeórico o-- "0..*" ReferenciaBibliográfica
GrupoDeVariables *-- "0..*" Variable
GrupoDeVariables *-- "0..*" NotaReflexivaDeGrupoDeVariables
PreguntaDeInvestigación "0..*" -- "0..*" Variable

' -- [v6] §2.2 — ConfiguraciónDeSaturaciónGlobal coordina RastreadorDeSaturación --
ConfiguraciónDeSaturaciónGlobal --> RastreadorDeSaturación : "coordina término de fase"

' -- Sistema de Orientación --
SistemaDeOrientación --> PlantillaMetodológica             : "carga"
SistemaDeOrientación --> IProveedorDeOrientación           : "despacha"
PlantillaMetodológica ..> NodoDeLienzo                     : "puebla"
LienzoDelPlanDeAnálisis *-- "0..*" NodoDeLienzo
LienzoDelPlanDeAnálisis *-- "0..*" BordeDeLienzo
NodoDeLienzo --> "0..1" Tutorial
NodoDeLienzo --> "0..1" TooltipDeOrientación
SesiónDelAsistenteDeInvestigación --> Proyecto
SesiónDelAsistenteDeInvestigación ..> Memo                 : "puede proponer"

' -- Bibliografía --
ÍndiceRAGBibliográfico o-- "0..*" ReferenciaBibliográfica

' -- Corpus y seguridad de archivos --
Documento "1" --> "0..1" EscánerMalware                   : "pasa por"
EscánerMalware --> SanitizadorArchivos                     : "si limpio"
SanitizadorArchivos --> Documento                          : "actualiza"
Documento *-- "1..*" Segmento
Documento *-- ÍndiceEstructuralDeDocumento
Documento *-- MetadatosDeDocumento
Documento *-- "0..*" MotorPrimario
Documento o-- "0..1" InformeDeAdecuaciónDeDocumento
Documento o-- "0..1" InformeDeCríticaDeDocumento
Segmento *-- "0..*" Oración
Segmento "0..*" *-- "0..*" SugerenciaDeAnotación
BufferDeResiduos o-- "0..*" Segmento

' -- NLP --
IncrustadorONNX --> CachéDeIncrustacionesCompartidas       : "produce vectores"
CachéDeIncrustacionesCompartidas ..> ResultadoDeIncrustación
AnálisisReinert *-- "1..*" ClaseReinert
AnálisisReinert *-- InformeLexicométrico
ClaseReinert o-- "0..*" FiguraRetórica
InformeDeSíntesisDeClase "0..*" -- "1" ClaseReinert
InformeSociolingüístico *-- ResultadoRF_SHAP
InformeSociolingüístico *-- ResultadoMCA
ResultadoDeIncrustación --> CachéDeIncrustacionesCompartidas
ResultadoBERTopic --> CachéDeIncrustacionesCompartidas

' -- Codificación --
Categoría *-- "0..*" PropiedadDeCategoría
Categoría *-- RastreadorDeSaturación
Categoría *-- "0..*" EventoDeBorradoDeMemoria
AsignaciónDeCódigo --> Categoría
AsignaciónDeCódigo --> Segmento
RelaciónDeCategoría --> "1" Categoría                      : "categoríaA"
RelaciónDeCategoría --> "1" Categoría                      : "categoríaB"
RelaciónDeCategoría -- "0..1" ConfiguraciónDePruebaDeHipótesis
CandidatoAFusión --> "2" Categoría
CandidatoARelación --> "2" Categoría
BucleDeComparaciónConstante -- Categoría
BucleDeComparaciónConstante -- "0..1" Variable
BucleDeComparaciónConstante *-- "0..*" ResultadoDeAnálisisParalelo
RegistroDePreservaciónDeAnomalías "0..*" --> "0..*" Segmento
MotorDeComparaciónSecuencial ..> Categoría                 : "compara"
MotorDeComparaciónSecuencial ..> Memo                      : "activa"
RegistroDeCambioDeDiferencias ..> Categoría
RegistroDeCambioDeDiferencias ..> Memo
' [v6] §2.9 — incidentesMotivadores apuntan a segmentos concretos
RegistroDeCambioDeDiferencias "0..*" ..> "0..*" Segmento   : "incidentesMotivadores"

DocCode --> Documento : documentoId
DocCode --> Categoría : codeId
CodePrototype --> Categoría : codeId
CodeEmbeddingCache --> Categoría : codeId
CodeDocumentSummary --> Categoría : codeId
CodeDocumentSummary --> Documento : documentId
CodeGlobalSummary --> Categoría : codeId
Hypothesis --> Proyecto : projectId
Hypothesis --> Categoría : codeId (opcional)
HypothesisDecision --> Hypothesis : hypothesisId
ProcessingState --> Documento : entityId (cuando entityType='document')
ProcessingState --> Segmento : entityId (cuando entityType='segment')
ProcessingState --> Categoría : entityId (cuando entityType='code')
SaturationMetrics --> Categoría : codeId
GraphEntity --> Proyecto : projectId
GraphRelation --> GraphEntity : sourceId
GraphRelation --> GraphEntity : targetId

SemanticChunker ..> Segmento : produce
BatchLLMProcessor ..> AsignaciónDeCódigo : genera
BiEncoderModel ..> CodeEmbeddingCache : utiliza
BiEncoderModel ..> CodePrototype : referencia
HybridVectorIndex ..> Segmento : indexa
MaterializedViewManager ..> CodeDocumentSummary : refresca
IncrementalSaturationCalculator ..> SaturationMetrics : actualiza
IncrementalSaturationCalculator ..> CodeGlobalSummary : lee

' -- Memos --
BancoDeMemos *-- "0..*" Memo
Memo "0..*" -- "0..*" Categoría
Memo "0..*" -- "0..*" Segmento
Memo --> Usuario
BancoDeMemos --> MemosFinales
MemosFinales *-- "0..*" GrupoTemático
GrupoTemático o-- "0..*" Memo

' -- Interpretación --
SesiónInterpretativa *-- "0..*" GestoInterpretativo
GestoInterpretativo ..> Memo

' -- Visualización --
ArtefactoDeVisualización <|-- ViñetaNarrativa
ArtefactoDeVisualización <|-- MapaRadialDeDistribución
ArtefactoDeVisualización <|-- VisualizaciónDeLíneaDeTiempo
ArtefactoDeVisualización <|-- DiagramaDeProceso
ArtefactoDeVisualización <|-- GrafoDeCoocurrencia
ArtefactoDeVisualización <|-- DiagramaSankey
ArtefactoDeVisualización <|-- DendrogramaDeClústeres
ArtefactoDeVisualización <|-- ResultadoDeTablaCruzada
ArtefactoDeVisualización <|-- MapaDePosiciones

' -- Capa de IA --
AgenteCoordinador --> AgenteDelegador
AgenteDelegador --> IAgente
AgenteEnrutador --> ConfiguraciónDeEnrutamientoDeModelos
BucleGeneradorCrítico --> AgenteCrítico
BucleGeneradorCrítico --> IAgente                          : "productor"
AplicadorDePolíticasIA ..> Informe
ConstructorDeContextoDeAgente --> AdministradorDeVentanaDeContextoRodante
ConstructorDeContextoDeAgente --> Categoría
Anti_RepeticiónDeBuclesDeRetroalimentación --> BucleDeRetroalimentación
EjecutorPorLotesDeAPI --> IAgente
AgenteEnrutador --> ProxyLiteLLM                           : "despacha llamadas LLM"
ProxyLiteLLM --> GestorVersionesModelo                     : "valida hash"
ProxyLiteLLM --> DetectorInyeccionPrompt                   : "sanitiza entrada"
ProxyLiteLLM --> ConfiguraciónDeEnrutamientoDeModelos      : "lee umbrales"
' [v6] §2.5 — trazabilidad por ejecución de agente
BucleGeneradorCrítico --> RegistroEjecuciónAgente          : "registra veredicto"
AgenteDelegador --> RegistroEjecuciónAgente                : "registra despacho"
RegistroEjecuciónAgente ..> IAgente                        : "registra ejecución de"
RegistroEjecuciónAgente --> Fase                           : "pertenece a"
OrquestadorDeFlujoDeTrabajo *-- "0..*" RegistroEjecuciónAgente

' -- Flujo de Trabajo --
OrquestadorDeFlujoDeTrabajo *-- "1..*" Fase
OrquestadorDeFlujoDeTrabajo *-- "0..*" BucleDeRetroalimentación
OrquestadorDeFlujoDeTrabajo *-- AdministradorDeVentanaDeContextoRodante
OrquestadorDeFlujoDeTrabajo *-- AgenteCoordinador
OrquestadorDeFlujoDeTrabajo *-- AgenteDelegador
OrquestadorDeFlujoDeTrabajo *-- Anti_RepeticiónDeBuclesDeRetroalimentación
OrquestadorDeFlujoDeTrabajo --> EspecificaciónDeEjecución
BucleDeRetroalimentación --> Fase

' -- Workers --
CeleryApp --> TareaDocumento
TareaDocumento --> RegistroIdempotenciaTarea                : "registra id"
TareaDocumento --> NotificadorWebSocket                     : "notifica progreso"

' -- Salida y Redacción --
RegistroDeOrdenamiento *-- "0..*" IteraciónDeOrdenamiento
RegistroDeOrdenamiento *-- "0..*" GrupoTeórico
RegistroDeOrdenamiento o-- "0..*" RegistroDeVacío
Informe *-- "1..*" SecciónDeInforme
Informe "0..*" -- "0..*" ReglaDeRedacción
GrupoTeórico o-- "0..*" Categoría
GrupoTeórico o-- "0..*" Memo

@enduml

```

[](assets://./workspace/afd7131b-bb46-4e70-8ebc-61301c2c5c49/MEPwwTQ-dbS2cpMXuwGzE)
