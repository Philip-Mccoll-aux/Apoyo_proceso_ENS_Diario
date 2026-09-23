"""Análisis puro en Python (sin dependencia de PowerFactory) que transforma un
``ModeloRed`` en un conjunto de DataFrames, uno por cada "correlación" o vista
derivada del modelo. Todo esto es independiente de DIgSILENT y por lo tanto
se puede probar con datos sintéticos (ver tests/test_analisis.py).
"""
from __future__ import annotations

import random
from math import asin, cos, radians, sin, sqrt
from typing import Optional

import networkx as nx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .modelo import ModeloRed

RADIO_TIERRA_KM = 6371.0088


def distancia_haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en línea recta ("great circle") entre dos puntos GPS, en km."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * RADIO_TIERRA_KM * asin(sqrt(min(1.0, a)))


def construir_grafo(modelo: ModeloRed, solo_en_servicio: bool = True) -> nx.MultiGraph:
    """Construye el grafo eléctrico bus-rama del modelo.

    Se usa un MultiGraph porque puede haber más de una rama (p. ej. líneas en
    paralelo) entre el mismo par de barras; eso importa para el análisis N-1.
    """
    grafo = nx.MultiGraph()
    barras_validas = set()
    for barra in modelo.barras:
        if solo_en_servicio and not barra.en_servicio:
            continue
        grafo.add_node(barra.id, **_atributos_barra(barra))
        barras_validas.add(barra.id)

    for rama in modelo.ramas:
        if solo_en_servicio and not rama.en_servicio:
            continue
        if rama.barra_desde not in barras_validas or rama.barra_hasta not in barras_validas:
            continue
        longitud = rama.longitud_km if rama.longitud_km and rama.longitud_km > 0 else 1.0
        reactancia = rama.x_ohm if rama.x_ohm and rama.x_ohm > 0 else longitud
        grafo.add_edge(
            rama.barra_desde,
            rama.barra_hasta,
            key=rama.id,
            nombre=rama.nombre,
            tipo=rama.tipo,
            longitud_km=longitud,
            x_ohm=reactancia,
            r_ohm=rama.r_ohm,
            tension_kv=rama.tension_kv,
        )
    return grafo


def _atributos_barra(barra) -> dict:
    return {
        "nombre": barra.nombre,
        "tension_kv": barra.tension_kv,
        "zona": barra.zona,
        "area": barra.area,
        "subestacion": barra.subestacion,
        "lat": barra.lat,
        "lon": barra.lon,
    }


def hoja_resumen(modelo: ModeloRed, grafo: nx.MultiGraph) -> pd.DataFrame:
    componentes = list(nx.connected_components(grafo)) if grafo.number_of_nodes() else []
    filas = [
        ("Proyecto", modelo.nombre_proyecto),
        ("Caso de estudio", modelo.nombre_caso_estudio),
        ("Barras totales", len(modelo.barras)),
        ("Barras en el grafo (en servicio)", grafo.number_of_nodes()),
        ("Ramas totales", len(modelo.ramas)),
        ("Ramas en el grafo (en servicio)", grafo.number_of_edges()),
        ("Generadores", len(modelo.generadores)),
        ("Cargas", len(modelo.cargas)),
        ("Barras con coordenadas GPS", sum(1 for b in modelo.barras if b.tiene_coordenadas)),
        ("Componentes conexas", len(componentes)),
        ("Islas eléctricas (>1 componente)", "Sí" if len(componentes) > 1 else "No"),
    ]
    return pd.DataFrame(filas, columns=["Indicador", "Valor"])


def hoja_grafo_electrico(modelo: ModeloRed) -> pd.DataFrame:
    filas = []
    for rama in modelo.ramas:
        filas.append(
            {
                "id": rama.id,
                "nombre": rama.nombre,
                "tipo": rama.tipo,
                "barra_desde": rama.barra_desde,
                "barra_hasta": rama.barra_hasta,
                "en_servicio": rama.en_servicio,
                "tension_kv": rama.tension_kv,
                "longitud_km": rama.longitud_km,
                "r_ohm": rama.r_ohm,
                "x_ohm": rama.x_ohm,
            }
        )
    return pd.DataFrame(filas)


