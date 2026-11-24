# SIMBA — Extrato (arquivo IV EXTRATO)

Arquivo IV do SIMBA, leiaute da Instrução Normativa BCB 636/2025 (Anexo I, campos 1 a 27, e
Anexo II, códigos do tipo de lançamento). A IN entra em vigor em 01/12/2026 (art. 7º): use
este documento a partir dessa data.

## O que é

Uma linha por lançamento das contas investigadas no período do afastamento do sigilo (IN
art. 2º, IV). É um dos cinco arquivos da resposta ao caso; os outros são AGÊNCIAS, CONTAS,
TITULARES e ORIGEM-DESTINO, gerados com os mesmos parâmetros.

## Parâmetros da geração

Os mesmos nos cinco documentos SIMBA: `caso`, `documentos` (CPFs e CNPJs da ordem, somente
dígitos, sem pontos, traços ou barras: o documento formatado não encontra contas e o caso sai
como resposta vazia para ele, sem erro; a conferência antes da aprovação avisa o documento sem
conta), `contas` (números de conta da ordem com DV, só dígitos; preencher só quando o ofício
restringir a contas específicas: o normal é não preencher, e, ausente, entram todas as contas
dos documentos; preencher sem a ordem pedir omite contas do investigado), `inicio` e `fim` (primeiro e último dia do afastamento). Duas gerações do
mesmo `caso` são a mesma entrega: a mais nova substitui o rascunho anterior.

O `fim` tem de ser um dia que já acabou no calendário do Reporter: a geração lê um período
fechado, e o lançamento gravado depois não desloca a numeração entre os arquivos.
O `fim` também não pode ser anterior ao `inicio`: um período invertido é recusado ao gerar,
em vez de sair um arquivo sem lançamento nenhum.

## Quais lançamentos entram

As operações das contas do caso que movem saldo em reais (`balance_affected`, `BRL`), não
apagadas, do início do dia `inicio` ao fim do dia `fim` no calendário do Reporter. As reservas e
liberações do Midaz (operações `ON_HOLD` e `RELEASE`) ficam fora: a transferência que passou
por reserva sai uma vez só, com a operação que a concluiu. Num ledger que valida rotas, a reserva
cancelada sai como um débito e um crédito de mesmo valor (a reserva e a devolução), e uma reserva
ainda aberta na data de corte sai como débito, sem a operação que a concluiria. As contas
do caso são as mesmas do CONTAS: as que um documento da ordem titula (cotitular,
representante e procurador não entram).

## Número do lançamento e o ORIGEM-DESTINO

O campo 1 (`CODIGO_CHAVE_EXTRATO`) e o campo 7 (`NUMERO_DOCUMENTO`) são o número sequencial
do lançamento no arquivo. O ORIGEM-DESTINO lê o mesmo conjunto de lançamentos, na mesma
ordem (por transação e operação), e numera do mesmo jeito: o mesmo lançamento tem o mesmo
número nos dois arquivos.

- **Gere os dois em seguida, com os mesmos parâmetros.** Um lançamento gravado entre as duas
  gerações desloca os números. Confira que os dois arquivos têm o mesmo número de
  lançamentos (o último campo 2 do ORIGEM-DESTINO e o último campo 1 do EXTRATO); se não
  baterem, gere os dois de novo.
- O campo 27 (`IDENTIFICADOR_SESSAO`) é um número por transação: as operações da mesma
  transação (por exemplo, o Pix e a tarifa dele) repetem o número.

## Código do tipo de lançamento (campo 9, Anexo II)

Na ordem, a primeira regra que vale:

1. **Pelo tipo da operação no Midaz**: a cobrança de dívida de tarifa (`FEE_SETTLEMENT`, no
   débito) `105`, mesmo dentro de um revert (a cobrança é tarifa, não estorno); o bloqueio
   judicial (`BLOCK`, no débito) `150`; o desbloqueio (`UNBLOCK`, no crédito) `272` (IN 636,
   Anexo II).
