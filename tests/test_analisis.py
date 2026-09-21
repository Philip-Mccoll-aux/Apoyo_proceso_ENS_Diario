import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from digsilent_correlaciones import analisis
from digsilent_correlaciones.config import CONFIG

from fixtures import construir_modelo_sintetico


def test_distancia_haversine_valor_conocido():
    # Santiago - Valparaiso: ~100 km en línea recta (valor de referencia conocido).
    d = analisis.distancia_haversine_km(-33.4489, -70.6693, -33.0472, -71.6127)
    assert 90 < d < 110


def test_construir_grafo_filtra_fuera_de_servicio():
    modelo = construir_modelo_sintetico()
    grafo = analisis.construir_grafo(modelo, solo_en_servicio=True)
    assert grafo.number_of_nodes() == 4  # B5 está fuera de servicio
    assert "B5" not in grafo.nodes
    assert grafo.number_of_edges() == 4


def test_hoja_resumen_cuenta_elementos():
    modelo = construir_modelo_sintetico()
    grafo = analisis.construir_grafo(modelo)
    df = analisis.hoja_resumen(modelo, grafo)
    valores = dict(zip(df["Indicador"], df["Valor"]))
    assert valores["Barras totales"] == 5
    assert valores["Barras en el grafo (en servicio)"] == 4
    assert valores["Componentes conexas"] == 1


def test_matriz_adyacencia_simetrica_y_binaria():
    modelo = construir_modelo_sintetico()
    grafo = analisis.construir_grafo(modelo)
    matriz = analisis.hoja_matriz_adyacencia(grafo, umbral=200)
    assert matriz is not None
    assert (matriz.values == matriz.values.T).all()
    assert set(matriz.values.flatten()).issubset({0, 1})
    # Santiago-Rancagua están directamente conectadas.
    assert matriz.loc["Santiago", "Rancagua"] == 1
    # Santiago-Curico no están directamente conectadas.
    assert matriz.loc["Santiago", "Curico"] == 0


def test_matriz_adyacencia_none_sobre_umbral():
    modelo = construir_modelo_sintetico()
    grafo = analisis.construir_grafo(modelo)
    assert analisis.hoja_matriz_adyacencia(grafo, umbral=1) is None


def test_cercania_geografica_matriz_pequena():
    modelo = construir_modelo_sintetico()
    df = analisis.hoja_cercania_geografica(modelo, umbral=200, num_vecinos=10)
    assert "Santiago" in df.index and "Curico" in df.columns
    assert df.loc["Santiago", "Santiago"] == 0
    assert df.loc["Santiago", "Curico"] == df.loc["Curico", "Santiago"]
    assert df.loc["Santiago", "Curico"] > 0


def test_cercania_geografica_vecinos_cuando_supera_umbral():
    modelo = construir_modelo_sintetico()
    df = analisis.hoja_cercania_geografica(modelo, umbral=1, num_vecinos=2)
    assert set(df.columns) == {"barra", "vecino_cercano", "distancia_km"}
    assert (df.groupby("barra").size() <= 2).all()


def test_distancia_electrica_respeta_ruta_mas_corta():
    modelo = construir_modelo_sintetico()
    grafo = analisis.construir_grafo(modelo)
    matriz = analisis.hoja_distancia_electrica(grafo, peso="x_ohm", umbral=200, num_vecinos=10)
    assert matriz is not None
    # Rancagua-Curico: x=5.0 directo.
    assert math.isclose(matriz.loc["Rancagua", "Curico"], 5.0)
    # Santiago-Curico: min(via Rancagua = 9+5=14, via Valparaiso+Rancagua = 10+13+5=28) = 14
    assert math.isclose(matriz.loc["Santiago", "Curico"], 14.0)


def test_niveles_tension_agrupa_correctamente():
    modelo = construir_modelo_sintetico()
    df = analisis.hoja_niveles_tension(modelo)
    fila_220 = df[df["tension_kv"] == 220].iloc[0]
    assert fila_220["num_barras"] == 3
    fila_110 = df[df["tension_kv"] == 110].iloc[0]
    assert fila_110["num_barras"] == 2  # incluye la barra fuera de servicio


def test_zonas_areas_balance_generacion_carga():
    modelo = construir_modelo_sintetico()
    df = analisis.hoja_zonas_areas(modelo)
    fila_centro = df[df["zona"] == "Centro"].iloc[0]
    assert fila_centro["gen_mw"] == 300
    assert fila_centro["carga_mw"] == 120
    assert fila_centro["balance_mw"] == 180
    fila_sur = df[df["zona"] == "Sur"].iloc[0]
    assert fila_sur["carga_mw"] == 80


def test_centralidad_identifica_punto_articulacion():
    modelo = construir_modelo_sintetico()
    grafo = analisis.construir_grafo(modelo)
    df = analisis.hoja_centralidad(grafo)
    fila_rancagua = df[df["barra"] == "Rancagua"].iloc[0]
    assert fila_rancagua["punto_de_articulacion_n1"] == True  # noqa: E712
    fila_santiago = df[df["barra"] == "Santiago"].iloc[0]
    assert fila_santiago["punto_de_articulacion_n1"] == False  # noqa: E712


def test_elementos_criticos_n1_detecta_solo_la_rama_radial():
    modelo = construir_modelo_sintetico()
    grafo = analisis.construir_grafo(modelo)
    df = analisis.hoja_elementos_criticos_n1(grafo)
    assert list(df["id"]) == ["L34"]  # el anillo no tiene elementos N-1 críticos


def test_correlaciones_estadisticas_estructura():
    modelo = construir_modelo_sintetico()
    grafo = analisis.construir_grafo(modelo)
    df = analisis.hoja_correlaciones_estadisticas(modelo, grafo, peso="x_ohm")
    assert "distancia_geografica_km" in df.columns
    fila_diagonal = df[df["Pearson"] == "distancia_geografica_km"].iloc[0]
    assert math.isclose(fila_diagonal["distancia_geografica_km"], 1.0)


def test_generar_todas_las_hojas_no_lanza_excepciones():
    modelo = construir_modelo_sintetico()
    hojas = analisis.generar_todas_las_hojas(modelo, CONFIG)
    assert "Resumen" in hojas
    assert "Grafo_Electrico" in hojas
    assert "Elementos_Criticos_N1" in hojas
    for nombre, df in hojas.items():
        assert df is not None, nombre
