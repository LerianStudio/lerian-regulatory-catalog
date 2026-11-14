# Schemas do evtAberturaeFinanceira

| Arquivo | Origem | sha256 |
|---|---|---|
| `evtAberturaeFinanceira-v1_5_0.xsd` | Receita Federal, Portal SPED, e-Financeira › Schemas › ADE Cofis 10/2026 › Eventos (`http://sped.rfb.gov.br/item/show/8200`), baixado em 11/11/2026. Em produção desde 01/09/2026. Cópia byte a byte: não edite. | `8c70f8ad5a4eb6d6b4f91b8c615735c791a209c8083df7f8c6ffdce2db9a9abf` |
| `xmldsig-core-schema.xsd` | W3C, XML Signature Syntax and Processing (`https://www.w3.org/TR/xmldsig-core/xmldsig-core-schema.xsd`), a mesma cópia de `br/rfb/efinanceira-cad-declarante/schema/`. O XSD do evento o importa como `../../Comum/xmldsig-core-schema.xsd`. | `d102ad3df7664c307e0c2c776ba4a90513b1969974d8a940bae1a77f9f21e15d` |

O Anexo II (Leiautes Gerais v1.5.0), de onde vêm as regras do contrato, está em
`br/rfb/efinanceira-cad-declarante/schema/anexo-ii-leiautes-gerais-v1-5-0.pdf`.

## XSD e Anexo II

Onde os dois divergem, o contrato segue o XSD, porque é ele que recusa o arquivo:

- `indRetificacao` só aceita `1` e `2`; o Anexo II lista também o `3`;
- `RepresLegal` é opcional (`minOccurs="0"`); o Anexo II o diz 1-1;
- o CPF aceita de 1 a 11 posições no XSD; o contrato pede as 11 que o Anexo II pede.

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
