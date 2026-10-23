# Cadoc 4111 — Saldos Contábeis Diários

> Documento de leitura. Explica o que este regulatório é e o que a Lerian assume
> ao gerá-lo. **Não repete o contrato**: campos, formatos, padrões e periodicidade
> são declarados em `contract.yaml`, e é ele que vale. O que está aqui é o que
> nenhum arquivo consegue dizer.

## O que é

Informe **diário** de saldos contábeis ao Banco Central, por rubrica do COSIF.
Base normativa: Res. BCB 208/2022, IN BCB 524/2024 e 644/2025.

Ele responde uma pergunta por conta, ao fim de cada dia útil: **quanto havia**, ou
**quanto passou**. São duas perguntas diferentes, e é a distinção mais importante
deste documento — veja "As duas classes de conta".

## O que o torna diferente do balancete (4010/4016)

No balancete, as linhas do arquivo vêm do **plano de contas do cliente**: cada
instituição reporta as rubricas que usa.

Aqui não. O conjunto de contas é **fechado e definido pelo regulador** — são estas
trinta rubricas e nenhuma outra (Instruções §4.2.2.a). Elas vivem em `contas.yaml`,
publicado por este catálogo, e não no banco do cliente.

A consequência prática é a razão de o desenho ser assim: uma conta que a sua
consulta não devolveu **continua no arquivo, valendo zero**.

Isso importa porque o arquivo não tem como distinguir duas situações que produzem
a mesma ausência. Uma conta de saldo realmente zero **pode** ser omitida — as
Instruções permitem (§4.2.2.a). Mas uma conta com saldo diferente de zero cujo
mapeamento não alcançou as linhas — rubrica escrita de outro jeito, filtro que
recortou demais — sumiria exatamente do mesmo modo, e aí o arquivo estaria errado.

Com o conjunto fechado, as duas situações deixam de ser a mesma coisa: a linha
sempre existe, e o que se vê é um zero. Um zero que não deveria estar ali é um
erro **visível**, que alguém pode conferir; uma linha ausente não é.

## As duas classes de conta

Cada rubrica de `contas.yaml` carrega uma coluna `measure`, que diz qual das duas
perguntas ela responde:

**`stock` — saldo.** Quanto havia na conta ao fim do dia informado. Acumula desde
a abertura do razão, com o sinal da natureza da conta (uma conta de ativo tem
natureza devedora; uma de passivo, credora). É o mesmo número que o 4010 reporta
no fim do mês.

**`flow` — volume.** Quanto **passou** pela conta no mês, em valor absoluto,
reiniciando a cada virada de mês (Instruções §4.2.2.a). São as cinco rubricas
`3.0.9.70.XX`, de transações realizadas.

As duas diferem em **duas coisas**, e confundir qualquer uma delas produz um
número errado com a mesma aparência de certo:

| | `stock` | `flow` |
|---|---|---|
| **Cálculo** | soma **com sinal**, reexpressa na natureza da conta | soma o **valor absoluto** das transações |
| **Janela** | abre na abertura do razão | abre no primeiro dia do mês |

O exemplo que torna isso concreto: entrou 100 e saiu 100 no mês. Isso é **200 de
volume** e **zero de saldo** — os dois números são legítimos, e cada classe de
conta pede um. Somar o fluxo com sinal daria zero e **subnotificaria o volume**.

É por diferirem nas duas coisas que o binding de exemplo declara duas consultas
sobre a mesma tabela. Não é redundância.

**O volume é o que foi DEBITADO na 3.0.9.70 no mês.** Cada transação de pagamento
é registrada a débito da 3.0.9.70.XX contra a **9.0.9.70.00.00-7** (Controle), que é
uma conta só (IN BCB 538). As instruções exigem que
o volume reinicie a cada mês **e** que, no último dia, ele coincida com o saldo da
mesma conta no 4010 (§4.2.2.b). As duas coisas só fecham se a conta for **zerada
na virada do mês** por uma reversão (a crédito da 3.0.9.70). Por isso a consulta de
fluxo lê só os débitos: a reversão não é transação, e somá-la declararia o mês
anterior de novo.

## O que a Lerian assume do seu razão

A geração é **homologada contra o Midaz**. O binding é seu, e apontá-lo para outro
razão é possível — mas o motor lê as colunas que você nomeia exatamente como elas
são, e não tem como avisar que significam outra coisa. Duas suposições, em
particular, erram em silêncio e produzem um arquivo bem formado com o número
errado:

