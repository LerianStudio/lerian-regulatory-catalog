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

| Branch | Papel |
|---|---|
| `develop` | onde um documento é curado; é o que um Reporter de desenvolvimento acompanha, para o documento ser exercitado de ponta a ponta antes de virar tag |
| `main` | o que já passou por revisão e está pronto para virar tag |
| tags | o que o cliente fixa |

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

O Reporter não lê este repositório. Ele busca a release **mais recente** e baixa o
único `.tar.gz` anexado a ela — um pacote com o índice, os documentos publicados e
um manifesto com o SHA-256 de cada arquivo, que o próprio Reporter confere antes de
instalar. Nada aqui chega a um cliente até uma release existir.

A tag é a versão do **catálogo**, no formato `vX.Y.Z`, e é o que dispara a
publicação. Ela não tem relação com as versões dos documentos: `metadata.version`
em cada contrato é por documento, independente, e é o que o cliente fixa quando
assina. Uma release `v1.4.0` pode carregar o 4010 na 1.0.0 e o 4111 na 2.3.1 — a
versão da release diz quando o conjunto foi publicado, nunca o que cada documento é.

Como cortar:

1. Confira localmente: `python3 tools/validate.py`.
2. `git tag -s v1.0.0 -m "catálogo 1.0.0"` e `git push origin v1.0.0`.
3. O CI valida, monta o pacote, confere que ele é reproduzível, o relê como o
   Reporter releria e publica a release. Nada disso acontece sem a tag.

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
por acidente de ordenação. O `SHA256SUMS` que acompanha é para conferência humana e
não termina em `.tar.gz` de propósito — qualquer anexo novo precisa respeitar isso.

Uma release marcada como *pre-release* ou *draft* é invisível para o Reporter, que
pede `releases/latest`. Publicar uma não corrige um catálogo quebrado, e também não
quebra um que esteja no ar.

O pacote é **reproduzível**: a mesma árvore produz os mesmos bytes, sempre. É o que
permite a alguém remontar a release e comparar com o que publicamos. O CI confere
isso a cada execução, montando duas vezes.

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