def hoja_matriz_adyacencia(grafo: nx.MultiGraph, umbral: int) -> Optional[pd.DataFrame]:
    n = grafo.number_of_nodes()
    if n == 0 or n > umbral:
        return None
    simple = nx.Graph(grafo)  # colapsa aristas paralelas para la matriz binaria
    nombres = {nid: data.get("nombre", nid) for nid, data in simple.nodes(data=True)}
    orden = list(simple.nodes())
    matriz = nx.to_pandas_adjacency(simple, nodelist=orden, weight=None)
    matriz = matriz.rename(index=nombres, columns=nombres)
    return matriz.astype(int)


def hoja_cercania_geografica(
    modelo: ModeloRed, umbral: int, num_vecinos: int
) -> pd.DataFrame:
    barras_geo = [b for b in modelo.barras if b.tiene_coordenadas]
    if len(barras_geo) < 2:
        return pd.DataFrame(columns=["Aviso"], data=[["No hay al menos 2 barras con coordenadas GPS en el modelo."]])

    if len(barras_geo) <= umbral:
        ids = [b.id for b in barras_geo]
        nombres = [b.nombre for b in barras_geo]
        n = len(barras_geo)
        datos = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d = distancia_haversine_km(
                    barras_geo[i].lat, barras_geo[i].lon, barras_geo[j].lat, barras_geo[j].lon
                )
                datos[i, j] = datos[j, i] = d
        return pd.DataFrame(datos, index=nombres, columns=nombres).round(3)

    # Modelo grande: comparar todos los pares es O(N^2) e impracticable con
    # miles de barras (una red nacional puede tener decenas de miles). En vez
    # de eso, se usa un árbol espacial (KD-tree) sobre una proyección plana
    # local aproximada para encontrar candidatos en O(N log N); la distancia
    # que se reporta es siempre la haversine exacta entre esos candidatos, la
    # proyección solo se usa para elegir quiénes son "cercanos".
    lat_media = radians(sum(b.lat for b in barras_geo) / len(barras_geo))
    coordenadas = np.array([(b.lon * cos(lat_media), b.lat) for b in barras_geo])
    arbol = cKDTree(coordenadas)
    k = min(num_vecinos + 1, len(barras_geo))  # +1: el punto es su propio vecino más cercano
    _, indices_vecinos = arbol.query(coordenadas, k=k)

    filas = []
    for i, vecinos in enumerate(np.atleast_2d(indices_vecinos)):
        origen = barras_geo[i]
        for j in vecinos:
            if j == i:
                continue
            destino = barras_geo[j]
            d = distancia_haversine_km(origen.lat, origen.lon, destino.lat, destino.lon)
            filas.append(
                {
                    "barra": origen.nombre,
                    "vecino_cercano": destino.nombre,
                    "distancia_km": round(d, 3),
                }
            )
    return pd.DataFrame(filas)


