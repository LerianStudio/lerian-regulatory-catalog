# Cadoc 4016 — Balanço Patrimonial Analítico

> Documento de leitura. Explica o que este regulatório é e o que a Lerian assume
> ao gerá-lo. **Não repete o contrato**: campos, formatos, padrões e periodicidade
> são declarados em `contract.yaml`, e é ele que vale. O que está aqui é o que
> nenhum arquivo consegue dizer.

## O que é

O balanço **semestral** da instituição ao Banco Central, com data-base em junho e
dezembro. O leiaute é o mesmo do 4010 (um documento só para os dois), e o arquivo
também: saldo de fechamento por rubrica COSIF, acumulado desde a abertura e
expresso na natureza de cada conta, com as contas-mãe derivadas da soma das filhas.
Tudo o que o manual do 4010 diz sobre saldo, natureza, retificadoras, contas-mãe,
último dia útil e precondições do cadastro no Midaz vale aqui sem mudança.

## O que o torna diferente do 4010

Uma coisa: **o balanço é a posição depois de apurado o resultado.** Por isso o
arquivo não admite as contas de resultado — grupos 7 (Receitas) e 8 (Despesas)
(leiaute p.6).

O binding de exemplo exclui essas rubricas na consulta, e o contrato confere no
arquivo pronto: uma rubrica que começa com 7 ou 8 recusa o documento, porque
indica que o filtro do binding não excluiu o resultado.

Rubrica com saldo zero **pode ser omitida** (leiaute p.6): emitir ou não é decisão
sua, e as duas formas são aceitas.

## A apuração do resultado precisa estar lançada

Excluir as contas de resultado do arquivo **não apura o resultado**. O lucro ou o
prejuízo do semestre só aparece no Patrimônio Líquido se o encerramento das contas
de resultado contra o PL estiver **lançado no razão** até a data-base, como o COSIF
manda fazer ao fim de cada semestre.

Sem esse lançamento, o arquivo sai bem formado e o balanço não fecha: o ativo
reflete o resultado do semestre e o PL não. Nada no arquivo aponta o erro, e o
motor **não confere** se ativo é igual a passivo mais PL.

No Midaz, o encerramento é uma transação como outra qualquer, com as rubricas de
resultado de um lado e a de lucros ou prejuízos acumulados do outro, configuradas
nas rotas. Lançá-la é parte do fechamento do semestre do cliente, e conferir o
rascunho — o PL inclui o resultado? o balanço fecha? — é parte de aprovar.

## Precondições do cadastro no Midaz

As mesmas do 4010 (veja o manual dele), mais a apuração acima. Em resumo: rotas
obrigatórias com rubrica COSIF de dez dígitos em toda ação; reserva que se anula
pela própria rubrica; Reporter no fuso de Brasília; a instituição é a organização
do Midaz, com o CNPJ verificável no cadastro dela e igual ao da instituição
cadastrada no Reporter; só reais, só o que moveu saldo
e só o que não foi apagado.

## Limitações conhecidas desta versão

- **O fechamento do balanço não é conferido** (ativo = passivo + PL). É o que a
  pessoa que revisa o rascunho confere antes de aprovar.
- **Existência da rubrica não é conferida.** O contrato confere a forma do código,
  não que a rubrica exista no elenco COSIF vigente.
- **Ordem de remessa.** O BCB só recepciona a data-base N depois de aceita a N-1;
  o Reporter não faz o envio, e um arquivo gerado fora de ordem é válido.
- **O calendário cobre 2025 a 2027.** Uma data-base fora disso é recusada até a
  cobertura ser estendida, o que é parte da curadoria anual.

## Fonte primária

O leiaute dos documentos 4010 e 4016, citado acima como "leiaute":
<https://www.bcb.gov.br/content/estabilidadefinanceira/cosif_leiautes/Leiaute_4010_xmlV0.pdf>

Em qualquer divergência entre este manual e a fonte primária, **a fonte primária
prevalece** — e a divergência é um defeito da curadoria, que deve ser reportado.