2. **Estorno** (revert do Midaz, transação com `parent_transaction_id`): o de uma transferência
   (lançamento com trilho ou com dado de Pix na metadata) sai `140` no débito e `264` no crédito;
   os demais, como o de uma tarifa, `142` e `266` (estornos diversos, IN 636, Anexo II).
3. **Tarifa** (operação que o motor de tarifas do Midaz marcou com `feeLeg`): `105`; o
   reembolso de dívida de tarifa (`FEE_REFUND`, num revert) é um estorno: `266`.
4. **Plugin com contrato de correlação** (TED, Pix JD), pela metadata da transação
   (`rail`, `flow`, `direction`; direção vazia vale a natureza): devolução (`REFUND`) `140`/
   `264`; Pix enviado ou entre contas da instituição `135`, recebido `261`; TED enviada `134`,
   recebida `259`; transferência TED ou interna entre contas da instituição (`P2P`) `133`/`258`.
5. **Pix lerian**: recebido (`payment_type` `PIX_IN`) `261`, ou `223` quando a iniciação foi
   por QR Code; devolução (`original_end_to_end_id`) `140`/`264`; enviado (`end_to_end_id` com
   `initiation_id`) `135`.
6. **Nada acima**: `125` no débito, `218` no crédito.

Só sai código do lado da natureza (débito `1xx`, crédito `2xx`). O código `116` nunca sai.

**Atenção, códigos genéricos:** `125` e `218` são descontinuados em 01/06/2028 (IN 636, art. 2º,
§ 4º) sem substituto indicado. Saem com eles: lançamento sem metadata de plugin, tarifa
avulsa sem `feeLeg`, transferência interna sem metadata, MED, Pix Automático e bloqueio
cautelar. Revise as linhas com `125`/`218` antes de aprovar.

## O que o tenant preenche no mapeamento (binding)

1. **Número da agência** (`numero_agencia`): o mesmo cadastro de agências do AGÊNCIAS, 5
   dígitos sem DV, `00001` sem agência física. Os valores do exemplo são sintéticos.
2. **Código Compe** (`compe`): 3 dígitos, ou `999` se a instituição não tem.
3. **Nome no Unicad** (`nomeUnicad`).
4. **Canal** (`interfaceTransacao`, campo 17): um código de 1 a 9 da IN para todas as linhas
   (o exemplo declara `9`, outros). Nenhuma aplicação Lerian registra o canal por lançamento.
5. **Fonte `midaz_metadata`**: o Mongo da metadata do Midaz (coleções `transaction` e
   `operation`), que a configuração padrão do Reporter não traz; cadastre-a antes.
6. **Fontes dos plugins de Pix** (`pix_lerian`, `pix_jd`), as mesmas do ORIGEM-DESTINO: o
   TxId do campo 26 está só no plugin. Quem não usa um plugin apaga as consultas dele e
   declara vazio cada conjunto `trilho_*` dele, com o motivo:
   `trilho_pix_jd_envios: {emptyReason: "a instituicao nao usa o Pix JD"}`. Não apague o
   conjunto: sem origem, o campo obrigatório dele fica pendente e o rascunho não pode ser
   aprovado.

O CNPJ vem da organização do Midaz; tipo da conta do CRM (`regulatory_fields.account_type`).

Num tenant com mais de uma organização, o cadastro da instituição no Reporter restringe
`organization.id` à organização dela; sem isso a leitura traz todas, e a geração é recusada
(o CNPJ lido não é o da instituição, ou chegam duas linhas para uma) em vez de escolher uma.

## Data, hora, valores e saldo

- **Data (campo 6)**: o dia civil de Brasília do instante do lançamento (`created_at` da
  operação). **Hora (campo 23)**: o mesmo instante em UTC, `hhmmss` (IN 636, art. 3º, VI). Um Pix às
  23:30 de 09/12 em Brasília sai `09122026` e `023000`. O instante tem de chegar ao Reporter
  em UTC; se chegar em outro fuso, a geração é recusada (não sai a hora errada).
