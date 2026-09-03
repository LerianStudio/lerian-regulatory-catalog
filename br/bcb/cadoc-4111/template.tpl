{# Cadoc 4111 — Saldos Contábeis Diários. #}
{# Define APENAS a forma de saída. Formato e sinal vivem no contrato; de onde vem #}
{# cada saldoDia vive no binding; QUAIS contas existem vêm do conjunto fechado. #}
{# Contas de saldo zero podem ser omitidas, então o loop percorre só o que o #}
{# binding resolveu — as de estoque nesta versão (fluxo é pendência da Fase 4). #}
<?xml version="1.0" encoding="UTF-8"?>
<documento codigoDocumento="4111" cnpj="{{ institution.cnpj8 }}" dataBase="{{ system.dataBase }}" tipoRemessa="{{ system.tipoRemessa }}">
  <contas>
{%- for c in saldos_diarios %}
    <conta codigoConta="{{ c.cosifCode }}" saldoDia="{{ c.saldoDia }}" />
{%- endfor %}
  </contas>
</documento>
