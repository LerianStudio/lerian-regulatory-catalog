# SIMBA — Titulares (arquivo III TITULARES)

Arquivo III do SIMBA, leiaute da Instrucao Normativa BCB 636/2025 (Anexo I, campos 1 a 28).
A IN entra em vigor em 01/12/2026 (art. 7o): use este documento a partir dessa data.

## O que e

Uma linha por vinculo de uma pessoa com uma conta: o titular, os cotitulares, os
representantes e os procuradores das contas (IN art. 2o, III). E um dos cinco arquivos da
resposta ao caso; os outros sao AGENCIAS, CONTAS, EXTRATO e ORIGEM-DESTINO, gerados com os
mesmos parametros.

## Parametros da geracao

Os mesmos nos cinco documentos SIMBA: `caso`, `documentos` (CPFs e CNPJs da ordem, so
digitos), `contas` (numeros de conta da ordem com DV, so digitos; ausente, todas as contas
dos documentos), `inicio` e `fim` (primeiro e ultimo dia do afastamento). Duas geracoes do
mesmo `caso` sao a mesma entrega: a mais nova substitui o rascunho anterior.

## Quais linhas entram

Para cada conta do caso (as contas em que um documento da ordem e o **titular**; encerradas
entram, apagadas do CRM nao):

1. **Titular** (campo 5 = `T`): uma linha, com o cadastro do titular no CRM. O titular e
   sempre uma pessoa da ordem, entao o campo 6 sai `1`.
2. **Cotitulares** (campo 5 = `1`, `2`, ...): uma linha por parte relacionada da conta com o
   papel `PRIMARY_HOLDER`, numeradas a partir de `1` em cada conta, na ordem em que o CRM
   guarda as partes (a ordem de inclusao).
3. **Demais partes** (campo 5 = `L`, `P`, `R` ou `O`): uma linha por parte relacionada com
   outro papel, com o codigo que o binding declara para esse papel.

Nas linhas de parte, o campo 6 sai `1` se o documento da parte esta entre os `documentos` da
ordem e `0` se nao.

- **Cotitular**: nesta versao, a conta em que o documento investigado e so cotitular nao
  entra; a decisao esta pendente (o motor ainda nao executa "titular OU cotitular", e o
  indice das partes no CRM nao separa o papel).
- **Contas de contraparte**: a IN pede os titulares das contas do arquivo CONTAS, que tambem
  lista as contas da mesma instituicao com que as investigadas transacionaram (campo 7 = `3`
  no CONTAS). Nesta versao as pessoas dessas contas nao entram.

## O que o tenant preenche no mapeamento (binding)

1. **Numero da agencia** (`numero_agencia`): o mesmo cadastro de agencias do AGENCIAS, 5
   digitos sem DV, `00001` sem agencia fisica. Os valores do exemplo sao sinteticos. Conta
   sem `banking_details.branch` no CRM, ou com agencia fora do cadastro, recusa a geracao.
2. **Codigo do papel** (`vinculo`): o CRM tem os papeis `PRIMARY_HOLDER` (cotitular, `C` no
   binding, numerado pelo template), `LEGAL_REPRESENTATIVE` (representante legal, `L`) e
   `RESPONSIBLE_PARTY`. Declare o codigo que `RESPONSIBLE_PARTY` recebe no seu cadastro:
   `R` representante, `P` procurador ou `O` outros. O exemplo usa `P`. Papel sem codigo
   declarado recusa a geracao.
3. **Codigo Compe** (`compe`): 3 digitos, ou `999` se a instituicao nao tem.
4. **Nome no Unicad** (`nomeUnicad`).
5. **Contrato de cambio** (`contratoCambio`, campo 28): `0` se a instituicao nao firma
   contrato de cambio. Nenhuma aplicacao Lerian registra contrato de cambio; a instituicao
   que firma nao tem fonte para o `1` neste documento.

O CNPJ vem da organizacao do Midaz. O tipo da conta vem do CRM
(`regulatory_fields.account_type`: DEPOSIT 1, SAVINGS 2, INVESTMENT 3,
OTHER_FINANCIAL_INVESTMENTS 4, NON_RESIDENT 5, PAYMENT 6). O tipo de pessoa do titular vem do
cadastro (`NATURAL_PERSON` 1, `LEGAL_PERSON` 2); outro valor recusa a geracao.

## De onde vem cada campo do titular

- Nome, documento, endereco principal (linha 1 e linha 2, CEP, UF, pais), telefones,
  e-mails, nome social e renda: o cadastro do titular no CRM.
- UF (campo 14): a sigla do endereco principal convertida no codigo IBGE pela tabela de
  `br/bcb/simba/tabelas/uf-ibge.compute.yaml`.
- Pais (campo 15): `Brasil` para o codigo `BR` do cadastro.
- Telefone (campo 17): o celular; sem celular, o outro telefone.
- Renda (campo 18): a renda mensal bruta declarada pela pessoa natural, em centavos sem
  separador (`500050` para R$ 5.000,50); data de referencia no campo 19.
