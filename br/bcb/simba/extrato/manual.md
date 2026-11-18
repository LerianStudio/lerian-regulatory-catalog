# SIMBA — Extrato (arquivo IV EXTRATO)

Arquivo IV do SIMBA, leiaute da Instrucao Normativa BCB 636/2025 (Anexo I, campos 1 a 27, e
Anexo II, codigos do tipo de lancamento). A IN entra em vigor em 01/12/2026 (art. 7o): use
este documento a partir dessa data.

## O que e

Uma linha por lancamento das contas investigadas no periodo do afastamento do sigilo (IN
art. 2o, IV). E um dos cinco arquivos da resposta ao caso; os outros sao AGENCIAS, CONTAS,
TITULARES e ORIGEM-DESTINO, gerados com os mesmos parametros.

## Parametros da geracao

Os mesmos nos cinco documentos SIMBA: `caso`, `documentos` (CPFs e CNPJs da ordem, so
digitos), `contas` (numeros de conta da ordem com DV, so digitos; ausente, todas as contas
dos documentos), `inicio` e `fim` (primeiro e ultimo dia do afastamento). Duas geracoes do
mesmo `caso` sao a mesma entrega: a mais nova substitui o rascunho anterior.

## Quais lancamentos entram

As operacoes das contas do caso que movem saldo em reais (`balance_affected`, `BRL`), nao
apagadas, do inicio do dia `inicio` ao fim do dia `fim` no calendario do Reporter. As contas
do caso sao as mesmas do CONTAS: as que um documento da ordem titula (cotitular: decisao
pendente).

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

1. **Estorno** (revert do Midaz, transacao com `parent_transaction_id`): `140` no debito,
   `264` no credito.
2. **Tarifa** (operacao que o motor de tarifas do Midaz marcou com `feeLeg`): `105`.
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

## Data, hora, valores e saldo

- **Data (campo 6)**: o dia civil de Brasilia do instante do lancamento (`created_at` da
  operacao). **Hora (campo 23)**: o mesmo instante em UTC, `hhmmss` (IN art. 3o VI). Um Pix as
  23:30 de 09/12 em Brasilia sai `09122026` e `023000`. O instante tem de chegar ao Reporter
  em UTC; se chegar em outro fuso, a geracao e recusada (nao sai a hora errada).
- **Valor (campo 10)**: centavos, sem separador e sem sinal (`10000` para R$ 100,00).
- **Natureza (campo 11)**: `C` credito, `D` debito; operacao sem direcao recusa a geracao.
- **Saldo (campos 12 e 13)**: o saldo disponivel que o Midaz gravou na operacao, em centavos,
  sem sinal; o campo 13 sai `D` se o saldo for negativo e `C` nos demais.

## Campos que saem em branco ou com sentinela, e por que

- 14 (`INFO_ADICIONAIS_LOCAL_TRANSACAO`), 20 a 22 (IP, porta, MAC), 24 e 25 (chave Pix): em
  branco; nenhuma aplicacao Lerian registra o dado, ou a chave nao esta na metadata.
- 18 e 19: `0000000` e `00`, as sentinelas da IN para localizacao indisponivel.
- 26 (`ID_TRANSACAO_PIX`): o EndToEndId gravado na metadata da transacao Pix; o txid de QR
  Code nao esta na metadata (sai no ORIGEM-DESTINO). Fora do Pix, em branco.
- 8: a descricao da operacao; vazia, a da transacao.

## Limitacoes desta versao

- **Saldo do Midaz, nao soma corrida**: o campo 12 e o saldo disponivel gravado pelo Midaz, na
  ordem em que gravou. Com lancamento retroativo, ou conta com mais de uma chave de saldo, a
  linha nao fecha com o saldo do CONTAS. O saldo disponivel nao fica abaixo de zero: conta no
  cheque especial sai com `000` e `C`, e o valor bloqueado fica fora. O motor nao tem soma
  corrida.
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
