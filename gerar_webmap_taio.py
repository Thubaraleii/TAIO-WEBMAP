"""Webmap -- quarto produto web (só o mapa, tela cheia), com tiles reais
(zoom/pan continuo via Leaflet -- diferente dos outros 3 produtos, que usam
Plotly com imagem de fundo estática esticada). Precisa de internet quando
aberto (carrega tiles de satelite/OSM/CartoDB sob demanda), mas em troca tem
zoom infinito de verdade.

Camadas (todas do Taió -- mesmo catalogo unificado dos outros produtos):
  - Pontos de campo (308, coloridos por litologia, popup com detalhes)
  - Mapa geologico atualizado (6 formacoes) + sill/dique digitalizados
  - Dados estruturais (235 pontos classificados) + lineamentos de satelite (98)
  - Rios/estradas/localidades (OSM, so os nomeados)

Uso:
    python visualizacao_web/gerar_webmap_taio.py

Gera:
    visualizacao_web/webmap_taio.html
"""
import base64
import io
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator

BASE = Path(__file__).parent
BANCO = BASE.parent.parent / "2_Banco_de_Dados"
TOPO_NPY = BASE.parent / "dados_entrada" / "topografia_drone" / "topografia_xyz.npy"
PONTOS_CAMPO_GPKG = BANCO / "Unificação" / "GPKG_Novos" / "pontos_unificados_completo.gpkg"
PONTOS_ESTRUTURAIS_GPKG = BANCO / "Unificação" / "GPKG_Novos" / "nuvem_pontos_direcoes.gpkg"
LINEAMENTOS_GPKG = BANCO / "Unificação" / "lineamentos_direcoes.gpkg"
# litologia_processada.shp (ETL: 2_Banco_de_Dados/scripts_etl/processar_litologia_atualizada.py)
# substitui o mapa geologico real (CPRM) + o poligon_intrusiva.shp antigo --
# um shp so, com sill/dique redigitalizados (coluna "formacao") e as 6
# formacoes sedimentares, incl. deposito quaternario (coluna "tipo" ==
# "sedimentar"/"intrusiva").
LITOLOGIA_ATUALIZADA = BANCO / "dados_base" / "litologia_processada.shp"
OSM_RIOS = BANCO / "saida_processada" / "osm_rios.geojson"
OSM_ESTRADAS = BANCO / "saida_processada" / "osm_estradas.geojson"
OSM_LUGARES = BANCO / "saida_processada" / "osm_lugares.geojson"
LOGO_PATH = BASE / "assets" / "logo_gstech.jpg"
OUT_HTML = BASE / "webmap_taio.html"

MARCA_ROXO_ESCURO = "#2D0A4A"
MARCA_ROXO = "#7B2FFF"
MARCA_AZUL = "#2E6F95"
MARCA_NAVY = "#1B1F2E"
MARCA_CINZA_CLARO = "#F2F2F2"
MARCA_FONTE = "Montserrat, Arial, sans-serif"

COR_SILL = "#A63D2F"
COR_DIQUE = "#1B4332"
NOMES_CAMADAS = ["Teresina", "Serra Alta", "Irati", "Palermo", "Rio Bonito"]
CORES_CAMADAS = ["#D6C79A", "#8C8C86", "#3E362C", "#B5AE93", "#C9A66B"]
COR_QUATERNARIO = "#D9CB82"
CORES_LITOLOGIA_MAPA = dict(zip(NOMES_CAMADAS, CORES_CAMADAS))
CORES_LITOLOGIA_MAPA["Depósito quaternário"] = COR_QUATERNARIO
CORES_LITOLOGIA_CAMPO = {
    "sill_diabasio": COR_SILL, "sill_diabasio_cprm": COR_SILL,
    "dique": COR_DIQUE, "dique_cprm": COR_DIQUE,
    "encaixante_teresina": CORES_CAMADAS[0], "encaixante_serra_alta": CORES_CAMADAS[1],
    "encaixante_irati": CORES_CAMADAS[2], "encaixante_palermo": CORES_CAMADAS[3],
    "encaixante_rio_bonito": CORES_CAMADAS[4], "encaixante_sedimentar": "#999999",
}
COR_LITOLOGIA_PADRAO = "#999999"
CORES_CLASSIFICACAO_ESTRUTURAL = {
    "acamamento_sedimentar": "#C9A66B",
    "fratura_falha": "#D64545",
    "dique_provavel_relevo_positivo": "#2E7D5B",
    "dique_confirmado_mapa": COR_DIQUE,
    "falha_ou_dique_ambiguo_relevo_negativo": "#E8A33D",
    "contato_sill_encaixante": "#A63D2F",
    "fabrica_interna_intrusao": "#7B2FFF",
}
COR_CLASSIFICACAO_PADRAO = "#999999"

