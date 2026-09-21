"""Modelo sintético usado por las pruebas: un anillo de 3 barras (B1-B2-B3-B1)
más una barra radial B4 colgada de B3 mediante una única línea (por lo tanto
esa línea es el único elemento N-1 crítico del sistema), y una barra B5
totalmente aislada (fuera de servicio) para probar el filtrado.

Coordenadas aproximadas de 4 ciudades chilenas reales, para poder verificar
la distancia haversine contra un valor conocido.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from digsilent_correlaciones.modelo import Barra, Inyeccion, ModeloRed, Rama


def construir_modelo_sintetico() -> ModeloRed:
    barras = [
        Barra(id="B1", nombre="Santiago", tension_kv=220, zona="Centro", area="SIC", lat=-33.4489, lon=-70.6693),
        Barra(id="B2", nombre="Valparaiso", tension_kv=220, zona="Centro", area="SIC", lat=-33.0472, lon=-71.6127),
        Barra(id="B3", nombre="Rancagua", tension_kv=220, zona="Centro", area="SIC", lat=-34.1708, lon=-70.7444),
        Barra(id="B4", nombre="Curico", tension_kv=110, zona="Sur", area="SIC", lat=-34.9828, lon=-71.2394),
        Barra(id="B5", nombre="Fuera de Servicio", tension_kv=110, zona="Sur", area="SIC", en_servicio=False),
    ]
    ramas = [
        Rama(id="L12", nombre="Santiago-Valparaiso", tipo="Linea", barra_desde="B1", barra_hasta="B2",
             tension_kv=220, longitud_km=100, r_ohm=1.0, x_ohm=10.0),
        Rama(id="L23", nombre="Valparaiso-Rancagua", tipo="Linea", barra_desde="B2", barra_hasta="B3",
             tension_kv=220, longitud_km=130, r_ohm=1.3, x_ohm=13.0),
        Rama(id="L31", nombre="Rancagua-Santiago", tipo="Linea", barra_desde="B3", barra_hasta="B1",
             tension_kv=220, longitud_km=90, r_ohm=0.9, x_ohm=9.0),
        Rama(id="L34", nombre="Rancagua-Curico", tipo="Trafo2", barra_desde="B3", barra_hasta="B4",
             tension_kv=110, longitud_km=None, r_ohm=0.5, x_ohm=5.0),
    ]
    inyecciones = [
        Inyeccion(id="G1", nombre="Central 1", barra="B1", tipo="Generador", p_mw=300, zona="Centro", area="SIC"),
        Inyeccion(id="D1", nombre="Consumo Curico", barra="B4", tipo="Carga", p_mw=80, zona="Sur", area="SIC"),
        Inyeccion(id="D2", nombre="Consumo Rancagua", barra="B3", tipo="Carga", p_mw=120, zona="Centro", area="SIC"),
    ]
    return ModeloRed(
        barras=barras,
        ramas=ramas,
        inyecciones=inyecciones,
        nombre_proyecto="Proyecto de prueba",
        nombre_caso_estudio="Caso base",
    )
