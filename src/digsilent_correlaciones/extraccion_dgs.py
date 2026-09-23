"""Construye un ``ModeloRed`` a partir de los bloques ya parseados de un
archivo DGS (ver ``lector_dgs.py``). No depende de PowerFactory: corre en
cualquier máquina con Python.

Nota sobre las impedancias de transformadores: DGS no exporta R/X en Ohm
directamente, sino los parámetros de placa (tensión de cortocircuito uk%,
pérdidas de cobre, potencia nominal) en la tabla de tipo TypTr2. Aquí se
calcula una aproximación estándar de la impedancia de cortocircuito a partir
de esos parámetros. Es suficiente para ponderar "distancia eléctrica" de
forma relativa (comparar qué tan lejos está una barra de otra); no reemplaza
un modelo de flujo de potencia.
"""
from __future__ import annotations

from math import sqrt

import pandas as pd

from .lector_dgs import columna_id
from .modelo import Barra, Inyeccion, ModeloRed, Rama

_CLASES_RAMA_2T = {
    "ElmLne": "Linea",
    "ElmTr2": "Trafo2",
    "ElmCoup": "Interruptor",
}
_CLASES_INYECCION = {
    "ElmSym": "Generador",
    "ElmGenstat": "Generador",
    "ElmLod": "Carga",
}


def _valor(fila, columna, default=None):
    if columna not in fila or pd.isna(fila[columna]):
        return default
    return fila[columna]


def _coordenada_vacia(lat, lon) -> bool:
    """(0, 0) es el valor por defecto/sin-inicializar de GPSlat/GPSlon en DGS,
    no una ubicación real (Null Island) — hay que tratarlo como dato faltante,
    igual que None."""
    if lat is None or lon is None:
        return True
    try:
        return float(lat) == 0.0 and float(lon) == 0.0
    except (TypeError, ValueError):
        return True


def _en_servicio(fila) -> bool:
    if "outserv" in fila.index and not pd.isna(fila["outserv"]):
        return int(fila["outserv"]) == 0
    if "on_off" in fila.index and not pd.isna(fila["on_off"]):
        return int(fila["on_off"]) == 1
    return True


def _mapa_cubiculos(bloques: dict[str, pd.DataFrame]) -> dict[str, list[str]]:
    """{id_del_elemento: [ids de barra a las que está conectado]}, en el orden del archivo."""
    cubiculos = bloques.get("StaCubic")
    mapa: dict[str, list[str]] = {}
    if cubiculos is None or cubiculos.empty:
        return mapa
    for _, fila in cubiculos.iterrows():
        obj_id = _valor(fila, "obj_id")
        fold_id = _valor(fila, "fold_id")
        if obj_id is None or fold_id is None:
            continue
        mapa.setdefault(str(obj_id), []).append(str(fold_id))
    return mapa


def _tabla_por_id(bloques: dict[str, pd.DataFrame], clase: str) -> dict:
    df = bloques.get(clase)
    if df is None or df.empty:
        return {}
    col = columna_id(df)
    return {str(fila[col]): fila for _, fila in df.iterrows()}


def _impedancia_linea(fila_linea, tipos_linea: dict) -> tuple[float | None, float | None]:
    tipo = tipos_linea.get(str(_valor(fila_linea, "typ_id")))
    longitud = _valor(fila_linea, "dline")
    if tipo is None or longitud is None:
        return None, None
    rline, xline = _valor(tipo, "rline"), _valor(tipo, "xline")
    r_ohm = rline * longitud if rline is not None else None
    x_ohm = xline * longitud if xline is not None else None
    return r_ohm, x_ohm


def _impedancia_trafo2(fila_trafo, tipos_trafo: dict) -> tuple[float | None, float | None]:
    tipo = tipos_trafo.get(str(_valor(fila_trafo, "typ_id")))
    if tipo is None:
        return None, None
    uk, u_hv, s_n = _valor(tipo, "uktr"), _valor(tipo, "utrn_h"), _valor(tipo, "strn")
    if uk is None or u_hv is None or not s_n:
        return None, None
    z_base = (u_hv**2) / s_n
    zsc_pu = uk / 100.0
    pcu = _valor(tipo, "pcutr")
    rsc_pu = (pcu / 1000.0) / s_n if pcu is not None else 0.0
    xsc_pu = sqrt(max(zsc_pu**2 - rsc_pu**2, 0.0))
    return rsc_pu * z_base, xsc_pu * z_base


