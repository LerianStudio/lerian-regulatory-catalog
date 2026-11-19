# SIMBA — Extrato (arquivo IV EXTRATO)

Arquivo IV do SIMBA, leiaute da Instrucao Normativa BCB 636/2025 (Anexo I, campos 1 a 27, e
Anexo II, codigos do tipo de lancamento). A IN entra em vigor em 01/12/2026 (art. 7o): use
este documento a partir dessa data.

## O que e

Uma linha por lancamento das contas investigadas no periodo do afastamento do sigilo (IN
art. 2o, IV). E um dos cinco arquivos da resposta ao caso; os outros sao AGENCIAS, CONTAS,
TITULARES e ORIGEM-DESTINO, gerados com os mesmos parametros.

## Parametros da geracao

Os mesmos nos cinco documentos SIMBA: `caso`, `documentos` (CPFs e CNPJs da ordem, somente
digitos, sem pontos, tracos ou barras: o documento formatado nao encontra contas e o caso sai
como resposta vazia para ele, sem erro; a conferencia antes da aprovacao avisa o documento sem
conta), `contas` (numeros de conta da ordem com DV, so digitos; preencher so quando o oficio
restringir a contas especificas: o normal e nao preencher, e ausente entram todas as contas
dos documentos; preencher sem a ordem pedir omite contas do investigado), `inicio` e `fim` (primeiro e ultimo dia do afastamento). Duas geracoes do
mesmo `caso` sao a mesma entrega: a mais nova substitui o rascunho anterior.

O `fim` tem de ser um dia que ja acabou no calendario do Reporter: a geracao le um periodo
fechado, e o lancamento gravado depois nao desloca a numeracao entre os arquivos.

## Quais lancamentos entram

As operacoes das contas do caso que movem saldo em reais (`balance_affected`, `BRL`), nao
apagadas, do inicio do dia `inicio` ao fim do dia `fim` no calendario do Reporter. As reservas e
liberacoes do Midaz (operacoes `ON_HOLD` e `RELEASE`) ficam fora: a transferencia que passou
por reserva sai uma vez so, com a operacao que a concluiu. Num ledger que valida rotas, a reserva
cancelada sai como um debito e um credito de mesmo valor (a reserva e a devolucao), e uma reserva
ainda aberta na data de corte sai como debito, sem a operacao que a concluiria. As contas
do caso sao as mesmas do CONTAS: as que um documento da ordem titula (cotitular,
representante e procurador nao entram).

## Numero do lancamento e o ORIGEM-DESTINO

O campo 1 (`CODIGO_CHAVE_EXTRATO`) e o campo 7 (`NUMERO_DOCUMENTO`) sao o numero sequencial
do lancamento no arquivo. O ORIGEM-DESTINO le o mesmo conjunto de lancamentos, na mesma
ordem (por transacao e operacao), e numera do mesmo jeito: o mesmo lancamento tem o mesmo
numero nos dois arquivos.

- **Gere os dois em seguida, com os mesmos parametros.** Um lancamento gravado entre as duas
  geracoes desloca os numeros. Confira que os dois arquivos tem o mesmo numero de
  lancamentos (o ultimo campo 2 do ORIGEM-DESTINO e o ultimo campo 1 do EXTRATO); se nao
  baterem, gere os dois de novo.
- O campo 27 (`IDENTIFICADOR_SESSAO`) e um numero por transacao: as operacoes da mesma
  transacao (por exemplo, o Pix e a tarifa dele) repetem o numero.

## Codigo do tipo de lancamento (campo 9, Anexo II)

Na ordem, a primeira regra que vale:

1. **Estorno** (revert do Midaz, transacao com `parent_transaction_id`): o de uma transferencia
   (lancamento com trilho ou com dado de Pix na metadata) sai `140` no debito e `264` no credito;
   os demais, como o de uma tarifa, `142` e `266` (estornos diversos, IN :411 e :507).
2. **Tarifa** (operacao que o motor de tarifas do Midaz marcou com `feeLeg`, e a cobranca de
   divida de tarifa, `FEE_SETTLEMENT`, que o Midaz grava sem `feeLeg`): `105`; o reembolso
   (`FEE_REFUND`, num revert) e um estorno: `266`.
3. **Plugin com contrato de correlacao** (TED, Pix JD), pela metadata da transacao
   (`rail`, `flow`, `direction`; direcao vazia vale a natureza): devolucao (`REFUND`) `140`/
   `264`; Pix enviado ou entre contas da instituicao `135`, recebido `261`; TED enviada `134`,
   recebida `259`; transferencia TED ou interna entre contas da instituicao (`P2P`) `133`/`258`.
