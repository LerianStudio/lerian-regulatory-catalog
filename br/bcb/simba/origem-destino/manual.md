# SIMBA — Origem-Destino (arquivo V ORIGEM-DESTINO)

Arquivo V do SIMBA, leiaute da Instrução Normativa BCB 636/2025 (Anexo I, campos 1 a 28).
A IN entra em vigor em 01/12/2026 (art. 7º): use este documento a partir dessa data.

## O que é

Quem está do outro lado de cada lançamento do EXTRATO (IN 636, art. 2º, V): uma ou mais linhas
por lançamento, e todo lançamento do EXTRATO tem pelo menos uma. É um dos cinco arquivos da
resposta ao caso, gerado com os mesmos parâmetros dos outros.

## Parâmetros da geração

Os mesmos nos cinco documentos SIMBA: `caso`, `documentos`, `contas` (opcional), `inicio` e
`fim`. Duas gerações do mesmo `caso` são a mesma entrega: a mais nova substitui a anterior.
`documentos` leva somente dígitos, sem pontos, traços ou barras: o documento formatado não
encontra contas, e o caso sai como resposta vazia para ele, sem erro; a conferência antes da
aprovação avisa o documento sem conta. `contas` se preenche só quando o ofício restringir a contas específicas; o normal é não
preencher (ausente, todas as contas dos documentos), e preencher sem a ordem pedir omite
contas do investigado.

O `fim` tem de ser um dia que já acabou no calendário do Reporter: a geração lê um período
fechado, e o lançamento gravado depois não desloca a numeração entre os arquivos.
O `fim` também não pode ser anterior ao `inicio`: um período invertido é recusado ao gerar,
em vez de sair um arquivo sem lançamento nenhum.

Num tenant com mais de uma organização, o cadastro da instituição no Reporter restringe
`organization.id` à organização dela; sem isso a leitura traz todas, e a geração é recusada
(o CNPJ lido não é o da instituição, ou chegam duas linhas para uma) em vez de escolher uma.
Se o escopo dela é declarado tabela a tabela, inclua nele a `transfer_initiations` do Pix lerian
(de onde vem a chave Pix do campo 26): a tabela lida por junção entra no escopo como as outras, e a
que ele não cobre também faz o Reporter recusar a geração.

## Ligação com o EXTRATO

O campo 2 (`CODIGO_CHAVE_EXTRATO`) é o número do lançamento no EXTRATO, e o campo 4 o mesmo
número de documento do campo 7 do EXTRATO. Os dois documentos leem o mesmo conjunto de
lançamentos, na mesma ordem, e numeram do mesmo jeito. O campo 1 (`CODIGO_CHAVE_OD`) é um
número sequencial único no arquivo.

**Gere o EXTRATO e o ORIGEM-DESTINO em seguida, com os mesmos parâmetros.** Um lançamento
gravado entre as duas gerações desloca os números: confira que o último campo 2 daqui e o
último campo 1 do EXTRATO são o mesmo número; se não forem, gere os dois de novo.

## De onde vem a contraparte

Na ordem, a primeira que existe:

1. **Tarifa** (a operação que o motor de tarifas do Midaz marcou com `feeLeg`, e a cobrança
   ou o reembolso de dívida de tarifa, operações `FEE_SETTLEMENT` e `FEE_REFUND`, que o Midaz
   grava sem `feeLeg`): a própria instituição (Compe, CNPJ, nome no Unicad, pessoa jurídica). Conta
   e tipo de conta (campos 7 e 8) ficam em branco, porque a contraparte não é uma conta de
   cliente, e o campo 18 diz isso: `tarifa da propria instituicao; sem conta de contraparte` (IN 636, art. 2º, § 1º).
