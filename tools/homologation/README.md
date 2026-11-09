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
| `i-efinanceira-cadastro` | **Sintético, declarado como tal** | o evtCadDeclarante da e-Financeira (`br.rfb.efinanceira-cad-declarante`): só uma organização, criada com o endereço, sem ledger nem lançamento; o original aprovado e baixado, uma retificação com recibo, as recusas do pedido (recibo na original, retificação sem recibo, recibo fora do formato, segunda original) e as duas regras do contrato que recusam a geração (município de outra UF, residências sem `BR`) |
| `j-efinanceira-completo` | **Sintético, declarado como tal** | o evtCadDeclarante com TODO opcional preenchido (GIIN, categoria, tpNome, tpEndereco), três tipos de entidade e duas residências, numa organização nova de CNPJ alfanumérico (`EF9J2K7A000114`) e `line1` com vírgula e pontos (`Av. Brasil, 1.500 sala 10.0`, escrito como veio); o original julgado e só então aprovado; uma retificação a pedido (3); uma retificação corrigida no rascunho (`municipio`) com o mesmo id antes e depois; e as recusas de pattern na geração (apóstrofo no nome, GIIN com a letra O, logradouro de 147), com o logradouro de 146 e a cidade de 40 gerando um `enderecoLivre` de 199 que o XSD aceita |
| `k-efinanceira-sem-original` | **Sintético, declarado como tal** | o declarante cujo original foi enviado por outra ferramenta: a primeira geração no Reporter é uma retificação com recibo, aceita sem original (`filing.remittance.reference`), julgada e aprovada; depois dela, um original é recusado com `409 RPT-0202` |

Os cenários A a H tocam juntos as 30 linhas do conjunto do 4111 e os nove grupos do 4010. A
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

O cenário I (e-Financeira) roda igual; o `setup` só cria a organização (ou põe nela
o endereço do cenário) e o `reports` precisa de `--bindings` ou de uma assinatura que
já exista (ver "e-Financeira" abaixo):

```bash
S=tools/homologation/scenario/i-efinanceira-cadastro.json
python3 tools/homologation/homologate.py setup   $S
python3 tools/homologation/homologate.py reports $S --bindings .
```

`MIDAZ_URL` (padrão `https://ledger.sandbox.lerian.net`) e `REPORTER_URL` (padrão
`http://localhost:4005`) mudam os alvos. Sem `--bindings`, gera com o binding que a
assinatura já tem. Com `--bindings <raiz de um catálogo>`, aplica o
`binding.example.yaml` daquele checkout antes de gerar — é como se homologa uma
branch do catálogo **antes** de cortar a release.

O comando `reports` sai com código 1 se algum arquivo divergir. Cada arquivo de
CADOC é julgado por: XML bem formado com a declaração no primeiro byte; o XSD oficial que
o catálogo guarda (o do 4111 é o vigente desde 02/01/2025); toda rubrica com dez
dígitos e DV válido;
nada dos grupos 7 e 8 no 4016; e cada linha contra o gabarito. O evento da
e-Financeira tem julgamento próprio (ver "e-Financeira" abaixo).

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
  ao log, o caso falha dizendo isso. Antes do log, o motivo é procurado no próprio
  relatório: uma recusa do motor (um código `RPT-`) fica no `metadata` dele
  (`error_code`, `error`) nas versões do Reporter que a gravam, e então o log não é
  preciso.

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

## e-Financeira: o evtCadDeclarante (cenário I)

O cadastro do declarante não tem período: não há `dataBase` nem `tipoRemessa`.
Toda geração para a mesma instituição é a mesma entrega (`filing.period: []`), e o
que a distingue são os parâmetros: `indRetificacao` (`1` original, `2`/`3`
retificação) e `nrRecibo` (só na retificação, no formato
`[0-9]{1,18}-[0-9]{2}-[0-9]{3}-[0-9]{4}-[0-9]{1,18}`). Cada entrada do gabarito traz
`documentId`, um `label` e os `parameters` da geração; os CADOCs seguem como estão.

**Só a organização.** Um cenário sem `ledger` (nem `ledgers`) é de organização:
o `setup` a cria pela API do Midaz COM o endereço (`address.line1`, `line2`,
`zipCode`, `city`, `state` com a sigla da UF, `country`) ou, se ela já existe com
outro endereço, o atualiza (`PATCH /v1/organizations/{id}`); `reports` e `ledger`
só conferem que o endereço é o do cenário. Não há arquivo de estado.

**Os campos que o cliente preenche.** O binding de referência deixa `manual`,
pendente, o que o Midaz não guarda (ambiente, CRS, FATCA, município, as listas de
tipos de entidade e de residências fiscais, e os opcionais GIIN, categoria, tipo de
nome e de endereço). Um rascunho com pendência obrigatória não é aprovado nem
baixado, então o cenário declara em `fills` o que o cliente preenche uma vez no
mapeamento: `"dataset.campo": "valor"` vira `value:` e `"dataset.campo": [...]`
vira `values: [...]` no `binding.example.yaml` (o de `--bindings`; sem ele, o que a
assinatura já tem), antes de ir para a assinatura. Só um campo `from: manual` é
preenchido — outro qualquer para a execução — e o `pendingReason` fica; o conjunto
`nifs` continua declarado vazio. Uma entrada do gabarito pode trazer os próprios
`fills`, por cima dos do cenário: é como se prova uma regra do contrato.