4. **Pix lerian**: recebido (`payment_type` `PIX_IN`) `261`, ou `223` quando a iniciacao foi
   por QR Code; devolucao (`original_end_to_end_id`) `140`/`264`; enviado (`end_to_end_id` com
   `initiation_id`) `135`.
5. **Nada acima**: `125` no debito, `218` no credito.

So sai codigo do lado da natureza (debito `1xx`, credito `2xx`). O codigo `116` nunca sai.

**Atencao, codigos genericos:** `125` e `218` sao descontinuados em 01/06/2028 (IN art. 2o,
§ 4o) sem substituto indicado. Saem com eles: lancamento sem metadata de plugin, tarifa
avulsa sem `feeLeg`, transferencia interna sem metadata, MED, Pix Automatico e bloqueio
cautelar. Revise as linhas com `125`/`218` antes de aprovar.

## O que o tenant preenche no mapeamento (binding)

1. **Numero da agencia** (`numero_agencia`): o mesmo cadastro de agencias do AGENCIAS, 5
   digitos sem DV, `00001` sem agencia fisica. Os valores do exemplo sao sinteticos.
2. **Codigo Compe** (`compe`): 3 digitos, ou `999` se a instituicao nao tem.
3. **Nome no Unicad** (`nomeUnicad`).
4. **Canal** (`interfaceTransacao`, campo 17): um codigo de 1 a 9 da IN para todas as linhas
   (o exemplo declara `9`, outros). Nenhuma aplicacao Lerian registra o canal por lancamento.
5. **Fonte `midaz_metadata`**: o Mongo da metadata do Midaz (colecoes `transaction` e
   `operation`), que a configuracao padrao do Reporter nao traz; cadastre-a antes.

O CNPJ vem da organizacao do Midaz; tipo da conta do CRM (`regulatory_fields.account_type`).

Num tenant com mais de uma organizacao, o cadastro da instituicao no Reporter restringe
`organization.id` a organizacao dela; sem isso a leitura traz todas, e a geracao e recusada
(o CNPJ lido nao e o da instituicao, ou chegam duas linhas para uma) em vez de escolher uma.

## Data, hora, valores e saldo

- **Data (campo 6)**: o dia civil de Brasilia do instante do lancamento (`created_at` da
  operacao). **Hora (campo 23)**: o mesmo instante em UTC, `hhmmss` (IN art. 3o VI). Um Pix as
  23:30 de 09/12 em Brasilia sai `09122026` e `023000`. O instante tem de chegar ao Reporter
  em UTC; se chegar em outro fuso, a geracao e recusada (nao sai a hora errada).
- **Valor (campo 10)**: centavos, sem separador e sem sinal (`10000` para R$ 100,00).
- **Natureza (campo 11)**: `C` credito, `D` debito; operacao sem direcao recusa a geracao.
- **Saldo (campos 12 e 13)**: o saldo da conta depois do lancamento, como a IN pede: o
  disponivel que o Midaz gravou na operacao, mais o bloqueado (`on_hold`), menos o cheque
  especial usado (gravado no `snapshot` da operacao). Em centavos, sem sinal; o campo 13 sai
  `D` se o saldo for devedor e `C` nos demais. A conta no cheque especial sai devedora
  (`1250` e `D` com R$ 12,50 usados).

## Campos que saem em branco ou com sentinela, e por que

- 14 (`INFO_ADICIONAIS_LOCAL_TRANSACAO`), 20 a 22 (IP, porta, MAC), 24 e 25 (chave Pix): em
  branco; nenhuma aplicacao Lerian registra o dado, ou a chave nao esta na metadata.
- 18 e 19: `0000000` e `00`, as sentinelas da IN para localizacao indisponivel.
- 26 (`ID_TRANSACAO_PIX`): o EndToEndId gravado na metadata da transacao Pix; o txid de QR
  Code nao esta na metadata (sai no ORIGEM-DESTINO). Fora do Pix, em branco.
- 8: a descricao da operacao; vazia, a da transacao.

## Investigado sem conta

Quando nenhum documento da ordem tem conta na instituicao, nao ha arquivo a gerar: os
arquivos do SIMBA sao das contas (IN art. 1o, :23) e nao tem cabecalho (art. 3o, I, :59).
O AGENCIAS, o CONTAS e o TITULARES do caso recusam a geracao antes de montar o arquivo
(erro RPT-0195); nao gere este. Responda a requisicao sem arquivo, pelo atendimento:
CCS0012 com a situacao 03, relacionamento inexistente (Catalogo de Servicos do SFN,
Volume III, evento CCS0012; Dicionario de Dominios do Banco Central, dominio
SitAtedmntReq).