def hoja_distancia_electrica(
    grafo: nx.MultiGraph,
    peso: str,
    umbral: int,
    num_vecinos: int,
    umbral_pesado: int = 3000,
    tamano_muestra: int = 500,
    semilla: int = 42,
) -> Optional[pd.DataFrame]:
    if grafo.number_of_nodes() == 0:
        return None
    simple = nx.Graph()
    simple.add_nodes_from(grafo.nodes(data=True))
    for u, v, data in grafo.edges(data=True):
        w = data.get(peso) or 1.0
        if simple.has_edge(u, v):
            simple[u][v]["weight"] = min(simple[u][v]["weight"], w)  # rama paralela más corta
        else:
            simple.add_edge(u, v, weight=w)

    nombres = {nid: data.get("nombre", nid) for nid, data in simple.nodes(data=True)}
    n = simple.number_of_nodes()

    if n <= umbral:
        orden = list(simple.nodes())
        matriz = pd.DataFrame(np.inf, index=orden, columns=orden)
        for origen, distancias in nx.all_pairs_dijkstra_path_length(simple, weight="weight"):
            for destino, d in distancias.items():
                matriz.loc[origen, destino] = d
        matriz = matriz.rename(index=nombres, columns=nombres)
        return matriz.round(3)

    # Calcular la ruta más corta desde CADA barra (todos contra todos) es
    # O(N * E log N): impracticable con miles de barras. Si la red supera
    # "umbral_pesado", se calcula solo desde una muestra aleatoria de barras
    # en vez de desde todas, dejando explícito que es una muestra.
    if n <= umbral_pesado:
        origenes = list(simple.nodes())
        es_muestra = False
    else:
        origenes = random.Random(semilla).sample(list(simple.nodes()), min(tamano_muestra, n))
        es_muestra = True

    filas = []
    for origen in origenes:
        distancias = nx.single_source_dijkstra_path_length(simple, origen, weight="weight")
        ordenados = sorted(distancias.items(), key=lambda x: x[1])
        contador = 0
        for destino, d in ordenados:
            if destino == origen:
                continue
            filas.append(
                {
                    "barra": nombres[origen],
                    "barra_electricamente_cercana": nombres[destino],
                    f"distancia_electrica_{peso}": round(d, 3),
                    "calculado_sobre_muestra": es_muestra,
                }
            )
            contador += 1
            if contador >= num_vecinos:
                break
    return pd.DataFrame(filas)


def hoja_niveles_tension(modelo: ModeloRed) -> pd.DataFrame:
    filas = {}
    for barra in modelo.barras:
        nivel = barra.tension_kv
        d = filas.setdefault(nivel, {"tension_kv": nivel, "num_barras": 0, "num_barras_en_servicio": 0})
        d["num_barras"] += 1
        if barra.en_servicio:
            d["num_barras_en_servicio"] += 1
    for rama in modelo.ramas:
        nivel = rama.tension_kv
        if nivel not in filas:
            filas[nivel] = {"tension_kv": nivel, "num_barras": 0, "num_barras_en_servicio": 0}
        filas[nivel].setdefault("num_ramas", 0)
        filas[nivel]["num_ramas"] = filas[nivel].get("num_ramas", 0) + 1
    df = pd.DataFrame(list(filas.values()))
    if not df.empty:
        df = df.sort_values("tension_kv", ascending=False, na_position="last").reset_index(drop=True)
    return df


def hoja_zonas_areas(modelo: ModeloRed) -> pd.DataFrame:
    resumen: dict[tuple, dict] = {}

    def clave(zona, area):
        return (zona or "(sin zona)", area or "(sin área)")

    for barra in modelo.barras:
        k = clave(barra.zona, barra.area)
        d = resumen.setdefault(
            k, {"zona": k[0], "area": k[1], "num_barras": 0, "gen_mw": 0.0, "carga_mw": 0.0}
        )
        d["num_barras"] += 1

    for iny in modelo.inyecciones:
        k = clave(iny.zona, iny.area)
        d = resumen.setdefault(
            k, {"zona": k[0], "area": k[1], "num_barras": 0, "gen_mw": 0.0, "carga_mw": 0.0}
        )
        if iny.en_servicio:
            if iny.tipo == "Generador":
                d["gen_mw"] += iny.p_mw
            else:
                d["carga_mw"] += iny.p_mw

    df = pd.DataFrame(list(resumen.values()))
    if not df.empty:
        df["balance_mw"] = df["gen_mw"] - df["carga_mw"]
        df = df.sort_values(["zona", "area"]).reset_index(drop=True)
    return df