| Suposição | Se o seu razão não a cumpre |
|---|---|
| O valor do lançamento é uma **magnitude**, e o lado (débito/crédito) vive numa coluna própria | Somar o valor entrega o **saldo líquido** onde o documento pede o **volume**: 100 de entrada e 100 de saída dariam zero, não 200 |
| Toda linha é um lançamento contábil, e uma **reserva se anula pela própria rubrica** (débito e crédito na mesma conta), sem status a filtrar | Num razão que grava a reserva como movimento de um lado só, o valor reservado entra no saldo antes de ser capturado |

Conferir isso contra a sua base de origem é parte de mapear o binding. O cabeçalho
do `binding.example.yaml` diz, linha a linha, o que o exemplo assume.

## As contas-mãe são a soma do que está abaixo delas

O regulador lista contas de níveis diferentes da mesma árvore: Disponibilidades
(1.1.0) ao lado de Caixa (1.1.1) e Depósitos Bancários (1.1.2); Depósitos à Vista
(4.1.1) ao lado das suas filhas por tipo de depositante. Ninguém lança em
Disponibilidades — ela é a soma das filhas, mais as subcontas que o seu razão
mantiver sob elas (uma `1.1.1.10` sua sobe para Caixa e para Disponibilidades).

O contrato declara como o código COSIF se divide em níveis (`rowSet.hierarchy`:
larguras 1-1-1-2-2-2 e um dígito verificador), e o motor soma a árvore por essa
declaração. É também o que decide **o que é lido** do razão: só as rubricas que
estão sob alguma das trinta contas. Receitas, despesas, operações de crédito e o
resto do seu plano de contas não entram na leitura, e por isso não precisam de
natureza na tabela nem podem recusar a geração.

Uma subconta sua **não vira linha** do arquivo: o conjunto é fechado. Ela só
contribui para as linhas acima dela.

## Precondições do cadastro no Midaz

O binding de exemplo lê a rubrica COSIF de `operation.route_code`, que o Midaz
preenche a partir da rubrica configurada na **rota de operação**
(`accountingEntries`), por ação (`direct`, `hold`, `commit`, `cancel`, `revert`…)
e por lado (débito/crédito). O Midaz é genérico e não conhece o COSIF: **configurar
a rubrica certa em cada rota é responsabilidade do cliente.** Para o arquivo sair
certo:

- **Rotas obrigatórias no ledger** (`accounting.validateRoutes` ligado). Uma
  operação sem rota fica sem rubrica, e o Reporter recusa o documento — gerar sem
  ela faria dinheiro sumir do balanço. A recusa nomeia a coluna vazia.
- **Rubrica COSIF de dez dígitos, sem ponto nem traço, em toda rota e toda ação**
  que movimente uma conta do documento.
- **A rubrica de `commit` igual à de `direct`** nas contas de estoque: o Midaz
  grava operações novas no commit, com a rubrica dessa ação, e é por elas que o
  valor capturado entra no saldo.
- **A mesma rubrica no débito e no crédito de `hold` e de `cancel`.** O Midaz não
  grava status na operação (o `APPROVED` vive na transação), então nada filtra a
  reserva: ela entra na soma. Com rotas validadas, o hold grava na conta de origem
  um débito e um crédito, um com cada rubrica da ação, e o cancel grava outro par;
  com a mesma rubrica nos dois lados cada par se anula, e o saldo só muda no
  commit. Nenhuma operação é gravada no destino durante a reserva. Na prática: rota
  **bidirecional** com a mesma rubrica em todas as ações — é também a única forma
  de rota que aceita `revert`.
- **Nenhuma reserva nas contas de fluxo** (3.0.9.70.XX). O fluxo soma o valor
  ABSOLUTO de cada lançamento, então o par do hold, que se anula num saldo, conta
  duas vezes no volume. Registre o volume com lançamentos diretos.
- **O Reporter no fuso de Brasília** (`REPORT_TIMEZONE=America/Sao_Paulo`). O dia
  regulatório é o dia civil brasileiro, e o Midaz guarda o instante em UTC: um Pix
  às 23:30 de sexta é 02:30 de sábado em UTC. Com o Reporter em UTC ele cai no
  sábado — sai do 4111 de sexta e, quando essa sexta é o último dia útil do mês,
  também do balancete do mês. Provado na homologação (27/02/2026).
