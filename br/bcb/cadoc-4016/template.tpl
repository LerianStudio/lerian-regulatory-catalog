{# Cadoc 4016 — Balanço Patrimonial Analítico. #}
{# Define APENAS a forma de saída. Formato e sinal do saldo vivem no contrato; a #}
{# exclusão dos grupos 7 e 8 é filtro de EXTRAÇÃO e vive na consulta do binding. #}
{# Idêntico ao 4010 em estrutura, mudando o codigoDocumento. #}
<?xml version="1.0" encoding="UTF-8"?>
<documento codigoDocumento="4016" cnpj="{{ institution.cnpj8 }}" dataBase="{{ system.dataBase }}" tipoRemessa="{{ system.tipoRemessa }}">
  <contas>
{%- for c in cosif_balances %}
    <conta codigoConta="{{ c.cosifCode }}" saldo="{{ c.saldo }}" />
{%- endfor %}
  </contas>
</documento>
