# Lerian Regulatory Catalog

Contratos e templates curados pela Lerian para geração de arquivos regulatórios.

Consumido pelo **Reporter**, que baixa deste repositório os documentos que o
cliente ativou. O cliente não escreve nem edita nada aqui — ele preenche apenas o
**binding**, que fica na instalação dele.

## As três peças

O que torna um documento reaproveitável entre clientes é a separação entre três
coisas que costumam vir fundidas num template só:

| Peça | Responde | Quem escreve | Onde vive |
|---|---|---|---|
| **Contrato** | *o que* o documento precisa — conjuntos de dados, grão, agregação, campos, tipos, domínios, formatos, regras | Lerian | este repositório |
| **Template** | *onde* cada campo aparece — a sintaxe do arquivo e a posição dos campos | Lerian | este repositório |
| **Binding** | *de onde* o dado vem — base, tabela, coluna; ou valor fixo, parâmetro, edição manual, CNPJ da instituição que entrega | cliente | instalação do cliente |

A divisão não é estética. As três mudam por motivos diferentes e em ritmos
diferentes: contrato e template mudam quando o regulador revisa o leiaute; binding
muda quando o cliente troca de base. Fundidas num arquivo só — que é como a
maioria das implementações começa — uma revisão do regulador obriga a tocar no
arquivo de todos os clientes, e o custo de acompanhar a regulação passa a crescer
com o número de clientes.

## Estrutura

```
<país>/<regulador>/<documento>/
├── contract.yaml          o contrato (a definição dos dados)
├── template.tpl           a forma de saída
├── binding.example.yaml   exemplo preenchido, para orientar o cliente
└── schema/                material de curadoria (ver abaixo)
```

Exemplo: `br/bcb/cadoc-4010/`.

## Sobre os arquivos em `schema/`

São os XSDs publicados pelo regulador. Estão aqui como **fonte para escrever e
revisar o contrato**, não como algo que o Reporter executa.

Isso é deliberado. O XSD descreve forma, não significado: ele diz que um saldo é
decimal, mas não que o sinal precisa seguir a natureza da conta. E às vezes nem a
forma ele fecha — no 4010 as duas casas decimais estão declaradas como *máximo*,
então um saldo escrito como `0` passa na validação de schema e está errado no
arquivo. Ou seja, uma camada de regras acima do XSD sempre seria necessária. O
contrato é essa camada, e o XSD é a referência contra a qual ele é conferido por
gente, na curadoria.

Uma etapa automática de validação contra o regulador pode vir depois. Ela não é
pré-requisito para gerar.

## O que este repositório NÃO publica

Tabela sobre o plano de contas do cliente. O que é do cliente vai no binding, do
lado dele; o validador recusa uma tabela de natureza que nenhum contrato declara.

Tabelas do REGULADOR são outra coisa e cabem aqui, porque são parte do que o
documento é. A **natureza das rubricas COSIF** é uma delas: o elenco de contas do
BACEN diz quais são retificadoras, então ela é publicada ao lado de cada contrato
(`natureza.yaml`), gerada do PDF do elenco em `br/bcb/cosif/` por
`tools/natureza.py` — nunca escrita à mão. O validador confere que cada cópia traz
o sha256 do elenco publicado e que todas são iguais.

**Garantia sobre razões que não sejam o Midaz.** Os bindings de exemplo são
escritos contra o Midaz, e é contra o Midaz que a geração é homologada. Eles são
exemplos justamente porque o binding é do cliente: apontá-los para outro razão é
decisão dele, e a correção do arquivo passa a depender de um ecossistema que não
conhecemos.

Isso não é formalidade. O motor lê as colunas que o binding nomeia, exatamente
como elas são — ele não tem como saber que a coluna de valor de outro razão
carrega o sinal do lançamento em vez da magnitude, e a soma que aqui dá o volume
do mês lá daria o saldo líquido. O arquivo sai bem formado nos dois casos. Os
exemplos declaram no cabeçalho o que assumem do razão; conferir isso contra a base
de origem é parte de mapear.

## Curadoria

O contrato é escrito a partir do manual do leiaute e do XSD publicados pelo
regulador. **O Reporter confia no contrato**: não há conferência contra o XSD em
tempo de execução, então um erro aqui gera arquivo errado com confiança.

A consequência é que o controle de qualidade não é um validador — é a revisão.
Mudança de contrato exige revisor com conhecimento do documento. Ver
[CONTRIBUTING.md](CONTRIBUTING.md).

## Versões

Cada contrato declara sua versão em `metadata.version`, e a instalação do cliente
fixa a versão que adotou — uma correção publicada aqui não muda o que ele gera até
ele adotar.

Publicar é cortar uma tag `vX.Y.Z`, que versiona o **catálogo** e não os documentos:
o CI monta um pacote com tudo e o anexa a uma release, que é o que o Reporter busca.
Ver [CONTRIBUTING.md](CONTRIBUTING.md).

Não há diretório por versão: duplicar a árvore inteira a cada revisão torna o
histórico ilegível, e é exatamente o que o git já resolve.
