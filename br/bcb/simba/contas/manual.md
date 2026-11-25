# SIMBA — Contas (arquivo II CONTAS)

Arquivo II do SIMBA, leiaute da Instrução Normativa BCB 636/2025 (Anexo I, campos 1 a 12).
A IN entra em vigor em 01/12/2026 (art. 7º): use este documento a partir dessa data.

## O que é

Uma linha por conta: as contas investigadas e as contas da mesma instituição com as quais
elas transacionaram no período do afastamento do sigilo (IN 636, art. 2º, II). É um dos cinco
arquivos da resposta ao caso; os outros são AGÊNCIAS, TITULARES, EXTRATO e
ORIGEM-DESTINO, gerados com os mesmos parâmetros.

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

## Quais contas entram

- **Investigadas** (campo 7 = `1` com lançamento no período, `2` sem): as contas em que um
  documento da ordem é o **titular** ou **cotitular**. Encerradas entram, com a data de
  encerramento.
  Apagadas do CRM não entram.
- **Cotitular entra**: a conta em que o documento investigado é cotitular (parte
  `PRIMARY_HOLDER` do instrumento no CRM) também é conta do caso. A conta em que ele é só
  representante legal ou `RESPONSIBLE_PARTY` não entra.
- **Contas com que as investigadas transacionaram** (campo 7 = `3`): as outras pernas dos
  lançamentos das contas investigadas no período, quando são conta de cliente no CRM. Uma
  conta que também é investigada sai uma vez só, como investigada.

## O que o tenant preenche no mapeamento (binding)

1. **Número da agência**: vem do CRM (`banking_details.branch`), como está gravado; o
   template completa com zeros (`1` e `0001` saem `00001`). Com letra, hífen ou mais de 5
   dígitos, ou sem o número, a geração é recusada.
2. **Código Compe** (`compe`): 3 dígitos, ou `999` se a instituição não tem.
3. **Nome no Unicad** (`nomeUnicad`).
4. **Instituição sucedida** (`contaIncorporada`, campo 12): manual. Ver Campos que o Midaz
   não possui.

O CNPJ vem da organização do Midaz. O tipo da conta vem do CRM
(`regulatory_fields.account_type`: DEPOSIT 1, SAVINGS 2, INVESTMENT 3,
OTHER_FINANCIAL_INVESTMENTS 4, NON_RESIDENT 5, PAYMENT 6); conta sem tipo recusa a geração,
então preencha o tipo no CRM antes.

Num tenant com mais de uma organização, o cadastro da instituição no Reporter restringe
`organization.id` à organização dela; sem isso a leitura traz todas, e a geração é recusada
(o CNPJ lido não é o da instituição, ou chegam duas linhas para uma) em vez de escolher uma.

## Saldos (campos 10 e 11)

O período vai do início do dia `inicio` ao fim do dia `fim` no calendário do Reporter
(`REPORT_TIMEZONE`, padrão `America/Sao_Paulo`). O saldo é a soma, com sinal, dos lançamentos que movem saldo em reais desde a abertura:
crédito soma, débito subtrai, inclusive na chave de sistema `overdraft` (no saque que
entra no cheque especial, o Midaz grava ali a parte sacada; no crédito que o paga, a parte
paga), sem as reservas e liberações. O inicial vai até o
início do primeiro dia do afastamento; o final, até o fim do último. Os valores saem em
centavos, sem separador (`10000` para R$ 100,00; `000` para zero ou sem lançamento até a
data).

- **Saldo negativo**: o Anexo I não dá sinal nem natureza a estes campos, e um campo
  numérico não admite traço (IN 636, art. 3º, VII). Uma conta que começa ou termina devedora
  (cheque especial) sai com o saldo em valor absoluto (`1250` para -R$ 12,50): o arquivo
  não mostra que o saldo era devedor. Antes de aprovar, confira as contas com saldo
  negativo, inclusive as que não tiveram lançamento no período.
- **Reserva (hold)**: as reservas e liberações do Midaz não entram no saldo nem nos
  lançamentos, e a transferência concluída sai uma vez só. Num ledger que valida rotas, uma
  reserva ainda aberta na data de corte já tirou o valor do disponível, e o saldo sai sem ele.
- Cliente com arquivo morto do Midaz (`retain`) perde o histórico antigo e o saldo sai
  errado sem aviso: o SIMBA parte de cliente sem `retain`.

## Campos que podem sair em branco, e por quê

- `DATA_ABERTURA_CONTA` (campo 5): vem do CRM (`banking_details.opening_date`); a IN não dá
  sentinela, e sem a data o campo sai em branco.
- `CONTA_INSTITUICAO_INCORPORADA` (campo 12): o CNPJ da instituição sucedida, campo manual. O
  Midaz não registra sucessão. Vazio, a conta é nativa e o campo sai em branco, como a IN
  manda.

Sem data de encerramento, o campo 6 sai `31129999`, a sentinela da IN.

A data de encerramento é lida como dia (`civilDate` no binding): o CRM a guarda como a
meia-noite UTC do dia, e a API do CRM normaliza para essa meia-noite qualquer valor que
receba, com ou sem hora ou fuso (`2026-06-30T00:00:00-03:00` vira o dia 30). Um valor gravado
fora da API com hora diferente da meia-noite UTC recusa a geração (RPT-0143).

## Nome dos arquivos na entrega

O arquivo baixado do Reporter tem o nome do relatório (o identificador da geração, com
extensão `.txt`), e não o nome que a entrega exige. Antes de validar e transmitir, renomeie
cada um dos cinco arquivos com o prefixo do número do caso, no formato
`999-XXX-999999-99_ARQUIVO.TXT` (Memorando de Instrução MI 001 - ASSPA/PGR, item 1.4, b). O
número do caso é o mesmo informado no parâmetro `caso` da geração, como está no ofício. Este
arquivo é o `<caso>_CONTAS.TXT`; para o caso 001-MPF-005097-79, por exemplo,
`001-MPF-005097-79_CONTAS.TXT`.

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
- **Número da conta**: sai como o CRM o guarda (`banking_details.account`), até 20 posições;
  confira que o valor cadastrado inclui o DV.
- **Texto sem acento**: o nome da instituição passa pela conversão para ASCII do template, e
  TAB, CR e LF viram espaço. O número da conta não passa pela conversão: com TAB, CR ou LF
  ele recusa a geração. Um caractere fora do ASCII que a conversão não cobre (por exemplo `°`, `’`, `–`, `ø`)
  recusa a geração, porque o arquivo é ASCII (IN 636, art. 3º): a recusa mostra o campo e o valor,
  e o cadastro tem de ser corrigido.
- **Preview do template**: a pré-visualização de template do manager recusa este template,
  porque ele usa uma macro. A geração não.
- **Uma instituição por arquivo**: um documento entregue em base individual não soma
  instituições diferentes.

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

## Fonte primária

Instrução Normativa BCB 636/2025, art. 2º, II; art. 3º; Anexo I, arquivo II Contas
(transcrição em `br/bcb/simba/normas/IN-BCB-636-2025.md`):
https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?tipo=Instru%C3%A7%C3%A3o%20Normativa%20BCB&numero=636
