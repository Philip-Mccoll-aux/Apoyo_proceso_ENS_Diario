"""Extracción de un ``ModeloRed`` a partir de un proyecto abierto en DIgSILENT
PowerFactory.

Este módulo SOLO se puede ejecutar dentro del entorno Python de PowerFactory
(o desde Python externo con el módulo ``powerfactory`` en el ``sys.path``,
ver README). No tiene pruebas automatizadas porque no hay forma de simular la
API COM/objeto de PowerFactory de forma fiable fuera de la propia aplicación;
por eso se mantiene deliberadamente delgado y delega toda la lógica de
análisis al módulo ``analisis``, que sí está cubierto por tests.
"""
from __future__ import annotations

from .modelo import Barra, Inyeccion, ModeloRed, Rama

# Clases de PowerFactory que se consideran "ramas" de dos terminales.
_CLASES_RAMA_2T = {
    "ElmLne": "Linea",
    "ElmTr2": "Trafo2",
    "ElmCoup": "Interruptor",
}


def _obtener_attr(obj, nombres_candidatos, default=None):
    """Prueba una lista de nombres de atributo y devuelve el primero que exista."""
    for nombre in nombres_candidatos:
        try:
            if obj.HasAttribute(nombre):
                valor = obj.GetAttribute(nombre)
                if valor not in (None, ""):
                    return valor
        except Exception:
            continue
    return default


def _en_servicio(obj) -> bool:
    try:
        return int(obj.GetAttribute("outserv")) == 0
    except Exception:
        return True


def _es_coordenada_vacia(lat, lon) -> bool:
    """(0, 0) es el valor por defecto/sin-inicializar del campo GPS en
    PowerFactory, no una ubicación real (Null Island) — se trata como dato
    faltante, igual que None."""
    if lat is None or lon is None:
        return True
    try:
        return float(lat) == 0.0 and float(lon) == 0.0
    except (TypeError, ValueError):
        return True


def _obtener_coordenadas(elemento, config):
    lat = _obtener_attr(elemento, config["atributos_lat"])
    lon = _obtener_attr(elemento, config["atributos_lon"])
    if _es_coordenada_vacia(lat, lon):
        subestacion = getattr(elemento, "cpSubstat", None)
        if subestacion is not None:
            lat_sub = _obtener_attr(subestacion, config["atributos_lat"])
            lon_sub = _obtener_attr(subestacion, config["atributos_lon"])
            if not _es_coordenada_vacia(lat_sub, lon_sub):
                lat, lon = lat_sub, lon_sub
    if _es_coordenada_vacia(lat, lon):
        return (None, None)
    try:
        return (float(lat), float(lon))
    except (TypeError, ValueError):
        return (None, None)


def _bus_de_cubiculo(elemento, indice: int):
    """Devuelve la barra (ElmTerm) conectada en el cubículo ``indice`` (0 o 1)."""
    try:
        cubiculo = elemento.GetCubicle(indice)
    except Exception:
        cubiculo = None
    if cubiculo is None:
        cubiculo = getattr(elemento, f"bus{indice + 1}", None)
    if cubiculo is None:
        return None
    return getattr(cubiculo, "cterm", None)


def extraer_modelo(app, config: dict) -> ModeloRed:
    """Extrae barras, ramas, generadores y cargas del proyecto activo en ``app``.

    ``app`` es el objeto devuelto por ``powerfactory.GetApplication()``.
    """
    proyecto = app.GetActiveProject()
    if proyecto is None:
        raise RuntimeError(
            "No hay un proyecto activo en PowerFactory. Active un proyecto y un "
            "caso de estudio antes de ejecutar este script."
        )
    caso_estudio = app.GetActiveStudyCase()

    modelo = ModeloRed(
        nombre_proyecto=proyecto.loc_name,
        nombre_caso_estudio=caso_estudio.loc_name if caso_estudio else "",
    )

    barras_pf = app.GetCalcRelevantObjects("*.ElmTerm")
    ids_barras = set()
    for barra_pf in barras_pf:
        lat, lon = _obtener_coordenadas(barra_pf, config)
        modelo.barras.append(
            Barra(
                id=barra_pf.GetFullName(),
                nombre=barra_pf.loc_name,
                tension_kv=_obtener_attr(barra_pf, ["uknom"]),
                en_servicio=_en_servicio(barra_pf),
                zona=_obtener_attr(barra_pf, config["atributos_zona"]),
                area=_obtener_attr(barra_pf, config["atributos_area"]),
                subestacion=getattr(getattr(barra_pf, "cpSubstat", None), "loc_name", None),
                lat=lat,
                lon=lon,
            )
        )
        ids_barras.add(barra_pf.GetFullName())

    for clase_pf, tipo in _CLASES_RAMA_2T.items():
        for elemento in app.GetCalcRelevantObjects(f"*.{clase_pf}"):
            bus1 = _bus_de_cubiculo(elemento, 0)
            bus2 = _bus_de_cubiculo(elemento, 1)
            if bus1 is None or bus2 is None:
                continue
            modelo.ramas.append(
                Rama(
                    id=elemento.GetFullName(),
                    nombre=elemento.loc_name,
                    tipo=tipo,
                    barra_desde=bus1.GetFullName(),
                    barra_hasta=bus2.GetFullName(),
                    en_servicio=_en_servicio(elemento),
                    tension_kv=_obtener_attr(bus1, ["uknom"]),
                    longitud_km=_obtener_attr(elemento, ["dline"]),
                    r_ohm=_obtener_attr(elemento, ["R1"]),
                    x_ohm=_obtener_attr(elemento, ["X1"]),
                )
            )

    # Transformadores de 3 devanados: se modelan como 3 ramas hacia un nodo
    # ficticio interno (el propio elemento), igual que hace PowerFactory
    # internamente con el punto estrella.
    for trafo3 in app.GetCalcRelevantObjects("*.ElmTr3"):
        nodo_estrella = f"{trafo3.GetFullName()}::estrella"
        modelo.barras.append(
            Barra(id=nodo_estrella, nombre=f"{trafo3.loc_name} (estrella)", en_servicio=_en_servicio(trafo3))
        )
        for indice in range(3):
            bus = _bus_de_cubiculo(trafo3, indice)
            if bus is None:
                continue
            modelo.ramas.append(
                Rama(
                    id=f"{trafo3.GetFullName()}::dev{indice + 1}",
                    nombre=f"{trafo3.loc_name} (devanado {indice + 1})",
                    tipo="Trafo3",
                    barra_desde=bus.GetFullName(),
                    barra_hasta=nodo_estrella,
                    en_servicio=_en_servicio(trafo3),
                    tension_kv=_obtener_attr(bus, ["uknom"]),
                )
            )

    for clase_pf, tipo in (("ElmSym", "Generador"), ("ElmGenstat", "Generador"), ("ElmLod", "Carga")):
        for elemento in app.GetCalcRelevantObjects(f"*.{clase_pf}"):
            bus = _bus_de_cubiculo(elemento, 0)
            if bus is None or bus.GetFullName() not in ids_barras:
                continue
            potencia = _obtener_attr(elemento, ["pgini"] if tipo == "Generador" else ["plini"], default=0.0)
            modelo.inyecciones.append(
                Inyeccion(
                    id=elemento.GetFullName(),
                    nombre=elemento.loc_name,
                    barra=bus.GetFullName(),
                    tipo=tipo,
                    p_mw=float(potencia or 0.0),
                    en_servicio=_en_servicio(elemento),
                    zona=_obtener_attr(elemento, config["atributos_zona"]),
                    area=_obtener_attr(elemento, config["atributos_area"]),
                )
            )

    return modelo
