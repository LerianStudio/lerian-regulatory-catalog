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

A consequência prática é a razão de o desenho ser assim: uma conta que o razão do
cliente nunca movimentou **continua no arquivo, valendo zero**. Se as linhas
viessem dos dados, ela simplesmente não apareceria — e a omissão de conta só é
permitida quando o saldo é zero, então o arquivo sairia curto e seria rejeitado na
recepção, sem nada explicando por quê.

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

A diferença não é de cálculo, é de **janela**: as duas somam a mesma coluna do
mesmo razão, mas uma abre na abertura do razão e a outra no primeiro dia do mês.
Por isso o binding de exemplo declara duas consultas sobre a mesma tabela — não é
redundância.

E é por isso que somar com sinal importa: entrou 100 e saiu 100 no mês significa
**200 de volume** e **zero de saldo**. Os dois números são legítimos; cada classe
de conta pede um.

## O que a Lerian assume do seu razão

A geração é **homologada contra o Midaz**. O binding é seu, e apontá-lo para outro
razão é possível — mas o motor lê as colunas que você nomeia exatamente como elas
são, e não tem como avisar que significam outra coisa. Duas suposições, em
particular, erram em silêncio e produzem um arquivo bem formado com o número
errado:

| Suposição | Se o seu razão não a cumpre |
|---|---|
| O valor do lançamento é uma **magnitude**, e o lado (débito/crédito) vive numa coluna própria | Somar o valor entrega o **saldo líquido** onde o documento pede o **volume**: 100 de entrada e 100 de saída dariam zero, não 200 |
| Há um **status** que separa o que moveu dinheiro do que apenas reservou | Lançamentos pendentes ou cancelados entram na conta, inflando o que é declarado |

Conferir isso contra a sua base de origem é parte de mapear o binding. O cabeçalho
do `binding.example.yaml` diz, linha a linha, o que o exemplo assume.

## Precondição de configuração

A **natureza contábil** de cada rubrica — devedora ou credora — é propriedade do
plano de contas do cliente, não deste catálogo. Publicar uma tabela nossa criaria
uma segunda fonte de verdade que ninguém reconcilia. Ela é declarada no binding,
do seu lado; no exemplo contra o Midaz vem do COSIF referenciado nas rotas
contábeis.

## Limitações conhecidas desta versão

**Acúmulo de fim de semana.** Volumes de sábado, domingo e feriado devem ser
acumulados no próximo dia útil (Instruções §4.2.2.b). O calendário de dias úteis
que desloca essa apuração não existe nesta versão: um arquivo gerado para um dia
útil está correto, e um gerado para sábado reporta o próprio sábado em vez de
somar no dia útil seguinte.

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