2. **O plugin que liquidou a transação**, lido no banco dele:
   - Pix lerian: a origem do Pix recebido e o destino do Pix enviado (banco, agência, conta,
     CPF/CNPJ, nome, mensagem e TxId);
   - Pix JD: o pagador do Pix recebido e o recebedor do Pix enviado (idem; a conta sai com o
     dígito);
   - tipo de conta (IN 636, Anexo I, ORIGEM-DESTINO, campo 8): no Pix lerian, pelo domínio do SPI (catálogo de
     mensagens do SPI, tabela de domínios do pacs.008), conta corrente de cliente sai `1` e
     conta de poupança `2`; conta de pagamento (6 só quando pré-paga), conta-salário e conta
     PI saem em branco, com o motivo no campo 18, como o tipo ausente ou fora do domínio. No
     Pix JD, o plugin só guarda o tipo no Pix entre contas da própria instituição, no código
     do fornecedor, que tem as mesmas descrições do SPI: conta corrente de cliente sai `1` e
     conta poupança `2`, e o resto sai em branco com o motivo, como o Pix sem tipo gravado;
   - TED: na TED enviada, banco, agência, conta e nome do recebedor; na TED recebida, só o
     banco do pagador, e o motivo dos dados do pagador em branco no campo 18.
3. **A outra perna da mesma transação**, quando é conta de cliente da instituição no CRM
   (transferência entre clientes), tem a natureza oposta e o MESMO valor do lançamento:
   agência, conta, tipo, titular, com o Compe e o CNPJ da própria instituição. A perna de
   tarifa de quem pagou (outro valor) não vira contraparte.
4. **Nada acima**: uma linha só com os campos 1 a 4, `0` no campo 17 e a observação
   `contraparte nao identificada pelo trilho` no campo 18.

O campo 3 é o valor do lançamento (plugin, tarifa, linha vazia) ou o da outra perna
(contraparte interna), em centavos. O campo 9 da contraparte do plugin sai `1` com CPF
(11 dígitos), `2` com CNPJ (14) e em branco sem documento. O campo 17 é sempre `0`.

## Código Compe da contraparte (campo 5)

Na contraparte de outra instituição, o plugin grava o ISPB; o template o converte no código
Compe pela lista de participantes do STR publicada pelo Banco Central
(`br/bcb/simba/tabelas/ParticipantesSTR.csv`); ISPB fora da lista ou sem código sai `999`.
O trecho do template que faz a conversão é gerado a partir dessa tabela de participantes do
catálogo, e o validador do catálogo recusa o template se o trecho não for o gerado. ISPB vazio ou
ausente sai `999` (nunca o Banco do Brasil, cujo ISPB é `00000000`); uma TED recebida
registrada antes de o plugin gravar o ISPB do remetente cai nesse caso. O `999` marca tanto a
instituição sem código Compe quanto o ISPB desconhecido (vazio ou fora da lista): o arquivo
não separa os dois casos.
Na tarifa e na contraparte interna, o Compe da própria instituição. Na tarifa, o campo 6
é a agência da conta investigada, como no cadastro de agências do AGÊNCIAS: a agência
física, ou `00001` na instituição sem agência física (IN 636, Anexo I, AGÊNCIAS, campo 2, e
ORIGEM-DESTINO, campo 6).

## CNPJ da instituição da contraparte (campo 19)

Na contraparte de outra instituição, o template converte o ISPB gravado pelo plugin no CNPJ
que a lista de participantes do Pix publicada pelo Banco Central dá
(`br/bcb/simba/tabelas/ParticipantesPix.csv`, só a seção dos participantes ativos); é a
única lista do Banco Central que liga ISPB a CNPJ. O trecho do template que faz a conversão
é gerado a partir dessa tabela de participantes do catálogo, e o validador do catálogo recusa
o template se o trecho não for o gerado. ISPB vazio ou ausente, ou fora da lista (uma TED com banco que só
participa do STR, por exemplo), deixa o campo em branco e acrescenta ao campo 18, depois de
`; ` quando ele já tem texto, o motivo `CNPJ da instituicao da contraparte nao informado:
ISPB ausente ou fora da lista de participantes ativos do Pix`.
Na tarifa e na contraparte interna, o CNPJ da própria instituição.

## O que o tenant preenche no mapeamento (binding)

1. **Número da agência**: vem do CRM (`banking_details.branch`); o template completa com
   zeros (`1` e `0001` saem `00001`).
