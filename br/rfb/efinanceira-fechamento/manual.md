# e-Financeira — Fechamento (evtFechamentoeFinanceira)

Evento de Fechamento da e-Financeira, leiaute v1.5.0 (ADE Cofis 10/2026), em produção
desde 01/09/2026.

**Versão mínima do Reporter:** a que traz os períodos de parâmetro (`span`, `within`,
`notBefore`). Um Reporter anterior recusa este contrato ao assinar o documento. A
marcação "excluído na Receita" (ver abaixo) também só existe a partir dessa versão.

## O que é

O fechamento da e-Financeira de um **semestre**: diz à Receita que a instituição terminou
de enviar a movimentação daquele semestre, se houve movimento de operações financeiras
e se ela tem, ou não, contas a reportar no CRS e no FATCA. O arquivo não leva totais,
só **indicadores**.

O arquivo leva sempre o grupo de operações financeiras (`FechamentoMovOpFin`). Não saem:

- o grupo de Previdência Privada (`FechamentoPP`) — IP, SCD e SCFI não são habilitadas
  na Previdência Privada;
- o fechamento da movimentação anual (`FechamentoMovOpFinAnual`) — o `evtMovOpFinAnual`
  não é usado;
- as entidades patrocinadas do FATCA (`EntPatDecExterior`) — pedem o cadastro de
  patrocinado (`evtCadPatrocinado`), que este catálogo não tem. Uma declarante
  patrocinadora no FATCA não fecha o semestre por este documento;
- o indicador de nada a declarar (`nadaADeclarar`) — o Anexo II se contradiz sobre
  quando ele é aceito (ver abaixo, "Nada a declarar não sai").

A Receita só aceita o fechamento com uma **abertura ativa com a mesma data inicial**
(MS1009): envie antes a abertura do semestre, com a mesma data inicial, por este catálogo
(`br.rfb.efinanceira-abertura`) ou por outra ferramenta.

## O semestre

Como na abertura, a geração pede o parâmetro `semestre`, pelo **último mês** dele:

| Valor | Semestre | `dtInicio` e `dtFim` no arquivo |
|---|---|---|
| `2026-06` | janeiro a junho de 2026 | `2026-01-01` e `2026-06-30` |
| `2026-12` | julho a dezembro de 2026 | `2026-07-01` e `2026-12-31` |

Outro mês é recusado na hora. Cada semestre é uma entrega: um fechamento original e,
depois, retificações.

### Abertura ou encerramento no meio do semestre

A Receita aceita um período menor que o semestre só quando a instituição **foi aberta
ou encerrada dentro dele**. Informe as datas nos parâmetros opcionais:

- `dtInicio` — a data de abertura da instituição (`AAAA-MM-DD`), a mesma que a abertura
  do semestre levou;
- `dtFim` — a data de encerramento: a da extinção, fusão, incorporação ou cisão total.

Cada uma tem de cair **dentro do semestre**, e o encerramento não pode vir antes da
abertura (o mesmo dia é aceito). Fora disso, a geração é recusada na hora
(`400 RPT-0140`), dizendo o parâmetro e as datas do semestre. Deixe-as em branco no caso
comum: o arquivo leva as datas do semestre.

**Encerramento no meio do semestre pede situação especial.** Com `dtFim` antes do último
dia do semestre, a Receita exige `sitEspecial` diferente de `0` (MS1045). O Reporter
ainda não confere essa combinação: escolha a situação especial ao informar `dtFim`.

## Os indicadores

São parâmetros da geração: você os escolhe a cada fechamento.

| Parâmetro | Elemento no arquivo | Valores | Quando |
|---|---|---|---|
| `sitEspecial` | `infoFechamento/sitEspecial` | `0` não se aplica (padrão), `1` extinção, `2` fusão, `3` incorporação/incorporada, `5` cisão total | Sempre sai. Diferente de `0` quando a instituição encerrou no semestre por uma dessas situações; então `dtFim` é a data dela. Não existe o `4`. |
| `fechamentoMovOpFin` | `FechamentoMovOpFin/FechamentoMovOpFin` | `0` sem movimento, `1` com movimento — **obrigatório** | `1` se algum evento de movimento de operações financeiras foi enviado no semestre (MS1228); `0` se nenhum foi (MS1227). |
| `contasAReportarCRS` | `FechamentoMovOpFin/ContasAReportarCRS` | `0`, ou em branco | Declarante do CRS (`inDeclaranteCRS` 1 no cadastro) que fez a diligência e não tem contas reportáveis no semestre. A Receita o exige nesse caso (MS1225). |
| `contasAReportarFATCA` | `FechamentoMovOpFin/ContasAReportarFATCA` | `0`, ou em branco | Declarante do FATCA (`inDeclaranteFATCA` 1) sem contas reportáveis para os EUA no semestre. Pede o GIIN e a categoria no cadastro do declarante (MS1181, MS1170). Não vale para entidades patrocinadas. |

