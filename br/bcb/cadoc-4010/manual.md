# Cadoc 4010 — Balancete Patrimonial Analítico

> Documento de leitura. Explica o que este regulatório é e o que a Lerian assume
> ao gerá-lo. **Não repete o contrato**: campos, formatos, padrões e periodicidade
> são declarados em `contract.yaml`, e é ele que vale. O que está aqui é o que
> nenhum arquivo consegue dizer.

## O que é

O balancete **mensal** da instituição ao Banco Central: o saldo de fechamento de
cada rubrica COSIF no fim do mês, de todas as contas às quais a instituição presta
informação. É a fotografia contábil do mês, e é contra ela que outros documentos
são conferidos — o 4111 do último dia útil do mês tem de coincidir com este
balancete (Instruções do 4111, §4.2.2.b).

As linhas do arquivo vêm do **plano de contas do cliente**: cada instituição
reporta as rubricas que movimenta. Isso o separa do 4111, cujo conjunto de contas é
fechado e publicado pelo regulador.

## Saldo de fechamento, na natureza da conta

Cada linha responde **quanto havia** na rubrica no fim do mês: tudo o que foi
lançado desde a abertura do razão, somado com sinal (débito de um lado, crédito do
outro) e reexpresso na **natureza da própria conta**. Uma conta de ativo, devedora,
com saldo devedor sai positiva; uma de passivo, credora, com saldo credor também. A
convenção do razão não vaza para o arquivo.

A natureza é do **plano de contas do cliente**, não deste catálogo, e é declarada
no binding. No exemplo contra o Midaz ela é lida do primeiro dígito da rubrica
(grupo COSIF). A exceção que todo plano tem é a **retificadora** — provisão para
operações de crédito (1.6.9), depreciação acumulada —, credora dentro de um grupo
devedor. Declarada só pelo grupo, ela sai com o sinal trocado num arquivo bem
formado. Declare-a pelo prefixo dela: vale o prefixo mais longo que casa com a
rubrica.

O motor **não confere** se o sinal está certo. Quem confere é a pessoa que revisa o
rascunho antes de aprovar — é para isso que a geração termina em rascunho.

## As contas-mãe são a soma do que está abaixo delas

O leiaute pede todas as contas, inclusive as sintéticas: o exemplo do BCB lista
Ativo e Disponibilidades ao lado das analíticas. Ninguém lança numa conta sintética
— o Midaz não tem esse conceito —, então cada ancestral de uma rubrica movimentada
vira uma linha **derivada**, somada do que está abaixo dela e reexpressa na natureza
dela própria. Uma provisão, credora dentro do grupo 1, **abate** Operações de
Crédito na soma.

O contrato declara como o código se divide em níveis e como o dígito verificador
de cada ancestral é calculado; o motor monta a árvore por essa declaração.

## O mês fecha no último dia útil

O saldo é o do **último dia útil do mês** (leiaute §3.2.2.b), pelo calendário de
dias não úteis publicado com o documento (`dias-nao-uteis.yaml`): sábados,
domingos, feriados nacionais e os dias não úteis bancários — Carnaval, Sexta-feira
da Paixão e Corpus Christi. Quando o mês
termina num sábado, o que foi lançado naquele sábado pertence ao balancete do mês
seguinte — e o 4111 corta os dias pelo mesmo calendário, então os dois documentos
não discordam sobre onde um dia cai.

O mês só é gerável depois de encerrado no fuso do Reporter. Antes disso, o arquivo
traria parte do mês como se fosse o mês inteiro, e nada nele diria qual parte
falta.

## O que a Lerian assume do seu razão

A geração é **homologada contra o Midaz**. O binding é seu, e apontá-lo para outro
razão é possível — mas o motor lê as colunas que você nomeia exatamente como elas
são, e não tem como avisar que significam outra coisa. O que erra em silêncio e
produz um arquivo bem formado com o número errado:

| Suposição | Se o seu razão não a cumpre |
|---|---|
| O valor do lançamento é uma **magnitude**, e o lado (débito/crédito) vive numa coluna própria | A soma com sinal sai errada, e com ela o saldo de cada rubrica |
| Toda linha é um lançamento contábil, e uma **reserva se anula pela própria rubrica** (débito e crédito na mesma conta), sem status a filtrar | O valor reservado entra no saldo antes de ser capturado |
| A rubrica de cada lançamento está **no próprio lançamento** | Sem ela, não há em que linha somar o valor |

## Precondições do cadastro no Midaz

