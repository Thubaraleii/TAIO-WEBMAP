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
import pandas as pd
from PIL import Image
from pyproj import Transformer
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
from shapely.geometry import Point

BASE = Path(__file__).parent
BANCO = BASE.parent.parent / "2_Banco_de_Dados"
TOPO_NPY = BASE.parent / "dados_entrada" / "topografia_drone" / "topografia_xyz.npy"
PONTOS_CAMPO_GPKG = BANCO / "Unificação" / "GPKG_Novos" / "pontos_unificados_completo.gpkg"
PONTOS_ESTRUTURAIS_GPKG = BANCO / "Unificação" / "GPKG_Novos" / "nuvem_pontos_direcoes.gpkg"
LINEAMENTOS_GPKG = BANCO / "Unificação" / "lineamentos_direcoes.gpkg"
# base regional (ETL: 2_Banco_de_Dados/scripts_etl/exportar_geologia_regional_sc.py e atualizar_base_0711.py)
GEOLOGIA_REGIONAL_GPKG = BANCO / "dados_base" / "geologia_regional_sc.gpkg"
POCOS_GPKG = BANCO / "Unificação" / "pocos_regionais.gpkg"
PANORAMA_UTM = (440000.0, 6930000.0, 790000.0, 7110000.0)  # mesmo recorte do 3D regional
# litologia_processada.shp (ETL: 2_Banco_de_Dados/scripts_etl/processar_litologia_atualizada.py)
# substitui o mapa geologico real (CPRM) + o poligon_intrusiva.shp antigo --
# um shp so, com sill/dique redigitalizados (coluna "formacao") e as 6
# formacoes sedimentares, incl. deposito quaternario (coluna "tipo" ==
# "sedimentar"/"intrusiva").
LITOLOGIA_ATUALIZADA = BANCO / "dados_base" / "litologia_processada.shp"
GEOQUIMICA_CSV = BANCO / "QMC_TAIO_TODOS" / "geoquimica_dashboard.csv"
OSM_RIOS = BANCO / "saida_processada" / "osm_rios.geojson"
OSM_ESTRADAS = BANCO / "saida_processada" / "osm_estradas.geojson"
OSM_LUGARES = BANCO / "saida_processada" / "osm_lugares.geojson"
LOGO_PATH = BASE / "assets" / "logo_gstech.jpg"
OUT_HTML = BASE / "webmap_taio.html"

MARCA_ROXO_ESCURO = "#2D0A4A"
MARCA_ROXO = "#7B2FFF"
MARCA_NAVY = "#1B1F2E"
MARCA_CINZA_CLARO = "#F2F2F2"
MARCA_FONTE = "Montserrat, Arial, sans-serif"

COR_SILL = "#49B18C"
COR_DIQUE = "#AFEC7C"
COR_TI_ALTO = "#E67E22"
COR_TI_BAIXO = "#2E86C1"
NOMES_CAMADAS = ["Teresina", "Serra Alta", "Irati", "Palermo", "Rio Bonito"]
CORES_CAMADAS = ["#F8B6A0", "#FB8D74", "#C8625D", "#FF7757", "#E3644F"]  # paleta do mapa geologico (Teresina, Serra Alta, Irati, Palermo, Rio Bonito)
COR_QUATERNARIO = "#FFFBC2"
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
        f"<b>{r['nome_itc'] or r['ponto_id']}</b> ({r['ponto_id']})<br>"
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


def carregar_geoquimica():
    """Geoquimica bruta real (QMC_TAIO_TODOS, 41 amostras), coloridas por
    classificacao Alto/Baixo-Ti. 3 amostras de referencia sem coordenada real
    ficam de fora; as com ponto_id mas sem utm_e/utm_n na planilha (ex.:
    ITC-44B) usam a coordenada do ponto de campo correspondente."""
    df = pd.read_csv(GEOQUIMICA_CSV)
    if PONTOS_CAMPO_GPKG.exists():
        gdf_campo_bruto = gpd.read_file(PONTOS_CAMPO_GPKG)
        coord_campo = {row.ponto_id: (row.geometry.x, row.geometry.y) for row in gdf_campo_bruto.itertuples()}
        for i, row in df.iterrows():
            if pd.isna(row["utm_e"]) and pd.notna(row["ponto_id"]):
                xy = coord_campo.get(row["ponto_id"])
                if xy:
                    df.loc[i, "utm_e"], df.loc[i, "utm_n"] = xy
    df = df.dropna(subset=["utm_e", "utm_n"])
    gdf = gpd.GeoDataFrame(
        df, geometry=[Point(x, y) for x, y in zip(df["utm_e"], df["utm_n"])], crs=31982
    )
    gdf = para_wgs84(gdf)
    gdf["cor"] = gdf["classificacao_ti"].map({"Alto-Ti": COR_TI_ALTO, "Baixo-Ti": COR_TI_BAIXO}).fillna("#999999")
    gdf["categoria"] = gdf["classificacao_ti"].fillna("Sem dado")
    gdf["popup"] = gdf.apply(lambda r: (
        f"<b>{r['amostra']}</b> ({r['classificacao_ti']})<br>{r['origem']}<br>"
        f"TiO₂ {r['TiO2']:.2f}% · SiO₂ {r['SiO2']:.1f}%"
    ), axis=1)
    return gdf[["amostra", "cor", "categoria", "popup", "geometry"]]


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