LABELS_LITOLOGIA_CAMPO = {
    "sill_diabasio": "Soleira (diabásio)", "sill_diabasio_cprm": "Soleira (diabásio)",
    "dique": "Dique", "dique_cprm": "Dique",
    "encaixante_teresina": "Encaixante — Teresina", "encaixante_serra_alta": "Encaixante — Serra Alta",
    "encaixante_irati": "Encaixante — Irati", "encaixante_palermo": "Encaixante — Palermo",
    "encaixante_rio_bonito": "Encaixante — Rio Bonito", "encaixante_sedimentar": "Encaixante — indefinida",
}
CORES_HIPSOMETRICAS = ["#4F9AA8", "#9FC1A3", "#D8C88C", "#C6924A", "#A66A2C"]  # mesma paleta
# (baixo -> alto, rampa invertida em 10/08/2026) usada nos outros 3 produtos
# (ver gerar_secao_interativa.py/gerar_visualizador_3d.py)
RESOLUCAO_HIPSOMETRIA = 500  # pixels/eixo do raster gerado -- so precisa boa leitura na tela,
# nao e uma textura de alta precisao (PNG comprime bem, gradiente suave em poucas cores)

LABELS_CLASSIFICACAO_ESTRUTURAL = {
    "acamamento_sedimentar": "Acamamento sedimentar",
    "fratura_falha": "Fratura/falha",
    "dique_provavel_relevo_positivo": "Dique provável (relevo +)",
    "dique_confirmado_mapa": "Dique confirmado",
    "falha_ou_dique_ambiguo_relevo_negativo": "Falha/dique ambíguo (relevo −)",
    "contato_sill_encaixante": "Contato sill/encaixante",
    "fabrica_interna_intrusao": "Fábrica interna da intrusão",
}


def logo_base64():
    if not LOGO_PATH.exists():
        return None
    return base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


def cor_hex_para_rgb(hex_cor):
    hex_cor = hex_cor.lstrip("#")
    return tuple(int(hex_cor[i:i + 2], 16) for i in (0, 2, 4))


def calcular_hillshade(gz, xs, ys, altitude=45.0, azimuth=315.0):
    """Sombreamento de relevo (hillshade) classico -- deriva slope/aspect por
    diferencas finitas (np.gradient) e aplica a formula padrao de iluminacao
    (sol a 315 graus/NO, 45 graus de altura, convencao cartografica usual).
    Devolve array 0..1 (0 = sombra total, 1 = totalmente iluminado)."""
    espaco_linha = ys[1] - ys[0]  # negativo (ys decrescente, linha 0 = norte)
    espaco_coluna = xs[1] - xs[0]
    dzdy, dzdx = np.gradient(gz, espaco_linha, espaco_coluna)
    slope = np.arctan(np.hypot(dzdx, dzdy))
    aspect = np.arctan2(-dzdx, dzdy)
    azimute_rad = np.radians(360.0 - azimuth + 90.0)
    altitude_rad = np.radians(altitude)
    sombreado = (
        np.sin(altitude_rad) * np.cos(slope)
        + np.cos(altitude_rad) * np.sin(slope) * np.cos(azimute_rad - aspect)
    )
    return np.clip(sombreado, 0.0, 1.0)


