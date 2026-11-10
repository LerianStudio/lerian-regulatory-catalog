# SCR Documento 3040: fontes oficiais fixadas

Arquivos do Banco Central do Brasil, gravados sem alteração e com o nome oficial.
Página de origem: https://www.bcb.gov.br/estabilidadefinanceira/scrdoc3040
Baixados em 2026-11-10. Prefixo das URLs:
`https://www.bcb.gov.br/content/estabilidadefinanceira/Leiaute_de_documentos/scrdoc3040/`

| Arquivo | Última modificação no servidor | SHA-256 |
|---|---|---|
| `SCR3040_Leiaute.xls` | 2026-10-18 | `0eb74aa1245fd24bed37036d68c69d2045272e53f5fb1d96af336a376f1b1ba2` |
| `SCR_InstrucoesDePreenchimento_Doc3040.pdf` (138 páginas) | 2026-05-06 | `3a2f9dff406b404b26617ab0dce79b5992cc67ac410ff60047236c73b11daf8b` |

Conferir: `sha256sum SCR3040_Leiaute.xls SCR_InstrucoesDePreenchimento_Doc3040.pdf`.

## Sem XSD

A página do Documento 3040 não publica XSD. O leiaute é o `SCR3040_Leiaute.xls`
(planilha `Doc3040`: tags e atributos; planilha `Anexo`: domínios; planilha
`Anexo 26 - InfosAdicionais`). O validador oficial (`SCR3040_Validador.zip`, 12 MB, Java)
existe na página e não foi copiado. Nenhuma regra de leiaute pode citar XSD.

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