O XSD diz o indicador `FechamentoMovOpFin` opcional, mas com a abertura de operações
financeiras a Receita exige um valor certo (0 ou 1). O Reporter o pede sempre, e sem
padrão: dizer se houve movimento é declarar o semestre.

### Nada a declarar não sai

O Anexo II prevê o indicador `nadaADeclarar` (`1`) para a instituição obrigada à
e-Financeira que não tem nada a enviar, mas as regras dele se contradizem: ele só é
aceito se a abertura do semestre não levou nenhuma modalidade (MS1237, A II p.47); só
que uma abertura sem modalidade é recusada (MS1069, p.29), o fechamento tem de trazer ao
menos uma modalidade (MS1118, p.45) e o grupo de operações financeiras é recusado quando
a abertura não o levou (MS1049, p.48). Nenhum fechamento cumpre as quatro regras, então
esta versão não oferece o indicador. Como a Receita se comporta de fato não foi
conferido. Um semestre sem movimento se fecha com `fechamentoMovOpFin` `0`.

### Limitação desta versão: os indicadores são declarados

Na Receita, os indicadores dependem do que foi **enviado** no semestre: os eventos de
movimento, as contas reportáveis, os patrocinados. O Reporter não vê o que foi
transmitido, então nesta versão você **declara** cada indicador, e o Reporter confere só
que o valor é um dos que o XSD aceita. Se ele bate com o semestre, só a Receita
confere — um `fechamentoMovOpFin` `0` num semestre com movimento enviado é recusado lá
(MS1228).

Uma versão futura vai derivar os indicadores das movimentações (`evtMovOpFin`) aprovadas
no próprio Reporter no semestre. Ela espera o documento de movimentação.

## Original e retificação

| `indRetificacao` | Quando |
|---|---|
| `1` | O original: o primeiro fechamento do semestre. |
| `2` | Retificação espontânea: o fechamento do semestre mudou (um indicador, uma data). |

O XSD do fechamento não aceita o `3` (retificação a pedido), embora a regra MS1119 do
Anexo II o cite: vale o XSD, que é o que recusa o arquivo.

Numa retificação, informe também `nrRecibo`: o recibo de entrega do **último** evento
aceito daquele fechamento. A Receita devolve o recibo a quem transmitiu o arquivo; o
Reporter não o vê, então você o digita ao gerar. O formato é conferido na hora
(`999999999999999999-99-999-9999-999999999999999999`, de 15 a 49 posições).

Um original aprovado impede outro original **do mesmo semestre** (`409 RPT-0197`), mesmo
com outras datas ou outros indicadores: a Receita aceita um fechamento original ativo
por semestre (MS1212), e para fechar de novo pede a retificação. Uma retificação que
informa o recibo não precisa de um original aprovado no Reporter: o original pode ter
sido enviado por outra ferramenta.

Mudar `dtInicio` ou `dtFim` numa retificação é incerto: a chave do evento inclui as
datas (A II p.33) e a retificação tem de trazer a mesma chave do evento retificado
(MS1006); o leiaute do fechamento não tem uma regra que admita mudar a data, como a
abertura tem. O que a Receita faz com isso não foi conferido.

Cada geração tira um **id de evento novo** (`ID` + 18 dígitos, ordenado pelo instante da
geração): uma retificação é um evento novo, ligado ao anterior pelo recibo, nunca pelo id.

## Fechamento excluído: marque o relatório antes de fechar de novo

Um fechamento enviado por engano é excluído pela **Exclusão de Evento**
(`br.rfb.efinanceira-exclusao`), com o recibo dele, se a Receita aceitar a exclusão. Um
fechamento excluído não se retifica: o recibo dele não está mais ativo, e a Receita
recusa a retificação. O semestre é fechado de novo **como original**.

O Reporter não fica sabendo da exclusão. Depois que ela for transmitida e **aceita** pela
Receita, marque no Reporter como **"excluído na Receita"** o relatório Final do
fechamento excluído **e cada retificação aprovada** dele. Só então gere o novo
fechamento original do semestre: sem a marca, ele é recusado (`409 RPT-0197`), e com uma
retificação aprovada sem marca, também (`409 RPT-0203`).

## O arquivo sai sem assinatura

