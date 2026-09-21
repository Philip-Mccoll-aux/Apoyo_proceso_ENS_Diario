"""Script principal: ejecutar DENTRO de DIgSILENT PowerFactory.

Formas de ejecución (ver README.md para el detalle):

1. Como "Comando externo de Python" / script de PowerFactory (recomendado):
   cree un objeto ComPython en el proyecto apuntando a este archivo y
   ejecútelo desde PowerFactory. El módulo ``powerfactory`` ya estará
   disponible automáticamente.

2. Desde un Python externo, agregando la carpeta de la API de PowerFactory
   al ``sys.path`` antes de importar ``powerfactory`` (ejemplo típico en
   Windows):

       sys.path.append(r"C:\\Program Files\\DIgSILENT\\PowerFactory 2024 SP2\\Python\\3.11")

   y con PowerFactory ya abierto con el proyecto deseado activo.
"""
from __future__ import annotations

import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "src"))

from digsilent_correlaciones import analisis, exportar_excel, extraccion_pf  # noqa: E402
from digsilent_correlaciones.config import CONFIG  # noqa: E402


def main() -> None:
    import powerfactory  # disponible solo dentro del entorno de PowerFactory

    app = powerfactory.GetApplication()
    if app is None:
        raise RuntimeError(
            "No se pudo obtener la aplicación de PowerFactory. Ejecute este "
            "script desde dentro de PowerFactory."
        )

    app.ClearOutputWindow()
    app.PrintInfo("Extrayendo modelo de red desde PowerFactory...")
    modelo = extraccion_pf.extraer_modelo(app, CONFIG)
    app.PrintInfo(
        f"Modelo extraído: {len(modelo.barras)} barras, {len(modelo.ramas)} ramas, "
        f"{len(modelo.inyecciones)} inyecciones."
    )

    app.PrintInfo("Calculando correlaciones (grafo eléctrico, cercanía geográfica, centralidad, N-1)...")
    hojas = analisis.generar_todas_las_hojas(modelo, CONFIG)

    ruta_salida = CONFIG["ruta_salida"]
    exportar_excel.exportar(hojas, ruta_salida)
    app.PrintInfo(f"Listo. Archivo generado en: {ruta_salida}")


if __name__ == "__main__":
    main()
