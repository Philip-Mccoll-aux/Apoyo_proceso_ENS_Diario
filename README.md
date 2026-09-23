# Correlaciones de la red desde DIgSILENT PowerFactory

Script que toma un modelo de red abierto en DIgSILENT PowerFactory y genera
un archivo Excel con una hoja por cada "correlación"/vista derivada del
modelo: grafo de conexiones eléctricas, cercanía geográfica, distancia
eléctrica, niveles de tensión, zonas/áreas, centralidad de nodos, elementos
críticos N-1 y correlación estadística entre distancia geográfica y
eléctrica.

## Estructura del proyecto

```
src/digsilent_correlaciones/
  modelo.py          Estructuras de datos (Barra, Rama, Inyección, ModeloRed)
  extraccion_pf.py   Lee el proyecto activo de PowerFactory (API en vivo) y arma un ModeloRed
  lector_dgs.py      Parsea un archivo .dgs (exportado de PowerFactory) a tablas
  extraccion_dgs.py  Arma un ModeloRed a partir de esas tablas, sin PowerFactory
  analisis.py        Calcula todas las hojas a partir del ModeloRed (Python puro)
  exportar_excel.py  Escribe las hojas a un .xlsx con formato básico
  config.py          Parámetros ajustables (rutas, umbrales, nombres de atributos)
scripts/
  generar_correlaciones.py             Punto de entrada: ejecutar dentro de PowerFactory (API en vivo)
  generar_correlaciones_desde_dgs.py   Punto de entrada: ejecutar en cualquier Python, a partir de un .dgs
tests/
  test_analisis.py         Pruebas del motor de análisis con un modelo sintético
  test_extraccion_dgs.py   Pruebas del parser DGS con un archivo .dgs sintético
```

La separación es intencional: `extraccion_pf.py` (API en vivo) y
`lector_dgs.py`/`extraccion_dgs.py` (archivo DGS) son las dos formas de
alimentar datos, y ambas producen el mismo `ModeloRed`; todo lo demás
(`analisis.py`, `exportar_excel.py`) es Python puro compartido por las dos y
está cubierto por pruebas automatizadas.

## Dos formas de ejecutarlo

**Opción 1 — Sin PowerFactory, desde un archivo DGS (recomendada si quiere
desacoplarse de la aplicación):**

1. En PowerFactory, la persona con licencia exporta el proyecto activo a
   DGS: `File → Export → DGS...` (formato ASCII), obteniendo un archivo
   `.dgs` de texto plano — mucho más liviano que el `.pfd` nativo y sin las
   limitaciones de un binario propietario.
2. Ejecute, en cualquier máquina con Python (no requiere licencia ni la
   aplicación instalada):

   ```
   python scripts/generar_correlaciones_desde_dgs.py ruta/al/modelo.dgs -o correlaciones.xlsx
   ```

Limitación a tener presente: DGS no exporta directamente R/X en Ohm para los
transformadores, sino los parámetros de placa (uk%, pérdidas de cobre,
potencia nominal); `extraccion_dgs.py` calcula una aproximación estándar de
la impedancia de cortocircuito a partir de esos datos. Es válido para
ponderar "distancia eléctrica" de forma relativa, no para un estudio de
flujo de potencia.

**Opción 2 — Dentro de PowerFactory, con la API en vivo (útil si quiere que
el Excel siempre refleje el caso de estudio activo sin exportar nada):**

1. Abra su proyecto en PowerFactory y active el caso de estudio que quiere
   analizar (el script usa `GetCalcRelevantObjects`, es decir, respeta los
   elementos activos/en servicio del caso de estudio actual).
2. Revise `src/digsilent_correlaciones/config.py` y ajuste al menos
   `ruta_salida` (dónde se guardará el Excel).
