"""Lector del formato DGS ASCII de DIgSILENT PowerFactory.

DGS ("DIgSILENT Generic Schema") es el formato de intercambio de datos que
PowerFactory puede exportar (File → Export → DGS) sin necesidad de la propia
aplicación para volver a leerlo. Es texto plano con esta estructura:

    $$ElmTerm;ID(a:15);loc_name(a:40);outserv(i);uknom(r)
    *  comentario, se ignora
      1;Santiago;0;220
      2;Valparaiso;0;220
    $$StaCubic;ID(a:15);loc_name(a:40);fold_id(p);obj_id(p)
      10;Cubiculo 1;1;100

Cada línea "$$Clase;..." abre una nueva sección/tabla (una por clase de
PowerFactory: ElmTerm, ElmLne, StaCubic, etc.), donde cada atributo declara
su tipo entre paréntesis: ``a`` texto, ``p`` puntero/id (se trata como
texto), ``i`` entero, ``r``/``d`` número real. Las filas de datos que siguen
pertenecen a esa sección hasta la siguiente línea "$$...".

La conectividad eléctrica NO se guarda como "bus1"/"bus2" en el propio
elemento (eso es una comodidad de la API en vivo de PowerFactory, no del
archivo DGS); en el archivo se modela con objetos "StaCubic" intermedios:
cada cubículo tiene ``fold_id`` (la barra/ElmTerm donde vive) y ``obj_id``
(el elemento de dos terminales al que conecta). Un elemento con dos
terminales, como una línea, tiene dos cubículos con el mismo ``obj_id``.
"""
from __future__ import annotations

import pandas as pd

_TIPOS_POR_CODIGO = {"a": str, "p": str, "i": "Int64", "r": float, "d": float}


def leer_bloques_dgs(ruta: str) -> dict[str, pd.DataFrame]:
    """Parsea un archivo .dgs y devuelve {nombre_de_clase: DataFrame}."""
    columnas: dict[str, list[str]] = {}
    tipos: dict[str, list] = {}
    filas: dict[str, list[list[str]]] = {}
    bloque_actual = None

    with open(ruta, encoding="utf-8-sig", errors="replace") as f:
        for linea in f:
            linea = linea.rstrip("\n").rstrip("\r")

            if linea.startswith("$$"):
                partes = linea[2:].split(";")
                bloque_actual = partes[0]
                nombres, tipos_bloque = [], []
                for campo in partes[1:]:
                    if "(" not in campo:
                        continue
                    nombre, resto = campo.split("(", 1)
                    codigo = resto.rstrip(")").split(":")[0]
                    nombres.append(nombre)
                    tipos_bloque.append(_TIPOS_POR_CODIGO.get(codigo, str))
                columnas[bloque_actual] = nombres
                tipos[bloque_actual] = tipos_bloque
                filas.setdefault(bloque_actual, [])
                continue

            if linea.startswith("*") or not linea.strip():
                continue

            if bloque_actual is not None:
                nombres = columnas[bloque_actual]
                valores = linea.strip().split(";")
                if len(valores) < len(nombres):
                    valores += [""] * (len(nombres) - len(valores))
                elif len(valores) > len(nombres):
                    valores = valores[: len(nombres)]
                filas[bloque_actual].append(valores)

    bloques: dict[str, pd.DataFrame] = {}
    for nombre_bloque, nombres in columnas.items():
        df = pd.DataFrame(filas[nombre_bloque], columns=nombres)
        for columna, tipo in zip(nombres, tipos[nombre_bloque]):
            if tipo is float:
                df[columna] = pd.to_numeric(
                    df[columna].astype(str).str.replace(",", "."), errors="coerce"
                )
            elif tipo == "Int64":
                df[columna] = pd.to_numeric(df[columna], errors="coerce").astype("Int64")
        bloques[nombre_bloque] = df
    return bloques


def columna_id(df: pd.DataFrame) -> str:
    """El identificador único de fila se llama 'ID' en exports nuevos y 'FID' en algunos antiguos."""
    if "ID" in df.columns:
        return "ID"
    if "FID" in df.columns:
        return "FID"
    raise ValueError("La tabla no tiene columna 'ID' ni 'FID'.")
