# e-Financeira — Abertura (evtAberturaeFinanceira)

Evento de Abertura da e-Financeira, leiaute v1.5.0 (ADE Cofis 10/2026), em produção desde
01/09/2026.

**Versão mínima do Reporter:** a que traz os períodos de parâmetro (`span`, `within`,
`notBefore`) e as linhas escritas à mão no mapeamento (`rows`). Um Reporter anterior
recusa este contrato ao assinar o documento.

## O que é

A abertura da e-Financeira de um **semestre**: diz à Receita que a instituição vai
enviar a movimentação de operações financeiras daquele semestre e quem responde por ela:

- o **responsável pelas RMF** — a entidade (a declarante ou uma filial) e a pessoa que
  atendem as Requisições de Movimentação Financeira da Receita, com telefone e o
  endereço para onde elas são enviadas;
- os **responsáveis pela e-Financeira** — uma ou mais pessoas que atendem os pedidos
  de esclarecimento sobre o preenchimento, com telefone, endereço e e-mail;
- o **representante legal** da instituição perante a Receita (opcional).

O arquivo leva sempre o grupo de operações financeiras (`AberturaMovOpFin`). O grupo de
Previdência Privada (`AberturaPP`) não sai: é só para instituições habilitadas na
Previdência Privada, o que IP, SCD e SCFI não são.

A Receita só aceita a abertura de uma instituição com o **cadastro do declarante**
(`evtCadDeclarante`) ativo: envie-o antes, por este catálogo
(`br.rfb.efinanceira-cad-declarante`) ou por outra ferramenta.

## O semestre

A geração pede o parâmetro `semestre`, pelo **último mês** dele:

| Valor | Semestre | `dtInicio` e `dtFim` no arquivo |
|---|---|---|
| `2026-06` | janeiro a junho de 2026 | `2026-01-01` e `2026-06-30` |
| `2026-12` | julho a dezembro de 2026 | `2026-07-01` e `2026-12-31` |

Outro mês é recusado na hora. Cada semestre é uma entrega: uma abertura original e,
depois, retificações.

### Abertura ou encerramento no meio do semestre

A Receita aceita um período menor que o semestre só quando a instituição **foi aberta
ou encerrada dentro dele**: aí o arquivo leva a data de abertura no lugar do primeiro
dia, ou a de encerramento no lugar do último. Informe-as nos parâmetros opcionais:

- `dtInicio` — a data de abertura da instituição (`AAAA-MM-DD`);
- `dtFim` — a data de encerramento.

Cada uma tem de cair **dentro do semestre**, e o encerramento não pode vir antes da
abertura (o mesmo dia é aceito). Fora disso, a geração é recusada na hora
(`400 RPT-0140`), dizendo o parâmetro e as datas do semestre. Deixe-as em branco no caso
comum: o arquivo leva as datas do semestre. Que a instituição de fato abriu ou encerrou
naquelas datas, só a Receita confere.

## Original e retificação

| `indRetificacao` | Quando |
|---|---|
| `1` | O original: a primeira abertura do semestre. |
| `2` | Retificação espontânea: a abertura do semestre mudou (um contato, uma data). |

O XSD da abertura não aceita o `3` (retificação a pedido), embora o Anexo II o liste:
vale o XSD, que é o que recusa o arquivo.

Numa retificação, informe também `nrRecibo`: o recibo de entrega do **último** evento
aceito daquela abertura. A Receita devolve o recibo a quem transmitiu o arquivo; o
Reporter não o vê, então você o digita ao gerar. O formato é conferido na hora
(`999999999999999999-99-999-9999-999999999999999999`, de 15 a 49 posições).

Um original aprovado impede outro original **do mesmo semestre** (`409 RPT-0197`), mesmo
com outras datas: a Receita aceita uma abertura original ativa por semestre (MS1034).
Uma retificação que informa o recibo não precisa de um original aprovado no Reporter: o
original pode ter sido enviado por outra ferramenta.

Na retificação, a Receita só aceita mudar a data inicial dentro do mesmo semestre e se
não houver movimentação já enviada fora do novo período (MS1194, MS1198), e não aceita
uma data final que deixe de fora eventos já enviados (MS1011). O Reporter prende as
datas ao semestre; o resto, só a Receita sabe. E o Anexo II não fecha a questão: a
chave do evento inclui as datas (A II p.18), a retificação tem de trazer a mesma chave do
evento retificado (MS1006), e a REGRA_ALTERA_DTINI admite mudar a data inicial. O que a
Receita faz com uma retificação que muda uma data não foi conferido.

Cada geração tira um **id de evento novo** (`ID` + 18 dígitos, ordenado pelo instante da
geração): uma retificação é um evento novo, ligado ao anterior pelo recibo, nunca pelo id.

