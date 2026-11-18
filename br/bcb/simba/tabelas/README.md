# Tabelas de códigos do SIMBA

Tabelas de referência do leiaute da IN BCB 636/2025 (`../normas/IN-BCB-636-2025.md`).
**O Reporter não lê nada desta pasta**: o motor só lê a pasta de cada documento e o
`tables:` do contrato não faz "procura e preenche". Elas são proveniência e oráculo de
teste; a tradução que vai para o arquivo vive no `compute` (`case`) do binding ou no
template de cada documento. Não edite à mão: regere a partir da origem.

| Arquivo | Conteúdo | Origem |
|---|---|---|
| `uf-ibge.yaml` | UF (sigla) → código IBGE de 2 dígitos, 27 UFs | `br/rfb/e-financeira/tabelas/uf.txt` (Receita, `http://sped.rfb.gov.br/arquivo/download/1949`, baixado em 06/11/2026), sha256 `5816106201212a3ba1a17b787f278b7de6491342184f47ca5de041ccb66983ef`, linhas vigentes lidas por `tools/tabelas_receita.py` |
| `uf-ibge.compute.yaml` | O mesmo mapa como item de `compute` do binding (`case` com `otherwise: refuse`) | idem; `as` e `column` são marcadores a trocar no binding de cada documento |
| `anexo-ii.yaml` | Códigos do campo 9 `CODIGO_TIPO_LANCAMENTO` do arquivo IV EXTRATO: débito (66) e crédito (78) | IN 636, seção `## ANEXO II` da cópia (linhas 363-519) |
| `ParticipantesSTR.csv` | Participantes do STR: ISPB → código de compensação (`Número_Código`), cópia byte a byte (UTF-8 com BOM, 471 linhas + cabeçalho, 46.388 bytes) | Banco Central, `https://www.bcb.gov.br/content/estabilidadefinanceira/str1/ParticipantesSTR.csv`, baixado em 18/11/2026 11:17 UTC, sha256 `1e5c5f84d8cc4389864df50965c4fa00b4e7f954533fe7d7e5e857381c5de6e8` |

Notas:

- **UF.** O `uf.txt` vigente tem 28 linhas: as 27 UFs e `99|EX` (exterior, convenção da
  Receita). `EX` fica fora: no SIMBA, agência no exterior ou sem agência física é
  `"00"` (IN 636, Anexo I, Agências campo 6 `CODIGO_UF`, cópia linha 106). Esse
  sentinela é condição do template, não entra no `case`.
- **Anexo II.** As descrições são copiadas literalmente da norma (com as grafias dela) e
  servem de proveniência; não são texto de saída. `descontinuado_em_2028_06_01` marca os
  29 códigos do § 4º do art. 2º (cópia linha 55), descontinuados a partir de
  01/06/2028. O § 4º cita o código **116**, que não tem linha no Anexo II; ele aparece
  em `descontinuados_sem_linha_no_anexo_ii`, sem descrição.
- **ISPB → COMPE.** O código de compensação da contraparte (ORIGEM-DESTINO campo 5
  `COD_COMP_INSTITUIÇÃO_OD`, cópia linha 206) sai desta lista. A lista é a mesma para
  todo cliente, então vive no template do origem-destino, gerada desta cópia, e é
  congelada por versão do documento: uma lista nova do Banco Central é uma versão nova.
  Instituição com código e `Participa_da_Compe = Não` sai com o código; `n/a`, `0` ou
  ISPB fora da lista saem `999` (o "sem código Compe" da mesma linha 206).
- Fora desta pasta por enquanto: código IBGE de município (`*_CIDADE`, 7 dígitos).
