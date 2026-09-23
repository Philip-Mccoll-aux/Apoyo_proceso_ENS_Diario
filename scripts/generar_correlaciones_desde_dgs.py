"""Genera el Excel de correlaciones a partir de un archivo .dgs exportado de
PowerFactory (File -> Export -> DGS). No requiere PowerFactory instalado ni
licencia: corre con Python puro.

Uso:
    python scripts/generar_correlaciones_desde_dgs.py ruta/al/modelo.dgs
    python scripts/generar_correlaciones_desde_dgs.py ruta/al/modelo.dgs -o salida.xlsx
"""
from __future__ import annotations

import argparse
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "src"))

from digsilent_correlaciones import analisis, exportar_excel  # noqa: E402
from digsilent_correlaciones.config import CONFIG  # noqa: E402
from digsilent_correlaciones.extraccion_dgs import dgs_a_modelo  # noqa: E402
from digsilent_correlaciones.lector_dgs import leer_bloques_dgs  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ruta_dgs", help="Ruta al archivo .dgs exportado de PowerFactory")
    parser.add_argument(
        "-o", "--salida", default=None, help="Ruta del Excel de salida (por defecto, la de config.py)"
    )
    args = parser.parse_args()

    print(f"Leyendo {args.ruta_dgs}...")
    bloques = leer_bloques_dgs(args.ruta_dgs)
    nombre_proyecto = os.path.splitext(os.path.basename(args.ruta_dgs))[0]
    modelo = dgs_a_modelo(bloques, CONFIG, nombre_proyecto=nombre_proyecto)
    print(
        f"Modelo extraído: {len(modelo.barras)} barras, {len(modelo.ramas)} ramas, "
        f"{len(modelo.inyecciones)} inyecciones."
    )

    print("Calculando correlaciones...")
    hojas = analisis.generar_todas_las_hojas(modelo, CONFIG)

    ruta_salida = args.salida or CONFIG["ruta_salida"]
    exportar_excel.exportar(hojas, ruta_salida)
    print(f"Listo. Archivo generado en: {ruta_salida}")


if __name__ == "__main__":
    main()