def hoja_centralidad(
    grafo: nx.MultiGraph, umbral_pesado: int = 3000, tamano_muestra: int = 500, semilla: int = 42
) -> pd.DataFrame:
    if grafo.number_of_nodes() == 0:
        return pd.DataFrame()
    simple = nx.Graph(grafo)
    n = simple.number_of_nodes()
    grado = nx.degree_centrality(simple)
    # articulation_points y degree_centrality son O(V+E): siempre exactos,
    # incluso en redes grandes.
    puntos_articulacion = set(nx.articulation_points(simple)) if n > 2 else set()

    # betweenness_centrality exacta es O(V*E): impracticable en redes de
    # miles de barras. Por encima de "umbral_pesado" se usa la variante
    # aproximada de networkx, que estima el resultado a partir de un
    # muestreo de nodos origen ("k") en vez de recorrerlos todos.
    es_aproximada = n > umbral_pesado
    k = min(tamano_muestra, n) if es_aproximada else None
    intermediacion = nx.betweenness_centrality(
        simple, k=k, seed=semilla if es_aproximada else None, normalized=True
    )
    # closeness_centrality también es O(V*E) sin atajo de muestreo posible
    # (necesita las distancias completas desde cada nodo); en redes grandes
    # se omite en vez de tardar minutos u horas.
    cercania = {} if es_aproximada else nx.closeness_centrality(simple)

    filas = []
    for nid, datos in simple.nodes(data=True):
        filas.append(
            {
                "barra": datos.get("nombre", nid),
                "grado": simple.degree(nid),
                "centralidad_grado": round(grado.get(nid, 0.0), 4),
                "centralidad_intermediacion": round(intermediacion.get(nid, 0.0), 4),
                "intermediacion_es_aproximada": es_aproximada,
                "centralidad_cercania": round(cercania[nid], 4) if nid in cercania else None,
                "punto_de_articulacion_n1": nid in puntos_articulacion,
            }
        )
    df = pd.DataFrame(filas)
    return df.sort_values("centralidad_intermediacion", ascending=False).reset_index(drop=True)


def hoja_elementos_criticos_n1(grafo: nx.MultiGraph) -> pd.DataFrame:
    """Ramas cuya sola desconexión deja incomunicadas dos barras (N-1 crítico).

    Usa el algoritmo de "bridges" (O(V+E), una sola pasada) sobre una
    versión simplificada del grafo en vez de remover cada arista una por una
    y volver a comprobar conectividad (O(E*(V+E)): impracticable con miles
    de elementos). Para no marcar como crítica una línea que tiene un
    circuito paralelo entre las mismas barras, se cuenta la multiplicidad de
    cada par de barras en el MultiGraph original y solo se reportan los
    "bridges" cuya multiplicidad es 1.
    """
    simple = nx.Graph()
    simple.add_nodes_from(grafo.nodes())
    multiplicidad: dict[frozenset, int] = {}
    for u, v in grafo.edges(keys=False):
        clave = frozenset((u, v))
        multiplicidad[clave] = multiplicidad.get(clave, 0) + 1
        simple.add_edge(u, v)

    filas = []
    for componente in nx.connected_components(simple):
        if len(componente) < 2:
            continue
        for u, v in nx.bridges(simple.subgraph(componente)):
            if multiplicidad.get(frozenset((u, v)), 0) != 1:
                continue  # hay una rama paralela entre u y v: no es N-1 crítico
            clave, datos = next(iter(grafo.get_edge_data(u, v).items()))
            filas.append(
                {
                    "id": clave,
                    "nombre": datos.get("nombre", clave),
                    "tipo": datos.get("tipo"),
                    "barra_desde": grafo.nodes[u].get("nombre", u),
                    "barra_hasta": grafo.nodes[v].get("nombre", v),
                    "efecto": "Desconecta la red en dos partes si sale de servicio",
                }
            )
    return pd.DataFrame(filas)


