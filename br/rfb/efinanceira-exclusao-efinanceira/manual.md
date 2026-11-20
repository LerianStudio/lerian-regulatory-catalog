# e-Financeira — Exclusão da e-Financeira (evtExclusaoeFinanceira)

Evento de Exclusão da e-Financeira, leiaute v1.5.0 (ADE Cofis 10/2026), em produção desde
01/09/2026.

## O que é

A exclusão de um evento de **abertura** que ainda está em andamento — cujo
**fechamento ainda não foi enviado** —, seja a abertura da e-Financeira ou a abertura de
**Repasse** (A II p.61, campo 10), e, junto com ela, de **todos** os eventos de movimento
(operações financeiras e previdência privada) ou de repasse enviados depois dela. É como
desfazer o semestre aberto por engano para abri-lo de novo.

O arquivo não repete nada da abertura: leva só o CNPJ da instituição declarante e o
**recibo de entrega** da abertura, o número que a Receita devolveu quando a aceitou.

Para excluir um único evento enviado indevidamente, use o outro documento do catálogo, a
Exclusão de Evento (`evtExclusao`).

## O recibo

A geração pede um parâmetro, `nrReciboEvento`: o recibo de entrega da abertura a excluir.
A Receita devolve o recibo a quem transmitiu o arquivo; o Reporter não o vê, então você o
digita ao gerar. O formato é conferido na hora
(`999999999999999999-99-999-9999-999999999999999999`, de 15 a 49 posições), e um recibo
fora dele é recusado antes de gerar.

Que o recibo seja de uma abertura ainda **sem fechamento**, em andamento (A II p.60-61,
campos 9 e 10), e de uma abertura **ativa** **desta** instituição (MS1117), só a Receita
confere, ao receber a exclusão. Uma abertura já fechada não se exclui por este evento.

Cada recibo é uma entrega à parte. Gerar de novo para o mesmo recibo é permitido:
enquanto as duas gerações são rascunho, a mais nova é a que vale, e a anterior aparece
como substituída por ela. Não há retificação de uma exclusão — o leiaute não tem
`indRetificacao` —, então não há regra de original e substituição, e o Reporter **não**
impede aprovar duas exclusões do mesmo recibo: ele não sabe qual você transmitiu.
Transmita uma só; a segunda, depois da primeira aceita, é recusada pela Receita.

Cada geração tira um **id de evento novo** (`ID` + 18 dígitos, ordenado pelo instante da
geração), que não se repete entre os relatórios do Reporter. Que ele não repita um id que
outra ferramenta já enviou pela mesma instituição (MS1001), só a Receita confere.

## Depois da exclusão: marque o relatório excluído

O Reporter **não** liga o recibo digitado a um relatório dele e não fica sabendo da
exclusão: o recibo é da Receita, e os eventos podem ter sido enviados por outra
ferramenta. Depois que a exclusão for transmitida e **aceita** pela Receita, marque no
Reporter como **"excluída na Receita"** o relatório Final da abertura excluída **e cada
retificação aprovada** dela — você escolhe os relatórios; faça o mesmo com os dos eventos
enviados depois dela. Um relatório marcado sai da regra de um original, e o Reporter
volta a aceitar um original novo do mesmo período. Se faltar uma retificação aprovada, o
original novo é recusado (RPT-0203): o Reporter não aceita um original depois de uma
retificação aprovada que nomeou o recibo que ela substituiu.

A marcação só existe a partir da versão do Reporter que traz a marcação; numa versão
anterior, a ação não aparece.

Só então gere a abertura de novo, **como original**. Uma retificação é recusada pela
Receita: o recibo da abertura excluída não está mais ativo, e é dele que a retificação
dependeria.

## O arquivo sai sem assinatura

O XSD oficial exige a assinatura digital (`ds:Signature`) dentro de `<eFinanceira>`. O
Reporter gera o evento **sem** ela. Assinar com o e-CNPJ ICP-Brasil do declarante
(XMLDSig), montar o lote, cifrá-lo e transmiti-lo à Receita são da etapa que envia o
arquivo — cada regulador pede o seu certificado, e o Reporter não o guarda.

Por isso o arquivo baixado do Reporter não valida contra o XSD oficial tal como está; a
pasta `schema/` explica como validar antes e depois da assinatura.

## De onde vem cada valor

| No arquivo | De onde vem |
|---|---|
| `id` | Gerado pelo motor a cada geração. |
| `tpAmb` | Você preenche uma vez no mapeamento: `1` produção, `2` produção restrita (testes). |
| `aplicEmi`, `verAplic` | Constantes: `1` (aplicativo da empresa) e `Lerian Reporter`. |
| `cnpjDeclarante` | `organization.legal_document` do Midaz, conferido contra o cadastro da instituição. |
| `nrReciboEvento` | Parâmetro da geração. |

Enquanto o ambiente de destino estiver pendente, o rascunho sai com a pendência e não pode
ser aprovado nem baixado.

## O que o Reporter confere

- O formato do recibo, ao gerar.
- O CNPJ: 14 posições, letras e dígitos, e o da instituição da entrega.
- O domínio do ambiente e do emissor, e o tamanho da versão do aplicativo, sem aspas
  (`"`), apóstrofo (`'`) nem cerquilha (`#`), que a Receita proíbe no conteúdo.

## O que o Reporter não confere

- **Dígitos verificadores do CNPJ** (MS1002): o Reporter confia na origem do dado, o
  Midaz ou quem digita o valor; quem preenche responde por ele, e a Receita recusa um
  dígito errado.
- **Se o recibo é de uma abertura sem fechamento** (A II p.60-61, campos 9 e 10) **e
  ativa desta instituição** (REGRA_VALIDA_NR_RECIBO_EVENTO_ABERTURA, MS1117): só o
  formato é conferido.
- **Quais eventos saem junto com a abertura**: a Receita os exclui; o Reporter não sabe
  quais foram.
- **Ambiente de destino**: o `tpAmb` é seu; um `2` (produção restrita) enviado à produção
  é recusado pela Receita (MS1163).
- **Id único na base nacional** (REGRA_VALIDA_CHAVE_ACESSO): o Reporter não repete um id
  entre as gerações dele; um id já enviado por outra ferramenta, só a Receita vê (MS1001).
- **Hífen duplo** (`--`) na versão do aplicativo: a Receita recusa (MS1124, "caracteres especiais restritos", do Manual de
  Orientação do Usuário da e-Financeira v1.2, §6.2).
- **Duas exclusões aprovadas do mesmo recibo**: o Reporter não sabe qual foi transmitida.
- **Assinatura e transmissão**: da etapa que envia o arquivo.
- **Saber da exclusão**: o Reporter não liga o recibo a um relatório; você marca os
  relatórios Finais excluídos e cada retificação aprovada deles como "excluída na
  Receita".

## Fonte primária

- Anexo II do manual da e-Financeira — Leiautes Gerais, Exclusão da e-Financeira v1.5.0
  (ADE Cofis 10/2026): `br/rfb/efinanceira-cad-declarante/schema/anexo-ii-leiautes-gerais-v1-5-0.pdf`,
  páginas 13 a 14, 58 a 61 e 62 a 63.
- XSD oficial: `schema/evtExclusaoeFinanceira-v1_5_0.xsd`.