- E-mail (campo 25): o principal e o secundario, separados por `;`.
- Inicio e fim do vinculo (campos 20 e 21): abertura e encerramento da conta.

Nas partes relacionadas, o CRM guarda so documento, nome, papel e as datas de inicio e fim do
vinculo. O tipo de pessoa da parte (campo 7) sai do tamanho do documento: 11 posicoes CPF
(`1`), 14 posicoes CNPJ (`2`).

## Periodo

As datas saem no dia civil de Brasilia (`America/Sao_Paulo`), no formato `ddmmaaaa`. O periodo
do afastamento nao filtra os vinculos: entram as partes que o CRM tem na conta.

## Campos que podem sair em branco, e por que

A IN manda preencher todos os campos e, quando a informacao nao existe, usar o codigo que o
Anexo I indica (art. 2o, paragrafo 1o; art. 3o, III). Onde o Anexo I nao da codigo, o campo
sai em branco:

- `NOME_DOC_IDENTIFICACAO` e `NUMERO_DOC_IDENTIFICACAO` (campos 10 e 11): sempre em branco. O
  CRM guarda so CPF/CNPJ; nenhuma aplicacao Lerian registra RG, CTPS, passaporte ou o
  documento constitutivo da pessoa juridica.
- `CODIGO_CIDADE` (campo 13): sempre em branco. O CRM guarda o nome da cidade, sem o codigo
  IBGE. O codigo `0000000` e so para pessoa domiciliada no exterior e nao e usado no lugar
  do codigo faltante.
- `DATA_FIM_RELACIONAMENTO_CONTA` (campo 21): em branco enquanto o vinculo esta ativo (conta
  aberta, ou parte sem data de fim). A IN nao da codigo para vinculo ativo.
- `DISPOSITIVO_MOVEL_CADASTRADO` e `COMPUTADOR_CADASTRADO` (campos 26 e 27): sempre em
  branco. Nenhuma aplicacao Lerian registra os dispositivos cadastrados do cliente.
- Do titular, quando o cadastro nao tem o dado: endereco (12), CEP (16), telefone (17),
  renda e data da renda (18 e 19), nome social (24) e abertura da conta (20).
- `VALOR_RENDA` e `DATA_ATUALIZACAO_RENDA` (campos 18 e 19) da pessoa juridica: em branco. O
  CRM tem o faturamento anual da empresa, e a regra para declara-lo (anual ou mensal) esta
  em aberto.
- Das partes relacionadas: campos 12 a 19 e 24 em branco, porque a parte no CRM nao tem
  endereco, telefone, renda nem nome social.

Sem e-mail no cadastro, e sempre nas partes relacionadas, o campo 25 sai
`e-mail nao declarado`, o codigo da IN, sem acento.

## Limitacoes desta versao

- **UF do titular**: titular sem UF no endereco principal, com sigla fora da tabela ou
  domiciliado no exterior recusa a geracao. Corrija o cadastro antes de gerar.
- **Titular sem cadastro**: o cadastro do titular vem do CRM pelo documento da ordem e pelo
  `holder_id` da conta. Conta do caso cujo titular nao e encontrado no cadastro (apagado, ou
  com documento diferente do da ordem) fica sem tipo de pessoa, documento e nome, e a geracao
  e recusada.
- **Ordem dos cotitulares**: a numeracao segue a ordem em que o CRM guarda as partes, nao a
  data de inicio do vinculo. O campo 5 tem uma posicao: com dez ou mais cotitulares numa
  conta, o numero passa de uma posicao.
- **Titular repetido como parte**: o titular nao deve estar cadastrado tambem como parte
  relacionada da propria conta; se estiver, ele sai duas vezes (como `T` e como cotitular).
- **Vinculo removido**: uma parte removida do instrumento pela API do CRM sai da lista sem
  data de fim. O campo 21 so registra o fim do vinculo que o cadastro encerrou com a data.
- **Numero da conta**: sai como o CRM o guarda (`banking_details.account`), ate 20 posicoes;
  confira que o valor cadastrado inclui o DV.
- **Texto sem acento**: nomes, endereco, telefones e e-mails passam pela conversao para ASCII
  do template, e TAB vira espaco. **Quebra de linha (CR ou LF) dentro de um valor nao e
  retirada.**
- **Pessoa investigada nas partes**: o campo 6 compara o documento da parte com cada
  elemento da lista `documentos` da ordem, que vem so com digitos.
- **Preview do template**: a pre-visualizacao de template do manager recusa este template,
  porque ele usa uma macro. A geracao nao.
- **Uma instituicao por arquivo**: um documento entregue em base individual nao soma
  instituicoes diferentes.

## Fonte primaria

Instrucao Normativa BCB 636/2025, art. 2o, III; art. 3o; Anexo I, arquivo III Titulares
(transcricao em `br/bcb/simba/normas/IN-BCB-636-2025.md`):
https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Instru%C3%A7%C3%A3o%20Normativa%20BCB&numero=636
