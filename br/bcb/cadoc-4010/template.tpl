{#
  Cadoc 4010 — Balancete Patrimonial Analítico.

  Este arquivo define APENAS a forma de saída: a sintaxe (XML), a hierarquia dos
  elementos e a posição de cada campo dentro dela.

  O que NÃO está aqui, de propósito:

    - de onde o dado vem              → binding (o cliente preenche)
    - o que cada campo significa      → contrato
    - formato, escala, sinal contábil → contrato

  Compare com a versão anterior deste arquivo, onde o saldo era escrito

      {{ c.saldo|cosif_signed:c.cosifCode|decimal:2 }}

  Aqueles dois filtros são conhecimento contábil — "aplique a natureza da conta ao
  sinal", "imprima com duas casas" — e as mesmas duas regras também estavam
  declaradas no contrato. A mesma decisão em dois lugares, sem árbitro: se um dia
  discordassem, o arquivo sairia errado com as duas conferências passando. Agora
  vivem só no contrato e o motor as aplica ao popular.

  Salvaguarda do motor: um campo referenciado aqui e não declarado no contrato faz
  o template ser recusado; um campo declarado que nenhum template posiciona gera
  aviso na curadoria. É o que impede os dois arquivos de voltarem a divergir.
#}
<?xml version="1.0" encoding="UTF-8"?>
<documento codigoDocumento="4010" cnpj="{{ institution.cnpj8 }}" dataBase="{{ system.dataBase }}" tipoRemessa="{{ system.tipoRemessa }}">
  <contas>
{%- for c in cosif_balances %}
    <conta codigoConta="{{ c.cosifCode }}" saldo="{{ c.saldo }}" />
{%- endfor %}
  </contas>
</documento>
