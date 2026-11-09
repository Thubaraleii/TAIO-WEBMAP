# Webmap Taió

**Versão 1.0** · Projeto *Taió Plumbing System* (Mestrado em Geologia, UFSC)

🔗 **Acesso:** <https://thubaraleii.github.io/TAIO-WEBMAP/webmap_taio.html>

Mapa web (Leaflet) em tela cheia, de página única e sem servidor, para exploração integrada da geologia, das estruturas e dos dados
de campo do sistema intrusivo (soleiras e diques) de Taió.

## Funcionalidades

**Barra superior**
- **Mapa base:** Rico (CARTO Voyager), Satélite (Esri), Relevo (OpenTopoMap) e Hipsometria (raster gerado a partir do MDE).
- **Camadas:** Campo, Geologia Taió, Sill/Dique, Geologia SC, Lineamentos de satélite, Estruturas CPRM, Diques CPRM, Poços, Geoquímica, Estrutural e OSM (rios, estradas, localidades). O botão fica aceso quando a camada está ativa.
- **Vista:** enquadramento da área de Taió ou do panorama regional.

**Legenda lateral** (único painel lateral)
- Seções por camada, com liga/desliga da camada inteira ou de cada item (unidade, classe, tipo).
- Geologia regional com as 24 maiores unidades e o grupo “Outras unidades”.

**Camadas de dados**
- **Pontos de campo:** catálogo unificado, coloridos pela litologia padronizada, nomeados pelo código ITC; popup com atributos.
- **Geologia Taió:** polígonos das unidades sedimentares (Teresina, Serra Alta, Irati, Palermo, Rio Bonito) e depósito quaternário; **Sill/Dique:** polígonos das soleiras e diques.
- **Geologia SC / Estruturas / Diques (CPRM, 1:500.000):** mapa geológico regional recortado no panorama; falhas (azul), fraturas (rosa) e diques.
- **Lineamentos de satélite** positivos (cristas) e negativos (vales), com azimute, comprimento e formação predominante.
- **Dados estruturais** classificados; **Geoquímica** (Alto/Baixo-Ti); **Poços** ANP e SAG (profundidade total, categoria, situação).

## Dados e métodos

- Camadas vetoriais exportadas em GeoJSON (WGS84) com coordenadas arredondadas e geometrias simplificadas para reduzir o tamanho.
- O raster hipsométrico é gerado a partir do MDE de drone e embutido como imagem georreferenciada.
- A página é autocontida; apenas os mapas base dependem de acesso à internet.

## Idioma e navegação

- **Idioma:** o botão **EN / PT**, ao lado do logotipo, alterna a interface entre português e inglês em tempo real (menus, legendas, dicas, popups, rótulos e textos 3D). O padrão é **sempre o português**; o inglês vale na página aberta com `?lang=en`, parâmetro que o botão e os links entre as páginas repassam.
- **Hub:** o botão **← Hub** volta à página inicial do projeto, mantendo o idioma.
- **Tradução:** feita no navegador por dicionário (`tps_i18n_dict.py`, embutido na página por `tps_i18n.py` ao gerar o HTML). Dados de origem em português (por exemplo, descrições de campo e nomes próprios de unidades) permanecem no idioma original.

## Uso

Abra `webmap_taio.html` no navegador (conexão necessária para os mapas base) ou acesse a versão publicada. Clique em feições para ver os popups; use a legenda para filtrar.

## Regenerar os produtos

O repositório contém o HTML publicado e o script gerador. Para regenerar é necessário o conjunto de dados do projeto
(modelo digital de elevação, litologia, pontos de campo, lineamentos, poços), que **não é distribuído** neste repositório.

```bash
python gerar_webmap_taio.py
```

Dependências Python: `numpy`, `pandas`, `geopandas`, `shapely`, `pyproj`, `rasterio`, `scipy`, `plotly`, `leaflet` (carregado por CDN).

## Estrutura

```
webmap_taio.html         produto gerado
gerar_webmap_taio.py     gerador
assets/                  logotipo e ícones
```

## Referências

