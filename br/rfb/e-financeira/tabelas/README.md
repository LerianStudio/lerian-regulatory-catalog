# Tabelas de códigos da e-Financeira

Cópias, byte a byte, das tabelas que a Receita publica no Portal SPED
(e-Financeira › Downloads › Tabelas de códigos, `http://sped.rfb.gov.br/pasta/show/1932`),
baixadas em 06/11/2026. A Receita valida cada evento contra a tabela **vigente na data
de recepção**; não edite estes arquivos — baixe de novo e regere.

| Arquivo | Tabela | Origem |
|---|---|---|
| `municipios.txt` | Municípios (código IBGE de 7 dígitos) | `http://sped.rfb.gov.br/arquivo/download/1934` |
| `paises.txt` | Países (ISO 3166-1 alfa-2) | `http://sped.rfb.gov.br/arquivo/download/1937` |
| `uf.txt` | Unidades da Federação | `http://sped.rfb.gov.br/arquivo/download/1949` |
| `categorias-declarante.txt` | Categorias de Declarante | `http://sped.rfb.gov.br/arquivo/download/2455` |
| `tipos-nome.txt` | Tipos de Nome | `http://sped.rfb.gov.br/arquivo/download/2457` |
| `tipos-endereco.txt` | Tipos de Endereço | `http://sped.rfb.gov.br/arquivo/download/2458` |

O formato é o da Receita: `versão=N COLUNAS` na primeira linha e `código|nome|DT_INI|DT_FIM`
nas seguintes (DT_FIM vazio enquanto vigente). A codificação varia (UTF-8 ou Latin-1) e
a de países traz o arquivo duas vezes, a primeira cópia cortada no meio de uma linha —
`tools/tabelas_receita.py` lê assim mesmo.

O que deriva daqui:

- `municipios.yaml` de cada documento que a declara: `python3 tools/tabelas_receita.py`.
- os domínios que os contratos declaram (países, UF, tipos de nome e de endereço,
  categorias): `tools/test_tabelas_receita.py` confere que cada um é exatamente o conjunto
  vigente da tabela. Uma tabela nova da Receita que muda um domínio muda o contrato e
  sobe a versão do documento.
