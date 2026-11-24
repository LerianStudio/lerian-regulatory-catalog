# SIMBA — Agências (arquivo I AGÊNCIAS)

Arquivo I do SIMBA, leiaute da Instrução Normativa BCB 636/2025 (Anexo I, campos 1 a 14).
A IN entra em vigor em 01/12/2026 (art. 7º): use este documento a partir dessa data.

## O que é

Uma linha por agência envolvida no caso, sem repetir: a agência de cada conta investigada
e a de cada conta da mesma instituição com a qual uma conta investigada transacionou no
período do afastamento do sigilo (IN 636, art. 2º, I). É um dos cinco arquivos da resposta ao
caso; os outros são CONTAS, TITULARES, EXTRATO e ORIGEM-DESTINO, gerados com os mesmos
parâmetros.

## Parâmetros da geração

Os mesmos nos cinco documentos SIMBA:

- `caso`: o número do caso, como está na ordem (`001-MPF-000001-01`).
- `documentos`: os CPFs e CNPJs da ordem, somente dígitos, sem pontos, traços ou barras. O
  documento formatado não encontra contas, e o caso sai como resposta vazia para ele, sem
  erro; a conferência antes da aprovação avisa o documento sem conta.
- `contas`: os números de conta da ordem, com DV, só dígitos. Preencher só quando o ofício
  restringir a contas específicas; o normal é não preencher e, ausente, entram todas as contas
  dos documentos. Preencher sem a ordem pedir omite contas do investigado.
- `inicio` e `fim`: o primeiro e o último dia do afastamento do sigilo.

O `fim` tem de ser um dia que já acabou no calendário do Reporter: a geração lê um período
fechado, e o lançamento gravado depois não desloca a numeração entre os arquivos.
O `fim` também não pode ser anterior ao `inicio`: um período invertido é recusado ao gerar,
em vez de sair um arquivo sem lançamento nenhum.

Duas gerações do mesmo `caso` são a mesma entrega: a mais nova substitui o rascunho
anterior, mesmo com documentos ou período corrigidos.

## Quais contas entram

- Contas em que um documento da ordem é o **titular** (o documento do instrumento no CRM).
- Contas encerradas **entram** (o encerramento não filtra).
- Contas apagadas do CRM **não entram**.
- **Só titular**: a conta em que o documento investigado é só cotitular, representante
  ou procurador não entra; o índice das partes no CRM não separa o papel.
- Contas com que as do caso transacionaram: as outras pernas dos lançamentos das contas do
  caso no período que têm instrumento no CRM. Conta de sistema ou de liquidação, sem
  instrumento, não entra.

## O que o tenant preenche no mapeamento (binding)

1. **Cadastro de agências**, uma vez na implantação. Agência não existe como entidade no
   Midaz nem no CRM: o CRM guarda só o número da agência de cada conta
   (`banking_details.branch`). Cada atributo é um `case` por esse número:
   `numero_agencia` (5 dígitos, sem DV), `nome_agencia`, `endereco_agencia`,
   `codigo_cidade` (IBGE, 7 dígitos), `codigo_uf` (IBGE, 2 dígitos; SP = 35),
   `pais_agencia`, `cep_agencia`, `telefone_agencia`, `data_abertura_agencia`,
   `data_fechamento_agencia` (agência aberta: `9999-12-31`, que sai `31129999`, a sentinela
   da IN para agência não fechada; IN 636, Anexo I, AGÊNCIAS, campo 11).
   Os valores do exemplo são **sintéticos** e precisam ser trocados. O cadastro é
   **fechado**: uma agência que ele não lista recusa a geração, e uma conta **sem**
   `banking_details.branch` no CRM também. Toda agência listada tem **todos** os
   atributos: o Reporter não aceita valor vazio num `case`. A agência sem agência física
   (instituição digital: o número que o cadastro mapeia para `00001`) é cadastrada com as
   sentinelas do Anexo I (ver abaixo). O mesmo `numero_agencia` vai no binding do CONTAS.
2. **Código Compe** da instituição (`compe`): 3 dígitos, ou `999` se ela não tem.
3. **Nome no Unicad** (`nomeUnicad`): exatamente como está no cadastro do Banco Central.
4. **Se a instituição possui agência física** (`possuiAgenciaFisica`, campo 14): `1`
   possui, `2` não possui. É um valor da instituição, não de cada agência.

O CNPJ vem da organização do Midaz.

Num tenant com mais de uma organização, o cadastro da instituição no Reporter restringe
`organization.id` à organização dela; sem isso a leitura traz todas, e a geração é recusada
(o CNPJ lido não é o da instituição, ou chegam duas linhas para uma) em vez de escolher uma.

## Instituição sem agência física

