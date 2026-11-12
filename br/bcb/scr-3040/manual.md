# SCR Documento 3040 - Dados Individualizados de Risco de Crédito

> Documento de leitura. Explica o que este regulatório é e o que a instituição precisa
> configurar para gerá-lo. **Não repete o contrato**: campos, formatos, domínios e lacunas
> estão em `contract.yaml`, e é ele que vale.

## O que é

Remessa **mensal** ao Sistema de Informações de Crédito (SCR) do Banco Central, uma por
data-base (`AAAA-MM`): cada cliente, as operações de crédito dele, os vencimentos, as
garantias e as informações adicionais. Fontes oficiais fixadas em `schema/` (origem, data e
SHA-256 em `schema/README.md`).

O esquema oficial vem dentro do validador
(`SCR3040_Validador.zip`) e está fixado em `schema/scr3040.202607.xsd` (ver `schema/README.md`).
O validador oficial (Java) não está neste repositório: **rode-o sobre o arquivo gerado antes de enviar.**

## O que esta versão cobre

Cabeçalho (`Doc3040`), `Cli`, `Op`, `Venc`, `Gar` e dois `Inf`: 1002 (adquirida de pessoa não
integrante do SFN, hoje só a recompra de consignado) e 1701 (reestruturação), mais o `Inf`
de saída da operação que deixou a instituição no mês. Ficam fora `Agreg`, `Sicor`, `ConIpocs`,
`ContInstFinRes4966`, `Estagio`, `Perda` e os demais `Inf`.

**Operação que saiu no mês.** O Lender entrega a linha uma vez, no mês da saída, com `exit_type` (0301, 0302,
0304, 0310, 0311, 0316 ou 0317), e o template escreve um `Inf` de saída: sem `ProvConsttd` e sem `Venc`
(Instruções p.89, "Informações proibidas"); `Cd`, `Ident` e `Valor` só saem quando têm valor (p.88-95). No 0316,
`Cd` é o IPOC novo, composto como o `IPOC` da operação, e `Qtd="02"` é o motivo renegociação (Anexo 34, p.95). Lacunas
declaradas em `saida-do-mes`: 0311 `Ident` e `Cd`, 0316 `Valor` do art. 22 e 0304 `Ident` de fundo sem CNPJ.

O arquivo **não é particionado**: `Parte="1"` e `TpArq="F"` (Instruções p.8). `TotalCli` é a
contagem de `Cli` do arquivo; ver a lacuna `cli-por-holder`.

## De onde vem cada grupo

| Grupo | Fonte | Observação |
|---|---|---|
| `Doc3040` (CNPJ) | organização do Midaz | a raiz de 8 dígitos é cortada pelo motor |
| `Doc3040` (responsável, metodologias) | perfil de reporte da instituição | sem fonte viva: pendência |
| `Cli` | Lender (`scr_operation_current`) e CRM do Midaz | o Lender nomeia o titular; o CRM dá documento, tipo e criação |
| `Op` | Lender (`scr_operation_current`) | uma linha por contrato no livro na data-base |
| `Venc` | Lender (`scr_maturity_current`) | um atributo `vCOD` por código com valor |
| `Gar` | Lender (`scr_guarantee_current`) e CRM | o garantidor pessoal tem o documento lido do CRM |
| `Inf` 1002 e 1701 | Lender (`scr_operation_current`) | só as operações que têm a data |
| `Inf` de saída | Lender (`scr_operation_current`) | só a linha com `exit_type` |

O **Lender nunca publica CPF, CNPJ ou nome**. O binding de referência junta as consultas em
memória, depois da leitura: o titular (`holder_id`, `midaz_organization_id`) vai ao CRM e
volta com o documento.

## O que a instituição configura

1. **Fontes de dados.** Três: `lender` (o Postgres do tenant), `midaz_onboarding` e `plugin_crm`.
2. **Escopo da fonte `lender`, escrito à mão.** A proposta automática de instituições só cobre
   a tabela de organização do Midaz e tabela com coluna `organization_id`, e as visões do
   Lender têm `midaz_organization_id`. No escopo da instituição, liste as **três visões**
   (`public__scr_operation_current`, `public__scr_maturity_current`,
   `public__scr_guarantee_current`), cada uma com a condição
   `midaz_organization_id = <organização da instituição>`. Sem isso o Reporter recusa a leitura.
3. **Permissão no banco do tenant do Lender**, para o papel de banco do Reporter, e nada mais:

       GRANT SELECT ON scr_operation_current, scr_maturity_current, scr_guarantee_current TO <papel do Reporter>;

   O Reporter só lê as três visões, nunca uma tabela operacional do Lender. A migração do
   Lender não dá esse grant: o papel é por ambiente.
4. **Job do Lender ligado.** O dataset só existe depois que o job diário de publicação roda
   para a competência; o 3040 de um mês lê a última versão publicada dela.
5. **Os campos pendentes**, abaixo.

## Rascunho até a instituição completar

O binding de referência declara `generatable: false`: o arquivo sai como **rascunho**, com
estes campos em branco, porque o leiaute os obriga e nenhuma fonte viva os tem:

- `Doc3040`: `NomeResp`, `EmailResp`, `TelResp` (`DDTTTTTTTT`), `MetodApPE` (C ou S), `MetodDifTJE` (S ou N);
- `Op`: `OrigemRec` (Anexo 4) e `CEP`;
- `Cli`: `Autorzc`, `PorteCli` e `FatAnual`.

Informe-os em `manualOverrides` do binding da instituição ou ligue uma fonte. Passam a ser
campos comuns do arquivo.

## O que o documento escolhe por você

Cada escolha (`NatuOp`, `Indx` e `PercIndx`, `Cd` e `IPOC`, `PercGar` ou `VlrOrig`, só reais, data-base)
está comentada em `template.tpl` e nas lacunas de `contract.yaml` (`q4-natuop-ccb-comprada`, `indx-pos-fixado`).

## O que este documento ainda não entrega

A lista completa, com quem responde cada item, é o `knownGaps` de `contract.yaml`. As que mais
pesam para a remessa:

1. **As sete perguntas regulatórias** (IPOC, unicidade do `Contrt`, bloco `Gar` e Anexos 12 e
   47 a 49, `NatuOp` de CCB comprada, `CaracEspecial 01` e `Inf 1701` depois da conversão,
   Anexo 42, primeira data-base depois do corte): **a remessa desta versão não é enviável**
   até a consulta ao BACEN responder.
2. **A operação que saiu do livro no mês** sai com `Inf` de saída; as lacunas dele estão em `saida-do-mes`.
3. **Garantia de contrato carregado** só a partir da data-base que contém o dia da carga.
4. **`Cli.IniRelactCli`** (decisão do Fred, 10/11): sai o menor entre o dia civil da criação do titular no
   CRM (America/Sao_Paulo) e o contrato mais antigo dele no Lender, em qualquer estado (liquidado,
   refinanciado, baixado ou vendido também contam; o carregado conta pela data da CCB original).
   Nunca depois de uma `DtContr` do mesmo cliente, e nunca avança de uma remessa para outra
   enquanto existir um contrato mais antigo.
5. **`Venc` 205 a 290** sem a dedução da renda não recebida em stop accrual.
6. **Indx na taxa flutuante**: o XSD exige `Indx` em todo `Op`; a taxa flutuante sai sem ele
   (`indx-pos-fixado`) e não valida até a lane F6.
