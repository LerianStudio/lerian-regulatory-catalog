# Schemas do evtFechamentoeFinanceira

| Arquivo | Origem | sha256 |
|---|---|---|
| `evtFechamentoeFinanceira-v1_5_0.xsd` | Receita Federal, Portal SPED, e-Financeira › Schemas › ADE Cofis 10/2026 › Eventos (`http://sped.rfb.gov.br/item/show/8206`), baixado em 11/11/2026. Em produção desde 01/09/2026. Cópia byte a byte: não edite. | `3e6a6fdd361e0ebcd46909adc1754e331bac48b4d4e35e7bb1353c1af035144a` |
| `xmldsig-core-schema.xsd` | W3C, XML Signature Syntax and Processing (`https://www.w3.org/TR/xmldsig-core/xmldsig-core-schema.xsd`), a mesma cópia de `br/rfb/efinanceira-cad-declarante/schema/`. O XSD do evento o importa como `../../Comum/xmldsig-core-schema.xsd`. | `d102ad3df7664c307e0c2c776ba4a90513b1969974d8a940bae1a77f9f21e15d` |

O Anexo II (Leiautes Gerais v1.5.0), de onde vêm as regras do contrato, está em
`br/rfb/efinanceira-cad-declarante/schema/anexo-ii-leiautes-gerais-v1-5-0.pdf`.

## XSD e Anexo II

Onde os dois divergem, o contrato segue o XSD, porque é ele que recusa o arquivo:

- `indRetificacao` só aceita `1` e `2`; a regra MS1119 do Anexo II cita também o `3`;
- `ContasAReportarFATCA` fica direto em `FechamentoMovOpFin`; o resumo do Anexo II mostra
  um grupo `EntDecExterior` que o XSD não tem;
- a ordem é `ContasAReportarCRS` e depois `ContasAReportarFATCA`; o Anexo II os numera
  ao contrário (21 e 20);
- o indicador `FechamentoMovOpFin` é opcional no XSD (`minOccurs="0"`); o Anexo II o diz
  1-1. O contrato o pede sempre (ver o parâmetro `fechamentoMovOpFin`).

## A assinatura

O XSD oficial exige `ds:Signature` dentro de `<eFinanceira>`. O Reporter entrega o
evento **sem assinatura**: assinar (XMLDSig com o e-CNPJ ICP-Brasil do declarante),
montar o lote, cifrá-lo e transmiti-lo são da borda que envia o arquivo à Receita.
Um arquivo saído do Reporter, portanto, não valida contra este XSD tal como está.

A homologação do catálogo (`tools/homologation`) é onde o arquivo gerado é validado
contra uma cópia derivada na hora, sem o elemento `ds:Signature` e sem o import — este
arquivo nunca é alterado, e a cópia não pode divergir dele. Quem valida o arquivo JÁ
ASSINADO usa os dois XSDs desta pasta, com o import apontando para o
`xmldsig-core-schema.xsd`.