1. Milani, E. J.; Melo, J. H. G.; Souza, P. A.; Fernandes, L. A.; França, A. B. (2007). Bacia do Paraná. *Boletim de Geociências da Petrobras*, 15(2), 265–287.
2. Schneider, R. L.; Mühlmann, H.; Tommasi, E.; Medeiros, R. A.; Daemon, R. F.; Nogueira, A. A. (1974). Revisão estratigráfica da Bacia do Paraná. In: *Anais do 28º Congresso Brasileiro de Geologia*, Porto Alegre, SBG, 1, 41–65.
3. Frank, H. T.; Gomes, M. E. B.; Formoso, M. L. L. (2009). Review of the areal extent and the volume of the Serra Geral Formation, Paraná Basin, South America. *Pesquisas em Geociências*, 36(1), 49–57.
4. Peate, D. W. (1997). The Paraná–Etendeka Province. In: Mahoney, J. J.; Coffin, M. F. (eds.), *Large Igneous Provinces*. AGU Geophysical Monograph 100, 217–245.
5. Agafonkin, V. **Leaflet** — an open-source JavaScript library for interactive maps. <https://leafletjs.com>
6. Plotly Technologies Inc. (2015). **Collaborative data science** (Plotly.js). Montréal. <https://plot.ly>
7. Mapzen / Amazon Web Services. **Terrain Tiles** (formato Terrarium). <https://registry.opendata.aws/terrain-tiles/>
8. OpenStreetMap contributors. **OpenStreetMap**. <https://www.openstreetmap.org/copyright>
9. CPRM/SGB — Serviço Geológico do Brasil. **Geologia e Recursos Minerais do Estado de Santa Catarina — Mapa Geológico 1:500.000 (SIG SC)**. <https://geosgb.sgb.gov.br>
10. ANP — Agência Nacional do Petróleo, Gás Natural e Biocombustíveis. **Dados abertos — poços**. <https://www.gov.br/anp>
11. Harris, C. R. et al. (2020). Array programming with NumPy. *Nature*, 585, 357–362.
12. Virtanen, P. et al. (2020). SciPy 1.0: fundamental algorithms for scientific computing in Python. *Nature Methods*, 17, 261–272.
13. Jordahl, K. et al. **GeoPandas**. Zenodo. <https://geopandas.org>; Gillies, S. et al. **Shapely** e **Rasterio**. <https://github.com/shapely/shapely>, <https://github.com/rasterio/rasterio>.

## Licença e uso

- **Código** (scripts de geração e JavaScript das páginas): licença **MIT** — ver [`LICENSE`](LICENSE).
- **Produtos gerados** (HTML, figuras, tabelas derivadas): **CC BY 4.0** — uso, adaptação e redistribuição permitidos com atribuição ao autor.
- **Dados de terceiros** incorporados mantêm as licenças e os termos das fontes originais (tabela em *Créditos e fontes de dados*).
- Os modelos são **interpretativos** e dependem da qualidade e da densidade dos dados de entrada; **não substituem** estudo geológico, hidrogeológico ou geotécnico de detalhe, nem devem ser usados como base única para decisões de engenharia, perfuração ou licenciamento.
- Fornecido “como está”, sem garantias de qualquer tipo.

## Créditos e fontes de dados

| Fonte | Uso | Termos |
|---|---|---|
| Levantamento de campo do autor (pontos, estruturas, geoquímica, MDE de drone) | Dados primários da área de Taió | CC BY 4.0 (autor) |
| CPRM/SGB — Mapa Geológico do Estado de Santa Catarina 1:500.000 (SIG SC) | Geologia regional, falhas, fraturas e diques regionais | Dados abertos CPRM/SGB — citar a fonte |
| ANP — Tabela de poços (dados abertos) | Poços de petróleo/gás (posição e profundidade total) | Dados abertos ANP — citar a fonte |
| Cadastro de poços do Sistema Aquífero Guarani (SAG) | Poços do SAG (posição e profundidade), arquivo KML do projeto | Citar a fonte original do cadastro |
| OpenStreetMap contributors | Rios, estradas e localidades | ODbL 1.0 — © OpenStreetMap contributors |
| Esri World Imagery | Imagem de satélite (tiles e textura) | Termos da Esri — uso com atribuição |
| CARTO / OpenTopoMap | Mapas base do webmap | Atribuição nos próprios mapas (OSM, SRTM, OpenTopoMap CC-BY-SA) |
| AWS Terrain Tiles (formato Terrarium) | Relevo e batimetria regionais (derivados de SRTM, GEBCO e outras fontes) | Atribuição conforme o provedor dos tiles |
| Plotly.js (MIT), Leaflet (BSD-2-Clause) | Bibliotecas de visualização embutidas/carregadas nas páginas | Licenças originais |

## Como citar

> JESUS, A. H. de. **Webmap Taió**, versão 1.0. 2026. Projeto *Taió Plumbing System* — Mestrado em Geologia, UFSC. Disponível em: <https://thubaraleii.github.io/TAIO-WEBMAP/webmap_taio.html>.

## Autoria

**Afonso Henrique de Jesus** — Mestrado em Geologia, Universidade Federal de Santa Catarina (UFSC).
Projeto: *Architecture and Geochemical Evolution of the Taió Intrusive Plumbing System* (Taió, SC — Bacia do Paraná).