def hoja_correlaciones_estadisticas(
    modelo: ModeloRed,
    grafo: nx.MultiGraph,
    peso: str,
    tamano_muestra: int = 500,
    semilla: int = 42,
) -> pd.DataFrame:
    """Correlación (Pearson) entre distancia geográfica, distancia eléctrica y
    número de saltos, calculada sobre pares de barras que tienen coordenadas
    GPS y están en la misma componente conexa del grafo.

    No hace falta ser exhaustivo para que una correlación sea representativa,
    así que cuando hay más de "tamano_muestra" barras con GPS se toma una
    muestra aleatoria de ese tamaño en vez de recorrerlas todas: evita tanto
    el costo de una ruta más corta desde cada una de miles de barras como un
    número de pares que de todos modos sería excesivo para este propósito.
    """
    barras_geo = [b for b in modelo.barras if b.tiene_coordenadas and grafo.has_node(b.id)]
    if len(barras_geo) < 3:
        return pd.DataFrame(
            [["Se requieren al menos 3 barras con coordenadas GPS conectadas para calcular correlaciones."]],
            columns=["Aviso"],
        )
    if len(barras_geo) > tamano_muestra:
        barras_geo = random.Random(semilla).sample(barras_geo, tamano_muestra)
    barras_por_id = {b.id: b for b in barras_geo}

    simple = nx.Graph()
    simple.add_nodes_from(grafo.nodes(data=True))
    for u, v, data in grafo.edges(data=True):
        w = data.get(peso) or 1.0
        if simple.has_edge(u, v):
            simple[u][v]["weight"] = min(simple[u][v]["weight"], w)
        else:
            simple.add_edge(u, v, weight=w)

    filas = []
    ids = list(barras_por_id.keys())
    for i, origen in enumerate(ids):
        try:
            saltos = nx.shortest_path_length(simple, origen)
            distancias = nx.shortest_path_length(simple, origen, weight="weight")
        except nx.NetworkXError:
            continue
        b1 = barras_por_id[origen]
        for j in range(i + 1, len(ids)):
            destino = ids[j]
            if destino not in distancias:
                continue  # distinta componente conexa
            b2 = barras_por_id[destino]
            filas.append(
                {
                    "distancia_geografica_km": distancia_haversine_km(b1.lat, b1.lon, b2.lat, b2.lon),
                    f"distancia_electrica_{peso}": distancias[destino],
                    "num_saltos": saltos[destino],
                }
            )

    df_pares = pd.DataFrame(filas)
    if df_pares.empty:
        return pd.DataFrame(
            [["No hay pares de barras con GPS dentro de la misma componente conexa."]], columns=["Aviso"]
        )

    correlacion = df_pares.corr(method="pearson").round(4)
    correlacion.index.name = "Pearson"
    correlacion = correlacion.reset_index()
    nota = pd.DataFrame(
        [[f"Calculado sobre {len(df_pares)} pares de barras con coordenadas GPS.", None, None, None]],
        columns=correlacion.columns,
    )
    return pd.concat([correlacion, nota], ignore_index=True)


def generar_todas_las_hojas(modelo: ModeloRed, config: dict) -> dict[str, pd.DataFrame]:
    grafo = construir_grafo(modelo, solo_en_servicio=config.get("solo_en_servicio", True))
    umbral = config.get("umbral_matriz_completa", 200)
    vecinos = config.get("num_vecinos_cercanos", 10)
    peso = config.get("peso_distancia_electrica", "x_ohm")
    umbral_pesado = config.get("umbral_analisis_pesado", 3000)
    tamano_muestra = config.get("tamano_muestra_redes_grandes", 500)
    semilla = config.get("semilla_muestreo", 42)

    hojas: dict[str, pd.DataFrame] = {
        "Resumen": hoja_resumen(modelo, grafo),
        "Grafo_Electrico": hoja_grafo_electrico(modelo),
        "Niveles_Tension": hoja_niveles_tension(modelo),
        "Zonas_Areas": hoja_zonas_areas(modelo),
        "Centralidad_Nodos": hoja_centralidad(grafo, umbral_pesado, tamano_muestra, semilla),
        "Elementos_Criticos_N1": hoja_elementos_criticos_n1(grafo),
        "Cercania_Geografica": hoja_cercania_geografica(modelo, umbral, vecinos),
        "Correlaciones_Estadisticas": hoja_correlaciones_estadisticas(
            modelo, grafo, peso, tamano_muestra, semilla
        ),
    }

    matriz_adyacencia = hoja_matriz_adyacencia(grafo, umbral)
    if matriz_adyacencia is not None:
        hojas["Matriz_Adyacencia"] = matriz_adyacencia

    distancia_electrica = hoja_distancia_electrica(
        grafo, peso, umbral, vecinos, umbral_pesado, tamano_muestra, semilla
    )
    if distancia_electrica is not None:
        hojas["Distancia_Electrica"] = distancia_electrica

    return hojas
