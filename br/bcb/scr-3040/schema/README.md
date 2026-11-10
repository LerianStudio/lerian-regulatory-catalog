# SCR Documento 3040: fontes oficiais fixadas

Arquivos do Banco Central do Brasil, gravados sem alteração e com o nome oficial.
Página de origem: https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3040
Baixados em 2026-11-10. Prefixo das URLs:
`https://www.bcb.gov.br/content/estabilidadefinanceira/Leiaute_de_documentos/scrdoc3040/`

| Arquivo | Última modificação no servidor | SHA-256 |
|---|---|---|
| `SCR3040_Leiaute.xls` | 2026-10-18 | `0eb74aa1245fd24bed37036d68c69d2045272e53f5fb1d96af336a376f1b1ba2` |
| `SCR_InstrucoesDePreenchimento_Doc3040.pdf` (138 páginas) | 2026-05-06 | `3a2f9dff406b404b26617ab0dce79b5992cc67ac410ff60047236c73b11daf8b` |
| `scr3040.202607.xsd` (extraído de `SCR3040_Validador.zip`, `classes/br/gov/bcb/scr2/parsing/util/`; 11679931 bytes, SHA-256 do zip `262d4d155a2bf3100ac27c53add5be911c3d60575e12cb5c9765ef032106ad91`) | 2026-07-31 (data no zip) | `bbaf26f0627dcafbe92ce8d44e99dfd348734a522be36bdf48d39dd8a05f15ec` |

Conferir: `sha256sum SCR3040_Leiaute.xls SCR_InstrucoesDePreenchimento_Doc3040.pdf`.

## XSD

A página não publica XSD, mas o validador oficial (`SCR3040_Validador.zip`, baixado em 2026-11-10, Java)
carrega os esquemas e o mais recente, `scr3040.202607.xsd` ("data-base Maio/2026", versão 1.5), está fixado aqui.
O zip não foi copiado. Ele decide: o aninhamento `Doc3040 > Cli > Op > (Venc, Gar, Inf)` (`tipoOperacao`),
atributos decimais como `xs:decimal` (separador ponto, `tipoValor`, `tipoTaxa`) e `TpVlrGar` com o padrão `0[1-2]`
(`tipoValorDeGarantia`).

## Onde cada coisa está

Citar como `arquivo, página` (PDF; a numeração é a do PDF, igual à do sumário) ou
`arquivo, planilha, linha` (XLS; linha 1-indexada).

Instruções de preenchimento (`SCR_InstrucoesDePreenchimento_Doc3040.pdf`):

| Assunto | Página |
|---|---|
| Instruções gerais | 3 |
| Cabeçalho do documento XML | 7 |
| Informações do Cliente (`<Cli>`) | 10 |
| Informações Básicas da Operação (`<Op>`) | 17 |
| Valor de Vencimentos (`<Venc>`) | 73 |
| Informações de Garantias (`<Gar>`) | 78 |
| Informações Adicionais (`<Inf>`) | 86 |
| Histórico de alterações (inclui a criação dos Anexos 47, 48 e 49 na data-base maio/2026) | ver "Histórico" no fim do PDF |

Leiaute (`SCR3040_Leiaute.xls`, planilha `Anexo`):

| Anexo | Linha |
|---|---|
| 1 Código do Vencimento (`vCOD`) | 1 |
| 2 Natureza da Operação | 36 |
| 3 Modalidade | 55 |
| 8 Característica Especial | 264 |
| 12 Garantias | 318 |
| 47 Situação da Garantia | 921 |
| 48 Tipo Valor da Garantia | 930 |
| 49 Compartilhamento da Garantia | 935 |

O Anexo 26 (Informações Adicionais) é a planilha `Anexo 26 - InfosAdicionais`.
Os Anexos 47, 48 e 49 e as alterações nos Anexos 3, 12 e 26 valem a partir da
data-base maio/2026 (planilha `HistoricoAtualizacoes` e histórico do PDF).

A tabela de `vCOD` não ganha cópia no catálogo: vive no Lender, com arquivo e linha
deste diretório em cada faixa.
