import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from digsilent_correlaciones import analisis
from digsilent_correlaciones.config import CONFIG
from digsilent_correlaciones.extraccion_dgs import dgs_a_modelo
from digsilent_correlaciones.lector_dgs import leer_bloques_dgs

from fixtures_dgs import TEXTO_DGS_SINTETICO


def _modelo_de_prueba(tmp_path):
    ruta = tmp_path / "modelo_prueba.dgs"
    ruta.write_text(TEXTO_DGS_SINTETICO, encoding="utf-8")
    bloques = leer_bloques_dgs(str(ruta))
    return dgs_a_modelo(bloques, CONFIG, nombre_proyecto="Proyecto de prueba (DGS)")


def test_leer_bloques_reconoce_todas_las_secciones(tmp_path):
    ruta = tmp_path / "modelo_prueba.dgs"
    ruta.write_text(TEXTO_DGS_SINTETICO, encoding="utf-8")
    bloques = leer_bloques_dgs(str(ruta))
    assert set(bloques.keys()) == {
        "ElmTerm", "StaCubic", "ElmLne", "TypLne", "ElmTr2", "TypTr2", "ElmSym", "ElmLod",
    }
    assert len(bloques["ElmTerm"]) == 5
    assert len(bloques["ElmLne"]) == 3


def test_decimales_con_coma_se_parsean_como_float(tmp_path):
    ruta = tmp_path / "modelo_prueba.dgs"
    ruta.write_text(TEXTO_DGS_SINTETICO, encoding="utf-8")
    bloques = leer_bloques_dgs(str(ruta))
    fila = bloques["TypLne"].iloc[0]
    assert math.isclose(fila["rline"], 0.01)
    assert math.isclose(fila["xline"], 0.1)


def test_barras_y_coordenadas(tmp_path):
    modelo = _modelo_de_prueba(tmp_path)
    assert len(modelo.barras) == 5
    santiago = next(b for b in modelo.barras if b.nombre == "Santiago")
    assert santiago.tension_kv == 220
    assert santiago.en_servicio is True
    assert math.isclose(santiago.lat, -33.4489)
    assert santiago.zona == "Centro"
    fuera_servicio = next(b for b in modelo.barras if b.nombre == "FueraDeServicio")
    assert fuera_servicio.en_servicio is False
    assert not fuera_servicio.tiene_coordenadas


def test_grafo_topologia_correcta(tmp_path):
    modelo = _modelo_de_prueba(tmp_path)
    grafo = analisis.construir_grafo(modelo, solo_en_servicio=True)
    assert grafo.number_of_nodes() == 4  # barra 5 excluida por estar fuera de servicio
    assert grafo.number_of_edges() == 4  # 3 lineas + 1 trafo
    assert grafo.has_edge("1", "2")  # Santiago-Valparaiso
    assert grafo.has_edge("3", "4")  # Rancagua-Curico (via trafo)
    assert not grafo.has_edge("1", "4")


def test_impedancia_linea_calculada_desde_typlne(tmp_path):
    modelo = _modelo_de_prueba(tmp_path)
    linea = next(r for r in modelo.ramas if r.nombre == "Santiago-Valparaiso")
    assert math.isclose(linea.r_ohm, 1.0)  # 100 km * 0.01 ohm/km
    assert math.isclose(linea.x_ohm, 10.0)  # 100 km * 0.1 ohm/km


def test_impedancia_trafo_calculada_desde_typtr2(tmp_path):
    modelo = _modelo_de_prueba(tmp_path)
    trafo = next(r for r in modelo.ramas if r.tipo == "Trafo2")
    # z_base = 100^2/100 = 100 ohm; zsc_pu=0.1; rsc_pu=(100/1000)/100=0.001
    z_base, zsc_pu, rsc_pu = 100.0, 0.1, 0.001
    xsc_pu = math.sqrt(zsc_pu**2 - rsc_pu**2)
    assert math.isclose(trafo.r_ohm, rsc_pu * z_base, rel_tol=1e-6)
    assert math.isclose(trafo.x_ohm, xsc_pu * z_base, rel_tol=1e-6)


def test_generadores_y_cargas_conectados_a_su_barra(tmp_path):
    modelo = _modelo_de_prueba(tmp_path)
    assert len(modelo.generadores) == 1
    assert modelo.generadores[0].barra == "1"
    assert modelo.generadores[0].p_mw == 300
    cargas = {c.barra: c.p_mw for c in modelo.cargas}
    assert cargas == {"4": 80, "3": 120}


def test_pipeline_completo_genera_todas_las_hojas(tmp_path):
    modelo = _modelo_de_prueba(tmp_path)
    hojas = analisis.generar_todas_las_hojas(modelo, CONFIG)
    assert "Elementos_Criticos_N1" in hojas
    criticos = hojas["Elementos_Criticos_N1"]
    assert list(criticos["nombre"]) == ["Rancagua-Curico"]  # única rama radial
