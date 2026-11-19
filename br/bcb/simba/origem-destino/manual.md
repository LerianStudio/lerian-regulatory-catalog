# SIMBA — Origem-Destino (arquivo V ORIGEM-DESTINO)

Arquivo V do SIMBA, leiaute da Instrucao Normativa BCB 636/2025 (Anexo I, campos 1 a 28).
A IN entra em vigor em 01/12/2026 (art. 7o): use este documento a partir dessa data.

## O que e

Quem esta do outro lado de cada lancamento do EXTRATO (IN art. 2o, V): uma ou mais linhas
por lancamento, e todo lancamento do EXTRATO tem pelo menos uma. E um dos cinco arquivos da
resposta ao caso, gerado com os mesmos parametros dos outros.

## Parametros da geracao

Os mesmos nos cinco documentos SIMBA: `caso`, `documentos`, `contas` (opcional), `inicio` e
`fim`. Duas geracoes do mesmo `caso` sao a mesma entrega: a mais nova substitui a anterior.
`documentos` leva somente digitos, sem pontos, tracos ou barras: o documento formatado nao
encontra contas, e o caso sai como resposta vazia para ele, sem erro; a conferencia antes da
aprovacao avisa o documento sem conta. `contas` se preenche so quando o oficio restringir a contas especificas; o normal e nao
preencher (ausente, todas as contas dos documentos), e preencher sem a ordem pedir omite
contas do investigado.

O `fim` tem de ser um dia que ja acabou no calendario do Reporter: a geracao le um periodo
fechado, e o lancamento gravado depois nao desloca a numeracao entre os arquivos.

Num tenant com mais de uma organizacao, o cadastro da instituicao no Reporter restringe
`organization.id` a organizacao dela; sem isso a leitura traz todas, e a geracao e recusada
(o CNPJ lido nao e o da instituicao, ou chegam duas linhas para uma) em vez de escolher uma.

## Ligacao com o EXTRATO

O campo 2 (`CODIGO_CHAVE_EXTRATO`) e o numero do lancamento no EXTRATO, e o campo 4 o mesmo
numero de documento do campo 7 do EXTRATO. Os dois documentos leem o mesmo conjunto de
lancamentos, na mesma ordem, e numeram do mesmo jeito. O campo 1 (`CODIGO_CHAVE_OD`) e um
numero sequencial unico no arquivo.

**Gere o EXTRATO e o ORIGEM-DESTINO em seguida, com os mesmos parametros.** Um lancamento
gravado entre as duas geracoes desloca os numeros: confira que o ultimo campo 2 daqui e o
ultimo campo 1 do EXTRATO sao o mesmo numero; se nao forem, gere os dois de novo.

## De onde vem a contraparte

Na ordem, a primeira que existe:

1. **Tarifa** (a operacao que o motor de tarifas do Midaz marcou com `feeLeg`): a propria
   instituicao (Compe, CNPJ, nome no Unicad, pessoa juridica).
2. **O plugin que liquidou a transacao**, lido no banco dele:
   - Pix lerian: a origem do Pix recebido e o destino do Pix enviado (banco, agencia, conta,
     CPF/CNPJ, nome, mensagem e txid; sem txid, o EndToEndId);
   - Pix JD: o pagador do Pix recebido e o recebedor do Pix enviado (idem; a conta sai com o
     digito);
   - tipo de conta (campo 8, IN :209): no Pix lerian, pelo dominio do SPI (catalogo de
     mensagens do SPI, tabela de dominios do pacs.008), conta corrente de cliente sai `1` e
     conta de poupanca `2`; conta de pagamento (6 so quando pre-paga), conta-salario e conta
     PI saem em branco, com o motivo no campo 18, como o tipo ausente ou fora do dominio. No
     Pix JD, o plugin so guarda o tipo no Pix entre contas da propria instituicao, no codigo
     do fornecedor, que tem as mesmas descricoes do SPI: conta corrente de cliente sai `1` e
     conta poupanca `2`, e o resto sai em branco com o motivo, como o Pix sem tipo gravado;
   - TED: na TED enviada, banco, agencia, conta e nome do recebedor; na TED recebida, so o
     banco do pagador, e o motivo dos dados do pagador em branco no campo 18.
