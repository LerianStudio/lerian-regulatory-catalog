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
natureza declarada no binding nem podem recusar a geração.

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

A **natureza contábil** de cada rubrica — devedora ou credora — é propriedade do
plano de contas do cliente, não deste catálogo. Publicar uma tabela nossa criaria
uma segunda fonte de verdade que ninguém reconcilia. Ela é declarada no binding,
do seu lado; no exemplo contra o Midaz vem do COSIF referenciado nas rotas
contábeis.

## Limitações conhecidas desta versão

**Acúmulo de fim de semana.** Volumes de sábado, domingo e feriado devem ser
acumulados no próximo dia útil (Instruções §4.2.2.b). O calendário de dias úteis
que faz esse deslocamento não existe nesta versão, e o efeito disso depende de o
fim de semana atravessar ou não a virada do mês:

- **Dentro do mesmo mês**, o volume do fim de semana entra no arquivo do próximo
  dia útil naturalmente, porque a janela do fluxo cobre o mês inteiro até a
  data-base. É o resultado que a regra pede, alcançado por outro caminho.
- **Atravessando a virada do mês** — um sábado dia 31 com o próximo dia útil já no
  mês seguinte —, não entra: a janela do arquivo do dia 1º abre no dia 1º, e o
  volume do dia 31 ficou no mês anterior, cujo último arquivo é anterior a ele.
  **Esse volume não é reportado em arquivo nenhum.**
- Um arquivo gerado **para o próprio sábado** reporta o sábado, em vez de somá-lo
  ao dia útil seguinte.

**O XSD publicado está desatualizado.** O `schema/XSD_4111.xsd` é a v1.0 de
30/03/2023 e contradiz as instruções vigentes em três pontos: diz código de conta
de 8 dígitos (as instruções mandam 10 desde 02/01/2025), saldo com mínimo zero (as
instruções mandam sinal pela natureza, que admite negativo) e no máximo 25 contas
(o conjunto atual tem 30). Nos três, **a instrução vigente prevalece** e é o que
este contrato segue. Validar contra o XSD publicado reprovaria um arquivo correto.

## Fonte primária

As Instruções de Preenchimento oficiais, citadas acima como "Instruções §":
<https://www.bcb.gov.br/content/estabilidadefinanceira/Documents/Leiaute_de_documentos/saldosDiariosInstrucoesPreenchimentoV2.pdf>

Em qualquer divergência entre este manual e a fonte primária, **a fonte primária
prevalece** — e a divergência é um defeito da curadoria, que deve ser reportado.
