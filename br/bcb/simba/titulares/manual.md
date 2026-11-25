# SIMBA — Titulares (arquivo III TITULARES)

Arquivo III do SIMBA, leiaute da Instrução Normativa BCB 636/2025 (Anexo I, campos 1 a 28).
A IN entra em vigor em 01/12/2026 (art. 7º): use este documento a partir dessa data.

## O que é

Uma linha por vínculo de uma pessoa com uma conta: o titular, os cotitulares, os
representantes e os procuradores das contas do arquivo CONTAS (IN 636, art. 2º, III): as contas
do caso e as contas da mesma instituição com que elas transacionaram no período. É um dos cinco arquivos da
resposta ao caso; os outros são AGÊNCIAS, CONTAS, EXTRATO e ORIGEM-DESTINO, gerados com os
mesmos parâmetros.

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

## Quais linhas entram

Para cada conta do caso (as contas em que um documento da ordem é o **titular** ou
**cotitular**; encerradas entram, apagadas do CRM não):

1. **Titular** (campo 5 = `T`): uma linha, com o cadastro do titular no CRM. O campo 6 sai
   `1` quando o documento do titular está na ordem e `0` quando não está: na conta em que o
   investigado é só cotitular, o titular pode ser outra pessoa.
2. **Cotitulares** (campo 5 = `1`, `2`, ...): uma linha por parte relacionada da conta com o
   papel `PRIMARY_HOLDER`, numeradas a partir de `1` em cada conta, na ordem em que o CRM
   guarda as partes (a ordem de inclusão).
3. **Demais partes** (campo 5 = `L`, `P`, `R` ou `O`): uma linha por parte relacionada com
   outro papel, com o código que o binding declara para esse papel.

Nas linhas de parte, o campo 6 sai `1` se o documento da parte está entre os `documentos` da
ordem e `0` se não.

Depois das contas do caso vem cada **conta de contraparte**: as contas da mesma instituição
com que uma conta do caso transacionou no período, as mesmas que o CONTAS lista com o campo 7
= `3` (a mesma consulta `contas_contraparte` nos dois bindings). Cada uma tem as mesmas linhas
(titular `T`, cotitulares numerados, demais partes); o campo 6 diz se a PESSOA teve o sigilo afastado (IN 636, Anexo I, TITULARES, campo 6): `1` se o documento está entre os `documentos` da ordem, `0` se não,
como nas contas do caso. O titular sai do cadastro do CRM pelo
`holder_id` da conta. Uma conta de contraparte que também é conta do caso sai uma vez só, como
conta do caso.

- **Só titular**: a conta em que o documento investigado é só cotitular, representante
  ou procurador não entra; o índice das partes no CRM não separa o papel.

## O que o tenant preenche no mapeamento (binding)

1. **Número da agência**: vem do CRM (`banking_details.branch`), como está gravado; o
   template completa com zeros (`1` e `0001` saem `00001`). Com letra, hífen ou mais de 5
   dígitos, ou sem o número, a geração é recusada.
2. **Código do papel** (`vinculo`): o CRM tem os papéis `PRIMARY_HOLDER` (cotitular, `C` no
   binding, numerado pelo template), `LEGAL_REPRESENTATIVE` (representante legal, `L`) e
   `RESPONSIBLE_PARTY`. O CRM não define o que é `RESPONSIBLE_PARTY`: declare o código que
   ele recebe no seu cadastro, `R` representante, `P` procurador ou `O` outros, nas duas
   consultas de partes (`partes_dados` e `partes_contraparte_dados`). O exemplo usa `O`, o
   único código que não afirma procuração nem representação; troque para `P` ou `R` se o seu
   processo usa o papel para procurador ou representante. Papel sem código declarado recusa
   a geração.
3. **Código Compe** (`compe`): 3 dígitos, ou `999` se a instituição não tem.
4. **Nome no Unicad** (`nomeUnicad`).
5. **Contrato de câmbio** (`operaCambio`, campo 28): declare na implantação se a instituição
   firma contrato de câmbio. Com `nao`, o campo 28 sai `0` em toda linha. Com `sim`, o campo
   28 de cada pessoa sai de `contratoCambio` (`0` ou `1`), campo manual: o Midaz não registra
   contrato de câmbio. Sem o valor, o campo sai em branco e a conferência aponta.
