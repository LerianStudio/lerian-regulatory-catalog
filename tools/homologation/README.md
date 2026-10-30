# Homologação contra o Midaz

Prova que os documentos do catálogo geram o arquivo certo a partir de um razão
**Midaz de verdade**, e não de linhas escritas à mão num banco de teste.

Três peças, e a separação entre elas é o que dá valor ao resultado:

| Peça | O que é |
|---|---|
| `scenario/*.json` | Uma contabilidade fictícia: organização, plano de contas COSIF (cada rubrica é uma conta do Midaz com a natureza dela), rotas contábeis e lançamentos datados |
| `expected/*.json` | O gabarito de cada documento, **escrito à mão** a partir dos lançamentos. Nunca calculado pelo script nem pelo Reporter, senão a conferência compararia o motor com ele mesmo |
| `homologate.py` | Monta o cenário **só pela API do Midaz**, confere o razão, gera no Reporter e compara cada arquivo com o gabarito |

## Os cenários

| Cenário | Perfil | O que cobre |
|---|---|---|
| `a-pagare-ip` | IP emissora pré-paga e credenciadora | conta pré-paga, recursos de clientes, controle de compensação, liquidação, fluxos do emissor e do credenciador; **hold → commit, hold → cancel e estorno** |
| `b-crediflex-scfi` | Sociedade de crédito, financiamento e investimento | aceite cambial, saldo credor em conta de empréstimo, obrigação zerada no mês, estorno, e uma **retificadora** real do elenco — (-) Perda Esperada sobre Empréstimos, credora dentro do grupo 1 — sem natureza declarada no binding |
| `d-calendario` | **Sintético, declarado como tal** | fevereiro de 2026 termina num sábado: balancete fechado no último dia útil, volume de sábado e domingo no primeiro dia útil de março, e o 4111 de sábado recusado |
| `c-cobertura` | **Sintético, declarado como tal** | toda linha do 4111 que A e B não alcançam; lançamento na linha-mãe e em subcontas do cliente (soma da árvore); fluxo de agosto fora da janela; corte diário (dia 15 x dia 30); lançamento depois da data-base; grupo 2 e uma retificadora do PL ((-) Capital a Realizar, devedora) |
| `e-cheque-especial` | **Sintético, declarado como tal** | cheque especial no saldo de uma conta de depósito: o débito acima do saldo fica só com a parte coberta na rubrica do depósito (que vai a zero, nunca negativo) e o excedente vira uma operação companheira (`OVERDRAFT`) na rubrica de Adiantamentos a Depositantes que a rota declara; um crédito quita primeiro o adiantamento; um débito com saldo zero sai com a perna original de valor 0 |
| `f-bloqueio` | **Sintético, declarado como tal** | bloqueio judicial como a transação BLOCK do Midaz: o valor vai do saldo `default` para um saldo `bloqueio` da mesma conta, sob a mesma rubrica, e o depósito continua inteiro no 4010 e no 4111 (o bloqueio limita o que se gasta, não o que se deve); o desbloqueio (UNBLOCK) devolve parte |
| `g-livros-multiplos` | **Sintético, declarado como tal** | a instituição é a organização: dois ledgers (Contas e Tesouraria) lidos juntos pelo escopo só de organização, e lançamentos CROSS-LEDGER entre eles pela API v2 — cada parte fechada contra a `@external/BRL` do ledger com a rubrica da rota-ponte, que zera na soma dos livros. A v2 não retrodata: o 4111 do dia e o 4010 do mês dos lançamentos ficam como recusa esperada até o período fechar |
| `h-cnpj-alfanumerico` | **Sintético, declarado como tal** | organização com CNPJ no formato alfanumérico da Receita (`LR4ZAB12000138`): o Midaz o aceita no `legalDocument`, o Reporter o normaliza e confere os dígitos verificadores, e a raiz do cabeçalho sai com letras (`cnpj="LR4ZAB12"`) no 4010 e no 4111 |

Juntos tocam as 30 linhas do conjunto do 4111 e os nove grupos do 4010. A
contabilidade é fictícia: as rubricas fora do conjunto do 4111 têm nome plausível
do COSIF e dígito verificador **calculado** (DV = soma de dígito × peso 9,3,7,9,3,7,9,3,7,
mod 10 — reproduz as 30 rubricas oficiais), e um contador deve conferir os nomes.

## Rodar

