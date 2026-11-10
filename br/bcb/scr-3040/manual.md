# SCR Documento 3040 - Dados Individualizados de Risco de Crédito

> Documento de leitura. Explica o que este regulatório é e o que a instituição precisa
> configurar para gerá-lo. **Não repete o contrato**: campos, formatos, domínios e lacunas
> estão em `contract.yaml`, e é ele que vale.

## O que é

Remessa **mensal** ao Sistema de Informações de Crédito (SCR) do Banco Central, uma por
data-base (`AAAA-MM`): cada cliente, as operações de crédito dele, os vencimentos, as
garantias e as informações adicionais. Fontes oficiais fixadas em `schema/` (origem, data e
SHA-256 em `schema/README.md`).

**Não há XSD.** A página do BACEN não publica esquema; o leiaute é a planilha. Este
documento foi escrito contra a planilha e as instruções, e nada o confere contra um esquema
oficial. O validador oficial do BACEN (Java) não está neste repositório: **rode-o sobre o
arquivo gerado antes de enviar.**

## O que esta versão cobre

Cabeçalho (`Doc3040`), `Cli`, `Op`, `Venc`, `Gar` e dois `Inf`: 1002 (adquirida de pessoa não
integrante do SFN, hoje só a recompra de consignado) e 1701 (reestruturação). Ficam fora
`Agreg`, `Sicor`, `ConIpocs`, `ContInstFin`, `ContInstFinRes4966`, `Estagio`, `Perda` e os
demais `Inf`, entre eles toda a saída do mês (0301 a 0317).

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

## O que o documento escolhe por você, e onde está escrito

- **`NatuOp`**: 01 para a operação concedida, 03 para a recompra de consignado. A operação
  adquirida (`origin = acquisition`) sai **sem** natureza e sem `Inf 1002`: a regra espera a
  consulta ao BACEN (`q4-natuop-ccb-comprada`).
- **`Indx` e `PercIndx`**: 11 e 0 só na taxa prefixada. Na taxa flutuante saem de fora
  (`indx-pos-fixado`).
- **`Cd` e `IPOC`**: o cliente PJ leva a raiz do CNPJ e o PF leva o CPF inteiro; `DetCli` é o
  CNPJ inteiro, só do PJ (Instruções p.17-18).
- **`PercGar` ou `VlrOrig`**: `TpVlrGar` 02 escreve `PercGar`, 01 escreve `VlrOrig` (Instruções p.79).
- **Só reais.** O binding lê operações em BRL e escreve `VarCamb="790"`.
- **Fonte de verdade da data-base:** `competencia` da visão é a competência do dataset
  (`dataBase`), e a visão corrente é a maior `version` dela.

## O que este documento ainda não entrega

A lista completa, com quem responde cada item, é o `knownGaps` de `contract.yaml`. As que mais
pesam para a remessa:

1. **As sete perguntas regulatórias** (IPOC, unicidade do `Contrt`, bloco `Gar` e Anexos 12 e
   47 a 49, `NatuOp` de CCB comprada, `CaracEspecial 01` e `Inf 1701` depois da conversão,
   Anexo 42, primeira data-base depois do corte): **a remessa desta versão não é enviável**
   até a consulta ao BACEN responder.
2. **A operação que saiu do livro no mês** não aparece no mês da saída, nem com `Inf` de saída.
3. **Garantia de contrato carregado** só a partir da data-base que contém o dia da carga.
4. **`Venc` 205 a 290** sem a dedução da renda não recebida em stop accrual.
5. **Aninhamento e separador decimal** sem prova oficial local (`sem-xsd-aninhamento`,
   `separador-decimal`): o validador oficial decide.
