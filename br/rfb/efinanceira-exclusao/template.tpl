{# e-Financeira — evtExclusao (Exclusão de evento), leiaute v1.5.0. #}
{# Define APENAS a forma de saída, na ordem do XSD. Tamanho, domínio e forma vivem #}
{# no contrato; de onde vem cada valor vive no binding. O recibo do evento a excluir #}
{# é o parâmetro da geração, conferido pelo pattern do contrato. Sem ds:Signature: a #}
{# borda que transmite o arquivo o assina. O id é "ID" + os 18 dígitos que o motor gera. #}
<?xml version="1.0" encoding="UTF-8"?>
<eFinanceira xmlns="http://www.eFinanceira.gov.br/schemas/evtExclusao/v1_5_0">
  <evtExclusao id="ID{{ declarante.eventId }}">
    <ideEvento>
      <tpAmb>{{ declarante.tpAmb }}</tpAmb>
      <aplicEmi>{{ declarante.aplicEmi }}</aplicEmi>
      <verAplic>{{ declarante.verAplic }}</verAplic>
    </ideEvento>
    <ideDeclarante>
      <cnpjDeclarante>{{ declarante.cnpj }}</cnpjDeclarante>
    </ideDeclarante>
    <infoExclusao>
      <nrReciboEvento>{{ system.nrReciboEvento }}</nrReciboEvento>
    </infoExclusao>
  </evtExclusao>
</eFinanceira>
