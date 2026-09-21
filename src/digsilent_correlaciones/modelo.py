"""Estructuras de datos independientes de PowerFactory.

Estas clases son el punto de desacople entre la extracción (que depende de la
API de PowerFactory y no puede probarse fuera de DIgSILENT) y el análisis
(que es Python puro y sí se puede probar con datos sintéticos).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Barra:
    id: str
    nombre: str
    tension_kv: Optional[float] = None
    en_servicio: bool = True
    zona: Optional[str] = None
    area: Optional[str] = None
    subestacion: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

    @property
    def tiene_coordenadas(self) -> bool:
        return self.lat is not None and self.lon is not None


@dataclass
class Rama:
    """Un elemento de dos terminales que conecta dos barras: línea, transformador
    de dos devanados o interruptor/seccionador."""

    id: str
    nombre: str
    tipo: str  # "Linea" | "Trafo2" | "Interruptor" | "Trafo3*"
    barra_desde: str
    barra_hasta: str
    en_servicio: bool = True
    tension_kv: Optional[float] = None
    longitud_km: Optional[float] = None
    r_ohm: Optional[float] = None
    x_ohm: Optional[float] = None


@dataclass
class Inyeccion:
    """Generador o carga: un elemento de una sola terminal con una potencia activa."""

    id: str
    nombre: str
    barra: str
    tipo: str  # "Generador" | "Carga"
    p_mw: float = 0.0
    en_servicio: bool = True
    zona: Optional[str] = None
    area: Optional[str] = None


@dataclass
class ModeloRed:
    barras: list[Barra] = field(default_factory=list)
    ramas: list[Rama] = field(default_factory=list)
    inyecciones: list[Inyeccion] = field(default_factory=list)
    nombre_proyecto: str = ""
    nombre_caso_estudio: str = ""

    @property
    def generadores(self) -> list[Inyeccion]:
        return [i for i in self.inyecciones if i.tipo == "Generador"]

    @property
    def cargas(self) -> list[Inyeccion]:
        return [i for i in self.inyecciones if i.tipo == "Carga"]
