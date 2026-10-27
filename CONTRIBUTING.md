# Como contribuir com um documento

Este repositório carrega conhecimento regulatório, não código de produto. Um erro
aqui não quebra o build de ninguém — ele produz um arquivo regulatório errado, com
aparência de certo, entregue ao regulador. Por isso o processo é mais rígido do que
o tamanho dos arquivos sugere.

## Antes de abrir um PR

1. **Trabalhe a partir da fonte primária.** O manual do leiaute e o XSD publicados
   pelo regulador. Blog de fornecedor, apresentação de conferência e resposta de
   fórum não servem como fonte — já erramos assim antes, afirmando que o Cadoc 3040
   havia sido substituído pelo 3044 com base num artigo de terceiro; o manual do
   próprio BACEN diz que um não substitui nem complementa o outro.
2. **Registre a fonte** em `metadata.sourceOfTruth`, com URL.
3. **Escreva o contrato antes do template.** Se o template precisar de um campo que
   o contrato não declara, o contrato está incompleto — não adicione ao template.

## O que vai em cada arquivo

A regra que resolve a maioria das dúvidas: **se a decisão vale para o campo onde
quer que ele apareça, é contrato. Se vale só para aquela posição no arquivo, é
template.**

Formato, escala, sinal e domínio são propriedades do campo → contrato. Nunca
repita uma dessas no template: a mesma decisão em dois lugares pode divergir, e não
há árbitro para decidir qual vence.

Grão e agregação também são contrato. "Uma linha por rubrica, acumulada desde a
abertura até a data-base" é parte do que o documento *é*; deixar isso no template
esconde o cálculo num artefato de apresentação, onde não pode ser conferido nem
reaproveitado.

## A entrega e a remessa (`filing`)

O motor não sabe o que é data-base nem que, no BCB, `I` é inclusão e `S` é
substituição. Quem diz é o contrato, no bloco `filing`:

```yaml
filing:
  period: [dataBase]          # o que faz duas gerações serem a mesma entrega
  remittance:
    parameter: tipoRemessa    # o parâmetro que diz se é original ou substituição
    original: I
    replacement: S
```

Declarado, o motor aplica três regras: uma entrega **original** aprovada por período,
por assinatura; **substituição** só depois de aprovada a original do período; e a
geração mais nova do mesmo período e da mesma remessa substitui a anterior ainda não
aprovada. `period` é opcional (ausente: todo parâmetro menos o da remessa) e
`remittance` também (ausente: nenhuma regra de original e substituição). A
ferramenta de conferência recusa um parâmetro que o contrato não declara, a remessa
dentro do período e valores fora do `domain` do parâmetro.

## Consolidação (`consolidation`)

Os dados de uma mesma instituição podem estar em mais de uma base: mais de um ledger, um
core antigo e o novo durante uma migração, um ERP ao lado do razão. Por isso **todo
conjunto de várias linhas que não pende de outro declara a sua consolidação** — por qual
chave as linhas de mais de uma fonte são a mesma linha, e o que acontece com cada campo:

```yaml
consolidation:
  key: [cosifCode]            # a identidade da linha (a do conjunto, quando ele declara)
  whenKeyRepeats: combine     # combine (padrão) | refuse: a mesma chave em duas fontes é recusada
  columns: {saldo: sum}       # todo campo que não é chave nem derivado: sum | equal | first
```

A regra é do documento e só quem cura sabe qual é: num balancete o saldo da mesma rubrica
em duas bases **soma**; num documento por operação, a mesma operação em duas bases é
duplicidade e o certo é `refuse`; um dado cadastral repetido deve ser **igual** (`equal`)
ou vale o da primeira fonte (`first`). A ferramenta de conferência recusa um conjunto de
várias linhas sem `consolidation`, para que nenhum documento saia sem a possibilidade de
ler de outra base por esquecimento.

Consolidar é ler a **mesma instituição** de mais de uma base. Um documento entregue em
base individual não soma instituições diferentes; o documento de um conglomerado é outro
documento, com contrato próprio. O manual de cada documento diz isso ao cliente.

## Regras e severidade

Toda regra declara `severity`. Escolha pensando em quem recebe o resultado:

- `error` — impede a geração. Use quando entregar o arquivo é pior que não entregar.
- `warning` — gera e avisa. Use quando o arquivo é válido mas a remessa provavelmente
  será rejeitada por contexto (ordem de data-base, por exemplo).
- `info` — registra. Use para o que é opcional no leiaute e é decisão do cliente.

Errar para o lado de `error` trava a operação do cliente numa véspera de prazo.
Errar para o lado de `warning` entrega arquivo errado. Nenhum dos dois é o padrão
seguro — decida caso a caso e escreva o porquê na mensagem.

## Revisão