O XSD oficial exige a assinatura digital (`ds:Signature`) dentro de `<eFinanceira>`. O
Reporter gera o evento **sem** ela. Assinar com o e-CNPJ ICP-Brasil do declarante
(XMLDSig), montar o lote, cifrá-lo e transmiti-lo à Receita são da etapa que envia o
arquivo — cada regulador pede o seu certificado, e o Reporter não o guarda.

Por isso o arquivo baixado do Reporter não valida contra o XSD oficial tal como está; a
pasta `schema/` explica como validar antes e depois da assinatura.

## De onde vem cada valor

O mapeamento de referência lê da organização do Midaz só o CNPJ; o ambiente de destino
você preenche **uma vez** no mapeamento. O resto são parâmetros da geração.

| No arquivo | De onde vem |
|---|---|
| `id` | Gerado pelo motor a cada geração. |
| `indRetificacao`, `nrRecibo` | Parâmetros da geração. |
| `tpAmb` | Você preenche: `1` produção, `2` produção restrita (testes). |
| `aplicEmi`, `verAplic` | Constantes: `1` (aplicativo da empresa) e `Lerian Reporter`. |
| `cnpjDeclarante` | `organization.legal_document`, conferido contra o cadastro da instituição. |
| `dtInicio`, `dtFim` | O primeiro e o último dia do `semestre`, ou os parâmetros `dtInicio` e `dtFim` quando informados. |
| `sitEspecial` | Parâmetro da geração (`0` quando não informado). |
| `FechamentoMovOpFin`, `ContasAReportarCRS`, `ContasAReportarFATCA` | Parâmetros da geração. |

Enquanto o `tpAmb` estiver pendente, o rascunho sai com a pendência e não pode ser
aprovado nem baixado.

## O que o Reporter confere

- O `semestre` em junho ou dezembro; `dtInicio` e `dtFim` dentro dele, o fim não antes do
  início — ao gerar.
- Cada indicador num dos valores do XSD, e o `fechamentoMovOpFin` sempre informado — ao
  gerar.
- O formato do recibo, exigido na retificação e recusado no original; original único por
  semestre.
- O CNPJ da declarante: 14 posições, letras e dígitos, o da instituição da entrega.
- A versão do aplicativo sem aspas (`"`), apóstrofo (`'`) e cerquilha (`#`), que a
  Receita proíbe no conteúdo.

## O que o Reporter não confere

- **Dígitos verificadores do CNPJ** (MS1002): o Reporter confia na origem do dado, o
  Midaz ou quem digita o valor; quem preenche responde por ele, e a Receita recusa um
  dígito errado.
- **Os indicadores contra o que foi enviado** (MS1227, MS1228, MS1225): declarados por
  você nesta versão.
- **Abertura ativa do semestre** (MS1009, MS1049): envie a abertura antes, com a mesma
  data inicial.
- **Original enviado por outra ferramenta** no mesmo semestre (MS1212): só a Receita vê.
- **Situação especial e data final** (MS1045): `dtFim` no meio do semestre pede
  `sitEspecial` diferente de `0`, e o Reporter ainda não cruza os dois parâmetros.
- **Abertura ou encerramento de fato no meio do semestre** (MS1008) e **data final que
  corta eventos enviados** (MS1011): o Reporter confere só que as datas caem no semestre.
- **GIIN e categoria no cadastro do declarante** com `contasAReportarFATCA` (MS1181,
  MS1170).
- **Entidades patrocinadas** (MS1189, MS1195, MS1229, MS1131): o grupo não sai.
- **Retificação que muda as datas** (MS1006): o Anexo II não diz se a chave pode mudar.
- **Recibo do último evento** (MS1004, MS1006): só o formato é conferido.
- **Ambiente de destino**: um `tpAmb` `2` enviado à produção é recusado (MS1163).
- **Id único na base nacional** (MS1001): o Reporter não repete um id entre as gerações
  dele; um id já enviado por outra ferramenta, só a Receita vê.
- **Hífen duplo** (`--`) na versão do aplicativo: a Receita recusa (MS1124, "caracteres especiais restritos", do Manual de
  Orientação do Usuário da e-Financeira v1.2, §6.2).
- **Fechamento excluído**: você marca os relatórios como "excluído na Receita" antes de
  fechar o semestre de novo.
- **Assinatura e transmissão**: da etapa que envia o arquivo.

## Fonte primária

- Anexo II do manual da e-Financeira — Leiautes Gerais, Fechamento da e-Financeira v1.5.0
  (ADE Cofis 10/2026): `br/rfb/efinanceira-cad-declarante/schema/anexo-ii-leiautes-gerais-v1-5-0.pdf`,
  páginas 33 a 53.
- XSD oficial: `schema/evtFechamentoeFinanceira-v1_5_0.xsd`.