2. **Código Compe** (`compe`) e **nome no Unicad** (`nomeUnicad`) da instituição.
3. **Fontes de dados**: `midaz_metadata` (o Mongo da metadata do Midaz) e uma fonte por plugin
   usado: `pix_lerian`, `pix_jd`, `bank_transfer`. Quem não usa um plugin apaga as consultas
   dele e declara vazio cada conjunto `trilho_*` dele, com o motivo:
   `trilho_pix_jd_envios: {emptyReason: "a instituicao nao usa o Pix JD"}`. Não apague o
   conjunto: sem origem, os campos obrigatórios dele ficam pendentes e o rascunho não pode
   ser aprovado.

## Campos em branco, e por quê

- 8 (tipo da conta) da contraparte de outra instituição: sai com o código da IN só onde o
  tipo que o plugin grava casa com ele ao pé da letra (conta corrente, poupança,
  investimento); conta de pagamento, de depósito, garantida, salário e PI, e o tipo ausente
  ou fora do domínio, saem em branco, com o motivo no campo 18 (ver De onde vem a
  contraparte).
- 19 (CNPJ da instituição) da contraparte de outra instituição: sai em branco quando o
  plugin não grava o ISPB ou a instituição não é participante ativa do Pix, com o motivo
  no campo 18 (ver CNPJ da instituição da contraparte).
- 12 e 13 (documento de identificação da contraparte), 14 a 16 (boleto e cheque) e 20 a 24
  (boleto): campos manuais do lançamento. Pix e TED trazem só o CPF/CNPJ, e boleto e cheque
  não são produtos Lerian. Vazios, saem em branco. Saem na linha do trilho e na linha vazia;
  na tarifa e na outra perna interna, em branco.
- 25 e 26 (chave Pix da contraparte): no Pix enviado, a chave do recebedor (Pix lerian: da
  iniciação do Pix, `transfer_initiations`; Pix JD: `payee_key`); no Pix JD recebido, a chave
  do pagador quando o plugin a grava (`payer_key`). O tipo vira o código da IN (1 CPF/CNPJ, 2
  telefone, 3 e-mail, 4 aleatória) e o telefone sai só com dígitos, a partir do 55. Em branco
  no Pix sem chave, no Pix lerian recebido (o pagador não usa chave) e na TED.
- 28 (TxId do Pix, `TransactionIdentification <TxId>`; IN 636, Anexo I, ORIGEM-DESTINO,
  campo 28): o TxId que o plugin grava, o
  mesmo do campo 26 do EXTRATO; nunca o EndToEndId, que é outro identificador. Sem TxId, o
  campo sai em branco e o campo 18 da linha do Pix diz por quê (IN 636, art. 2º, § 1º), depois do
  motivo do tipo de conta e antes do motivo do CNPJ, separados por `; `:
  - `TxId nao informado: Pix sem identificador de conciliacao`: o Pix não tem TxId (Pix por
    chave ou manual, ou QR estático sem TxId, que traz `***` no lugar dele: Manual de Padrões
    para Iniciação do Pix, 2.6.2, nota 25), ou seja, inexistência da informação. Vale para o
    Pix recebido nos dois plugins e para o Pix enviado pelo Pix lerian;
  - `TxId nao informado: o plugin de Pix nao grava o TxId do Pix enviado`: Pix enviado pelo Pix
    JD, inclusive o pagamento de QR dinâmico, que tem TxId: o plugin o repassa ao SPI e não o
    guarda, ou seja, inviabilidade técnica.
- 27 e 28 fora do Pix.

## Campos que o Midaz não possui

Um campo do Anexo I que nenhuma aplicação Lerian registra entra no mapeamento como manual
(`from: manual`), com o motivo no `pendingReason`: o Midaz não possui o campo, e a
instituição o informa. Há três formas, e o campo é opcional nas três:

1. **Correção no rascunho**, linha a linha, para poucos casos.
2. **Uma base da instituição**: uma fonte adicional (`also`) do mesmo conjunto, com a consulta
   na base dela e a mesma chave do conjunto (`rowKey`); o Reporter une as linhas pela chave.
3. **Deixar pendente**: o campo sai em branco (ou com a sentinela que a IN dá), como a IN
   aceita na inexistência da informação (IN 636, art. 2º, § 1º).