3. **A outra perna da mesma transacao**, quando e conta de cliente da instituicao no CRM
   (transferencia entre clientes), tem a natureza oposta e o MESMO valor do lancamento:
   agencia, conta, tipo, titular, com o Compe e o CNPJ da propria instituicao. A perna de
   tarifa de quem pagou (outro valor) nao vira contraparte.
4. **Nada acima**: uma linha so com os campos 1 a 4, `0` no campo 17 e a observacao
   `contraparte nao identificada pelo trilho` no campo 18.

O campo 3 e o valor do lancamento (plugin, tarifa, linha vazia) ou o da outra perna
(contraparte interna), em centavos. O campo 9 da contraparte do plugin sai `1` com CPF
(11 digitos), `2` com CNPJ (14) e em branco sem documento. O campo 17 e sempre `0`.

## Codigo Compe da contraparte (campo 5)

Na contraparte de outra instituicao, o plugin grava o ISPB; o template o converte no codigo
Compe pela lista de participantes do STR publicada pelo Banco Central
(`br/bcb/simba/tabelas/ParticipantesSTR.csv`); ISPB fora da lista ou sem codigo sai `999`.
O trecho do template que faz a conversao e gerado da lista por `tools/ispb_compe.py`, e o
validador do catalogo recusa o template se o trecho nao for o gerado. ISPB vazio ou
ausente sai `999` (nunca o Banco do Brasil, cujo ISPB e `00000000`); uma TED recebida
registrada antes de o plugin gravar o ISPB do remetente cai nesse caso. O `999` marca tanto a
instituicao sem codigo Compe quanto o ISPB desconhecido (vazio ou fora da lista): o arquivo
nao separa os dois casos.
Na tarifa e na contraparte interna, o Compe da propria instituicao. Na tarifa, o campo 6
e a agencia da conta investigada, como no cadastro de agencias do AGENCIAS: a agencia
fisica, ou `00001` na instituicao sem agencia fisica (IN :100, :207).

## O que o tenant preenche no mapeamento (binding)

1. **Numero da agencia** (`numero_agencia`): o mesmo cadastro de agencias do AGENCIAS.
2. **Codigo Compe** (`compe`) e **nome no Unicad** (`nomeUnicad`) da instituicao.
3. **Fontes de dados**: `midaz_metadata` (o Mongo da metadata do Midaz) e uma fonte por plugin
   usado: `pix_lerian`, `pix_jd`, `bank_transfer`. Quem nao usa um plugin apaga as consultas
   dele e o conjunto `trilho_*` correspondente do binding.

## Campos em branco, e por que

- 8 (tipo da conta) da contraparte de outra instituicao: sai com o codigo da IN so onde o
  tipo que o plugin grava casa com ele ao pe da letra (conta corrente, poupanca,
  investimento); conta de pagamento, de deposito, garantida, salario e PI, e o tipo ausente
  ou fora do dominio, saem em branco, com o motivo no campo 18 (ver De onde vem a
  contraparte).
- 19 (CNPJ da instituicao) da contraparte de outra instituicao: os plugins gravam so o
  ISPB, e a lista de participantes do STR nao traz o CNPJ.
- 12 e 13 (documento de identificacao): nao existe em nenhuma aplicacao.
- 14 a 16 e 20 a 24 (boleto e cheque): nao existem como produto.
- 19 (CNPJ da instituicao da contraparte): sai na tarifa e na contraparte interna; na de
  outra instituicao fica em branco, porque o plugin grava so o ISPB.
- 25 e 26 (chave Pix da contraparte): a chave fica em outra tabela do Pix lerian, e o tipo
  da chave no Pix JD e um codigo do plugin sem de-para definido.
- 27 e 28 fora do Pix.

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