6. **Campos que o Midaz não possui** (manuais, no titular e no cadastro da parte):
   `nomeDocIdentificacao` e `numeroDocIdentificacao` (10 e 11), `codigoCidade` (13),
   `dispositivos` e `computadores` (26 e 27); `contratoCambio` (28) no titular e na linha da parte.

O CNPJ vem da organização do Midaz. O tipo da conta vem do CRM
(`regulatory_fields.account_type`: DEPOSIT 1, SAVINGS 2, INVESTMENT 3,
OTHER_FINANCIAL_INVESTMENTS 4, NON_RESIDENT 5, PAYMENT 6). O tipo de pessoa do titular vem do
cadastro (`NATURAL_PERSON` 1, `LEGAL_PERSON` 2); outro valor recusa a geração.

Num tenant com mais de uma organização, o cadastro da instituição no Reporter restringe
`organization.id` à organização dela; sem isso a leitura traz todas, e a geração é recusada
(o CNPJ lido não é o da instituição, ou chegam duas linhas para uma) em vez de escolher uma.

## De onde vem cada campo do titular

- Nome, documento, endereço principal (linha 1 e linha 2, CEP, UF, país), telefones,
  e-mails, nome social e renda: o cadastro do titular no CRM.
- Quem mora no exterior: o país do endereço principal é um código da tabela que não é o do
  Brasil, em maiúscula ou minúscula (`br` é o Brasil). Sem país no cadastro, a pessoa é
  tratada como no Brasil.
- UF (campo 14): para quem mora no Brasil, a sigla do endereço principal convertida no
  código IBGE pela tabela de `br/bcb/simba/tabelas/uf-ibge.compute.yaml`, em maiúscula ou
  minúscula (`sp` é SP); sigla com espaço ou pontuação recusa a geração; para quem mora no
  exterior, `00` (IN 636, Anexo I, TITULARES, campo 14), mesmo que o cadastro traga uma sigla igual à de uma UF. Quem mora
  no Brasil sem sigla no cadastro sai com o campo em branco: a IN só dá o `00` para o
  exterior, e a informação que não existe fica sem preencher (IN 636, art. 2º, § 1º).
- País (campo 15): o nome do país do código ISO 3166-1 alfa-2 do cadastro, pela tabela de
  países da Receita (`br/rfb/e-financeira/tabelas/paises.txt`), sem acentos e cortado em 40
  caracteres; `BR` sai `Brasil`. Sem país no cadastro, o campo sai em branco.
- Telefone (campo 17): o celular; sem celular, o outro telefone.
- Renda (campo 18): da pessoa natural, a renda mensal bruta declarada; da pessoa jurídica, o
  faturamento anual bruto declarado, como está no cadastro, sem dividir por 12 (a IN pede a
  renda declarada e não fixa o período). Em centavos sem separador (`500050` para
  R$ 5.000,50); a data de referência de cada um no campo 19. Só sai renda ou faturamento em
  BRL: a figura que o campo 18 imprime (a renda da pessoa natural, o faturamento da jurídica) em
  outra moeda recusa a geração (regras moeda-da-renda e moeda-do-faturamento); a outra figura do
  cadastro não é conferida, porque não vai ao arquivo. Moeda fora do formato ISO (três letras
  maiúsculas) também recusa. O catálogo não converte moeda; a IN não fala de moeda no campo 18 e só dá exemplos
  em reais (art. 3º, VIII). A API do CRM exige a moeda junto do valor: sem moeda não há renda, e o
  campo 18 sai em branco. Resíduo: um valor gravado sem moeda direto no banco, fora da API, sai
  como declarado, sem conferência de moeda.
- E-mail (campo 25): o principal e o secundário, separados por `;`.
- Início e fim do vínculo (campos 20 e 21): abertura e encerramento da conta. O encerramento
  da conta e o início e o fim do vínculo das partes são lidos como dia (`civilDate` no
  binding): o CRM os guarda como a meia-noite UTC do dia, e a API do CRM normaliza para essa
  meia-noite qualquer valor que receba, com ou sem hora ou fuso (`2026-06-30T00:00:00-03:00`
  vira o dia 30). Um valor gravado fora da API com hora diferente da meia-noite UTC recusa a
  geração (RPT-0143). Partes gravadas nas versões beta da v3.5.0 do Midaz anteriores ao tipo
  de data podem ter essa hora e recusar a geração; regrave a data pela API.

