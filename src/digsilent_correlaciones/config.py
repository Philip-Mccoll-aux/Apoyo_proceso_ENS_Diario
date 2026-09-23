"""Parámetros ajustables sin tocar la lógica de extracción/análisis.

Los nombres de atributos de PowerFactory pueden variar levemente entre
versiones o entre modelos que usan atributos de usuario. Si la extracción no
encuentra coordenadas o impedancias, revise primero esta lista.
"""

CONFIG = {
    # Ruta del archivo Excel de salida.
    "ruta_salida": r"C:\Temp\correlaciones_red.xlsx",

    # Si es True, ignora elementos fuera de servicio (outserv=1) al construir
    # el grafo y todas las hojas derivadas de él.
    "solo_en_servicio": True,

    # Nombres candidatos de atributos de coordenadas GPS, en orden de
    # preferencia. Se buscan primero en la barra/terminal y, si no están,
    # en la subestación a la que pertenece.
    "atributos_lat": ["GPSlat", "e:GPSlat"],
    "atributos_lon": ["GPSlon", "e:GPSlon"],

    # Nombres candidatos para zona/área eléctrica.
    "atributos_zona": ["cpZone", "cpArea"],
    "atributos_area": ["cpArea", "cpZone"],

    # Por encima de este número de barras, las hojas de matriz completa
    # (adyacencia, distancia geográfica, distancia eléctrica) se reemplazan
    # por listados de "vecinos más cercanos" para no generar hojas de Excel
    # gigantes ni cálculos O(N^2) impracticables.
    "umbral_matriz_completa": 200,

    # Número de vecinos más cercanos a listar cuando se supera el umbral.
    "num_vecinos_cercanos": 10,

    # Por encima de este número de barras, los cálculos "todos contra todos"
    # sobre el grafo (distancia eléctrica, correlaciones, centralidad de
    # intermediación) dejan de ser exactos y pasan a estimarse sobre una
    # muestra aleatoria de nodos, para que el tiempo de cómputo no crezca
    # sin límite con el tamaño de la red (una red nacional puede tener
    # decenas de miles de barras). La cercanía geográfica no se ve afectada:
    # se calcula siempre de forma exacta con un árbol espacial (KD-tree).
    "umbral_analisis_pesado": 3000,

    # Cuántos nodos muestrear cuando se supera "umbral_analisis_pesado".
    "tamano_muestra_redes_grandes": 500,

    # Semilla para que el muestreo aleatorio sea reproducible.
    "semilla_muestreo": 42,

    # Atributo usado como peso de "distancia eléctrica": "longitud_km" o
    # "x_ohm". Si el elemento no tiene el atributo elegido, se usa 1.0 como
    # respaldo (equivalente a contar saltos).
    "peso_distancia_electrica": "x_ohm",
}
