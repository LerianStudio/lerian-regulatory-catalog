# SIMBA — Contas (arquivo II CONTAS)

Arquivo II do SIMBA, leiaute da Instrucao Normativa BCB 636/2025 (Anexo I, campos 1 a 12).
A IN entra em vigor em 01/12/2026 (art. 7o): use este documento a partir dessa data.

## O que e

Uma linha por conta: as contas investigadas e as contas da mesma instituicao com as quais
elas transacionaram no periodo do afastamento do sigilo (IN art. 2o, II). E um dos cinco
arquivos da resposta ao caso; os outros sao AGENCIAS, TITULARES, EXTRATO e
ORIGEM-DESTINO, gerados com os mesmos parametros.

## Parametros da geracao

Os mesmos nos cinco documentos SIMBA: `caso`, `documentos` (CPFs e CNPJs da ordem, somente
digitos, sem pontos, tracos ou barras: o documento formatado nao encontra contas e o caso sai
como resposta vazia para ele, sem erro; a conferencia antes da aprovacao avisa o documento sem
conta), `contas` (numeros de conta da ordem com DV, so digitos; preencher so quando o oficio
restringir a contas especificas: o normal e nao preencher, e ausente entram todas as contas
dos documentos; preencher sem a ordem pedir omite contas do investigado), `inicio` e `fim` (primeiro e ultimo dia do afastamento). Duas geracoes do
mesmo `caso` sao a mesma entrega: a mais nova substitui o rascunho anterior.

## Quais contas entram

- **Investigadas** (campo 7 = `1` com lancamento no periodo, `2` sem): as contas em que um
  documento da ordem e o **titular**. Encerradas entram, com a data de encerramento.
  Apagadas do CRM nao entram.
- **So titular**: a conta em que o documento investigado e so cotitular, representante
  ou procurador nao entra; o indice das partes no CRM nao separa o papel.
- **Contas com que as investigadas transacionaram** (campo 7 = `3`): as outras pernas dos
  lancamentos das contas investigadas no periodo, quando sao conta de cliente no CRM. Uma
  conta que tambem e investigada sai uma vez so, como investigada.

## O que o tenant preenche no mapeamento (binding)

1. **Numero da agencia** (`numero_agencia`): o mesmo cadastro de agencias do AGENCIAS, 5
   digitos sem DV, `00001` sem agencia fisica. Os valores do exemplo sao sinteticos. Conta
   sem `banking_details.branch` no CRM, ou com agencia fora do cadastro, recusa a geracao.
2. **Codigo Compe** (`compe`): 3 digitos, ou `999` se a instituicao nao tem.
3. **Nome no Unicad** (`nomeUnicad`).

O CNPJ vem da organizacao do Midaz. O tipo da conta vem do CRM
(`regulatory_fields.account_type`: DEPOSIT 1, SAVINGS 2, INVESTMENT 3,
OTHER_FINANCIAL_INVESTMENTS 4, NON_RESIDENT 5, PAYMENT 6); conta sem tipo recusa a geracao,
entao preencha o tipo no CRM antes.

Num tenant com mais de uma organizacao, o cadastro da instituicao no Reporter restringe
`organization.id` a organizacao dela; sem isso a leitura traz todas, e a geracao e recusada
(o CNPJ lido nao e o da instituicao, ou chegam duas linhas para uma) em vez de escolher uma.

## Saldos (campos 10 e 11)

O periodo vai do inicio do dia `inicio` ao fim do dia `fim` no calendario do Reporter
(`REPORT_TIMEZONE`, padrao `America/Sao_Paulo`). O saldo e a soma, com sinal, dos lancamentos que movem saldo em reais desde a abertura:
credito soma, debito subtrai, sem a chave de sistema `overdraft`. O inicial vai ate o
inicio do primeiro dia do afastamento; o final, ate o fim do ultimo. Os valores saem em
centavos, sem separador (`10000` para R$ 100,00; `000` para zero ou sem lancamento ate a
data).

- **Saldo negativo**: o Anexo I nao da sinal nem natureza a estes campos, e um campo
  numerico nao admite traco (IN art. 3o VII). Uma conta que comeca ou termina devedora
  (cheque especial) sai com o saldo em valor absoluto (`1250` para -R$ 12,50): o arquivo
  nao mostra que o saldo era devedor. Antes de aprovar, confira as contas com saldo
  negativo, inclusive as que nao tiveram lancamento no periodo.
- Cliente com arquivo morto do Midaz (`retain`) perde o historico antigo e o saldo sai
  errado sem aviso: o SIMBA parte de cliente sem `retain`.

## Campos que podem sair em branco, e por que

- `DATA_ABERTURA_CONTA` (campo 5): vem do CRM (`banking_details.opening_date`); a IN nao da
  sentinela, e sem a data o campo sai em branco.
- `CONTA_INSTITUICAO_INCORPORADA` (campo 12): sempre em branco. A IN manda deixar em branco
  a conta nativa, e nenhuma aplicacao Lerian registra que uma conta veio de uma instituicao
  sucedida.

Sem data de encerramento, o campo 6 sai `31129999`, a sentinela da IN.

## Limitacoes desta versao

- **Periodo por investigado**: a ordem pode dar um periodo de afastamento para cada
  investigado, e esta versao tem um so `inicio`/`fim` por caso (a geracao mais nova do
  mesmo `caso` substitui a anterior, entao o caso nao se divide em duas). Nao suportado
  nesta versao; tratar fora do Reporter. Gerar com o periodo mais amplo poria no arquivo
  movimento fora do afastamento.
- **Numero da conta**: sai como o CRM o guarda (`banking_details.account`), ate 20 posicoes;
  confira que o valor cadastrado inclui o DV.
- **Texto sem acento**: o nome da instituicao passa pela conversao para ASCII do template, e
  TAB vira espaco. **Quebra de linha (CR ou LF) dentro de um valor nao e retirada.**
- **Preview do template**: a pre-visualizacao de template do manager recusa este template,
  porque ele usa uma macro. A geracao nao.
- **Uma instituicao por arquivo**: um documento entregue em base individual nao soma
  instituicoes diferentes.

## Fonte primaria

Instrucao Normativa BCB 636/2025, art. 2o, II; art. 3o; Anexo I, arquivo II Contas
(transcricao em `br/bcb/simba/normas/IN-BCB-636-2025.md`):
https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Instru%C3%A7%C3%A3o%20Normativa%20BCB&numero=636