- **Parcela de cheque especial**: o lancamento que passou do saldo disponivel aparece no
  EXTRATO em duas linhas (a parte do disponivel e a do cheque especial), e aqui cada uma tem a
  sua linha, com a contraparte do plugin Pix ou TED da transacao. Numa transferencia interna,
  nenhuma das duas tem o valor da perna do outro lado, e as duas saem como contraparte nao
  identificada pelo trilho. Numa transacao que tambem tem tarifa, a parcela pode ser da tarifa
  e sai com a contraparte da transacao. A conferencia antes da aprovacao avisa essas
  transacoes, com o valor, para revisar a contraparte.
- **Periodo por investigado**: a ordem pode dar um periodo de afastamento para cada
  investigado, e esta versao tem um so `inicio`/`fim` por caso (a geracao mais nova do
  mesmo `caso` substitui a anterior, entao o caso nao se divide em duas). Nao suportado
  nesta versao; tratar fora do Reporter. Gerar com o periodo mais amplo poria no arquivo
  movimento fora do afastamento.
- **TED cifrada**: o documento do recebedor da TED enviada e os dados do pagador da TED
  recebida (exceto o banco) sao gravados cifrados pelo plugin e saem em branco. Na TED
  recebida, a agencia, a conta, o tipo de pessoa, o CPF/CNPJ e o nome do pagador (campos 6,
  7, 9, 10 e 11) ficam em branco com o motivo no campo 18 (OBSERVACAO); o `00001` do campo
  6 nao e usado, porque ele diz que nao ha agencia fisica (IN :207). O tipo de conta do
  pagador (campo 8) e o tipo que o STR informa, como o plugin o grava (conta corrente
  como `CACC`, poupanca como `SVGS`, conta de pagamento como `CPAY`, conta-salario como
  `SLRY`): conta corrente sai `1`, poupanca `2` e conta de investimento `3` (IN :209). Conta
  de pagamento e conta de deposito podem corresponder a mais de um codigo da IN (a de
  pagamento e `6` so quando pre-paga), e conta garantida e conta-salario nao tem codigo:
  saem em branco, com o motivo acrescentado ao campo 18; tambem o tipo ausente na mensagem
  ou fora do dominio. Na TED enviada, o tipo de conta do recebedor segue a mesma regra, e o
  tipo de pessoa e o CPF/CNPJ do recebedor (campos 9 e 10) saem em branco, porque o plugin
  grava o documento cifrado: o campo 18 diz isso, mais o motivo do tipo de conta quando o
  campo 8 tambem sai em branco. A devolucao de uma TED recebida e gravada pelo plugin como
  TED enviada so com o banco: agencia, conta, nome e tipo de conta saem em branco, e o
  campo 18 diz isso.
- **Devolucao e estorno**: nao herdam a contraparte da transacao original, e as linhas de
  devolucao dos plugins nao sao lidas: a devolucao e o revert do Midaz saem com a outra
  perna interna ou com a linha vazia.
- **Credito cross-ledger do Pix JD**: o plugin grava um id derivado do E2E em vez do id da
  linha; a contraparte desse credito sai pela outra perna ou vazia.
- **Provedor de outra empresa**: contraparte liquidada fora dos plugins Lerian nao e lida.
- **ISPB como texto**: o ISPB tem de chegar com os oito digitos como texto (os tres plugins
  gravam assim); um ISPB numerico com casas decimais sairia `999`.
- **Transferencia repartida**: um lancamento cujo valor se divide entre pernas de valores
  diferentes (um debito para duas contas) nao acha perna do mesmo valor e sai com a linha
  vazia.
- **Conta com duas pernas opostas na mesma transacao** (por exemplo, entre duas chaves de
  saldo da mesma conta): a propria conta pode sair como contraparte interna.
- **Texto sem acento**: nomes e mensagem passam pela conversao para ASCII do template, e TAB
  vira espaco. **Quebra de linha (CR ou LF) dentro de um valor nao e retirada.**
- **Preview do template**: a pre-visualizacao de template do manager recusa este template,
  porque ele usa macros. A geracao nao.

## Fonte primaria

Instrucao Normativa BCB 636/2025, art. 2o, V; art. 3o; Anexo I, arquivo V Origem-Destino
(transcricao em `br/bcb/simba/normas/IN-BCB-636-2025.md`):
https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Instru%C3%A7%C3%A3o%20Normativa%20BCB&numero=636
