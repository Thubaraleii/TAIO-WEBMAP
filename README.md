# Taió Plumbing System — Webmap

Mapa em tela cheia com zoom/pan contínuo (Leaflet, HTML autônomo — precisa
de internet pra carregar os tiles) do sistema intrusivo de Taió —
sill/soleira e dique de diabásio intrudindo formações sedimentares da
Bacia do Paraná.

Camadas: pontos de campo, mapa geológico real (CPRM), sill/dique
digitalizados, dados estruturais, lineamentos de satélite e camadas de
referência (rios/estradas/localidades — OSM). Basemaps: satélite,
relevo/topográfico, rico, escuro e OSM padrão. Legenda dinâmica liga/desliga
camadas inteiras ou classes individuais dentro de cada camada.

Abra `webmap_taio.html` direto no navegador.

Complemento do modelo 3D: [taio-plumbing-system-3d](https://github.com/Thubaraleii/taio-plumbing-system-3d).

Gerado por `gerar_webmap_taio.py` (Python, GeoPandas) — o script depende
dos dados do projeto completo (catálogo de pontos de campo, mapa geológico
CPRM, lineamentos, OSM) e não roda de forma standalone fora dessa
estrutura; está incluído aqui só como referência/histórico do código.

Criado por Afonso Henrique de Jesus.