O binding de exemplo lê a rubrica COSIF de `operation.route_code`, que o Midaz
preenche a partir da rubrica configurada na **rota de operação**
(`accountingEntries`), por ação e por lado. O Midaz é genérico e não conhece o
COSIF: **configurar a rubrica certa em cada rota é responsabilidade do cliente.**
Para o arquivo sair certo:

- **Rotas obrigatórias no ledger** (`accounting.validateRoutes` ligado). Uma
  operação sem rota fica sem rubrica, e o Reporter recusa o documento — gerar sem
  ela faria dinheiro sumir do balancete. A recusa nomeia a coluna vazia.
- **Rubrica COSIF de dez dígitos, sem ponto nem traço, em toda rota e toda ação**
  que movimente uma conta. A grafia de oito dígitos, anterior a 2025, é recusada:
  a retificação de uma data-base anterior a 2025 não é coberta por esta versão.
- **A rubrica de `commit` igual à de `direct`**, e **a mesma rubrica no débito e
  no crédito de `hold` e de `cancel`**: assim a reserva se anula na própria conta e
  o saldo só muda quando o valor é capturado. Na prática, rota **bidirecional** com
  a mesma rubrica em todas as ações.
- **O Reporter no fuso de Brasília** (`REPORT_TIMEZONE=America/Sao_Paulo`). O mês
  regulatório é o do calendário civil brasileiro, e o Midaz guarda o instante em
  UTC: um lançamento às 22:00 do último dia do mês é dia 1º em UTC. Com o Reporter
  em UTC, ele sai do balancete do mês a que pertence.
- **A instituição é a organização do Midaz.** O CNPJ do arquivo é lido da
  organização (`organization.legal_document`); o contrato o normaliza, confere os
  dígitos verificadores (numérico ou alfanumérico) e corta a raiz de oito
  posições. O Midaz aceita qualquer texto no `legalDocument`: um CNPJ que não
  verifica recusa a geração. O CNPJ lido também é conferido contra o cadastro da
  instituição no Reporter, e um diferente recusa a geração (`RPT-0196`). Todo ledger da organização entra no balancete,
  inclusive um criado depois; outra instituição é outra organização. Por isso
  **nenhum ledger de teste fica na organização de produção**.
- **Movimento entre os ledgers da organização** é interno à instituição: cada
  ledger fecha a sua transação contra a `@external/BRL` com a rubrica da
  rota-ponte (`accountingEntries.crossLedger`); com a mesma rubrica nos dois
  lados, ela zera na soma dos livros. Provado na homologação (cenário G).
- **Cheque especial: a rota declara onde cai o excedente.** Num débito acima do
  saldo, o Midaz deixa o depósito em zero e lança o excedente com a rubrica de
  `accountingEntries.overdraft` — o adiantamento a depositante, no ativo. Provado
  na homologação (cenário E).
- **Bloqueio de saldo não tira o valor do depósito**, desde que as duas pernas do
  BLOCK usem a mesma rubrica da conta: não declare `accountingEntries.block` e
  `unblock` (o Midaz usa a de `direct`) ou declare-as iguais a ela. Provado na
  homologação (cenário F).
- **Só reais, e só o que moveu saldo.** O binding de referência lê
  `asset_code = BRL`, `balance_affected = true` (uma anotação NOTED não entra) e
  só o que o Midaz não apagou.
- **As contas de volume do 4111 zeradas todo mês.** As rubricas 3.0.9.70.XX são
  saldo aqui, como qualquer outra. Se a instituição também entrega o 4111, reverta
  cada uma contra a 9.0.9.70.00.00-7 no primeiro dia do mês; sem isso o balancete
  acumula o volume desde a abertura e deixa de coincidir com o 4111 do último dia.

## Limitações conhecidas desta versão

- **Existência da rubrica não é conferida.** O contrato confere a forma do código
  (dez dígitos), não que a rubrica exista no elenco COSIF vigente. Uma rubrica que
  o plano de contas não contempla passa daqui e é rejeitada pelo BCB na recepção.
- **Ordem de remessa.** O BCB só recepciona a data-base N depois de aceita a N-1.
  Isso é regra de protocolo de envio, que o Reporter não faz: um arquivo gerado
  fora de ordem é válido.
- **O calendário cobre 2025 a 2027.** Uma data-base fora disso é recusada até a
  cobertura ser estendida, o que é parte da curadoria anual.

## Fonte primária

O leiaute dos documentos 4010 e 4016, citado acima como "leiaute §":
<https://www.bcb.gov.br/content/estabilidadefinanceira/cosif_leiautes/Leiaute_4010_xmlV0.pdf>

Em qualquer divergência entre este manual e a fonte primária, **a fonte primária
prevalece** — e a divergência é um defeito da curadoria, que deve ser reportado.