Quando a ordem tem mais de um investigado e so parte deles tem conta, os arquivos saem com
as contas de quem tem; quem nao tem e declarado sem relacionamento no atendimento da
requisicao.

Uma conta do caso sem lancamento no periodo sai no CONTAS com o campo 7 = 2 (IN :126) e nao
tem linha aqui. Quando nenhuma conta do caso tem lancamento, este arquivo sai vazio (0
byte, sem cabecalho, IN art. 3o, I) e e aprovado e entregue assim, com os outros quatro.
O contrato declara isso (`filing.allowEmpty`); um Reporter anterior a esse recurso recusa
o contrato na carga.

## Limitacoes desta versao

- **Cheque especial em duas linhas**: quando um saque passa do saldo disponivel, o Midaz
  grava a parte coberta pelo disponivel numa operacao e a parte tirada do cheque especial
  em outra (chave `overdraft`); um credito que paga o cheque especial tambem se divide. O
  arquivo traz as duas linhas, na mesma sessao (campo 27) e com o mesmo codigo da transacao,
  cada uma com o seu valor: o lancamento de R$ 100,00 com R$ 30,00 disponiveis sai como 30,00
  e 70,00; com o disponivel ja em zero, a parte do disponivel sai com R$ 0,00. A linha da
  parte do disponivel traz o saldo real da conta; a da parcela traz o saldo da chave de
  cheque especial (menos a divida, sem o valor bloqueado). Numa transacao que tambem tem
  tarifa, a parcela pode ser da tarifa e sai com o codigo e a contraparte da transacao. Num
  credito que quita a divida e sobra saldo, a parcela que paga o cheque especial sai com o
  saldo `000 C`; como o Midaz grava a parcela depois da linha principal, ela pode ser a
  ultima linha da conta no periodo e diferir do saldo final do CONTAS, que e o certo. A
  conferencia antes da aprovacao lista essas transacoes.
- **Periodo por investigado**: a ordem pode dar um periodo de afastamento para cada
  investigado, e esta versao tem um so `inicio`/`fim` por caso (a geracao mais nova do
  mesmo `caso` substitui a anterior, entao o caso nao se divide em duas). Nao suportado
  nesta versao; tratar fora do Reporter. Gerar com o periodo mais amplo poria no arquivo
  movimento fora do afastamento.
- **Saldo gravado por operacao, nao soma corrida**: o campo 12 sai dos saldos que o Midaz
  gravou em cada operacao, na ordem em que gravou. Com lancamento retroativo, ou conta com
  mais de uma chave de saldo, a linha nao fecha com o saldo do CONTAS. O motor nao tem soma
  corrida.
- **Operacao gravada antes do snapshot**: o Midaz passou a guardar o cheque especial usado em
  cada operacao a partir de uma versao; a operacao anterior nao o tem, e o saldo dela sai sem
  o cheque especial (como se fosse zero). A conferencia lista esses lancamentos.
- **Conta em ponto flutuante**: o template soma o saldo em ponto flutuante e arredonda ao
  centavo, meio centavo para longe do zero. Com duas casas, o resultado e exato bem abaixo de
  R$ 1e13 (medido com R$ 999.999.999.999,99). Com mais casas (tarifa percentual sem
  arredondamento, rateio por percentual), o meio centavo e decidido com folga de um
  milionesimo de centavo, que vale para saldos ate cerca de R$ 1 bilhao.
- **Codigos especificos sem marca**: Pix Saque, Pix Troco, mesma titularidade e boleto saem
  com o codigo largo (`135`/`261` no Pix, `134`/`259` na TED).
- **Texto sem acento**: descricao e nome da instituicao passam pela conversao para ASCII do
  template, e TAB vira espaco. **Quebra de linha (CR ou LF) dentro de um valor nao e retirada.**
- **Preview do template**: a pre-visualizacao de template do manager recusa este template,
  porque ele usa macros. A geracao nao.
- **Ordem**: a ordem do arquivo e a da leitura agrupada por transacao e operacao, nao a
  cronologica.

## Fonte primaria

Instrucao Normativa BCB 636/2025, art. 2o, IV e § 3o e § 4o; art. 3o; Anexo I, arquivo IV
Extrato; Anexo II (transcricao em `br/bcb/simba/normas/IN-BCB-636-2025.md`; tabela dos
codigos em `br/bcb/simba/tabelas/anexo-ii.yaml`):
https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Instru%C3%A7%C3%A3o%20Normativa%20BCB&numero=636