def gerar_hipsometria():
    """Raster PNG (base64) com tinta hipsometrica (mesma paleta dos outros 3
    produtos) a partir da topografia real (topografia_xyz.npy, curvas de
    nivel) -- webmap nao tem uma "camada de elevacao" pronta via tile (isso
    e dado proprio do projeto, nao um provedor publico), entao vira uma
    imagem estatica sobreposta (L.imageOverlay) com bounds reais em WGS84,
    igual a tecnica ja usada nos visualizadores 2D/3D pra hipsometria/satelite."""
    if not TOPO_NPY.exists():
        return None
    xyz = np.load(TOPO_NPY)
    xmin, ymin = xyz[:, 0].min(), xyz[:, 1].min()
    xmax, ymax = xyz[:, 0].max(), xyz[:, 1].max()

    linear = LinearNDInterpolator(xyz[:, :2], xyz[:, 2])
    nearest = NearestNDInterpolator(xyz[:, :2], xyz[:, 2])
    xs = np.linspace(xmin, xmax, RESOLUCAO_HIPSOMETRIA)
    ys = np.linspace(ymax, ymin, RESOLUCAO_HIPSOMETRIA)  # y decrescente: linha 0 = norte (topo da imagem)
    gx, gy = np.meshgrid(xs, ys)
    gz = linear(gx, gy)
    faltando = np.isnan(gz)
    if faltando.any():
        gz[faltando] = nearest(gx[faltando], gy[faltando])

    zmin, zmax = float(np.nanmin(gz)), float(np.nanmax(gz))
    t = np.clip((gz - zmin) / (zmax - zmin), 0.0, 1.0)
    paleta = np.array([cor_hex_para_rgb(c) for c in CORES_HIPSOMETRICAS], dtype=float)
    n_trechos = len(paleta) - 1
    posicao = t * n_trechos
    idx = np.clip(posicao.astype(int), 0, n_trechos - 1)
    frac = (posicao - idx)[..., None]
    rgb = paleta[idx] + (paleta[idx + 1] - paleta[idx]) * frac

    # multiplica pela textura de sombreamento do relevo (hillshade) -- reescala
    # de 0..1 pra 0.45..1.1 antes de multiplicar, senao as encostas em sombra
    # total (perto de 0) apagavam a cor por completo (preto puro); assim a
    # cor hipsometrica continua legivel em qualquer face, so modulada pela
    # textura do relevo (mais clara nas faces viradas pro sol, mais escura
    # nas faces em sombra) -- efeito classico de mapa hipsometrico + relevo.
    sombra = calcular_hillshade(gz, xs, ys)
    sombra_ajustada = (0.45 + 0.65 * sombra)[..., None]
    rgb = np.clip(rgb * sombra_ajustada, 0, 255).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(buf, format="PNG", optimize=True)
    png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    transformer = Transformer.from_crs("EPSG:31982", "EPSG:4326", always_xy=True)
    lon_min, lat_min = transformer.transform(xmin, ymin)
    lon_max, lat_max = transformer.transform(xmax, ymax)
    return png_b64, [[lat_min, lon_min], [lat_max, lon_max]]


def para_wgs84(gdf):
    if gdf.crs is None:
        gdf = gdf.set_crs(31982)
    return gdf.to_crs(4326)


def carregar_campo():
    gdf = para_wgs84(gpd.read_file(PONTOS_CAMPO_GPKG))
    gdf["cor"] = gdf["litologia_padronizada"].map(CORES_LITOLOGIA_CAMPO).fillna(COR_LITOLOGIA_PADRAO)
    gdf["categoria"] = gdf["litologia_padronizada"].map(LABELS_LITOLOGIA_CAMPO).fillna("Outra/indefinida")
    gdf["popup"] = gdf.apply(lambda r: (
        f"<b>{r['ponto_id']}</b><br>"
        f"Litologia: {r['litologia_padronizada'] or '—'}<br>"
        f"Tipo: {r['tipo_ponto'] or '—'}<br>"
        f"Qualidade: {r['qualidade_dado'] or '—'}<br>"
        + (f"Geoquímica: {r['geoquimica']} ({r['ti_geoquimico']})<br>" if r.get("geoquimica") == "Sim" else "")
        + (f"<br>{r['descricao_campo']}" if r.get("descricao_campo") else "")
    ), axis=1)
    return gdf[["ponto_id", "cor", "categoria", "popup", "geometry"]]


def carregar_estrutural():
    gdf = para_wgs84(gpd.read_file(PONTOS_ESTRUTURAIS_GPKG))
    gdf["cor"] = gdf["classificacao"].map(CORES_CLASSIFICACAO_ESTRUTURAL).fillna(COR_CLASSIFICACAO_PADRAO)
    gdf["categoria"] = gdf["classificacao"].map(LABELS_CLASSIFICACAO_ESTRUTURAL).fillna("Outra estrutura")
    gdf["popup"] = gdf.apply(lambda r: (
        f"<b>{r['ponto_id']}</b><br>"
        f"Classificação: {r['classificacao']}<br>"
        f"Formação: {r['formacao'] or '—'}<br>"
        f"Azimute/Strike: {r['azimute_ou_strike_deg']:.0f}°" if r["azimute_ou_strike_deg"] == r["azimute_ou_strike_deg"] else f"<b>{r['ponto_id']}</b><br>Classificação: {r['classificacao']}"
    ), axis=1)
    return gdf[["ponto_id", "classificacao", "cor", "categoria", "popup", "geometry"]]