def _preciso(gdf, tolerancia_m=None):
    """Reduz o tamanho do geojson: simplifica em UTM e arredonda as coordenadas (1e-5 grau ~ 1 m)."""
    import shapely
    if tolerancia_m:
        gdf = gdf.copy()
        gdf["geometry"] = gdf.geometry.simplify(tolerancia_m, preserve_topology=True)
    gdf = para_wgs84(gdf)
    gdf["geometry"] = shapely.set_precision(gdf.geometry.values, 1e-5)
    return gdf


def carregar_geologia_regional():
    """Mapa geologico de SC (CPRM 1:500.000) recortado no panorama; legenda com as 24 maiores unidades."""
    gdf = gpd.read_file(GEOLOGIA_REGIONAL_GPKG, layer="litologia")
    gdf["area"] = gdf.geometry.area
    ordem = gdf.groupby("nome")["area"].sum().sort_values(ascending=False)
    principais = set(ordem.index[:24])
    gdf["categoria"] = gdf["nome"].where(gdf["nome"].isin(principais), "Outras unidades")
    gdf["popup"] = gdf.apply(lambda r: (
        f"<b>{r['nome']}</b> ({r['sigla']})<br>{r['periodo'] if isinstance(r['periodo'], str) else 's/ período'}"
        f"{(' · ' + format(r['idade_max'], '.0f') + ' Ma') if r['idade_max'] == r['idade_max'] and r['idade_max'] else ''}<br>"
        f"{r['classe'] if isinstance(r['classe'], str) else ''}<br>{(r['litotipo'] or '')[:110] if isinstance(r['litotipo'], str) else ''}"
    ), axis=1)
    itens = [{"cor": gdf.loc[gdf["nome"] == n, "cor"].iloc[0], "label": n} for n in ordem.index[:24]]
    itens.append({"cor": "#C8C8C8", "label": "Outras unidades"})
    return _preciso(gdf[["categoria", "cor", "popup", "geometry"]], 150), itens


def carregar_estrutura_cprm():
    gdf = gpd.read_file(GEOLOGIA_REGIONAL_GPKG, layer="estrutura")
    gdf["cor"] = gdf["categoria"].map({"Falha": "#FF493D", "Fratura": "#9FB3C8", "Dobra / outra": "#C77DFF"}).fillna("#9FB3C8")
    gdf["popup"] = "<b>" + gdf["categoria"] + "</b><br>" + gdf["tipo"].astype(str) + "<br>CPRM/SGB (SIG SC 1:500.000)"
    return _preciso(gdf[["categoria", "cor", "popup", "geometry"]], 60)


def carregar_diques_cprm():
    gdf = gpd.read_file(GEOLOGIA_REGIONAL_GPKG, layer="dique")
    gdf["cor"] = COR_DIQUE
    gdf["categoria"] = "Dique CPRM"
    gdf["popup"] = "<b>Dique</b><br>CPRM/SGB (SIG SC 1:500.000)"
    return _preciso(gdf[["categoria", "cor", "popup", "geometry"]])


def carregar_pocos():
    gdf = gpd.read_file(POCOS_GPKG)
    gdf["categoria"] = gdf["fonte"].map(lambda f: "SAG (CPRM)" if str(f).startswith("CPRM") else "ANP")
    gdf["cor"] = gdf["categoria"].map({"ANP": "#F6B76B", "SAG (CPRM)": "#5BA3D9"})

    def popup(r):
        prof = f"{r['profundidade_m']:.0f} m" if r["profundidade_m"] == r["profundidade_m"] else "s/ dado"
        extra = "".join(f"<br>{k}: {r[k]}" for k in ("CATEGORIA", "SITUACAO", "CONCLUSAO") if k in r.index and isinstance(r[k], str))
        return f"<b>{r['nome']}</b><br>Profundidade: {prof}{extra}<br>{r['fonte']}"
    gdf["popup"] = gdf.apply(popup, axis=1)
    return _preciso(gdf[["categoria", "cor", "popup", "geometry"]])


