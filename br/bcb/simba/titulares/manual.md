# SIMBA — Titulares (arquivo III TITULARES)

Arquivo III do SIMBA, leiaute da Instrucao Normativa BCB 636/2025 (Anexo I, campos 1 a 28).
A IN entra em vigor em 01/12/2026 (art. 7o): use este documento a partir dessa data.

## O que e

Uma linha por vinculo de uma pessoa com uma conta: o titular, os cotitulares, os
representantes e os procuradores das contas do arquivo CONTAS (IN art. 2o, III): as contas
do caso e as contas da mesma instituicao com que elas transacionaram no periodo. E um dos cinco arquivos da
resposta ao caso; os outros sao AGENCIAS, CONTAS, EXTRATO e ORIGEM-DESTINO, gerados com os
mesmos parametros.

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

Depois das contas do caso vem cada **conta de contraparte**: as contas da mesma instituicao
com que uma conta do caso transacionou no periodo, as mesmas que o CONTAS lista com o campo 7
= `3` (a mesma consulta `contas_contraparte` nos dois bindings). Cada uma tem as mesmas linhas
(titular `T`, cotitulares numerados, demais partes); o campo 6 diz se a PESSOA teve o sigilo afastado (IN :142): `1` se o documento esta entre os `documentos` da ordem, `0` se nao,
como nas contas do caso. O titular sai do cadastro do CRM pelo
`holder_id` da conta. Uma conta de contraparte que tambem e conta do caso sai uma vez so, como
conta do caso.

- **So titular**: a conta em que o documento investigado e so cotitular, representante
  ou procurador nao entra; o indice das partes no CRM nao separa o papel.

## O que o tenant preenche no mapeamento (binding)

1. **Numero da agencia** (`numero_agencia`): o mesmo cadastro de agencias do AGENCIAS, 5
   digitos sem DV, `00001` sem agencia fisica. Os valores do exemplo sao sinteticos. Conta
   sem `banking_details.branch` no CRM, ou com agencia fora do cadastro, recusa a geracao.
2. **Codigo do papel** (`vinculo`): o CRM tem os papeis `PRIMARY_HOLDER` (cotitular, `C` no
   binding, numerado pelo template), `LEGAL_REPRESENTATIVE` (representante legal, `L`) e
   `RESPONSIBLE_PARTY`. O CRM nao define o que e `RESPONSIBLE_PARTY`: declare o codigo que
   ele recebe no seu cadastro, `R` representante, `P` procurador ou `O` outros, nas duas
   consultas de partes (`partes_dados` e `partes_contraparte_dados`). O exemplo usa `O`, o
   unico codigo que nao afirma procuracao nem representacao; troque para `P` ou `R` se o seu
   processo usa o papel para procurador ou representante. Papel sem codigo declarado recusa
   a geracao.
3. **Codigo Compe** (`compe`): 3 digitos, ou `999` se a instituicao nao tem.
4. **Nome no Unicad** (`nomeUnicad`).
5. **Contrato de cambio** (`operaCambio`, campo 28): declare na implantacao se a instituicao
   firma contrato de cambio. Com `nao`, o campo 28 sai `0` em toda linha. Com `sim`, a geracao
   e recusada: nenhuma aplicacao Lerian registra contrato de cambio, e nao ha fonte para o
   `1` neste documento.

O CNPJ vem da organizacao do Midaz. O tipo da conta vem do CRM
(`regulatory_fields.account_type`: DEPOSIT 1, SAVINGS 2, INVESTMENT 3,
OTHER_FINANCIAL_INVESTMENTS 4, NON_RESIDENT 5, PAYMENT 6). O tipo de pessoa do titular vem do
cadastro (`NATURAL_PERSON` 1, `LEGAL_PERSON` 2); outro valor recusa a geracao.

Num tenant com mais de uma organizacao, o cadastro da instituicao no Reporter restringe
`organization.id` a organizacao dela; sem isso a leitura traz todas, e a geracao e recusada
(o CNPJ lido nao e o da instituicao, ou chegam duas linhas para uma) em vez de escolher uma.

## De onde vem cada campo do titular

- Nome, documento, endereco principal (linha 1 e linha 2, CEP, UF, pais), telefones,
  e-mails, nome social e renda: o cadastro do titular no CRM.
- Quem mora no exterior: o pais do endereco principal e um codigo da tabela que nao e o do
  Brasil, em maiuscula ou minuscula (`br` e o Brasil). Sem pais no cadastro, a pessoa e
  tratada como no Brasil.
- UF (campo 14): para quem mora no Brasil, a sigla do endereco principal convertida no
  codigo IBGE pela tabela de `br/bcb/simba/tabelas/uf-ibge.compute.yaml`; para quem mora no
  exterior, `00` (IN :150), mesmo que o cadastro traga uma sigla igual a de uma UF.
- Pais (campo 15): o nome do pais do codigo ISO 3166-1 alfa-2 do cadastro, pela tabela de
  paises da Receita (`br/rfb/e-financeira/tabelas/paises.txt`), sem acentos e cortado em 40
  caracteres; `BR` sai `Brasil`. Sem pais no cadastro, o campo sai em branco.