def carregar_lineamentos():
    gdf = para_wgs84(gpd.read_file(LINEAMENTOS_GPKG))
    gdf["cor"] = gdf["tipo"].map({"Positivo": "#2E7D5B", "Negativo": "#E8A33D"}).fillna("#999999")
    gdf["categoria"] = gdf["tipo"]
    gdf["popup"] = gdf.apply(lambda r: (
        f"<b>Lineamento {r['tipo']}</b><br>"
        f"Azimute: {r['azimute_deg']:.0f}°<br>"
        f"Comprimento: {r['comprimento_m']:.0f} m<br>"
        f"Formação predominante: {r['formacao_cprm_predominante'] or '—'}"
    ), axis=1)
    return gdf[["tipo", "cor", "categoria", "popup", "geometry"]]


def carregar_intrusiva():
    gdf_lito = gpd.read_file(LITOLOGIA_ATUALIZADA)
    gdf = gdf_lito.loc[gdf_lito["tipo"] == "intrusiva", ["formacao", "geometry"]].rename(columns={"formacao": "tipo"})
    gdf = para_wgs84(gdf)
    gdf["cor"] = gdf["tipo"].map({"Soleira": COR_SILL, "Dique": COR_DIQUE}).fillna("#999999")
    gdf["categoria"] = gdf["tipo"]
    gdf["popup"] = gdf["tipo"]
    return gdf[["tipo", "cor", "categoria", "popup", "geometry"]]


def carregar_formacoes():
    gdf_lito = gpd.read_file(LITOLOGIA_ATUALIZADA)
    gdf = para_wgs84(gdf_lito[gdf_lito["tipo"] == "sedimentar"])
    gdf["cor"] = gdf["formacao"].map(CORES_LITOLOGIA_MAPA).fillna("#CCCCCC")
    gdf["categoria"] = gdf["formacao"]
    gdf["popup"] = gdf["formacao"]
    return gdf[["formacao", "cor", "categoria", "popup", "geometry"]]


def carregar_osm(caminho, rotulo, categoria):
    if not caminho.exists():
        return None
    gdf = para_wgs84(gpd.read_file(caminho))
    gdf = gdf.dropna(subset=["name"])
    gdf["popup"] = gdf["name"]
    gdf["categoria"] = categoria
    cols = ["name", "popup", "categoria", "geometry"]
    if "place" in gdf.columns:
        cols.insert(1, "place")
    return gdf[cols]