3. Ejecute `scripts/generar_correlaciones.py` de una de estas dos formas:

   **A — como script de PowerFactory (recomendado):**
   En el árbol del proyecto, cree un objeto `ComPython` (clic derecho en la
   carpeta "Scripts" → New → Script de Python) y en su propiedad de archivo
   apunte a `scripts/generar_correlaciones.py`. Ejecútelo con el botón de
   "Execute". El módulo `powerfactory` ya está disponible automáticamente en
   ese contexto.

   **B — desde Python externo:**
   Requiere que PowerFactory esté instalado en la misma máquina y con una
   licencia disponible. Antes de importar `powerfactory`, agregue al
   `sys.path` la carpeta de la API que trae la instalación, por ejemplo:

   ```python
   import sys
   sys.path.append(r"C:\Program Files\DIgSILENT\PowerFactory 2024 SP2\Python\3.11")
   ```

   (la versión exacta de Python debe coincidir con la que trae su instalación
   de PowerFactory). Luego ejecute `python scripts/generar_correlaciones.py`
   con PowerFactory abierto y el proyecto activo.

## Dependencias

Instalar en el entorno Python que va a correr el script (o el que ya trae
PowerFactory):

```
pip install -r requirements.txt
```

Para correr las pruebas (no requieren PowerFactory):

```
pip install -r requirements-dev.txt
pytest
```

## Hojas generadas

| Hoja | Contenido |
|---|---|
| `Resumen` | Conteo de barras/ramas/generadores/cargas, componentes conexas, si hay islas eléctricas |
| `Grafo_Electrico` | Listado de aristas: cada línea/transformador/interruptor con sus barras extremas, tensión, longitud, R y X |
| `Matriz_Adyacencia` | Matriz barra x barra (1 = conectadas directamente). Solo si el sistema tiene ≤ `umbral_matriz_completa` barras |
| `Cercania_Geografica` | Distancia en línea recta (haversine, km) entre barras con coordenadas GPS. Matriz completa en sistemas pequeños; lista de los N vecinos más cercanos por barra en sistemas grandes |
| `Distancia_Electrica` | Distancia mínima por el grafo (ruta más corta ponderada por reactancia o longitud, configurable) |
| `Niveles_Tension` | Cantidad de barras y ramas por nivel de tensión nominal |
| `Zonas_Areas` | Generación, carga y balance MW por zona/área eléctrica |
| `Centralidad_Nodos` | Grado, centralidad de intermediación, centralidad de cercanía y si la barra es punto de articulación (N-1) |
| `Elementos_Criticos_N1` | Ramas cuya sola salida de servicio deja dos partes de la red incomunicadas |
| `Correlaciones_Estadisticas` | Correlación de Pearson entre distancia geográfica, distancia eléctrica y número de saltos, calculada sobre pares de barras con GPS |

## Requisitos de datos en el modelo

- **Coordenadas GPS**: la hoja de cercanía geográfica y la de correlaciones
  necesitan que las barras (o su subestación) tengan cargados los atributos
  `GPSlat`/`GPSlon`. Si su modelo usa otros nombres de atributo (p. ej.
  atributos de usuario), agréguelos a `atributos_lat`/`atributos_lon` en
  `config.py`. Si usa la Opción 1 (DGS), además debe seleccionar esos campos
  al armar la definición de exportación en PowerFactory — DGS solo exporta
  las columnas que uno elige incluir por clase.
- **Zona/Área**: se busca en `cpZone`/`cpArea`; ajuste `config.py` si su
  modelo usa una convención distinta.
- Los transformadores de 3 devanados se representan internamente como 3
  ramas hacia un nodo "estrella" ficticio, igual que hace PowerFactory.

## Ajustar el tamaño de las matrices

Para sistemas grandes, una matriz N×N deja de ser práctica en Excel. Por
defecto, si el sistema supera `umbral_matriz_completa` barras (200 por
defecto), las hojas de adyacencia y de distancias pasan automáticamente a un
formato de "top-N vecinos más cercanos" (`num_vecinos_cercanos`, 10 por
defecto) en vez de la matriz completa.