- **Valor (campo 10)**: centavos, sem separador e sem sinal (`10000` para R$ 100,00).
- **Natureza (campo 11)**: `C` crédito, `D` débito; operação sem direção recusa a geração.
- **Saldo (campos 12 e 13)**: o saldo da conta depois do lançamento, como a IN pede: o
  disponível que o Midaz gravou na operação, mais o bloqueado (`on_hold`), menos o cheque
  especial usado (gravado no `snapshot` da operação). Em centavos, sem sinal; o campo 13 sai
  `D` se o saldo for devedor e `C` nos demais. A conta no cheque especial sai devedora
  (`1250` e `D` com R$ 12,50 usados).

## Campos que saem em branco ou com sentinela, e por quê

- 14 (`INFO_ADICIONAIS_LOCAL_TRANSACAO`), 20 a 22 (IP, porta, MAC), 24 e 25 (chave Pix): em
  branco; nenhuma aplicação Lerian registra o dado, ou a chave não está na metadata.
- 18 e 19: `0000000` e `00`, as sentinelas da IN para localização indisponível.
- 26 (`ID_TRANSACAO_PIX`, `TransactionIdentification <TxId>`; IN 636, Anexo I, EXTRATO,
  campo 26): o TxId que o plugin que liquidou o Pix grava, o mesmo do campo 28 do
  ORIGEM-DESTINO; nunca o EndToEndId, que é outro identificador. Em branco fora do Pix, no Pix
  sem TxId (por chave ou manual, ou QR estático com `***` no lugar do TxId) e no Pix enviado
  pelo Pix JD, que repassa o TxId ao SPI sem guardá-lo; o campo 18 do ORIGEM-DESTINO diz o
  motivo.
- 8: a descrição da operação; vazia, a da transação.

## Nome dos arquivos na entrega

O arquivo baixado do Reporter tem o nome do relatório (o identificador da geração, com
extensão `.txt`), e não o nome que a entrega exige. Antes de validar e transmitir, renomeie
cada um dos cinco arquivos com o prefixo do número do caso, no formato
`999-XXX-999999-99_ARQUIVO.TXT` (Memorando de Instrução MI 001 - ASSPA/PGR, item 1.4, b). O
número do caso é o mesmo informado no parâmetro `caso` da geração, como está no ofício. Este
arquivo é o `<caso>_EXTRATO.TXT`; para o caso 001-MPF-005097-79, por exemplo,
`001-MPF-005097-79_EXTRATO.TXT`.

Os cinco arquivos de uma entrega levam o mesmo prefixo: `<caso>_AGENCIAS.TXT`,
`<caso>_CONTAS.TXT`, `<caso>_TITULARES.TXT`, `<caso>_EXTRATO.TXT` e
`<caso>_ORIGEM_DESTINO.TXT` (com sublinhado no ORIGEM_DESTINO, como no memorando). Só o nome
muda: o conteúdo do arquivo não é alterado.

## Investigado sem conta

Quando nenhum documento da ordem tem conta na instituição, não há arquivo a gerar: os
arquivos do SIMBA são das contas (IN 636, art. 1º) e não têm cabeçalho (IN 636, art. 3º, I).
O AGÊNCIAS, o CONTAS e o TITULARES do caso recusam a geração antes de montar o arquivo
(erro RPT-0195); não gere este. Responda à requisição sem arquivo, pelo atendimento:
CCS0012 com a situação 03, relacionamento inexistente (Catálogo de Serviços do SFN,
Volume III, evento CCS0012; Dicionário de Domínios do Banco Central, domínio
SitAtedmntReq).

Quando a ordem tem mais de um investigado e só parte deles tem conta, os arquivos saem com
as contas de quem tem; quem não tem é declarado sem relacionamento no atendimento da
requisição.

Uma conta do caso sem lançamento no período sai no CONTAS com o campo 7 = 2 (IN 636, Anexo I,
CONTAS, campo 7) e não tem linha aqui. Quando nenhuma conta do caso tem lançamento, este
arquivo sai vazio (0 byte, sem cabeçalho, IN 636, art. 3º, I) e é aprovado e entregue assim, com
os outros quatro. O contrato declara isso (`filing.allowEmpty`); um Reporter anterior a esse
recurso recusa o contrato na carga.

## Limitações desta versão

