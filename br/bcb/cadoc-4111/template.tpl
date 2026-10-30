{# Cadoc 4111 — Saldos Contábeis Diários. #}
{# Define APENAS a forma de saída. Formato e sinal vivem no contrato; de onde vem #}
{# cada saldoDia vive no binding; QUAIS contas existem vêm do conjunto fechado. #}
{# O loop percorre o que o binding resolveu do conjunto fechado — as duas classes #}
{# de conta, estoque e fluxo. Conta de saldo zero pode ser omitida (I §4.2.2.a). #}
<?xml version="1.0" encoding="UTF-8"?>
<documento codigoDocumento="4111" cnpj="{{ institution.cnpj8 }}" dataBase="{{ system.dataBase }}" tipoRemessa="{{ system.tipoRemessa }}">
  <contas>
{%- for c in saldos_diarios %}
    <conta codigoConta="{{ c.cosifCode }}" saldoDia="{{ c.saldoDia }}" />
{%- endfor %}
  </contas>
</documento>