def dgs_a_modelo(bloques: dict[str, pd.DataFrame], config: dict, nombre_proyecto: str = "") -> ModeloRed:
    modelo = ModeloRed(nombre_proyecto=nombre_proyecto)
    cubiculos = _mapa_cubiculos(bloques)

    subestaciones = _tabla_por_id(bloques, "ElmSubstat")
    ids_barras = set()

    terminales = bloques.get("ElmTerm")
    if terminales is not None:
        for _, fila in terminales.iterrows():
            id_barra = str(fila[columna_id(terminales)])
            lat = _buscar_atributo(fila, config["atributos_lat"])
            lon = _buscar_atributo(fila, config["atributos_lon"])
            if _coordenada_vacia(lat, lon) and str(_valor(fila, "fold_id")) in subestaciones:
                subestacion = subestaciones[str(_valor(fila, "fold_id"))]
                lat_sub = _buscar_atributo(subestacion, config["atributos_lat"])
                lon_sub = _buscar_atributo(subestacion, config["atributos_lon"])
                if not _coordenada_vacia(lat_sub, lon_sub):
                    lat, lon = lat_sub, lon_sub
            if _coordenada_vacia(lat, lon):
                lat = lon = None
            modelo.barras.append(
                Barra(
                    id=id_barra,
                    nombre=str(_valor(fila, "loc_name", id_barra)),
                    tension_kv=_valor(fila, "uknom"),
                    en_servicio=_en_servicio(fila),
                    zona=_buscar_atributo(fila, config["atributos_zona"]),
                    area=_buscar_atributo(fila, config["atributos_area"]),
                    subestacion=str(_valor(subestaciones.get(str(_valor(fila, "fold_id")), {}), "loc_name"))
                    if str(_valor(fila, "fold_id")) in subestaciones
                    else None,
                    lat=float(lat) if lat is not None else None,
                    lon=float(lon) if lon is not None else None,
                )
            )
            ids_barras.add(id_barra)

    tipos_linea = _tabla_por_id(bloques, "TypLne")
    tipos_trafo2 = _tabla_por_id(bloques, "TypTr2")

    for clase, tipo_rama in _CLASES_RAMA_2T.items():
        tabla = bloques.get(clase)
        if tabla is None or tabla.empty:
            continue
        col_id = columna_id(tabla)
        for _, fila in tabla.iterrows():
            id_elemento = str(fila[col_id])
            barras_conectadas = cubiculos.get(id_elemento, [])
            if len(barras_conectadas) < 2:
                continue
            r_ohm = x_ohm = None
            if clase == "ElmLne":
                r_ohm, x_ohm = _impedancia_linea(fila, tipos_linea)
            elif clase == "ElmTr2":
                r_ohm, x_ohm = _impedancia_trafo2(fila, tipos_trafo2)
            modelo.ramas.append(
                Rama(
                    id=id_elemento,
                    nombre=str(_valor(fila, "loc_name", id_elemento)),
                    tipo=tipo_rama,
                    barra_desde=barras_conectadas[0],
                    barra_hasta=barras_conectadas[1],
                    en_servicio=_en_servicio(fila),
                    longitud_km=_valor(fila, "dline"),
                    r_ohm=r_ohm,
                    x_ohm=x_ohm,
                )
            )

    tabla_tr3 = bloques.get("ElmTr3")
    if tabla_tr3 is not None and not tabla_tr3.empty:
        col_id = columna_id(tabla_tr3)
        for _, fila in tabla_tr3.iterrows():
            id_elemento = str(fila[col_id])
            barras_conectadas = cubiculos.get(id_elemento, [])
            if len(barras_conectadas) < 2:
                continue
            nodo_estrella = f"{id_elemento}::estrella"
            modelo.barras.append(
                Barra(id=nodo_estrella, nombre=f"{_valor(fila, 'loc_name', id_elemento)} (estrella)")
            )
            for indice, barra_id in enumerate(barras_conectadas[:3]):
                modelo.ramas.append(
                    Rama(
                        id=f"{id_elemento}::dev{indice + 1}",
                        nombre=f"{_valor(fila, 'loc_name', id_elemento)} (devanado {indice + 1})",
                        tipo="Trafo3",
                        barra_desde=barra_id,
                        barra_hasta=nodo_estrella,
                        en_servicio=_en_servicio(fila),
                    )
                )

    for clase, tipo_iny in _CLASES_INYECCION.items():
        tabla = bloques.get(clase)
        if tabla is None or tabla.empty:
            continue
        col_id = columna_id(tabla)
        columna_potencia = "plini" if tipo_iny == "Carga" else "pgini"
        for _, fila in tabla.iterrows():
            id_elemento = str(fila[col_id])
            barras_conectadas = cubiculos.get(id_elemento, [])
            if not barras_conectadas or barras_conectadas[0] not in ids_barras:
                continue
            modelo.inyecciones.append(
                Inyeccion(
                    id=id_elemento,
                    nombre=str(_valor(fila, "loc_name", id_elemento)),
                    barra=barras_conectadas[0],
                    tipo=tipo_iny,
                    p_mw=float(_valor(fila, columna_potencia, 0.0) or 0.0),
                    en_servicio=_en_servicio(fila),
                    zona=_buscar_atributo(fila, config["atributos_zona"]),
                    area=_buscar_atributo(fila, config["atributos_area"]),
                )
            )

    return modelo


def _buscar_atributo(fila, nombres_candidatos):
    for nombre in nombres_candidatos:
        if nombre in fila.index if hasattr(fila, "index") else nombre in fila:
            valor = fila[nombre]
            if valor is not None and not (isinstance(valor, float) and pd.isna(valor)) and valor != "":
                return valor
    return None