Um PR que toque `contract.yaml` precisa de revisor que conheça o documento. A
revisão confere o contrato contra a fonte primária, campo a campo — não contra a
versão anterior do contrato, que é como um erro se perpetua.

## Versionar

- Correção que não muda o que já era gerado corretamente: patch.
- Campo novo, domínio novo, regra nova: minor.
- Mudança que altera arquivos já gerados e aceitos: major, e explique na descrição
  da tag o que muda para quem já adotou.

## Branches

O consumo do catálogo é por **tag** (`br.bcb.cadoc-4010/v1.0.0`): é o que a
instalação do cliente fixa, e é o que faz uma correção publicada aqui não mudar o
que ele gera até ele adotar. As branches existem para o que acontece antes disso.

| Branch | Papel | Quem lê |
|---|---|---|
| `develop` | onde um documento é curado | o Reporter de desenvolvimento, pelo diretório montado (`REGULATORY_CATALOG_DIR`) |
| `release-candidate` | o que vai ser homologado em staging; dela saem as tags `vX.Y.Z-rc.N`, publicadas como **pré-release** | o Reporter de staging (`REGULATORY_CATALOG_CHANNEL=prerelease`) |
| `main` | o que passou pelo staging; dela saem as tags `vX.Y.Z`, publicadas como **release** | o Reporter de produção (`REGULATORY_CATALOG_CHANNEL=stable`, o padrão) |

O conteúdo anda `develop → release-candidate → main`, sempre por PR. É o mesmo
fluxo dos serviços que leem o catálogo: um documento chega ao staging como
candidata, é exercitado lá contra dados reais, e só então vira release que um
cliente de produção pode assinar.

Trabalho novo sai de `develop`, volta por **PR**, e a conferência do CI é
obrigatória. Sem isso o processo desta página é convenção de honra: os três
primeiros commits deste repositório foram empurrados direto na `main`, passando por
cima do CI que roda em pull request — e foi o que motivou escrever esta seção.

## A ferramenta de conferência

`tools/validate.py` roda em todo PR e é a rede que impede um contrato errado de
entrar. `tools/test_validate.py` é a suíte que prova que essa rede não tem buraco:
cada conferência tem uma MUTAÇÃO correspondente — um catálogo de fixtures válido
quebrado de propósito num ponto — que exige a reprovação com a mensagem daquela
conferência.

    python3 tools/test_validate.py      # prova as conferências
    python3 tools/validate.py           # confere o catálogo

**Ao acrescentar uma conferência, acrescente a mutação.** Sem ela a conferência pode
ficar frouxa sem ninguém notar, e foi o que aconteceu quatro vezes seguidas antes da
suíte existir: vocabulário novo (`rowSet`, `byRowClass`, `manualOverrides`) entrou no
validador sem a precondição que o torna significativo, duas vezes no caminho gêmeo
do que tinha acabado de ser corrigido.

Ao acrescentar uma construção ao formato, ela nasce com três coisas:

1. a **precondição** que a valida;
2. a conferência em **todos os caminhos** onde a construção pode aparecer (um `from`
   direto e o mesmo `from` dentro de `byRowClass` são dois caminhos);
3. a **forma do valor** conferida antes do uso — YAML malformado deve reprovar, nunca
   estourar a ferramenta.

## Publicar uma release

O Reporter não lê este repositório. Ele busca a release **mais recente do seu
canal** — a release estável em produção, a mais nova de qualquer tipo (candidatas
incluídas) em staging — e baixa o único `.tar.gz` anexado a ela — um pacote com o índice, os documentos publicados e
um manifesto com o SHA-256 de cada arquivo, que o próprio Reporter confere antes de
instalar. Nada aqui chega a um cliente até uma release existir.

A tag é a versão do **catálogo** e é o que dispara a publicação. Há dois formatos,
e cada um só pode ser cortado da sua branch (o CI recusa os dois de outro lugar):

| Tag | Branch | Publicada como |
|---|---|---|
| `vX.Y.Z-rc.N` | `release-candidate` | pré-release — o staging lê, a produção nunca |
| `vX.Y.Z` | `main` | release — a produção lê |
 Ela não tem relação com as versões dos documentos: `metadata.version`
em cada contrato é por documento, independente, e é o que o cliente fixa quando
assina. Uma release `v1.4.0` pode carregar o 4010 na 1.0.0 e o 4111 na 2.3.1 — a
versão da release diz quando o conjunto foi publicado, nunca o que cada documento é.

Como cortar:

1. Confira localmente: `python3 tools/validate.py`.
2. Para o staging: leve a `develop` para a `release-candidate` por PR e, nela,
   `git tag -s v1.0.0-rc.1 -m "catálogo 1.0.0-rc.1"` e `git push origin v1.0.0-rc.1`.
   Cada correção durante a homologação é uma nova candidata (`-rc.2`, `-rc.3`…).