Nas partes relacionadas, o instrumento do CRM guarda só documento, nome, papel e as datas de
início e fim do vínculo. O tipo de pessoa da parte (campo 7) sai do tamanho do documento: 11
posições CPF (`1`), 14 posições CNPJ (`2`). O endereço, a UF, o país, o CEP, o telefone e o
nome social da parte (campos 12 a 17 e 24) saem do cadastro de titulares do CRM, pelo documento
da parte, com as mesmas regras do titular: a parte que também é titular no CRM tem esses campos
preenchidos. A renda e o e-mail (18, 19 e 25) dependem do papel, como diz o parágrafo abaixo.
As consultas `partes_documentos` e
`cadastro_partes` (e as `_contraparte`, para as contas de contraparte) fazem essa leitura: o
Reporter decifra o documento da parte e pergunta o cadastro pelo digest dele.

A ligação é pelo documento como está gravado: a parte no instrumento e a pessoa no cadastro de
titulares precisam ter o mesmo documento, sem pontos, traços ou barras; o CNPJ alfanumérico
mantém as letras. Com separador num cadastro e não no outro (`529.982.247-25` na parte,
`52998224725` no titular), a parte não é achada e sai como parte sem cadastro, com os campos 12
a 19 e 24 em branco, sem aviso. Confira o formato dos documentos no CRM na implantação.

Renda, data da renda e e-mail (campos 18, 19 e 25): a IN pede a renda declarada "pelo
correntista" (IN 636, Anexo I, TITULARES, campos 18 e 19; no Memorando de Instrução MI 001 - ASSPA/PGR, campo 18, "informada
pelo correntista") e o e-mail "declarado pelo titular" (IN 636, Anexo I, TITULARES, campo 25). Por isso dependem do papel:

- **Titular e cotitular** (campo 5 = `T`, `1`, `2`, ...): são correntistas e titulares da
  conta, e saem com a renda e o e-mail do próprio cadastro, nunca os do titular da conta.
- **Representante legal, representante, procurador e outros** (`L`, `R`, `P`, `O`): não são.
  Os campos 18 e 19 saem em branco e o 25 `e-mail nao declarado`, mesmo que a pessoa tenha
  cadastro de titular no CRM com renda e e-mail: a informação que a IN pede não existe para
  ela (IN 636, art. 2º, § 1º).

A parte sem cadastro sai com 18 e 19 em branco e o 25 `e-mail nao declarado`, qualquer que
seja o papel. A moeda da renda só é conferida de quem a imprime: a renda do cotitular em outra
moeda que não BRL recusa a geração, a do representante ou do procurador não. As consultas
`cotitulares_documentos` e `renda_cotitulares` (e as `_contraparte`) leem a moeda só das partes
com o papel `PRIMARY_HOLDER`.

## Período

As datas saem no dia civil de Brasília (`America/Sao_Paulo`), no formato `ddmmaaaa`. O período
do afastamento não filtra os vínculos: entram as partes que o CRM tem na conta.

## Campos que podem sair em branco, e por quê

A IN manda preencher todos os campos e, quando a informação não existe, usar o código que o
Anexo I indica (IN 636, art. 2º, § 1º; art. 3º, III). Onde o Anexo I não dá código, o campo
sai em branco:

- `NOME_DOC_IDENTIFICACAO` e `NUMERO_DOC_IDENTIFICACAO` (campos 10 e 11): campos manuais. O
  CRM guarda só CPF/CNPJ. Vazios, em branco.
- `CODIGO_CIDADE` (campo 13): para quem mora no Brasil, o código IBGE do campo manual
  `codigoCidade`; o CRM guarda o nome da cidade, sem o código. Vazio, em branco. Para quem
  mora no exterior sai `0000000`, o código que a IN dá para esse caso (IN 636, Anexo I,
  TITULARES, campo 13).
- `DATA_FIM_RELACIONAMENTO_CONTA` (campo 21): em branco enquanto o vínculo está ativo (conta
  aberta, ou parte sem data de fim). A IN não dá código para vínculo ativo.