CUIDADO: nunca dê um valor fixo (`value`) a um campo que muda por pessoa ou por lançamento.
O valor manual vale para todas as linhas.

## Versão do Midaz

Os mapeamentos de exemplo leem o CRM do Midaz 4.0 ou posterior. A partir da 4.0, a API do
CRM chama de instrumento (`instruments`) o que antes era alias, mas o Midaz continua
gravando os instrumentos na coleção `aliases_<organização>` do MongoDB, e é essa coleção que
o Reporter lê (`table: aliases`). Não troque `aliases` por `instruments` no mapeamento: a
coleção `instruments` não existe. Campos como `regulatory_fields.account_type`,
`related_parties` e `banking_details.closing_date` só existem no CRM do Midaz 4.x; com o
plugin de CRM anterior (v2.x) o documento não gera.

## Nome dos arquivos na entrega

O arquivo baixado do Reporter tem o nome do relatório (o identificador da geração, com
extensão `.txt`), e não o nome que a entrega exige. Antes de validar e transmitir, renomeie
cada um dos cinco arquivos com o prefixo do número do caso, no formato
`999-XXX-999999-99_ARQUIVO.TXT` (Memorando de Instrução MI 001 - ASSPA/PGR, item 1.4, b). O
número do caso é o mesmo informado no parâmetro `caso` da geração, como está no ofício. Este
arquivo é o `<caso>_ORIGEM_DESTINO.TXT`; para o caso 001-MPF-005097-79, por exemplo,
`001-MPF-005097-79_ORIGEM_DESTINO.TXT`.

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
arquivo sai vazio (0 byte, sem cabeçalho, IN 636, art. 3º, I) e é aprovado e entregue assim,
com os outros quatro.
O contrato declara isso (`filing.allowEmpty`); um Reporter anterior a esse recurso recusa
o contrato na carga.

## Limitações desta versão

- **Parcela de cheque especial**: o lançamento que passou do saldo disponível aparece no
  EXTRATO em duas linhas (a parte do disponível e a do cheque especial), e aqui cada uma tem a
  sua linha, com a contraparte do plugin Pix ou TED da transação. Numa transferência interna,
  nenhuma das duas tem o valor da perna do outro lado, e as duas saem como contraparte não
  identificada pelo trilho. Numa transação que também tem tarifa, a parcela pode ser da tarifa
  e sai com a contraparte da transação. A conferência antes da aprovação avisa essas
  transações, com o valor, para revisar a contraparte.
- **Período por investigado**: a ordem pode dar um período de afastamento para cada
  investigado, e esta versão tem um só `inicio`/`fim` por caso (a geração mais nova do
  mesmo `caso` substitui a anterior, então o caso não se divide em duas). Não suportado
  nesta versão; tratar fora do Reporter. Gerar com o período mais amplo poria no arquivo
  movimento fora do afastamento.