## Abertura excluída: marque o relatório antes de abrir de novo

Uma abertura enviada por engano, ainda sem fechamento, é excluída pela **Exclusão da
e-Financeira** (`br.rfb.efinanceira-exclusao-efinanceira`), com o recibo dela — e com ela
saem todos os eventos de movimento enviados depois. Uma abertura excluída não se
retifica: o recibo dela não está mais ativo, e a Receita recusa a retificação. O
semestre é aberto de novo **como original**.

A Exclusão da e-Financeira só vale **enquanto o fechamento do semestre não foi enviado**
(A II p.60-61). Com um fechamento ativo, exclua antes o fechamento pela **Exclusão de
Evento** (`br.rfb.efinanceira-exclusao`) e marque-o como "excluído na Receita" (ver o
manual do fechamento); só então exclua a abertura.

O Reporter não fica sabendo da exclusão. Depois que ela for transmitida e **aceita** pela
Receita, marque no Reporter como **"excluída na Receita"** o relatório Final da abertura
excluída **e cada retificação aprovada** dela. Só então gere a nova abertura original
do semestre: sem a marca, ela é recusada (`409 RPT-0197`), e com uma retificação
aprovada sem marca, também (`409 RPT-0203`). A marcação só existe a partir da versão do
Reporter que a traz.

## O arquivo sai sem assinatura

O XSD oficial exige a assinatura digital (`ds:Signature`) dentro de `<eFinanceira>`. O
Reporter gera o evento **sem** ela. Assinar com o e-CNPJ ICP-Brasil do declarante
(XMLDSig), montar o lote, cifrá-lo e transmiti-lo à Receita são da etapa que envia o
arquivo — cada regulador pede o seu certificado, e o Reporter não o guarda.

Por isso o arquivo baixado do Reporter não valida contra o XSD oficial tal como está; a
pasta `schema/` explica como validar antes e depois da assinatura.

## De onde vem cada valor

O mapeamento de referência lê da organização do Midaz só o CNPJ. Todo o resto o Midaz
não guarda: você preenche **uma vez** no mapeamento, e vale para todos os semestres.

| No arquivo | De onde vem |
|---|---|
| `id` | Gerado pelo motor a cada geração. |
| `indRetificacao`, `nrRecibo` | Parâmetros da geração. |
| `tpAmb` | Você preenche: `1` produção, `2` produção restrita (testes). |
| `aplicEmi`, `verAplic` | Constantes: `1` (aplicativo da empresa) e `Lerian Reporter`. |
| `cnpjDeclarante` | `organization.legal_document`, conferido contra o cadastro da instituição. |
| `dtInicio`, `dtFim` | O primeiro e o último dia do `semestre`, ou os parâmetros `dtInicio` e `dtFim` quando informados. |
| `ResponsavelRMF` | Você preenche os campos de `responsavelRMF`: `cnpj`, `cpf`, `nome`, `setor`, `ddd`, `telefone`, `ramal` (opcional), `logradouro`, `numero`, `complemento` (opcional), `bairro`, `cep`, `municipio` (o **nome**) e `uf`. |
| `RespeFin` (1 ou mais) | Você escreve as linhas de `respeFin`, uma por pessoa: os mesmos campos, sem o `cnpj`, mais o `email`. |
| `RepresLegal` (opcional) | Você preenche, se quiser informar: `cpf`, `setor`, `ddd`, `telefone` e `ramal` (opcional) de `represLegal`. |

### Os responsáveis pela e-Financeira

São linhas escritas no mapeamento, uma por pessoa, no lugar de `rows: []` — e o
`pendingReason` do conjunto sai quando há linhas:

```yaml
  respeFin:
    rows:
      - {cpf: "52998224725", nome: "Ana Souza", setor: "Compliance", ddd: "11",
         telefone: "33334444", ramal: "210", logradouro: "Av. Paulista", numero: "1000",
         complemento: "cj 101", bairro: "Bela Vista", cep: "01310100",
         municipio: "São Paulo", uf: SP, email: "ana@exemplo.com.br"}
      - {cpf: "16899535009", nome: "Bruno Lima", setor: "Tecnologia", ddd: "11",
         telefone: "33335555", logradouro: "Av. Paulista", numero: "1000",
         bairro: "Bela Vista", cep: "01310100", municipio: "São Paulo", uf: SP,
         email: "bruno@exemplo.com.br"}
```

