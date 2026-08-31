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