- **TED cifrada**: o documento do recebedor da TED enviada e os dados do pagador da TED
  recebida (exceto o banco) são gravados cifrados pelo plugin e saem em branco. Na TED
  recebida, a agência, a conta, o tipo de pessoa, o CPF/CNPJ e o nome do pagador (campos 6,
  7, 9, 10 e 11) ficam em branco com o motivo no campo 18 (OBSERVACAO); o `00001` do campo
  6 não é usado, porque ele diz que não há agência física (IN 636, Anexo I, ORIGEM-DESTINO,
  campo 6). O tipo de conta do
  pagador (campo 8) é o tipo que o STR informa, como o plugin o grava (conta corrente
  como `CACC`, poupança como `SVGS`, conta de pagamento como `CPAY`, conta-salário como
  `SLRY`): conta corrente sai `1`, poupança `2` e conta de investimento `3` (IN 636, Anexo I,
  ORIGEM-DESTINO, campo 8). Conta
  de pagamento e conta de depósito podem corresponder a mais de um código da IN (a de
  pagamento é `6` só quando pré-paga), e conta garantida e conta-salário não têm código:
  saem em branco, com o motivo acrescentado ao campo 18; também o tipo ausente na mensagem
  ou fora do domínio. Na TED enviada, o tipo de conta do recebedor segue a mesma regra, e o
  tipo de pessoa e o CPF/CNPJ do recebedor (campos 9 e 10) saem em branco, porque o plugin
  grava o documento cifrado: o campo 18 diz isso, mais o motivo do tipo de conta quando o
  campo 8 também sai em branco. O tipo do recebedor é obrigatório: toda TED enviada que
  chega ao arquivo o tem (a devolução de uma TED recebida, que o plugin grava sem ele, sai
  pelo revert do Midaz, ver Devolução e estorno). Os dados do remetente existem, cifrados no
  plugin de TED da instituição; esta versão do Reporter não os lê. A instituição declara a
  circunstância pela ressalva de inviabilidade técnica da IN 636 (art. 2º, § 1º): o
  motivo vai no campo 18 de cada linha. O memorando de leiaute do MPF (MI 001 - ASSPA/PGR, item 3) exige o maior
  número possível de identificações de beneficiários e ordenantes, sob pena de não aceitação
  da entrega: o MPF pode recusar uma entrega por causa destas linhas. Antes de transmitir um
  caso com TED recebida, confira se a instituição consegue obter os dados do remetente por
  outro meio.
- **Devolução e estorno**: não herdam a contraparte da transação original, e as linhas de
  devolução dos plugins não são lidas: a devolução e o revert do Midaz saem com a outra
  perna interna ou com a linha vazia. Exceção: a devolução de uma TED recebida (revert do Midaz)
  e o estorno pedido pelo banco remetente (lançamento novo) levam a metadata dela; esse débito
  sai com o remetente da TED recebida (o banco, e no campo 18
  o mesmo motivo dos dados cifrados), porque o dinheiro volta a ele. A cobrança de dívida de
  tarifa que o Midaz grava na mesma transação do crédito sai como tarifa.
- **Bloqueio e desbloqueio judicial** (operações `BLOCK` e `UNBLOCK` do Midaz): não há
  trilho; sai a outra perna em conta do CRM ou a linha vazia (`contraparte nao identificada
  pelo trilho`).
- **Crédito cross-ledger do Pix JD**: o plugin grava um id derivado do E2E em vez do id da
  linha; a contraparte desse crédito sai pela outra perna ou vazia.
- **Provedor de outra empresa**: contraparte liquidada fora dos plugins Lerian não é lida.
- **ISPB como texto**: o ISPB tem de chegar com os oito dígitos como texto (os três plugins
  gravam assim); um ISPB numérico com casas decimais sairia `999`.
- **Transferência repartida**: um lançamento cujo valor se divide entre pernas de valores
  diferentes (um débito para duas contas) não acha perna do mesmo valor e sai com a linha
  vazia.
- **Conta com duas pernas opostas na mesma transação** (por exemplo, entre duas chaves de
  saldo da mesma conta): a própria conta pode sair como contraparte interna.
- **Texto sem acento**: nomes e mensagem passam pela conversão para ASCII do template, e TAB,
  CR e LF viram espaço: uma quebra de linha no cadastro não parte o registro. O número da
  conta não passa pela conversão: com TAB, CR ou LF ele recusa a geração. Nos nomes, um
  caractere fora do ASCII que a conversão não cobre (por exemplo `°`, `’`, `–`, `ø`) recusa a
  geração, porque o arquivo é ASCII (IN 636, art. 3º). A mensagem do Pix (campo 27) é texto livre:
  até o filtro de transliteração do Reporter, ela pode levar ao arquivo um caractere fora do
  ASCII que a conversão não cobre (um emoji, por exemplo), em vez de recusar o arquivo inteiro.
- **Preview do template**: a pré-visualização de template do manager recusa este template,
  porque ele usa macros. A geração não.

## Fonte primária

Instrução Normativa BCB 636/2025, art. 2º, V; art. 3º; Anexo I, arquivo V Origem-Destino
(transcrição em `br/bcb/simba/normas/IN-BCB-636-2025.md`):
https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Instru%C3%A7%C3%A3o%20Normativa%20BCB&numero=636
