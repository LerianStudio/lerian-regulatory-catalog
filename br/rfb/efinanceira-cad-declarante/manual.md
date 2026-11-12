# e-Financeira — Cadastro do Declarante (evtCadDeclarante)

Evento de Informações da Entidade Declarante, leiaute v1.5.0 (ADE Cofis 10/2026), em
produção desde 01/09/2026.

## O que é

O cadastro da instituição na e-Financeira: CNPJ, razão social, endereço, situação no CRS
e no FATCA, tipos de entidade e países de residência fiscal. Não traz cliente nem
movimentação.

É o **primeiro** evento: a Receita recusa a abertura da e-Financeira de uma instituição
sem um cadastro ativo. É enviado **uma vez** por CNPJ — o `cnpjDeclarante` é a chave do
evento, e um segundo original é recusado — e reenviado como **retificação** sempre que
o cadastro muda.

## Original e retificação

A geração pede o parâmetro `indRetificacao`:

| Valor | Quando |
|---|---|
| `1` | O original: a primeira vez que a instituição se cadastra. |
| `2` | Retificação espontânea: o cadastro mudou e a instituição corrige. |
| `3` | Retificação a pedido: a Receita pediu a correção. |

Numa retificação, informe também `nrRecibo`: o número do recibo de entrega do evento que
está sendo retificado — o do **último** evento aceito. A Receita devolve o recibo a quem
transmitiu o arquivo; o Reporter não o vê, então você o digita ao gerar. O formato é
conferido na hora (`999999999999999999-99-999-9999-999999999999999999`); qual é o último
recibo, só a Receita sabe.

Um original já aprovado impede outro original da mesma instituição. Uma retificação que
informa o recibo não precisa de um original aprovado no Reporter: o original pode ter
sido enviado por outra ferramenta.

Cada geração tira um **id de evento novo** (`ID` + 18 dígitos, ordenado pelo instante da geração): uma
retificação é um evento novo, ligado ao anterior pelo recibo, nunca pelo id.

## O arquivo sai sem assinatura

O XSD oficial exige a assinatura digital (`ds:Signature`) dentro de `<eFinanceira>`. O
Reporter gera o evento **sem** ela. Assinar com o e-CNPJ ICP-Brasil do declarante
(XMLDSig), montar o lote, cifrá-lo e transmiti-lo à Receita são da etapa que envia o
arquivo — cada regulador pede o seu certificado, e o Reporter não o guarda.

Por isso o arquivo baixado do Reporter não valida contra o XSD oficial tal como está; a
pasta `schema/` explica como validar antes e depois da assinatura.

## De onde vem cada valor

O mapeamento de referência lê a organização do Midaz para o que o Midaz guarda; o resto
você preenche uma vez no mapeamento.

| No arquivo | De onde vem |
|---|---|
| `id` | Gerado pelo motor a cada geração. |
| `indRetificacao`, `nrRecibo` | Parâmetros da geração. |
| `tpAmb` | Você preenche: `1` produção, `2` produção restrita (testes). |
| `aplicEmi`, `verAplic` | Constantes: `1` (aplicativo da empresa) e `Lerian Reporter`. |
| `cnpjDeclarante` | `organization.legal_document`, conferido contra o cadastro da instituição. |
| `inDeclaranteCRS` | Você preenche (1 a 4). |
| `inDeclaranteFATCA` | Você preenche (1 a 5). |
| `tpEntidade` (1 a 5) | Você preenche a lista: 1, 2, 3, 4 ou 6. |
| `GIIN`, `CategoriaDeclarante` | Você preenche, quando se aplica. Instituição brasileira informante é `FATCA602`. |
| `NIF` | Declarado vazio: o Midaz não guarda identificação fiscal no exterior. Quem tem mapeia o conjunto `nifs` a partir da própria base. |
| `nome` | `organization.legal_name`. Deve ser idêntico ao do Cadastro CNPJ. |
| `tpNome`, `tpEndereco` | Você preenche, se quiser informar (`OECD207` para o nome legal). |
| `enderecoLivre` | Montado no formato do Anexo II, `endereço/cep/cidade/UF`, com `address.line1`, `address.zipCode`, `address.city` e `address.state`. |
| `municipio` | Você preenche: o código de 7 dígitos da tabela de Municípios da Receita. O Midaz guarda só o nome da cidade. |
| `UF`, `CEP`, `Pais` | `address.state`, `address.zipCode`, `address.country`. |
| `paisResid` (1 ou mais) | Você preenche a lista de países de residência fiscal, com `BR` entre eles. |

Enquanto um campo obrigatório que você preenche estiver pendente, o rascunho sai com a
pendência e não pode ser aprovado nem baixado.

## O que a organização no Midaz precisa ter

- `legalDocument`: o CNPJ (14 posições, numérico ou alfanumérico).
- `legalName`: a razão social, até 100 posições.
- `address.line1`: logradouro, número e complemento, até 146 posições. O `address.line2`
  não entra no arquivo: ponha o complemento no `line1`.
- `address.city`: o nome da cidade, até 40 posições.
- `address.zipCode`: o CEP com 8 dígitos (com ou sem o traço).
- `address.state`: a **sigla** da UF, duas letras (`SP`, não `São Paulo`).
- `address.country`: o código do país, duas letras (`BR`).

A Receita proíbe aspas (`"`), apóstrofo (`'`), cerquilha (`#`) e hífen duplo (`--`) no
conteúdo. Um nome ou endereço com aspas, apóstrofo ou cerquilha aparece no rascunho para
correção; o hífen duplo o Reporter não confere (ver abaixo).

## O que o Reporter confere

- Tamanho, domínio e formato de cada campo, pelas tabelas de códigos da Receita
  (países, UF, tipos de nome e de endereço, categorias de declarante).
- Que o município existe e é da UF do endereço.
- Que o Brasil está entre os países de residência fiscal.
- Que tipo de entidade, NIF e país de residência não se repetem.
- Que um NIF informado não é "not required" (e variantes) nem começa por nove números em
  sequência.
- Original único por instituição; recibo exigido na retificação e recusado no original.

## O que o Reporter não confere

- **Assinatura e transmissão**: da etapa que envia o arquivo.
- **GIIN obrigatório pelo histórico**: o GIIN passa a ser obrigatório quando a instituição
  já enviou movimentação reportável aos EUA; isso depende do histórico na Receita.
- **Hífen duplo** (`--`) num campo de texto: a Receita recusa (MS1124).
- **NIF de um só caractere repetido** (`AAAAAAAAA`): a Receita recusa (MS1233).
- **Razão social igual à do Cadastro CNPJ**: o nome vem da sua base.
- **Recibo do último evento**: só o formato é conferido.

## Fonte primária

- Anexo II do manual da e-Financeira — Leiautes Gerais, Cadastro de Declarante v1.5.0
  (ADE Cofis 10/2026): `schema/anexo-ii-leiautes-gerais-v1-5-0.pdf`.
- XSD oficial: `schema/evtCadDeclarante-v1_5_0.xsd`.
- Tabelas de códigos da Receita: `br/rfb/e-financeira/tabelas/`.
