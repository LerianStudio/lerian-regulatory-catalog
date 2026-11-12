# Schemas do evtExclusao

| Arquivo | Origem | sha256 |
|---|---|---|
| `evtExclusao-v1_5_0.xsd` | Receita Federal, Portal SPED, e-Financeira › Schemas › ADE Cofis 10/2026 › Eventos (`http://sped.rfb.gov.br/arquivo/download/8205`), baixado em 11/11/2026. Em produção desde 01/09/2026. Cópia byte a byte: não edite. | `0281b6289fb86ea45d292e100f4a373103107739956abb61d6c14e0bf65435d8` |
| `xmldsig-core-schema.xsd` | W3C, XML Signature Syntax and Processing (`https://www.w3.org/TR/xmldsig-core/xmldsig-core-schema.xsd`), a mesma cópia de `br/rfb/efinanceira-cad-declarante/schema/`. O XSD do evento o importa como `../../Comum/xmldsig-core-schema.xsd`. | `d102ad3df7664c307e0c2c776ba4a90513b1969974d8a940bae1a77f9f21e15d` |

O Anexo II (Leiautes Gerais v1.5.0), de onde vêm as regras do contrato, está em
`br/rfb/efinanceira-cad-declarante/schema/anexo-ii-leiautes-gerais-v1-5-0.pdf`.

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