- Telefone (campo 17): o celular; sem celular, o outro telefone.
- Renda (campo 18): da pessoa natural, a renda mensal bruta declarada; da pessoa juridica, o
  faturamento anual bruto declarado, como esta no cadastro, sem dividir por 12 (a IN pede a
  renda declarada e nao fixa o periodo). Em centavos sem separador (`500050` para
  R$ 5.000,50); a data de referencia de cada um no campo 19. So sai renda ou faturamento em
  BRL: a figura que o campo 18 imprime (a renda da pessoa natural, o faturamento da juridica) em
  outra moeda recusa a geracao (regras moeda-da-renda e moeda-do-faturamento); a outra figura do
  cadastro nao e conferida, porque nao vai ao arquivo. Moeda fora do formato ISO (tres letras
  maiusculas) tambem recusa. O catalogo nao converte moeda; a IN nao fala de moeda no campo 18 e o leiaute so da exemplos
  em R$ (art. 3o, VIII). A API do CRM exige a moeda junto do valor: sem moeda nao ha renda, e o
  campo 18 sai em branco. Residuo: um valor gravado sem moeda direto no banco, fora da API, sai
  como declarado, sem conferencia de moeda.
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
- `CODIGO_CIDADE` (campo 13): em branco para quem mora no Brasil. O CRM guarda o nome da
  cidade, sem o codigo IBGE. Para quem mora no exterior sai `0000000`, o codigo que a IN da
  para esse caso (IN :149); ele nao e usado no lugar do codigo faltante.
- `DATA_FIM_RELACIONAMENTO_CONTA` (campo 21): em branco enquanto o vinculo esta ativo (conta
  aberta, ou parte sem data de fim). A IN nao da codigo para vinculo ativo.
- `DISPOSITIVO_MOVEL_CADASTRADO` e `COMPUTADOR_CADASTRADO` (campos 26 e 27): sempre em
  branco. Nenhuma aplicacao Lerian registra os dispositivos cadastrados do cliente.
- Do titular, quando o cadastro nao tem o dado: endereco (12), CEP (16), telefone (17),
  renda e data da renda (18 e 19), nome social (24) e abertura da conta (20).
- Das partes relacionadas: campos 12 a 19 e 24 em branco, porque a parte no CRM nao tem
  endereco, telefone, renda nem nome social.

Sem e-mail no cadastro, e sempre nas partes relacionadas, o campo 25 sai
`e-mail nao declarado`, o codigo da IN, sem acento.

## Investigado sem conta

Quando nenhum documento da ordem tem conta na instituicao, nao ha arquivo a gerar: os
arquivos do SIMBA sao das contas (IN art. 1o, :23) e nao tem cabecalho (art. 3o, I, :59).
A geracao deste arquivo e recusada antes de montar o arquivo (erro RPT-0195), dizendo
quantas linhas cada consulta leu. Responda a requisicao sem arquivo, pelo atendimento:
CCS0012 com a situacao 03, relacionamento inexistente (Catalogo de Servicos do SFN,
Volume III, evento CCS0012; Dicionario de Dominios do Banco Central, dominio
SitAtedmntReq).

Quando a ordem tem mais de um investigado e so parte deles tem conta, os arquivos saem com
as contas de quem tem; quem nao tem e declarado sem relacionamento no atendimento da
requisicao.

## Limitacoes desta versao

- **Periodo por investigado**: a ordem pode dar um periodo de afastamento para cada
  investigado, e esta versao tem um so `inicio`/`fim` por caso (a geracao mais nova do
  mesmo `caso` substitui a anterior, entao o caso nao se divide em duas). Nao suportado
  nesta versao; tratar fora do Reporter. Gerar com o periodo mais amplo poria no arquivo
  movimento fora do afastamento.
- **UF e pais do titular**: quem mora no Brasil (pais `BR` ou sem pais) sem UF no endereco
  principal, ou com sigla fora da tabela, recusa a geracao, porque a IN so da o `00` para
  quem mora no exterior. Um pais informado que a tabela da Receita nao tem tambem recusa,
  porque o campo 15 pede o nome. As duas recusas valem tambem para o titular de uma conta de
  contraparte. Corrija o cadastro antes de gerar.
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
  do template, e TAB, CR e LF viram espaco: uma quebra de linha no cadastro nao parte o
  registro. O numero da conta nao passa pela conversao: com TAB, CR ou LF ele recusa a
  geracao.
- **Pessoa investigada nas partes**: o campo 6 compara o documento da parte com cada
  elemento da lista `documentos` da ordem, que vem so com digitos. Vale igual nas contas de
  contraparte: um investigado que e procurador numa delas sai `1`.
- **Preview do template**: a pre-visualizacao de template do manager recusa este template,
  porque ele usa uma macro. A geracao nao.
- **Uma instituicao por arquivo**: um documento entregue em base individual nao soma
  instituicoes diferentes.

## Fonte primaria

Instrucao Normativa BCB 636/2025, art. 2o, III; art. 3o; Anexo I, arquivo III Titulares
(transcricao em `br/bcb/simba/normas/IN-BCB-636-2025.md`):
https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Instru%C3%A7%C3%A3o%20Normativa%20BCB&numero=636