Cada linha é conferida contra o contrato quando o mapeamento é salvo: os campos
obrigatórios, o formato de cada valor e o CPF, que não se repete. As linhas saem no
arquivo na ordem em que foram escritas. Enquanto não há nenhuma, o conjunto é uma
pendência obrigatória: o rascunho sai sem `RespeFin` e não pode ser aprovado nem baixado.
Escrever as linhas fecha a pendência na **próxima geração** — uma correção do rascunho
não a fecha.

### O representante legal

É opcional no XSD (o Anexo II o diz obrigatório; vale o XSD). Quando vem, vem inteiro:
CPF, setor, DDD e número. O arquivo leva o grupo quando qualquer campo dele está
preenchido; um grupo pela metade é recusado pelo XSD, então preencha os quatro ou nenhum.

### Telefones, CEP e município

Telefone, ramal, DDD, CEP e CPF saem só com os algarismos. DDD e número são campos
separados: `(11)` no DDD vira `11`; `3333-4444` no telefone vira `33334444`. Não ponha o
DDD no `telefone`. O município do responsável pela RMF e dos responsáveis pela
e-Financeira é o **nome** da cidade, em texto livre — não o código da tabela de
Municípios que o cadastro do declarante pede. A UF é a sigla, uma das 27 UFs (a tabela
traz também `EX`, exterior, que o contrato não aceita).

O endereço do responsável pela RMF é para onde a Receita envia as requisições: tem de ser
o do **Cadastro CNPJ** do CNPJ informado no grupo. O Reporter não consulta o Cadastro CNPJ.

Enquanto um campo obrigatório que você preenche estiver pendente, o rascunho sai com a
pendência e não pode ser aprovado nem baixado.

## O que o Reporter confere

- O `semestre` em junho ou dezembro; `dtInicio` e `dtFim` dentro dele, o fim não antes do
  início — ao gerar.
- O formato do recibo, exigido na retificação e recusado no original; original único por
  semestre.
- O CNPJ da declarante e o do responsável pela RMF: 14 posições, letras e dígitos; o da
  declarante, o da instituição da entrega.
- Tamanho e formato de cada campo pelo XSD; CPF com 11 algarismos; a UF pela tabela de UF
  da Receita (MS2013); aspas (`"`), apóstrofo (`'`) e cerquilha (`#`), que a Receita
  proíbe no conteúdo, recusados.
- Ao menos um responsável pela e-Financeira, sem CPF repetido.

## O que o Reporter não confere

- **Cadastro do declarante ativo** (MS1007): envie o `evtCadDeclarante` antes.
- **Original enviada por outra ferramenta** no mesmo semestre (MS1034): só a Receita vê.
- **Abertura ou encerramento de fato no meio do semestre** (MS1008): o Reporter confere
  só que as datas caem no semestre.
- **Data de implantação do sistema** (MS1020): o Anexo II não diz qual é.
- **Retificação que muda as datas** (MS1194, MS1198, MS1011, MS1006): depende do que já
  foi enviado, e o Anexo II não diz se a chave pode mudar.
- **Recibo do último evento** (MS1004, MS1006): só o formato é conferido.
- **Dígitos verificadores do CNPJ e do CPF** (MS1002, MS1057): o Reporter confere só o
  formato (14 posições no CNPJ, 11 no CPF) e confia na origem do dado, o Midaz ou quem
  digita o valor no mapeamento ou corrige o rascunho; quem preenche responde por ele, e a
  Receita recusa um dígito errado.
- **Endereço da RMF igual ao do Cadastro CNPJ**: o endereço vem do mapeamento.
- **Representante legal inteiro**: um grupo pela metade passa daqui e é recusado pelo XSD.
- **Ambiente de destino**: um `tpAmb` `2` enviado à produção é recusado (MS1163).
- **Id único na base nacional** (MS1001): o Reporter não repete um id entre as gerações
  dele; um id já enviado por outra ferramenta, só a Receita vê.
- **Hífen duplo** (`--`) num campo de texto: a Receita recusa (MS1124, "caracteres especiais restritos", do Manual de
  Orientação do Usuário da e-Financeira v1.2, §6.2).
- **Abertura excluída**: você marca os relatórios como "excluída na Receita" antes de
  abrir o semestre de novo.
- **Assinatura e transmissão**: da etapa que envia o arquivo.

## Fonte primária

- Anexo II do manual da e-Financeira — Leiautes Gerais, Abertura da e-Financeira v1.5.0
  (ADE Cofis 10/2026): `br/rfb/efinanceira-cad-declarante/schema/anexo-ii-leiautes-gerais-v1-5-0.pdf`,
  páginas 18 a 32.
- XSD oficial: `schema/evtAberturaeFinanceira-v1_5_0.xsd`.
- Tabela de UF da Receita: `br/rfb/e-financeira/tabelas/uf.txt`.