Precisa de um Midaz (o sandbox, por padrão) e de um Reporter com a fonte
`midaz_transaction` apontando para o banco desse Midaz. Só biblioteca padrão,
Python 3.9+, e `xmllint` para a validação contra o XSD.

```bash
S=tools/homologation/scenario/a-pagare-ip.json

# 1. Monta o cenário no Midaz (idempotente: roda de novo sem duplicar) e confere o razão
python3 tools/homologation/homologate.py setup  $S

# 2. Gera os documentos no Reporter com os bindings DESTE checkout e compara com o gabarito
python3 tools/homologation/homologate.py reports $S --bindings .
```

`MIDAZ_URL` (padrão `https://ledger.sandbox.lerian.net`) e `REPORTER_URL` (padrão
`http://localhost:4005`) mudam os alvos. Sem `--bindings`, gera com o binding que a
assinatura já tem. Com `--bindings <raiz de um catálogo>`, aplica o
`binding.example.yaml` daquele checkout antes de gerar — é como se homologa uma
branch do catálogo **antes** de cortar a release.

O comando `reports` sai com código 1 se algum arquivo divergir. Cada arquivo é
julgado por: XML bem formado com a declaração no primeiro byte; o XSD oficial que
o catálogo guarda (o do 4111 é o vigente desde 02/01/2025); toda rubrica com dez
dígitos e DV válido;
nada dos grupos 7 e 8 no 4016; e cada linha contra o gabarito.

Três desfechos não geram arquivo, e o gabarito diz qual espera:

- `"refused": true` — recusa na hora (400, `RPT-0140`), como o 4111 de um sábado.
- **Período ainda aberto** — os contratos declaram `closed: true`, então uma
  data-base cujo mês (ou dia) ainda não terminou no horário de Brasília é recusada
  dizendo `has not closed`. O script decide pela data de hoje: o 4016 de 2026-12 é
  uma recusa esperada até 31/12/2026 e, de 01/01/2027 em diante, é gerado e julgado
  contra o gabarito, sem mexer em nada.
- `"errored": true` — a geração é aceita e termina em `Error`: o balancete sem
  conta nenhuma (o contrato declara o conjunto `nonEmpty`). Só `Error` não basta,
  porque qualquer falha termina assim: `errorContains` lista o que a recusa tem de
  dizer (`RPT-0195`, `'cosif_balances' has no row`), conferido no log do worker —
  o Reporter grava no relatório só uma mensagem genérica. O container do worker
  vem de `REPORTER_WORKER_CONTAINER` (padrão `midaz-reporter-worker`); sem acesso
  ao log, o caso falha dizendo isso.

Uma assinatura presa a outra versão que a do checkout só é trocada depois de o
Reporter confirmar que carrega a versão do checkout (`GET
/v1/regulatory/documents`, a lista do catálogo, que responde com ou sem assinatura); se não carrega, nada é alterado. Se a assinatura
nova ainda assim vier em outra versão, ela é desfeita e a anterior reativada.

Uma conta pode declarar `overdraft` (`rubric`, `description`, `limit` opcional): o
`setup` liga o cheque especial no saldo `default` (`PATCH .../balances/{id}`, o
Midaz cria sozinho o saldo companheiro `overdraft`) e põe a entrada
`accountingEntries.overdraft` na rota da conta — sem ela, com `validateRoutes`, o
Midaz recusa o débito que precisa do cheque especial (0492).

Uma conta pode declarar `balances` (saldos além do `default`, ex.: `bloqueio`), e um
lançamento pode ter `kind` `block`/`unblock` (os endpoints `/transactions/block` e
`/unblock`) e `debitBalance`/`creditBalance` (a chave do saldo de cada perna). Sem
`accountingEntries.block`/`unblock` na rota, o Midaz usa a rubrica `direct`: o
bloqueio fica dentro da rubrica da conta. Se o cliente declarar outra rubrica para o
bloqueio, os documentos mostram a reclassificação que ele configurou.

Um cenário de vários livros declara `ledgers` (cada um com `accountTypes` e
`accounts`), `bridge` (a rubrica da rota-ponte), `transactions` com `ledger` (dentro
de um livro, v1, datadas) e `crossTransactions` (entre livros, v2, datadas quando
rodam). O `setup` liga `crossLedger` e `validateRoutes` em cada ledger e cria as
rotas no nível da organização; o `ledger` mostra cada livro e a instituição, e
confere que a ponte zera.

