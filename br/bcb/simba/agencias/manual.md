# SIMBA — Agencias (arquivo I AGENCIAS)

Arquivo I do SIMBA, leiaute da Instrucao Normativa BCB 636/2025 (Anexo I, campos 1 a 14).
A IN entra em vigor em 01/12/2026 (art. 7o): use este documento a partir dessa data.

## O que e

Uma linha por agencia envolvida no caso, sem repetir: a agencia de cada conta investigada
e a de cada conta da mesma instituicao com a qual uma conta investigada transacionou no
periodo do afastamento do sigilo (IN art. 2o, I). E um dos cinco arquivos da resposta ao
caso; os outros sao CONTAS, TITULARES, EXTRATO e ORIGEM-DESTINO, gerados com os mesmos
parametros.

## Parametros da geracao

Os mesmos nos cinco documentos SIMBA:

- `caso`: o numero do caso, como esta na ordem (`001-MPF-000001-01`).
- `documentos`: os CPFs e CNPJs da ordem, so digitos.
- `contas`: os numeros de conta da ordem, com DV, so digitos. Ausente, entram todas as
  contas dos documentos.
- `inicio` e `fim`: o primeiro e o ultimo dia do afastamento do sigilo.

Duas geracoes do mesmo `caso` sao a mesma entrega: a mais nova substitui o rascunho
anterior, mesmo com documentos ou periodo corrigidos.

## Quais contas entram

- Contas em que um documento da ordem e o **titular** (o documento do instrumento no CRM).
- Contas encerradas **entram** (o encerramento nao filtra).
- Contas apagadas do CRM **nao entram**.
- **Cotitular**: nesta versao, a conta em que o documento investigado e so cotitular nao
  entra. A decisao esta pendente: o motor ainda nao executa a condicao "titular OU
  cotitular", e o indice das partes no CRM nao separa o papel (cotitular, procurador,
  responsavel).
- Procurador e representante: a conta de que o investigado e so procurador nao entra.
- Contas com que as do caso transacionaram: as outras pernas dos lancamentos das contas do
  caso no periodo que tem instrumento no CRM. Conta de sistema ou de liquidacao, sem
  instrumento, nao entra.

## O que o tenant preenche no mapeamento (binding)

1. **Cadastro de agencias**, uma vez na implantacao. Agencia nao existe como entidade no
   Midaz nem no CRM: o CRM guarda so o numero da agencia de cada conta
   (`banking_details.branch`). Cada atributo e um `case` por esse numero:
   `numero_agencia` (5 digitos, sem DV), `possui_agencia_fisica` (1 possui, 2 nao possui),
   `nome_agencia`, `endereco_agencia`, `codigo_cidade` (IBGE, 7 digitos),
   `codigo_uf` (IBGE, 2 digitos; SP = 35), `pais_agencia`, `cep_agencia`,
   `telefone_agencia`, `data_abertura_agencia`, `data_fechamento_agencia`.
   Os valores do exemplo sao **sinteticos** e precisam ser trocados. Uma agencia que o
   cadastro nao lista recusa a geracao, e uma conta **sem** `banking_details.branch` no CRM
   tambem: preencha o numero da agencia de toda conta (instituicao digital: o numero que
   o cadastro mapeia para `00001`). O mesmo `numero_agencia` vai no binding do CONTAS.
2. **Codigo Compe** da instituicao (`compe`): 3 digitos, ou `999` se ela nao tem.
3. **Nome no Unicad** (`nomeUnicad`): exatamente como esta no cadastro do Banco Central.

O CNPJ vem da organizacao do Midaz.

## Instituicao sem agencia fisica

Com `possui_agencia_fisica = 2`, o arquivo sai com as sentinelas do Anexo I, sem acento:
agencia `00001` (preencha `numero_agencia: "00001"`), nome e endereco
`nao possui agencia fisica`, cidade `0000000`, UF `00`, CEP `00000000`, telefone
`0000000000`. A data de abertura nao tem sentinela: informe a data de inicio de operacao
da instituicao, ou ela sai em branco. Sem data de fechamento, sai `31129999`.

## Periodo

O periodo vai do inicio do dia `inicio` ao fim do dia `fim` no calendario do Reporter
(`REPORT_TIMEZONE`, padrao `America/Sao_Paulo`).

## Campos que podem sair em branco, e por que

A IN manda informar o campo, ou a sentinela quando a propria IN da uma. Onde nao ha dado
nem sentinela, o campo sai **em branco**:

- `DATA_ABERTURA_AGENCIA` (campo 10): a IN nao da sentinela; sem data no cadastro, branco.
- `CODIGO_CIDADE`, `CODIGO_UF`, `ENDERECO_CEP` e `TELEFONE_AGENCIA` de agencia fisica sem o
  dado no cadastro: branco.

## Limitacoes desta versao

- **Agencia onde ocorreu a transacao**: a IN pede tambem a agencia na qual ocorreram
  transacoes. Nenhuma aplicacao Lerian registra isso; o arquivo leva so as agencias das
  contas.
- **Texto sem acento**: todo texto passa pela conversao para ASCII do template (acentos,
  cedilha, til, ordinais) e TAB dentro de um valor vira espaco. **Quebra de linha (CR ou LF)
  dentro de um valor nao e retirada** e quebraria a linha do arquivo: confira nomes e
  enderecos do cadastro antes de aprovar.
- **Preview do template**: a pre-visualizacao de template do manager recusa este template,
  porque ele usa uma macro. A geracao nao.
- **Uma instituicao por arquivo**: um documento entregue em base individual nao soma
  instituicoes diferentes.

## Fonte primaria

Instrucao Normativa BCB 636/2025, art. 2o, I; art. 3o; Anexo I, arquivo I Agencias
(transcricao em `br/bcb/simba/normas/IN-BCB-636-2025.md`):
https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Instru%C3%A7%C3%A3o%20Normativa%20BCB&numero=636