def main():
    print("Carregando camadas...")
    campo = carregar_campo()
    print(f"  campo: {len(campo)} pontos")
    estrutural = carregar_estrutural()
    print(f"  estrutural: {len(estrutural)} pontos")
    lineamentos = carregar_lineamentos()
    print(f"  lineamentos: {len(lineamentos)} linhas")
    geologia_regional, itens_geologia_regional = carregar_geologia_regional()
    estrutura_cprm = carregar_estrutura_cprm()
    diques_cprm = carregar_diques_cprm()
    pocos = carregar_pocos()
    print(f"  regional: {len(geologia_regional)} unidades, {len(estrutura_cprm)} estruturas CPRM, "
          f"{len(diques_cprm)} diques CPRM, {len(pocos)} poços")
    intrusiva = carregar_intrusiva()
    print(f"  sill/dique: {len(intrusiva)} polígonos")
    formacoes = carregar_formacoes()
    print(f"  formações: {len(formacoes)} polígonos")
    geoquimica = carregar_geoquimica()
    print(f"  geoquímica: {len(geoquimica)} amostras")
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
    geojson_geologia_regional = json.loads(geologia_regional.to_json())
    geojson_estrutura_cprm = json.loads(estrutura_cprm.to_json())
    geojson_diques_cprm = json.loads(diques_cprm.to_json())
    geojson_pocos = json.loads(pocos.to_json())
    lat_s, lon_o = Transformer.from_crs(31982, 4326, always_xy=True).transform(PANORAMA_UTM[0], PANORAMA_UTM[1])[::-1]
    lat_n, lon_l = Transformer.from_crs(31982, 4326, always_xy=True).transform(PANORAMA_UTM[2], PANORAMA_UTM[3])[::-1]
    bounds_panorama = [[lat_s, lon_o], [lat_n, lon_l]]
    geojson_formacoes = json.loads(formacoes.to_json())
    geojson_geoquimica = json.loads(geoquimica.to_json())
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
        "Geoquímica (Alto/Baixo-Ti)": {"tipo": "ponto", "itens": [
            {"cor": COR_TI_ALTO, "label": "Alto-Ti"}, {"cor": COR_TI_BAIXO, "label": "Baixo-Ti"},
        ]},
        "Dados estruturais": {"tipo": "ponto", "itens": [
            {"cor": cor, "label": LABELS_CLASSIFICACAO_ESTRUTURAL.get(k, k)}
            for k, cor in CORES_CLASSIFICACAO_ESTRUTURAL.items()
        ] + [{"cor": COR_CLASSIFICACAO_PADRAO, "label": "Outra estrutura"}]},
        "Lineamentos (satélite)": {"tipo": "linha", "itens": [
            {"cor": "#2E7D5B", "label": "Positivo"}, {"cor": "#E8A33D", "label": "Negativo"},
        ]},
    }
    legenda_data["Geologia regional (CPRM SC)"] = {"tipo": "area", "itens": itens_geologia_regional}
    legenda_data["Estruturas CPRM (falhas/fraturas)"] = {"tipo": "linha", "itens": [
        {"cor": "#FF493D", "label": "Falha"}, {"cor": "#9FB3C8", "label": "Fratura"}, {"cor": "#C77DFF", "label": "Dobra / outra"},
    ]}
    legenda_data["Diques CPRM"] = {"tipo": "linha", "itens": [{"cor": COR_DIQUE, "label": "Dique CPRM"}]}
    legenda_data["Poços (ANP/SAG)"] = {"tipo": "ponto", "itens": [
        {"cor": "#F6B76B", "label": "ANP"}, {"cor": "#5BA3D9", "label": "SAG (CPRM)"},
    ]}
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
  html, body {{ display: flex; flex-direction: column; }}
  #map {{ flex: 1; position: relative; min-height: 0; background: {MARCA_NAVY}; }}
  #barra-ferramentas {{
    display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: center; padding: 8px 70px 8px 14px; flex-shrink: 0;
    background: {MARCA_ROXO_ESCURO}; color: {MARCA_CINZA_CLARO}; border-bottom: 2px solid {MARCA_ROXO}; font-size: 12px;
  }}
  #barra-ferramentas h1 {{ font-size: 15px; margin: 0 8px 0 0; white-space: nowrap; }}
  #barra-ferramentas h1 b {{ color: {MARCA_ROXO}; }}
  #barra-ferramentas .grupo {{ display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }}
  #barra-ferramentas label {{ opacity: .7; text-transform: uppercase; font-size: 10px; letter-spacing: .06em; }}
  #barra-ferramentas button, #barra-ferramentas select {{
    background: {MARCA_NAVY}; color: {MARCA_CINZA_CLARO}; border: 1px solid {MARCA_ROXO}; border-radius: 5px;
    padding: 4px 9px; font: inherit; cursor: pointer;
  }}
  #barra-ferramentas button.ativo {{ background: {MARCA_ROXO}; color: {MARCA_NAVY}; }}
  #logo-barra {{ position: fixed; top: 8px; right: 12px; width: 46px; height: 46px; border-radius: 50%; border: 2px solid {MARCA_ROXO}; z-index: 1100; }}
  .leaflet-popup-content-wrapper {{ background: {MARCA_ROXO_ESCURO}; color: {MARCA_CINZA_CLARO}; border: 1px solid {MARCA_ROXO}; }}
  .leaflet-popup-tip {{ background: {MARCA_ROXO_ESCURO}; }}
  .leaflet-popup-content {{ font-family: {MARCA_FONTE}; font-size: 12px; }}
  .leaflet-control-layers {{ background: {MARCA_ROXO_ESCURO} !important; color: {MARCA_CINZA_CLARO}; border: 1px solid {MARCA_ROXO} !important; }}
  .leaflet-control-layers-toggle {{ filter: invert(1); }}
  #legenda {{
    background: rgba(45,10,74,0.92); color: {MARCA_CINZA_CLARO}; border: 1px solid {MARCA_ROXO};
    border-radius: 6px; padding: 8px 10px; font-size: 11px; max-width: 230px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4); display: flex; flex-direction: column;
  }}
  #legenda h4 {{ margin: 0 0 4px 0; font-size: 11px; color: {MARCA_ROXO}; text-transform: uppercase; letter-spacing: 0.03em; flex-shrink: 0; }}
  #legenda .legenda-corpo {{ overflow-y: auto; max-height: calc(100vh - 150px); padding-right: 4px; }}
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
<div id="barra-ferramentas"></div>
{f'<img id="logo-barra" src="data:image/jpeg;base64,{logo_b64}">' if logo_b64 else ''}
<div id="map"></div>
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
            registrarSub('Mapa geológico atualizado', f, layer);
        }},
    }});

    var geoRegionalLayer = L.geoJSON({json.dumps(geojson_geologia_regional, ensure_ascii=False)}, {{
        style: function(f) {{ return {{ color: '#333', weight: 0.3, fillColor: f.properties.cor, fillOpacity: 0.5 }}; }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup(f.properties.popup);
            registrarSub('Geologia regional (CPRM SC)', f, layer);
        }},
    }});
    var estruturaCprmLayer = L.geoJSON({json.dumps(geojson_estrutura_cprm, ensure_ascii=False)}, {{
        style: function(f) {{ return {{ color: f.properties.cor, weight: f.properties.categoria === 'Falha' ? 2 : 1.2, opacity: 0.9 }}; }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup(f.properties.popup);
            registrarSub('Estruturas CPRM (falhas/fraturas)', f, layer);
        }},
    }});
    var diquesCprmLayer = L.geoJSON({json.dumps(geojson_diques_cprm, ensure_ascii=False)}, {{
        style: function(f) {{ return {{ color: f.properties.cor, weight: 3.5, opacity: 0.95 }}; }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup(f.properties.popup);
            registrarSub('Diques CPRM', f, layer);
        }},
    }});
    var pocosLayer = L.geoJSON({json.dumps(geojson_pocos, ensure_ascii=False)}, {{
        pointToLayer: function(f, latlng) {{
            return L.marker(latlng, {{
                icon: L.divIcon({{
                    className: '', iconSize: [16, 16], iconAnchor: [8, 8],
                    html: '<div style="color:' + f.properties.cor + ';font-size:16px;line-height:16px;text-shadow:0 0 3px #000,0 0 3px #000;">&#9650;</div>',
                }}),
            }});
        }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup(f.properties.popup);
            registrarSub('Poços (ANP/SAG)', f, layer);
        }},
    }});

    var geoquimicaLayer = L.geoJSON({json.dumps(geojson_geoquimica, ensure_ascii=False)}, {{
        pointToLayer: function(f, latlng) {{
            var estilo = pontoEstilo(f.properties.cor, 6);
            estilo.color = '#000';
            return L.circleMarker(latlng, estilo);
        }},
        onEachFeature: function(f, layer) {{
            layer.bindPopup(f.properties.popup);
            registrarSub('Geoquímica (Alto/Baixo-Ti)', f, layer);
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
    geoRegionalLayer.addTo(map);
    formacoesLayer.addTo(map);
    intrusivaLayer.addTo(map);
    pocosLayer.addTo(map);
    campoLayer.addTo(map);

    var basemaps = {
        "Rico (CartoDB Voyager)": rico,
        "Satélite (Esri)": satelite,
        "Relevo/Topográfico": relevo,
    };
    var overlays = {
        "Pontos de campo": campoLayer,
        "Mapa geológico atualizado": formacoesLayer,
        "Sill/Dique": intrusivaLayer,
        "Geologia regional (CPRM SC)": geoRegionalLayer,
        "Estruturas CPRM (falhas/fraturas)": estruturaCprmLayer,
        "Diques CPRM": diquesCprmLayer,
        "Poços (ANP/SAG)": pocosLayer,
        "Geoquímica (Alto/Baixo-Ti)": geoquimicaLayer,
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
    // ---- barra superior (padrao dos demais produtos): mapa base, camadas e vistas ----
    var BOUNDS_TAIO = """ + json.dumps([[centro_lat - 0.12, centro_lon - 0.15], [centro_lat + 0.12, centro_lon + 0.15]]) + """;
    var BOUNDS_PANORAMA = """ + json.dumps(bounds_panorama) + """;
    var barra = document.getElementById('barra-ferramentas');
    function el(tag, props) { var e = document.createElement(tag); Object.assign(e, props || {}); return e; }
    function grupoBarra(rotulo, itens) {
        var g = el('div', { className: 'grupo' });
        g.appendChild(el('label', { textContent: rotulo }));
        itens.forEach(function(i) { g.appendChild(i); });
        barra.appendChild(g);
    }
    barra.appendChild(el('h1', { innerHTML: '<b>Webmap Taió</b> — Sistema Alimentador' }));
    var baseAtual = satelite;
    var selBase = el('select', {});
    Object.keys(basemaps).forEach(function(nome) { selBase.appendChild(el('option', { value: nome, textContent: nome, selected: basemaps[nome] === satelite })); });
    selBase.onchange = function() {
        map.removeLayer(baseAtual);
        baseAtual = basemaps[selBase.value];
        baseAtual.addTo(map);
        baseAtual.bringToBack && baseAtual.bringToBack();
        atualizarLegenda();
    };
    grupoBarra('Mapa base', [selBase]);
    var GRUPOS_CAMADAS = [
        ['Campo', ['Pontos de campo']], ['Geologia Taió', ['Mapa geológico atualizado']], ['Sill/Dique', ['Sill/Dique']],
        ['Geologia SC', ['Geologia regional (CPRM SC)']], ['Lineam. satélite', ['Lineamentos (satélite)']],
        ['Estruturas CPRM', ['Estruturas CPRM (falhas/fraturas)']], ['Diques CPRM', ['Diques CPRM']], ['Poços', ['Poços (ANP/SAG)']],
        ['Geoquímica', ['Geoquímica (Alto/Baixo-Ti)']], ['Estrutural', ['Dados estruturais']],
        ['OSM', ['Rios', 'Estradas', 'Localidades']],
    ];
    var botoesCamadas = GRUPOS_CAMADAS.map(function(g) {
        var nomes = g[1].filter(function(n) { return overlays[n]; });
        var b = el('button', { textContent: g[0] });
        b.onclick = function() {
            var ligar = !nomes.some(function(n) { return map.hasLayer(overlays[n]); });
            nomes.forEach(function(n) { if (ligar) map.addLayer(overlays[n]); else map.removeLayer(overlays[n]); });
            atualizarLegenda();
        };
        b._nomes = nomes;
        return b;
    });
    grupoBarra('Camadas', botoesCamadas);
    grupoBarra('Vista', [
        el('button', { textContent: 'Área de Taió', onclick: function() { map.fitBounds(BOUNDS_TAIO); } }),
        el('button', { textContent: 'Panorama regional', onclick: function() { map.fitBounds(BOUNDS_PANORAMA); } }),
    ]);
    function sincronizarBarra() {
        botoesCamadas.forEach(function(b) {
            b.classList.toggle('ativo', b._nomes.some(function(n) { return map.hasLayer(overlays[n]); }));
        });
    }
    setTimeout(function() { map.invalidateSize(); }, 50);
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
        sincronizarBarra();
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