O Midaz grava as operações de uma transação de forma **assíncrona**: a leitura do
razão espera até todo lançamento que o `setup` registrou aparecer, e para dizendo
quais faltam depois de 30s.

## O que esta ferramenta já encontrou

- **O Midaz não grava status na operação.** Os bindings filtravam
  `status = APPROVED`, que não casava linha nenhuma: 4010 e 4016 saíam vazios (e o
  XSD recusa um arquivo sem contas), o 4111 era recusado. O e2e do Reporter não
  via porque o seed SQL dele escreve `APPROVED` na operação à mão.
- **A reserva se anula pela rubrica, não por status.** Com rotas validadas o hold
  grava um par débito/crédito na origem e nada no destino; o commit move uma vez;
  o cancel se anula. Por isso as rotas do cenário são bidirecionais com a mesma
  rubrica em todas as ações — e só a rota bidirecional aceita estorno.
- **O 4010 não trazia as contas-mãe.** O leiaute pede "todas as contas contábeis
  às quais a entidade deve prestar informação" e o exemplo do BCB lista sintéticas
  (`1000000009`, `1100000002`) ao lado das analíticas; as instruções do 4111 pedem
  que o último dia coincida com o 4010. A conferência cruzada falhava nos três
  cenários. Corrigido: o contrato do 4010/4016 declara a hierarquia e o
  motor deriva cada conta-mãe, somando em convenção contábil (a provisão abate
  Operações de Crédito). A conferência passa nos três.
- **O período era cortado pelo mês corrido, e não pelo dia útil.** O volume de um
  sábado que fecha o mês sumia de todo 4111, o balancete fechava no fim do mês em
  vez do último dia útil, e o 4111 de sábado era gerado. Corrigido com o calendário
  de dias não úteis (`dias-nao-uteis.yaml`, curadoria da Lerian) que o contrato
  declara; o cenário D prova os três cortes.
- **O Midaz lista só o recente por padrão.** Sem `start_date`/`end_date`, a listagem
  de operações devolve vazio para lançamentos de meses atrás. A ferramenta passa o
  intervalo explícito; o Reporter lê o banco e não é afetado.
- **Fuso horário.** O Midaz guarda o instante em UTC e o dia regulatório é o dia
  civil brasileiro. Com `REPORT_TIMEZONE=UTC`, um Pix às 23:30 de sexta em Brasília
  caiu no sábado e sumiu do balancete de fevereiro (10.500 em vez de 10.505). Com
  `America/Sao_Paulo`, certo. Os cenários datam as reversões mensais em `-03:00`.
- **Anotações (NOTED).** O Midaz grava as operações de uma anotação com a rubrica
  da rota, valor ZERO e `balance_affected = false`. Não inflam saldo, mas fariam a
  rubrica aparecer como linha de 0,00. O binding de referência lê só
  `balance_affected = true` e só `asset_code = BRL` (o ledger é multiativo).
- **Mais de um ledger na organização.** A instituição é a organização: o escopo é
  só `organization_id` e todo ledger dela entra nos documentos. Um cenário que
  precisa ser lançado de novo vai para outra organização, nunca para um segundo
  ledger da mesma. O cross-ledger (cenário G) prova que a ponte zera na soma dos
  livros.
- **O XSD do 4111 aceita a raiz alfanumérica** (`[A-Za-z0-9]{8}`, XSD vigente desde
  02/01/2025): o cenário H gera o 4111 com `LR4ZAB12` e ele passa na validação.
- **Uma retificadora declarada só pelo grupo sai com o sinal trocado.** A
  natureza de cada rubrica é do elenco COSIF e é regra do contrato (a tabela
  `natureza`, aplicada pela regra `saldo-na-natureza` pelo prefixo mais longo). Os
  cenários usam só rubricas do elenco vigente: uma rubrica inventada dentro de um
  grupo existente receberia a natureza do grupo em silêncio, que é o erro que este
  achado descreve.

## Regras

- **Tudo pela API do Midaz, nunca no banco.** O Midaz mantém relações próprias
  (saldos, cache de rotas, conta externa) que um INSERT esqueceria — e foi um seed
  SQL que escondeu o primeiro achado acima.
- **O gabarito é escrito à mão.** Mudou um lançamento, refaça a conta e o gabarito.
- **Commit, cancel e estorno não são retrodatados** pelo Midaz: os casos de
  outubro rodam na data da execução e só entram nos documentos cuja data-base vem
  depois dela (o 4016 de dezembro).