- `DATA_INICIO_RELACIONAMENTO_CONTA` (campo 20) da parte relacionada: em branco quando o registro
  da parte no CRM não gravou a data de início (registro antigo). A IN não dá código para isso. A
  conta entra no caso mesmo assim (knownGap `cotitular-no-periodo`), e a conferência avisa o
  cotitular sem a data.
- `DISPOSITIVO_MOVEL_CADASTRADO` e `COMPUTADOR_CADASTRADO` (campos 26 e 27): campos manuais.
  O Midaz não registra os dispositivos cadastrados do cliente. Vazios, em branco.
- Campos manuais de uma parte sem cadastro no CRM: em branco. A parte sem cadastro não tem
  linha onde receber o valor.
- Do titular, quando o cadastro não tem o dado: endereço (12), UF (14) de quem mora no Brasil,
  CEP (16), telefone (17), renda e data da renda (18 e 19), nome social (24) e abertura da
  conta (20).
- Das partes relacionadas: os mesmos campos do titular, quando o cadastro dela não tem o
  dado. A parte sem cadastro de titular no CRM sai com os campos 12 a 19 e 24 em branco.
- Do representante legal, representante, procurador e outros (`L`, `R`, `P`, `O`): renda e
  data da renda (18 e 19) sempre em branco, mesmo com cadastro (IN 636, Anexo I, TITULARES,
  campos 18 e 19, "pelo correntista").

Sem e-mail no cadastro, na parte sem cadastro de titular e nas linhas `L`, `R`, `P` e `O`, o
campo 25 sai `e-mail nao declarado`, o código da IN (IN 636, Anexo I, TITULARES, campo 25), sem acento.

## Campos que o Midaz não possui

Um campo do Anexo I que nenhuma aplicação Lerian registra entra no mapeamento como manual
(`from: manual`), com o motivo no `pendingReason`: o Midaz não possui o campo, e a
instituição o informa. Há três formas, e o campo é opcional nas três:

1. **Correção no rascunho**, linha a linha, para poucos casos.
2. **Uma base da instituição**: uma consulta na base dela, juntada (`join`) à consulta que
   enche o conjunto pela chave da linha (a operação, a conta ou o documento), e o campo mapeado
   `from: query` com a coluna dela. O Reporter junta consultas de bases diferentes, como já
   junta o CRM e o razão do Midaz.
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
arquivo é o `<caso>_TITULARES.TXT`; para o caso 001-MPF-005097-79, por exemplo,
`001-MPF-005097-79_TITULARES.TXT`.

Os cinco arquivos de uma entrega levam o mesmo prefixo: `<caso>_AGENCIAS.TXT`,
`<caso>_CONTAS.TXT`, `<caso>_TITULARES.TXT`, `<caso>_EXTRATO.TXT` e
`<caso>_ORIGEM_DESTINO.TXT` (com sublinhado no ORIGEM_DESTINO, como no memorando). Só o nome
muda: o conteúdo do arquivo não é alterado.

## Investigado sem conta

Quando nenhum documento da ordem tem conta na instituição, não há arquivo a gerar: os
arquivos do SIMBA são das contas (IN 636, art. 1º) e não têm cabeçalho (art. 3º, I).
A geração deste arquivo é recusada antes de montar o arquivo (erro RPT-0195), dizendo
quantas linhas cada consulta leu. Responda à requisição sem arquivo, pelo atendimento:
CCS0012 com a situação 03, relacionamento inexistente (Catálogo de Serviços do SFN,
Volume III, evento CCS0012; Dicionário de Domínios do Banco Central, domínio
SitAtedmntReq).

Quando a ordem tem mais de um investigado e só parte deles tem conta, os arquivos saem com
as contas de quem tem; quem não tem é declarado sem relacionamento no atendimento da
requisição.

## Quem vem da versão 1.1.0

A 1.2.0 lê o cadastro das partes relacionadas por oito consultas novas do mapeamento:
`partes_documentos`, `cadastro_partes`, `cotitulares_documentos` e `renda_cotitulares`, e as
`_contraparte` delas. Elas preenchem quatro conjuntos novos: `cadastro_partes` e
`renda_cotitulares`, e os `_contraparte`. Um mapeamento escrito para a 1.1.0, sem elas, ainda
gera o rascunho, mas a aprovação é recusada: os campos obrigatórios dos conjuntos novos ficam
sem mapeamento. Para aprovar:

1. A instituição que tem o cadastro de titulares das partes no CRM copia as oito consultas e
   os quatro conjuntos do `binding.example.yaml` desta versão. Quem tem o dado preenche o campo
   com ele: a IN só deixa o campo sem a informação quando ela não existe ou é tecnicamente
   inviável (IN 636, art. 2º, § 1º).
2. Só a instituição que não tem esse cadastro declara os quatro conjuntos vazios (`emptyReason`,
   com o motivo), o que volta ao arquivo da 1.1.0: os campos 12 a 19 e 24 das partes em branco
   e o campo 25 `e-mail nao declarado`.

O rascunho guarda o mapeamento com que foi gerado, e a aprovação confere esse mapeamento, não
o atual. Depois de mudar o mapeamento, salve-o e gere um rascunho novo do mesmo `caso`: o
rascunho gerado antes continua sem poder ser aprovado.

## Limitações desta versão

- **Período por investigado**: a ordem pode dar um período de afastamento para cada
  investigado, e esta versão tem um só `inicio`/`fim` por caso (a geração mais nova do
  mesmo `caso` substitui a anterior, então o caso não se divide em duas). Não suportado
  nesta versão; tratar fora do Reporter. Gerar com o período mais amplo poria no arquivo
  movimento fora do afastamento.
- **UF e país do titular**: quem mora no Brasil (país `BR` ou sem país) com uma sigla de UF
  que a tabela não tem recusa a geração, porque a IN só dá o `00` para quem mora no exterior.
  Sem sigla nenhuma, não recusa: o campo 14 sai em branco (a informação não existe no
  cadastro). Um país informado que a tabela da Receita não tem também recusa, porque o campo
  15 pede o nome. As duas recusas valem também para o titular de uma conta de contraparte.
  Corrija o cadastro antes de gerar.
- **Titular sem cadastro**: o cadastro do titular vem do CRM pelo documento da ordem e pelo
  `holder_id` da conta. Conta do caso cujo titular não é encontrado no cadastro (apagado, ou
  com documento diferente do da ordem) fica sem tipo de pessoa, documento e nome, e a geração
  é recusada.
- **Ordem dos cotitulares**: a numeração segue a ordem em que o CRM guarda as partes, não a
  data de início do vínculo. O campo 5 tem uma posição: com dez ou mais cotitulares numa
  conta, o número passa de uma posição.
- **Titular repetido como parte**: o titular não deve estar cadastrado também como parte
  relacionada da própria conta; se estiver, ele sai duas vezes (como `T` e como cotitular).
- **Vínculo removido**: uma parte removida do instrumento pela API do CRM sai da lista sem
  data de fim. O campo 21 só registra o fim do vínculo que o cadastro encerrou com a data.
- **Número da conta**: sai como o CRM o guarda (`banking_details.account`), até 20 posições;
  confira que o valor cadastrado inclui o DV.
- **Texto sem acento**: nomes, endereço, telefones e e-mails passam pela conversão para ASCII
  do template, e TAB, CR e LF viram espaço: uma quebra de linha no cadastro não parte o
  registro. O número da conta não passa pela conversão: com TAB, CR ou LF ele recusa a
  geração. Um caractere fora do ASCII que a conversão não cobre (por exemplo `°`, `’`, `–`, `ø`)
  recusa a geração, porque o arquivo é ASCII (IN 636, art. 3º): a recusa mostra o campo e o valor,
  e o cadastro tem de ser corrigido.
- **Pessoa investigada nas partes**: o campo 6 compara o documento da parte com cada
  elemento da lista `documentos` da ordem, que vem só com dígitos. Vale igual nas contas de
  contraparte: um investigado que é procurador numa delas sai `1`.
- **Preview do template**: a pré-visualização de template do manager recusa este template,
  porque ele usa uma macro. A geração não.
- **Uma instituição por arquivo**: um documento entregue em base individual não soma
  instituições diferentes.

## Fonte primária

Instrução Normativa BCB 636/2025, art. 2º, III; art. 3º; Anexo I, arquivo III Titulares
(transcrição em `br/bcb/simba/normas/IN-BCB-636-2025.md`):
https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Instru%C3%A7%C3%A3o%20Normativa%20BCB&numero=636