Um campo que o Midaz preenche (o nome, o endereço) não é `manual`, então `fills`
não o alcança. Uma entrada prova o pattern dele com `binding`: `{"dataset.campo":
{"from": "constant", "value": "..."}}` troca o mapeamento inteiro do campo (tudo o
que ele tinha sai, isto entra) só naquela entrada — sem registrar outra
organização no Midaz. A entrada seguinte volta ao binding do cenário.

**Os desfechos de cada entrada:**

- **gerado e julgado** — `elements` diz cada elemento do arquivo; com
  `"approve": true` o rascunho é baixado e julgado, e só é aprovado (o original) se
  o arquivo passar — uma original errada aprovada ficaria Final para sempre naquele
  CNPJ. Numa execução seguinte, o original aprovado antes é o que se
  julga (um segundo original seria recusado), achado pelo documento e pelo CNPJ da
  instituição em qualquer assinatura — o Reporter guarda um original por
  declarante. Um rascunho com pendência obrigatória falha dizendo qual. Uma
  retificação com `approve` (o cenário K) é gerada e aprovada de novo a cada
  execução: retificações se repetem.
- **corrigido** — `correct` numa entrada gerada (rascunho): depois de julgado, o
  rascunho recebe `correct.overrides` em `POST /v1/regulatory/reports/{id}/overrides`
  com `If-Match` na `draftVersion` lida, é baixado de novo e julgado contra
  `correct.elements`, também escrito à mão. A versão do rascunho tem de mudar, e o
  id do evento NÃO: a correção re-renderiza as mesmas linhas, e o `generatedIds`
  do relatório continua nomeando o id do arquivo. A geração seguinte tem id maior.
- **`refused`** — recusa na hora: `{"status": 400, "code": "RPT-0140",
  "detailContains": [...]}` para o recibo na original, a retificação sem recibo e o
  recibo fora do formato; `{"status": 409, "code": "RPT-0197"}` para a segunda
  original depois da aprovada; `{"status": 409, "code": "RPT-0202"}` para o
  original depois de uma retificação aprovada sem original no Reporter (cenário K).
- **`errored`** — as regras do contrato (`municipio-da-uf`,
  `residencia-no-brasil`) rodam no worker, quando os valores são escritos: o pedido
  é aceito e a geração termina em `Error` com `RPT-0138` e o id da regra
  (`errorContains`). Esses casos são retificações com recibo, porque o original já
  está aprovado e outro original seria recusado antes de chegar à regra. Um valor
  fora do `pattern` de um campo termina igual, com `RPT-0138` e `Field '<campo>'`
  (cenário J: nome com apóstrofo, GIIN com a letra O, logradouro de 147).

**O julgamento** do arquivo:

- XML bem formado, com a declaração `<?xml` no **primeiro byte**;
- válido contra o XSD oficial sem a assinatura: o arquivo sai do Reporter
  sem `ds:Signature` (assinar é da borda que transmite), e o XSD oficial a exige.
  A cada execução o script deriva, numa pasta temporária, uma cópia de
  `schema/evtCadDeclarante-v1_5_0.xsd` sem o `<xs:import>` do XMLDSig e sem o
  `<xs:element ref="ds:Signature"/>` — cada um tem de aparecer exatamente uma vez,
  senão a execução para. O arquivo do catálogo nunca muda, e a cópia não diverge
  dele. Precisa do `xmllint`; sem ele, o caso falha;
- cada elemento contra o gabarito pelo caminho debaixo de `evtCadDeclarante`, sem
  o namespace (`infoCadastro/paisResid/Pais`): texto para um elemento, `null` para
  ausente (o `nrRecibo` na original, o `NIF` que a referência declara vazio, os
  opcionais não preenchidos), uma lista para os elementos naquela ordem e
  `{"unordered": [...]}` em qualquer ordem. Um elemento do arquivo que o gabarito
  não nomeia é "a mais";
- o `id` pela forma (`ID` + 18 dígitos) e, ao longo da execução, crescente — nunca
  pelo valor, que o motor tira a cada geração. A retificação é um evento novo, com
  id maior que o do original.

O `enderecoLivre` é `line1/CEP/cidade/UF`: o `line2` não entra, e o CEP sai em oito
dígitos, sem o traço com que o cenário o grava.

**Autenticação.** O script não manda token. Com a autenticação do Reporter ligada,
a aprovação exige o token de uma **pessoa** (`RPT-0201` para um token de aplicação);
a homologação roda contra um Reporter sem autenticação.

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