- **A instituição é a organização do Midaz.** O CNPJ do arquivo é LIDO da
  organização (`organization.legal_document` na base de onboarding), como qualquer
  outro valor; o contrato o normaliza (letras e dígitos, em maiúsculas) e corta a
  raiz de oito posições. O Midaz aceita qualquer texto no `legalDocument`:
  cadastrar a organização com o CNPJ certo é do cliente, e o contrato não confere
  os dígitos verificadores. E o CNPJ lido é conferido contra o cadastro da
  instituição no Reporter: se forem diferentes, a geração é recusada (`RPT-0196`)
  em vez de sair um arquivo de uma instituição registrado em nome de outra. A instituição é escopada **só** pela organização
  (`organization_id` nas operações, `id` na tabela de organizações): todo ledger
  dela é um livro da mesma instituição e entra nos documentos, inclusive um ledger
  criado depois. Outra instituição — outro CNPJ — é outra organização. Por isso
  **nenhum ledger de teste ou de homologação fica na organização de produção**: o
  que está nela entra no balancete.
- **Movimento entre os ledgers da organização (cross-ledger)** é interno à
  instituição. O Midaz grava uma transação por ledger, cada uma fechada contra a
  `@external/BRL` do ledger com a rubrica da rota-ponte
  (`accountingEntries.crossLedger`); com a mesma rubrica nos dois lados, ela zera
  na soma dos livros. Provado na homologação (cenário G).
- **Cheque especial: a rota declara onde cai o excedente.** Num débito acima do
  saldo, o Midaz deixa na conta só a parte coberta (o depósito vai a zero, nunca
  negativo) e lança o excedente numa operação companheira com a rubrica de
  `accountingEntries.overdraft` da rota — o adiantamento a depositante, no ativo.
  Sem essa entrada, com rotas validadas, o Midaz recusa o débito. Provado na
  homologação (cenário E).
- **Bloqueio de saldo não tira o valor do depósito.** O BLOCK do Midaz move o valor
  entre dois saldos da mesma conta. Para o depósito seguir inteiro no 4111 e no
  4010, as duas pernas precisam da MESMA rubrica da conta, e há dois jeitos certos
  de configurar a rota: **não declarar** `accountingEntries.block`/`unblock` — o
  Midaz usa então a rubrica de `direct` (a exigência de "rubrica em toda ação"
  vale para as ações que a rota declara) — ou declará-las com a **mesma rubrica**
  de `direct`. Uma rubrica diferente no `block` é escolha do cliente e aparece no
  arquivo como reclassificação. Provado na homologação (cenário F, sem a entrada).
- **Só reais.** O binding de referência lê `asset_code = BRL`; posição em outra
  moeda é convertida e lançada em reais pelo cliente, como o COSIF exige.
- **Anotações não entram.** Uma transação NOTED grava operações com a rubrica da
  rota, valor zero e `balance_affected = false`; o binding de referência lê só
  `balance_affected = true`, senão a rubrica apareceria como linha de 0,00 sem
  lançamento.
- **As contas de fluxo zeradas todo mês.** No primeiro dia do mês, reverta o saldo
  de cada 3.0.9.70.XX contra a 9.0.9.70.00.00-7. Sem isso o 4010 acumula o volume desde
  a abertura e deixa de coincidir com o 4111 do último dia, que é o que as
  instruções exigem.
- **Estorno: ponto em aberto, que o normativo não resolve.** A função da 3.0.9.70
  (IN BCB 538) é registrar o volume das transações "realizadas durante o mês", e nem
  ela nem as instruções do 4111 dizem se um pagamento estornado sai do volume. Duas
  situações diferentes:
    - uma **devolução** (um Pix devolvido, por exemplo) é uma nova transação de
      pagamento: entra a débito, como qualquer outra, e soma no volume;
    - a **correção** de um registro errado entra a crédito da 3.0.9.70, e este binding
      não a lê: o débito errado FICA no volume do mês e o crédito não o abate, em
      qualquer dia que a correção seja feita. O 4111 sai maior que o saldo da conta no
      4010, e a coincidência que as instruções exigem no último dia quebra.
  Antes de remeter um 4111 com uma correção dessas no mês, confirme o tratamento com
  o BCB. Um binding seu pode abater as correções (marcando-as e lendo-as), por sua
  conta e risco.