def main():
    print("Carregando camadas...")
    campo = carregar_campo()
    print(f"  campo: {len(campo)} pontos")
    estrutural = carregar_estrutural()
    print(f"  estrutural: {len(estrutural)} pontos")
    lineamentos = carregar_lineamentos()
    print(f"  lineamentos: {len(lineamentos)} linhas")
    intrusiva = carregar_intrusiva()
    print(f"  sill/dique: {len(intrusiva)} polígonos")
    formacoes = carregar_formacoes()
    print(f"  formações: {len(formacoes)} polígonos")
    rios = carregar_osm(OSM_RIOS, "rios", "Rio")
    estradas = carregar_osm(OSM_ESTRADAS, "estradas", "Estrada")
    lugares = carregar_osm(OSM_LUGARES, "lugares", "Localidade")
    print(f"  OSM: {len(rios) if rios is not None else 0} rios, "
          f"{len(estradas) if estradas is not None else 0} estradas, "
          f"{len(lugares) if lugares is not None else 0} lugares")

    print("Gerando raster de hipsometria...")
    hipsometria = gerar_hipsometria()
    print(f"  hipsometria: {'ok' if hipsometria else 'topografia_xyz.npy não encontrado, pulando'}")

    centro_lat = (campo.total_bounds[1] + campo.total_bounds[3]) / 2
    centro_lon = (campo.total_bounds[0] + campo.total_bounds[2]) / 2

    geojson_campo = json.loads(campo.to_json())
    geojson_estrutural = json.loads(estrutural.to_json())
    geojson_lineamentos = json.loads(lineamentos.to_json())
    geojson_intrusiva = json.loads(intrusiva.to_json())
    geojson_formacoes = json.loads(formacoes.to_json())
    geojson_rios = json.loads(rios.to_json()) if rios is not None else None
    geojson_estradas = json.loads(estradas.to_json()) if estradas is not None else None
    geojson_lugares = json.loads(lugares.to_json()) if lugares is not None else None

    logo_b64 = logo_base64()

    if hipsometria:
        hipso_b64, hipso_bounds = hipsometria
        trecho_hipsometria_js = (
            "var hipsometria = L.imageOverlay('data:image/png;base64," + hipso_b64 + "', "
            + json.dumps(hipso_bounds) + ", { opacity: 1 });"
        )
    else:
        trecho_hipsometria_js = "var hipsometria = null;"

    formacoes_itens = (
        formacoes.drop_duplicates(subset=["formacao", "cor"])[["formacao", "cor"]]
        .sort_values("formacao")
        .rename(columns={"formacao": "label"})
        .to_dict("records")
    )
    legenda_data = {
        "Pontos de campo": {"tipo": "ponto", "itens": [
            {"cor": cor, "label": LABELS_LITOLOGIA_CAMPO.get(k, k)}
            for k, cor in {
                "sill_diabasio": COR_SILL, "dique": COR_DIQUE,
                "encaixante_teresina": CORES_CAMADAS[0], "encaixante_serra_alta": CORES_CAMADAS[1],
                "encaixante_irati": CORES_CAMADAS[2], "encaixante_palermo": CORES_CAMADAS[3],
                "encaixante_rio_bonito": CORES_CAMADAS[4],
            }.items()
        ] + [{"cor": COR_LITOLOGIA_PADRAO, "label": "Outra/indefinida"}]},
        "Mapa geológico atualizado": {"tipo": "area", "itens": [
            {"cor": it["cor"], "label": it["label"]} for it in formacoes_itens
        ]},
        "Sill/Dique": {"tipo": "area", "itens": [
            {"cor": COR_SILL, "label": "Soleira"}, {"cor": COR_DIQUE, "label": "Dique"},
        ]},
        "Dados estruturais": {"tipo": "ponto", "itens": [
            {"cor": cor, "label": LABELS_CLASSIFICACAO_ESTRUTURAL.get(k, k)}
            for k, cor in CORES_CLASSIFICACAO_ESTRUTURAL.items()
        ] + [{"cor": COR_CLASSIFICACAO_PADRAO, "label": "Outra estrutura"}]},
        "Lineamentos (satélite)": {"tipo": "linha", "itens": [
            {"cor": "#2E7D5B", "label": "Positivo"}, {"cor": "#E8A33D", "label": "Negativo"},
        ]},
    }
    if geojson_rios is not None:
        legenda_data["Rios"] = {"tipo": "linha", "itens": [{"cor": "#2E6F95", "label": "Rio"}]}
    if geojson_estradas is not None:
        legenda_data["Estradas"] = {"tipo": "linha", "itens": [{"cor": "#4A4A4A", "label": "Estrada"}]}
    if geojson_lugares is not None:
        legenda_data["Localidades"] = {"tipo": "ponto", "itens": [{"cor": MARCA_ROXO, "label": "Localidade"}]}

    print("Montando HTML final...")
    html = f"""<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" type="image/png" href="assets/favicon.png">
<link rel="shortcut icon" href="assets/favicon.ico">
<link rel="apple-touch-icon" href="assets/apple-touch-icon.png">
<title>Webmap Taió — Sistema Alimentador</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; height: 100%; font-family: {MARCA_FONTE}; background: {MARCA_NAVY}; }}
  #map {{ position: absolute; top: 0; bottom: 0; left: 0; right: 0; background: {MARCA_NAVY}; }}
  #cabecalho {{
    position: absolute; top: 12px; left: 50%; transform: translateX(-50%); z-index: 1000;
    display: flex; align-items: center; gap: 10px; background: rgba(27,31,46,0.88);
    border: 1px solid {MARCA_ROXO}; border-radius: 10px; padding: 8px 16px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  }}
  #cabecalho img {{ width: 34px; height: 34px; border-radius: 50%; border: 1.5px solid {MARCA_ROXO}; }}
  #cabecalho h1 {{ font-size: 15px; margin: 0; color: {MARCA_CINZA_CLARO}; white-space: nowrap; }}
  #cabecalho h1 b {{ color: {MARCA_ROXO}; }}
  .leaflet-popup-content-wrapper {{ background: {MARCA_ROXO_ESCURO}; color: {MARCA_CINZA_CLARO}; border: 1px solid {MARCA_ROXO}; }}
  .leaflet-popup-tip {{ background: {MARCA_ROXO_ESCURO}; }}
  .leaflet-popup-content {{ font-family: {MARCA_FONTE}; font-size: 12px; }}
  .leaflet-control-layers {{ background: {MARCA_ROXO_ESCURO} !important; color: {MARCA_CINZA_CLARO}; border: 1px solid {MARCA_ROXO} !important; }}
  .leaflet-control-layers-toggle {{ filter: invert(1); }}
  #legenda {{
    background: rgba(45,10,74,0.92); color: {MARCA_CINZA_CLARO}; border: 1px solid {MARCA_ROXO};
    border-radius: 6px; padding: 8px 10px; font-size: 11px; max-width: 200px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4); display: flex; flex-direction: column;
  }}
  #legenda h4 {{ margin: 0 0 4px 0; font-size: 11px; color: {MARCA_ROXO}; text-transform: uppercase; letter-spacing: 0.03em; flex-shrink: 0; }}
  #legenda .legenda-corpo {{ overflow-y: auto; max-height: 42vh; padding-right: 4px; }}
  #legenda .legenda-corpo::-webkit-scrollbar {{ width: 6px; }}
  #legenda .legenda-corpo::-webkit-scrollbar-track {{ background: transparent; }}
  #legenda .legenda-corpo::-webkit-scrollbar-thumb {{ background: {MARCA_ROXO}; border-radius: 3px; }}
  #legenda .secao {{ margin-bottom: 6px; }}
  #legenda .secao:last-child {{ margin-bottom: 0; }}
  #legenda .secao-titulo {{
    font-weight: 600; opacity: 0.85; margin-bottom: 2px; display: flex; align-items: center; gap: 5px;
    cursor: pointer; border-radius: 4px; padding: 2px 3px; transition: background 0.12s;
  }}
  #legenda .secao-titulo:hover {{ background: rgba(123,47,255,0.25); }}
  #legenda .secao-titulo .marca {{ font-size: 10px; width: 11px; flex-shrink: 0; text-align: center; }}
  #legenda .secao.inativa .secao-titulo {{ opacity: 0.5; text-decoration: line-through; }}
  #legenda .item {{
    display: flex; align-items: center; gap: 6px; line-height: 1.5; padding: 1px 3px 1px 16px;
    cursor: pointer; border-radius: 4px; transition: background 0.12s;
  }}
  #legenda .item:hover {{ background: rgba(123,47,255,0.25); }}
  #legenda .item.item-inativa {{ opacity: 0.4; text-decoration: line-through; }}
  #legenda .item .marca-item {{ font-size: 9px; width: 10px; flex-shrink: 0; text-align: center; }}
  #legenda .amostra {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; border: 1px solid rgba(255,255,255,0.5); }}
  #legenda .amostra.linha {{ width: 14px; height: 3px; border-radius: 0; border: none; }}
  #legenda .amostra.area {{ border-radius: 2px; }}
  footer {{
    position: absolute; bottom: 4px; left: 50%; transform: translateX(-50%); z-index: 1000;
    font-size: 10px; color: {MARCA_CINZA_CLARO}; opacity: 0.6; pointer-events: none;
  }}
</style>
</head>
<body>
<div id="map"></div>
<div id="cabecalho">
  {f'<img src="data:image/jpeg;base64,{logo_b64}">' if logo_b64 else ''}
  <h1><b>Webmap Taió</b> — Sistema Alimentador (Soleira/Dique)</h1>
</div>
<footer>Criado por Afonso Henrique de Jesus</footer>
<script>
(function() {{
    var map = L.map('map', {{ zoomControl: true }}).setView([{centro_lat}, {centro_lon}], 11);

    // ---- basemaps (tiles reais, precisam de internet) ----
    var satelite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        attribution: 'Esri World Imagery', maxZoom: 19,
    }});
    var rico = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png', {{
        attribution: '&copy; OpenStreetMap &copy; CARTO', maxZoom: 20, subdomains: 'abcd',
    }});
    var escuro = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
        attribution: '&copy; OpenStreetMap &copy; CARTO', maxZoom: 20, subdomains: 'abcd',
    }});
    var osmPadrao = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        attribution: '&copy; OpenStreetMap contributors', maxZoom: 19,
    }});
    var relevo = L.tileLayer('https://{{s}}.tile.opentopomap.org/{{z}}/{{x}}/{{y}}.png', {{
        attribution: '&copy; OpenStreetMap contributors, SRTM &copy; OpenTopoMap (CC-BY-SA)',
        maxZoom: 17, subdomains: 'abc',
    }});
    {trecho_hipsometria_js}
    satelite.addTo(map);

    // ---- overlays ----
    function pontoEstilo(cor, raio) {{
        return {{ radius: raio, fillColor: cor, color: '{MARCA_CINZA_CLARO}', weight: 1, fillOpacity: 0.9 }};
    }}

    // rastreia sub-camadas por (nome da camada, categoria) pra permitir ligar/desligar item a item na legenda
    var subCamadas = {{}};
    function registrarSub(nome, f, layer) {{
        var cat = f.properties.categoria || 'Outro';
        if (!subCamadas[nome]) subCamadas[nome] = {{}};
        if (!subCamadas[nome][cat]) subCamadas[nome][cat] = [];
        subCamadas[nome][cat].push(layer);
    }}

    var campoLayer = L.geoJSON({json.dumps(geojson_campo, ensure_ascii=False)}, {{
        pointToLayer: function(f, latlng) {{ return L.circleMarker(latlng, pontoEstilo(f.properties.cor, 5)); }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup(f.properties.popup);
            registrarSub('Pontos de campo', f, layer);
        }},
    }});

    var estruturalLayer = L.geoJSON({json.dumps(geojson_estrutural, ensure_ascii=False)}, {{
        pointToLayer: function(f, latlng) {{ return L.circleMarker(latlng, pontoEstilo(f.properties.cor, 6)); }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup(f.properties.popup);
            registrarSub('Dados estruturais', f, layer);
        }},
    }});

    var lineamentosLayer = L.geoJSON({json.dumps(geojson_lineamentos, ensure_ascii=False)}, {{
        style: function(f) {{ return {{ color: f.properties.cor, weight: 2, dashArray: '4,3' }}; }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup(f.properties.popup);
            registrarSub('Lineamentos (satélite)', f, layer);
        }},
    }});

    var intrusivaLayer = L.geoJSON({json.dumps(geojson_intrusiva, ensure_ascii=False)}, {{
        style: function(f) {{ return {{ color: '#000', weight: 1, fillColor: f.properties.cor, fillOpacity: 0.75 }}; }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup(f.properties.popup);
            registrarSub('Sill/Dique', f, layer);
        }},
    }});

    var formacoesLayer = L.geoJSON({json.dumps(geojson_formacoes, ensure_ascii=False)}, {{
        style: function(f) {{ return {{ color: '#000', weight: 0.5, fillColor: f.properties.cor, fillOpacity: 0.55 }}; }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup(f.properties.popup);
            registrarSub('Mapa geológico real (CPRM)', f, layer);
        }},
    }});
"""

    if geojson_rios is not None:
        html += f"""
    var riosLayer = L.geoJSON({json.dumps(geojson_rios, ensure_ascii=False)}, {{
        style: {{ color: '#2E6F95', weight: 2 }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup('Rio ' + f.properties.popup);
            registrarSub('Rios', f, layer);
        }},
    }});
"""
    if geojson_estradas is not None:
        html += f"""
    var estradasLayer = L.geoJSON({json.dumps(geojson_estradas, ensure_ascii=False)}, {{
        style: {{ color: '#4A4A4A', weight: 2 }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup('Estrada ' + f.properties.popup);
            registrarSub('Estradas', f, layer);
        }},
    }});
"""
    if geojson_lugares is not None:
        html += f"""
    var lugaresLayer = L.geoJSON({json.dumps(geojson_lugares, ensure_ascii=False)}, {{
        pointToLayer: function(f, latlng) {{
            return L.marker(latlng, {{
                icon: L.divIcon({{
                    className: '', html: '<div style="color:{MARCA_ROXO};font-size:20px;text-shadow:0 0 3px black;">&#9660;</div>',
                    iconSize: [20, 20], iconAnchor: [10, 10],
                }}),
            }});
        }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup(f.properties.popup);
            registrarSub('Localidades', f, layer);
        }},
    }}).addTo(map);
"""

    html += """
    formacoesLayer.addTo(map);
    intrusivaLayer.addTo(map);
    campoLayer.addTo(map);

    var basemaps = {
        "Rico (CartoDB Voyager)": rico,
        "Satélite (Esri)": satelite,
        "Relevo/Topográfico": relevo,
        "Escuro (CartoDB Dark)": escuro,
        "OSM Padrão": osmPadrao,
    };
    var overlays = {
        "Pontos de campo": campoLayer,
        "Mapa geológico atualizado": formacoesLayer,
        "Sill/Dique": intrusivaLayer,
        "Dados estruturais": estruturalLayer,
        "Lineamentos (satélite)": lineamentosLayer,
    };
"""
    if hipsometria:
        html += '    basemaps["Hipsometria"] = hipsometria;\n'
    if geojson_rios is not None:
        html += '    overlays["Rios"] = riosLayer;\n'
    if geojson_estradas is not None:
        html += '    overlays["Estradas"] = estradasLayer;\n'
    if geojson_lugares is not None:
        html += '    overlays["Localidades"] = lugaresLayer;\n'

    html += """
    L.control.layers(basemaps, overlays, { collapsed: false }).addTo(map);
    L.control.scale({ metric: true, imperial: false }).addTo(map);

    // ---- legenda dinâmica: mostra só as seções das camadas ativas no mapa ----
    var legendaDados = """ + json.dumps(legenda_data, ensure_ascii=False) + """;
    var LegendaControl = L.Control.extend({
        options: { position: 'topright' },
        onAdd: function() {
            var div = L.DomUtil.create('div', 'leaflet-control');
            div.id = 'legenda';
            L.DomEvent.disableClickPropagation(div);
            L.DomEvent.disableScrollPropagation(div);
            this._div = div;
            return div;
        },
    });
    var legendaControl = new LegendaControl();
    legendaControl.addTo(map);

    function amostraHtml(tipo, cor) {
        if (tipo === 'linha') return '<span class="amostra linha" style="background:' + cor + '"></span>';
        if (tipo === 'area') return '<span class="amostra area" style="background:' + cor + '"></span>';
        return '<span class="amostra" style="background:' + cor + '"></span>';
    }

    function itemVisivel(nome, categoria) {
        var grupo = overlays[nome];
        var lista = (subCamadas[nome] && subCamadas[nome][categoria]) || [];
        if (!lista.length) return true;
        return lista.some(function(l) { return grupo.hasLayer(l); });
    }

    function atualizarLegenda() {
        var corpo = '';
        Object.keys(overlays).forEach(function(nome) {
            if (!legendaDados[nome]) return;
            var ativa = map.hasLayer(overlays[nome]);
            var info = legendaDados[nome];
            corpo += '<div class="secao' + (ativa ? '' : ' inativa') + '">';
            corpo += '<div class="secao-titulo" data-camada="' + nome + '" title="Ligar/desligar toda a camada">'
                   + '<span class="marca">' + (ativa ? '&#9745;' : '&#9744;') + '</span>' + nome + '</div>';
            info.itens.forEach(function(it) {
                var vis = itemVisivel(nome, it.label);
                corpo += '<div class="item' + (vis ? '' : ' item-inativa') + '" data-camada="' + nome + '" data-categoria="'
                       + it.label.replace(/"/g, '&quot;') + '" title="Ligar/desligar só este item">'
                       + '<span class="marca-item">' + (vis ? '&#9745;' : '&#9744;') + '</span>'
                       + amostraHtml(info.tipo, it.cor) + '<span>' + it.label + '</span></div>';
            });
            corpo += '</div>';
        });
        legendaControl._div.innerHTML = '<h4>Legenda (clique p/ ligar/desligar)</h4><div class="legenda-corpo">' + corpo + '</div>';

        legendaControl._div.querySelectorAll('.secao-titulo').forEach(function(el) {
            el.addEventListener('click', function() {
                var nome = el.getAttribute('data-camada');
                var layer = overlays[nome];
                if (map.hasLayer(layer)) {
                    map.removeLayer(layer);
                } else {
                    map.addLayer(layer);
                }
                atualizarLegenda();
            });
        });
        legendaControl._div.querySelectorAll('.item').forEach(function(el) {
            el.addEventListener('click', function() {
                var nome = el.getAttribute('data-camada');
                var categoria = el.getAttribute('data-categoria');
                var grupo = overlays[nome];
                var lista = (subCamadas[nome] && subCamadas[nome][categoria]) || [];
                if (!lista.length) return;
                var vis = lista.some(function(l) { return grupo.hasLayer(l); });
                lista.forEach(function(l) {
                    if (vis) grupo.removeLayer(l); else grupo.addLayer(l);
                });
                atualizarLegenda();
            });
        });
    }

    map.on('overlayadd', atualizarLegenda);
    map.on('overlayremove', atualizarLegenda);
    map.on('baselayerchange', atualizarLegenda);
    atualizarLegenda();
})();
</script>
</body>
</html>
"""

    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"Salvo em: {OUT_HTML}")


if __name__ == "__main__":
    main()
