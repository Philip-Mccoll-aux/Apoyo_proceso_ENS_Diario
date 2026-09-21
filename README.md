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
  extraccion_pf.py   Lee el proyecto activo de PowerFactory y arma un ModeloRed
  analisis.py        Calcula todas las hojas a partir del ModeloRed (Python puro)
  exportar_excel.py  Escribe las hojas a un .xlsx con formato básico
  config.py          Parámetros ajustables (rutas, umbrales, nombres de atributos)
scripts/
  generar_correlaciones.py   Punto de entrada: conecta a PowerFactory y orquesta todo
tests/
  test_analisis.py   Pruebas del motor de análisis con un modelo sintético
```

La separación es intencional: `extraccion_pf.py` es el único módulo que
depende de la API de PowerFactory (no se puede probar fuera de la
aplicación); todo lo demás es Python puro y está cubierto por pruebas
automatizadas.

## Cómo ejecutarlo

1. Abra su proyecto en PowerFactory y active el caso de estudio que quiere
   analizar (el script usa `GetCalcRelevantObjects`, es decir, respeta los
   elementos activos/en servicio del caso de estudio actual).
2. Revise `src/digsilent_correlaciones/config.py` y ajuste al menos
   `ruta_salida` (dónde se guardará el Excel).
3. Ejecute `scripts/generar_correlaciones.py` de una de estas dos formas:

   **Opción A — como script de PowerFactory (recomendado):**
   En el árbol del proyecto, cree un objeto `ComPython` (clic derecho en la
   carpeta "Scripts" → New → Script de Python) y en su propiedad de archivo
   apunte a `scripts/generar_correlaciones.py`. Ejecútelo con el botón de
   "Execute". El módulo `powerfactory` ya está disponible automáticamente en
   ese contexto.

   **Opción B — desde Python externo:**
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
  necesitan que las barras (o su subestación, `cpSubstat`) tengan cargados
  los atributos `GPSlat`/`GPSlon` en la página de datos básicos. Si su
  modelo usa otros nombres de atributo (p. ej. atributos de usuario),
  agréguelos a `atributos_lat`/`atributos_lon` en `config.py`.
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