A **natureza contábil** de cada rubrica — devedora ou credora — é do plano COSIF,
e o catálogo a publica junto com o contrato (`natureza.yaml`, gerada do elenco de
contas do BACEN; a mesma tabela do 4010, para que o último dia do mês feche com
ele). O que cabe a você é lançar na rubrica certa. Um plano de contas que não seja
o COSIF declara a própria tabela no binding, por sua conta.

## Dias úteis

O 4111 é gerado só para **dia útil já encerrado**, pelo calendário de dias não
úteis publicado com o documento (`dias-nao-uteis.yaml`): sábado, domingo, feriado
nacional e os dias não úteis bancários (Carnaval, Sexta-feira da Paixão e Corpus
Christi) não têm remessa, e o pedido para um deles é recusado dizendo qual
é o último dia útil antes dele.

O volume de sábado, domingo e feriado vai para o **primeiro dia útil seguinte**
(Instruções §4.2.2.b), mesmo quando ele cai no mês seguinte: a janela de volume de
um mês abre logo depois do último dia útil do mês anterior. Um sábado 31 entra no
arquivo da segunda-feira dia 2. O 4010 corta o mês pelo mesmo calendário, então o
último 4111 do mês e o balancete fecham no mesmo instante. Provado na homologação
(cenário D).

## Mais de uma base: consolidação dentro da mesma instituição

O 4111 é entregue **em base individual**: uma instituição, um arquivo, com os saldos
dela. Somar os saldos de instituições diferentes num único 4111 é envio errado.

Os saldos de uma mesma instituição podem, porém, estar em mais de uma base — mais de um
ledger no Midaz, um core antigo e o novo durante uma migração, o razão de pagamentos no
Midaz e as contas patrimoniais num ERP contábil. Para esses casos o mapeamento pode ler o
conjunto de mais de uma fonte: além da consulta do próprio conjunto, cada **fonte
adicional** (`also`) traz a sua consulta, as suas colunas e as suas condições.

O contrato declara a regra: as linhas se unificam pela rubrica (`cosifCode`), e o
`saldoDia` de todas as fontes é **somado**. Cada fonte é montada inteira, com as suas
contas-mãe, antes de unificar; a conta-mãe do arquivo é a soma das contas-mãe das
fontes.

Cuidados:

- **Só dados da própria instituição.** Uma fonte adicional lê **sem** o escopo da
  instituição da entrega; são as condições dela que garantem que entram só os dados
  desta instituição.
- **Soma é soma.** A mesma rubrica em duas fontes é somada — o certo quando o saldo
  está partido entre as bases, e o errado quando uma base é cópia da outra. Uma fonte
  não deve repetir lançamentos que outra já traz.
- **Mesma convenção.** Toda fonte entrega o valor na mesma convenção (crédito
  positivo, débito negativo) e escreve a rubrica do mesmo jeito: o motor compara a
  rubrica como texto exato.

Quem usa o mapeamento de referência do Midaz pode acrescentar fontes adicionais sem
deixar de usá-lo: a parte da referência continua homologada pela Lerian, e as fontes
acrescentadas são do cliente.

## Limitações conhecidas desta versão

**O calendário cobre 2025 a 2027.** Uma data-base fora disso é recusada até a
cobertura ser estendida, o que é parte da curadoria anual.

**O XSD é o vigente desde 02/01/2025.** O `schema/XSD_4111.xsd` aceita o código de
conta de 10 dígitos, até 30 contas, saldo com sinal (a natureza admite negativo) e a
raiz do CNPJ alfanumérica (IN RFB 2.229/2024). O cabeçalho do arquivo ainda diz
"Versão 1.0, criado em 30/03/2023": o BCB mudou o conteúdo sem mudar o rótulo, então
é pelo conteúdo que se distingue do anterior, de 8 dígitos e 25 contas.

## Fonte primária

As Instruções de Preenchimento oficiais, citadas acima como "Instruções §":
<https://www.bcb.gov.br/content/estabilidadefinanceira/Documents/Leiaute_de_documentos/saldosDiariosInstrucoesPreenchimentoV2.pdf>

Em qualquer divergência entre este manual e a fonte primária, **a fonte primária
prevalece** — e a divergência é um defeito da curadoria, que deve ser reportado.