3. Para a produção: leve a `release-candidate` homologada para a `main` por PR e,
   nela, `git tag -s v1.0.0 -m "catálogo 1.0.0"` e `git push origin v1.0.0`.
4. O CI valida, confere que a tag saiu da branch certa, monta o pacote, confere
   que ele é reproduzível, o relê como o Reporter releria e publica a release.
   Nada disso acontece sem a tag.

Para montar e conferir sem publicar — o que o CI faz em todo PR:

    python3 tools/release.py build --version 0.0.0-local --out /tmp/catalog.tar.gz
    python3 tools/release.py verify /tmp/catalog.tar.gz --version 0.0.0-local

### O que o pacote carrega

`catalog.yaml` e, de cada documento publicado no índice, tudo menos `schema/`. Os
XSDs e os manuais em PDF do regulador são fonte para ESCREVER e revisar o contrato,
não algo que o Reporter execute — hoje seriam 1,3 MB contra 30 KB de catálogo, e a
conta cresce a cada documento. Ficam no repositório, onde a curadoria os lê.

Um arquivo que o Reporter precise resolver em tempo de geração — a tabela de código
do regulador em `contas.yaml`, por exemplo — mora na raiz do documento, nunca em
`schema/`.

### Um pacote por release

Uma release publica **exatamente um** `.tar.gz`. O Reporter recusa uma que tenha
dois: de lá não há como dizer qual é o catálogo, e escolher um instalaria conteúdo
por acidente de ordenação. A assinatura (`.tar.gz.sig`), o `SHA256SUMS`, o `LICENSE`
e o `NOTICE` que acompanham não terminam em `.tar.gz` de propósito — qualquer anexo
novo precisa respeitar isso.

O que cada Reporter vê depende do seu canal. O de produção (`stable`) pede
`releases/latest`, que o GitHub responde sem *pre-releases* nem *drafts*: uma
candidata publicada não chega a ele. O de staging (`prerelease`) lê a release mais
nova que não seja *draft*, candidata ou não. Um *draft* não é lido por nenhum dos
dois.

O pacote é **reproduzível**: a mesma árvore produz os mesmos bytes, sempre. É o que
permite a alguém remontar a release e comparar com o que publicamos. O CI confere
isso a cada execução, montando duas vezes.

### A assinatura

Cada release publica, ao lado do pacote, `catalog-X.Y.Z.tar.gz.sig`: uma assinatura
Ed25519, em base64, sobre a mensagem `lerian-regulatory-catalog archive sha256:`
seguida do SHA-256 do pacote em hexadecimal. O Reporter confere a assinatura com as
chaves públicas que carrega no próprio código e **recusa** a release cuja assinatura
não confere. É ela que diz que a release foi publicada pela curadoria da Lerian:
o manifesto e o `SHA256SUMS` só dizem que o pacote chegou inteiro, e quem troca o
pacote troca os dois junto.

A mensagem é contrato com o Reporter (`pkg/reporter/catalog/signature.go`), como os
nomes dos arquivos abaixo: mudá-la aqui sem mudar lá faz toda release ser recusada.

**A chave.** A privada fica no segredo `CATALOG_SIGNING_KEY` do ambiente `release`
do repositório, em PEM (`openssl genpkey -algorithm ed25519`), e nunca sai dele. A
pública, em base64 dos 32 bytes (o job de publicação a imprime), vai para a lista
de chaves do Reporter. O ambiente `release` exige a aprovação de um administrador
antes de cada publicação.

**Trocar a chave** sem deixar ninguém sem catálogo: o Reporter passa a confiar nas
duas chaves, as releases passam a sair assinadas pela nova, e só numa versão
seguinte do Reporter a antiga sai da lista.

**Sem a chave configurada**, a release sai sem assinatura e o job avisa. Por
enquanto o Reporter ainda aceita uma release sem assinatura; quando ele passar a
exigir, publicar sem a chave deixará de ser possível.

### Os nomes dos arquivos são contrato com o Reporter

O Reporter lê exatamente `contract.yaml`, `template.tpl` e `binding.example.yaml`
dentro do diretório de cada documento. **Renomear um deles aqui é também uma mudança
no Reporter** — não é decisão de organização deste repositório.

Por isso o empacotamento nunca traduz um nome, e a publicação numa tag reprova se
algum documento do índice não carregar os três. Um documento publicado pela metade é
pior que um ausente: o cliente o assina e ele nunca gera. `tools/validate.py` apenas
AVISA sobre um `binding.example.yaml` faltando, porque durante a curadoria isso é
normal — publicar não é.

### A ferramenta de empacotamento

`tools/release.py` monta e confere; `tools/test_release.py` prova que a conferência
morde, corrompendo um pacote íntegro de sete maneiras e exigindo a recusa de cada
uma. Mesma disciplina do validador: conferência nova nasce com a mutação que a torna
significativa.