- **Cheque especial em duas linhas**: quando um saque passa do saldo disponível, o Midaz
  grava a parte coberta pelo disponível numa operação e a parte tirada do cheque especial
  em outra (chave `overdraft`); um crédito que paga o cheque especial também se divide. O
  arquivo traz as duas linhas, na mesma sessão (campo 27) e com o mesmo código da transação,
  cada uma com o seu valor: o lançamento de R$ 100,00 com R$ 30,00 disponíveis sai como 30,00
  e 70,00; com o disponível já em zero, a parte do disponível sai com R$ 0,00. A linha da
  parte do disponível traz o saldo real da conta; a da parcela traz o saldo da chave de
  cheque especial (menos a dívida, sem o valor bloqueado). Numa transação que também tem
  tarifa, a parcela pode ser da tarifa e sai com o código e a contraparte da transação. Num
  crédito que quita a dívida e sobra saldo, a parcela que paga o cheque especial sai com o
  saldo `000 C`; como o Midaz grava a parcela depois da linha principal, ela pode ser a
  última linha da conta no período e diferir do saldo final do CONTAS, que é o certo. A
  conferência antes da aprovação lista essas transações.
- **Período por investigado**: a ordem pode dar um período de afastamento para cada
  investigado, e esta versão tem um só `inicio`/`fim` por caso (a geração mais nova do
  mesmo `caso` substitui a anterior, então o caso não se divide em duas). Não suportado
  nesta versão; tratar fora do Reporter. Gerar com o período mais amplo poria no arquivo
  movimento fora do afastamento.
- **Saldo gravado por operação, não soma corrida**: o campo 12 sai dos saldos que o Midaz
  gravou em cada operação, na ordem em que gravou. Com lançamento retroativo, ou conta com
  mais de uma chave de saldo, a linha não fecha com o saldo do CONTAS. O motor não tem soma
  corrida.
- **Operação gravada antes do snapshot**: o Midaz passou a guardar o cheque especial usado em
  cada operação a partir de uma versão; a operação anterior não o tem, e o saldo dela sai sem
  o cheque especial (como se fosse zero). A conferência lista esses lançamentos.
- **Conta em ponto flutuante**: o template soma o saldo em ponto flutuante e arredonda ao
  centavo, meio centavo para longe do zero. Com duas casas, o resultado é exato bem abaixo de
  R$ 1e13 (medido com R$ 999.999.999.999,99). Com mais casas (tarifa percentual sem
  arredondamento, rateio por percentual), o meio centavo é decidido com folga de um
  milionésimo de centavo, que vale para saldos até cerca de R$ 1 bilhão.
- **Códigos específicos sem marca**: Pix Saque, Pix Troco, mesma titularidade e boleto saem
  com o código largo (`135`/`261` no Pix, `134`/`259` na TED).
- **Texto sem acento**: descrição e nome da instituição passam pela conversão para ASCII do
  template, e TAB, CR e LF viram espaço: uma quebra de linha não parte o registro. O número
  da conta não passa pela conversão: com TAB, CR ou LF ele recusa a geração. No nome da
  instituição, um caractere fora do ASCII que a conversão não cobre (por exemplo `°`, `’`,
  `–`, `ø`) recusa a geração, porque o arquivo é ASCII (IN 636, art. 3º). A descrição é texto
  livre: até o filtro de transliteração do Reporter, ela pode levar ao arquivo um caractere
  fora do ASCII que a conversão não cobre.
- **Preview do template**: a pré-visualização de template do manager recusa este template,
  porque ele usa macros. A geração não.
- **Ordem**: a ordem do arquivo é a da leitura agrupada por transação e operação, não a
  cronológica.

## Fonte primária

Instrução Normativa BCB 636/2025, art. 2º, IV e § 3º e § 4º; art. 3º; Anexo I, arquivo IV
Extrato; Anexo II (transcrição em `br/bcb/simba/normas/IN-BCB-636-2025.md`; tabela dos
códigos em `br/bcb/simba/tabelas/anexo-ii.yaml`):
https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Instru%C3%A7%C3%A3o%20Normativa%20BCB&numero=636