Com `possuiAgenciaFisica = 2`, toda linha sai com as sentinelas do Anexo I, sem acento,
qualquer que seja o cadastro: nome e endereço `nao possui agencia fisica`, cidade
`0000000`, UF `00`, CEP `00000000`, telefone `0000000000`. O número da agência vem do
cadastro: preencha `numero_agencia: "00001"`, que é o número que a IN pede (IN 636, Anexo I,
AGÊNCIAS, campo 2); com outro número, a linha sai com ele. A data de abertura não tem sentinela:
informe a data de início de operação da instituição. Agência aberta: fechamento
`9999-12-31`, que sai `31129999`.

Com `possuiAgenciaFisica = 1`, os campos saem do cadastro. Uma agência sem agência
física nessa instituição (a agência `00001`) é cadastrada com as mesmas sentinelas,
como no exemplo.

## Período

O período vai do início do dia `inicio` ao fim do dia `fim` no calendário do Reporter
(`REPORT_TIMEZONE`, padrão `America/Sao_Paulo`).

## Campos que podem sair em branco, e por quê

A IN manda informar o campo, ou a sentinela quando a própria IN dá uma. Onde não há dado
nem sentinela, o campo sai **em branco**:

- `DATA_ABERTURA_AGENCIA` (campo 10): a IN não dá sentinela. O cadastro do exemplo a
  preenche para toda agência; um binding que não mapeia `data_abertura_agencia` a deixa em
  branco em todas.
- Os demais campos do cadastro não saem em branco: toda agência listada tem todos os
  atributos (o Reporter recusa valor vazio num `case`). Na implantação, a agência física
  entra com o cadastro completo, telefone inclusive; sem isso ela não pode ser listada.

## Nome dos arquivos na entrega

O arquivo baixado do Reporter tem o nome do relatório (o identificador da geração, com
extensão `.txt`), e não o nome que a entrega exige. Antes de validar e transmitir, renomeie
cada um dos cinco arquivos com o prefixo do número do caso, no formato
`999-XXX-999999-99_ARQUIVO.TXT` (Memorando de Instrução MI 001 - ASSPA/PGR, item 1.4, b). O
número do caso é o mesmo informado no parâmetro `caso` da geração, como está no ofício. Este
arquivo é o `<caso>_AGENCIAS.TXT`; para o caso 001-MPF-005097-79, por exemplo,
`001-MPF-005097-79_AGENCIAS.TXT`.

Os cinco arquivos de uma entrega levam o mesmo prefixo: `<caso>_AGENCIAS.TXT`,
`<caso>_CONTAS.TXT`, `<caso>_TITULARES.TXT`, `<caso>_EXTRATO.TXT` e
`<caso>_ORIGEM_DESTINO.TXT` (com sublinhado no ORIGEM_DESTINO, como no memorando). Só o nome
muda: o conteúdo do arquivo não é alterado.

## Investigado sem conta

Quando nenhum documento da ordem tem conta na instituição, não há arquivo a gerar: os
arquivos do SIMBA são das contas (IN 636, art. 1º) e não têm cabeçalho (IN 636, art. 3º, I).
A geração deste arquivo é recusada antes de montar o arquivo (erro RPT-0195), dizendo
quantas linhas cada consulta leu. Responda à requisição sem arquivo, pelo atendimento:
CCS0012 com a situação 03, relacionamento inexistente (Catálogo de Serviços do SFN,
Volume III, evento CCS0012; Dicionário de Domínios do Banco Central, domínio
SitAtedmntReq).

Quando a ordem tem mais de um investigado e só parte deles tem conta, os arquivos saem com
as contas de quem tem; quem não tem é declarado sem relacionamento no atendimento da
requisição.

## Limitações desta versão

- **Período por investigado**: a ordem pode dar um período de afastamento para cada
  investigado, e esta versão tem um só `inicio`/`fim` por caso (a geração mais nova do
  mesmo `caso` substitui a anterior, então o caso não se divide em duas). Não suportado
  nesta versão; tratar fora do Reporter. Gerar com o período mais amplo poria no arquivo
  movimento fora do afastamento.
- **Agência onde ocorreu a transação**: a IN pede também a agência na qual ocorreram
  transações. Nenhuma aplicação Lerian registra isso; o arquivo leva só as agências das
  contas.
- **Texto sem acento**: todo texto passa pela conversão para ASCII do template (acentos,
  cedilha, til, ordinais) e TAB, CR e LF dentro de um valor viram espaço: uma quebra de
  linha no cadastro não parte o registro. Um caractere fora do ASCII que a conversão não cobre (por exemplo `°`, `’`, `–`, `ø`)
  recusa a geração, porque o arquivo é ASCII (IN 636, art. 3º): a recusa mostra o campo e o valor,
  e o cadastro tem de ser corrigido.
- **Preview do template**: a pré-visualização de template do manager recusa este template,
  porque ele usa uma macro. A geração não.
- **Uma instituição por arquivo**: um documento entregue em base individual não soma
  instituições diferentes.

## Fonte primária

Instrução Normativa BCB 636/2025, art. 2º, I; art. 3º; Anexo I, arquivo I Agências
(transcrição em `br/bcb/simba/normas/IN-BCB-636-2025.md`):
https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Instru%C3%A7%C3%A3o%20Normativa%20BCB&numero=636
