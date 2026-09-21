"""Análisis puro en Python (sin dependencia de PowerFactory) que transforma un
``ModeloRed`` en un conjunto de DataFrames, uno por cada "correlación" o vista
derivada del modelo. Todo esto es independiente de DIgSILENT y por lo tanto
se puede probar con datos sintéticos (ver tests/test_analisis.py).
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Optional

import networkx as nx
import numpy as np
import pandas as pd

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

    # Modelo grande: en vez de una matriz N x N, listamos los k vecinos más
    # cercanos de cada barra (más útil y liviano de todas formas).
    filas = []
    for i, origen in enumerate(barras_geo):
        distancias = []
        for j, destino in enumerate(barras_geo):
            if i == j:
                continue
            d = distancia_haversine_km(origen.lat, origen.lon, destino.lat, destino.lon)
            distancias.append((destino, d))
        distancias.sort(key=lambda x: x[1])
        for destino, d in distancias[:num_vecinos]:
            filas.append(
                {
                    "barra": origen.nombre,
                    "vecino_cercano": destino.nombre,
                    "distancia_km": round(d, 3),
                }
            )
    return pd.DataFrame(filas)


def hoja_distancia_electrica(
    grafo: nx.MultiGraph, peso: str, umbral: int, num_vecinos: int
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

    filas = []
    for origen, distancias in nx.all_pairs_dijkstra_path_length(simple, weight="weight"):
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


def hoja_centralidad(grafo: nx.MultiGraph) -> pd.DataFrame:
    if grafo.number_of_nodes() == 0:
        return pd.DataFrame()
    simple = nx.Graph(grafo)
    grado = nx.degree_centrality(simple)
    intermediacion = nx.betweenness_centrality(simple, weight=None, normalized=True)
    cercania = nx.closeness_centrality(simple)
    puntos_articulacion = set(nx.articulation_points(simple)) if simple.number_of_nodes() > 2 else set()

    filas = []
    for nid, datos in simple.nodes(data=True):
        filas.append(
            {
                "barra": datos.get("nombre", nid),
                "grado": simple.degree(nid),
                "centralidad_grado": round(grado.get(nid, 0.0), 4),
                "centralidad_intermediacion": round(intermediacion.get(nid, 0.0), 4),
                "centralidad_cercania": round(cercania.get(nid, 0.0), 4),
                "punto_de_articulacion_n1": nid in puntos_articulacion,
            }
        )
    df = pd.DataFrame(filas)
    return df.sort_values("centralidad_intermediacion", ascending=False).reset_index(drop=True)


def hoja_elementos_criticos_n1(grafo: nx.MultiGraph) -> pd.DataFrame:
    """Ramas cuya sola desconexión deja incomunicadas dos barras (N-1 crítico).

    Se evalúa sobre el MultiGraph real (no uno simplificado) para no marcar
    como crítica una línea que tiene un circuito paralelo entre las mismas
    barras.
    """
    filas = []
    trabajo = grafo.copy()
    for u, v, k, datos in list(grafo.edges(keys=True, data=True)):
        trabajo.remove_edge(u, v, key=k)
        sigue_conectado = trabajo.has_node(u) and trabajo.has_node(v) and nx.has_path(trabajo, u, v)
        trabajo.add_edge(u, v, key=k, **datos)
        if not sigue_conectado:
            filas.append(
                {
                    "id": k,
                    "nombre": datos.get("nombre", k),
                    "tipo": datos.get("tipo"),
                    "barra_desde": grafo.nodes[u].get("nombre", u),
                    "barra_hasta": grafo.nodes[v].get("nombre", v),
                    "efecto": "Desconecta la red en dos partes si sale de servicio",
                }
            )
    return pd.DataFrame(filas)


def hoja_correlaciones_estadisticas(
    modelo: ModeloRed, grafo: nx.MultiGraph, peso: str
) -> pd.DataFrame:
    """Correlación (Pearson) entre distancia geográfica, distancia eléctrica y
    número de saltos, calculada sobre todos los pares de barras que tienen
    coordenadas GPS y están en la misma componente conexa del grafo.
    """
    barras_geo = [b for b in modelo.barras if b.tiene_coordenadas and grafo.has_node(b.id)]
    if len(barras_geo) < 3:
        return pd.DataFrame(
            [["Se requieren al menos 3 barras con coordenadas GPS conectadas para calcular correlaciones."]],
            columns=["Aviso"],
        )

    simple = nx.Graph()
    simple.add_nodes_from(grafo.nodes(data=True))
    for u, v, data in grafo.edges(data=True):
        w = data.get(peso) or 1.0
        if simple.has_edge(u, v):
            simple[u][v]["weight"] = min(simple[u][v]["weight"], w)
        else:
            simple.add_edge(u, v, weight=w)

    filas = []
    ids = [b.id for b in barras_geo]
    for i, origen in enumerate(ids):
        try:
            saltos = nx.shortest_path_length(simple, origen)
            distancias = nx.shortest_path_length(simple, origen, weight="weight")
        except nx.NetworkXError:
            continue
        for j in range(i + 1, len(ids)):
            destino = ids[j]
            if destino not in distancias:
                continue  # distinta componente conexa
            b1 = next(b for b in barras_geo if b.id == origen)
            b2 = next(b for b in barras_geo if b.id == destino)
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

    hojas: dict[str, pd.DataFrame] = {
        "Resumen": hoja_resumen(modelo, grafo),
        "Grafo_Electrico": hoja_grafo_electrico(modelo),
        "Niveles_Tension": hoja_niveles_tension(modelo),
        "Zonas_Areas": hoja_zonas_areas(modelo),
        "Centralidad_Nodos": hoja_centralidad(grafo),
        "Elementos_Criticos_N1": hoja_elementos_criticos_n1(grafo),
        "Cercania_Geografica": hoja_cercania_geografica(modelo, umbral, vecinos),
        "Correlaciones_Estadisticas": hoja_correlaciones_estadisticas(modelo, grafo, peso),
    }

    matriz_adyacencia = hoja_matriz_adyacencia(grafo, umbral)
    if matriz_adyacencia is not None:
        hojas["Matriz_Adyacencia"] = matriz_adyacencia

    distancia_electrica = hoja_distancia_electrica(grafo, peso, umbral, vecinos)
    if distancia_electrica is not None:
        hojas["Distancia_Electrica"] = distancia_electrica

    return hojas
