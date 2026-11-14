{# e-Financeira — evtFechamentoeFinanceira (Fechamento da e-Financeira), leiaute v1.5.0. #}
{# Define APENAS a forma de saída, na ordem do XSD. Domínio e forma vivem no #}
{# contrato; de onde vem cada valor vive no binding. Elemento opcional vazio é #}
{# omitido (A II: campo não preenchido não é informado). As datas são as do semestre #}
{# (system.periods.semestre), salvo a data de abertura ou de encerramento que a #}
{# geração informa. Os indicadores são parâmetros da geração; os de valor único #}
{# (ContasAReportarCRS e ContasAReportarFATCA 0) saem só quando informados, #}
{# comparados ao valor para que o "0" nunca dependa de ser verdadeiro. O #}
{# nadaADeclarar não sai (knownGap nada-a-declarar-fora). #}
{# O grupo FechamentoMovOpFin sai sempre: FechamentoPP, FechamentoMovOpFinAnual e #}
{# EntPatDecExterior estão fora. Sem ds:Signature: a borda que transmite o arquivo o #}
{# assina. O id é "ID" + os 18 dígitos que o motor gera. #}
<?xml version="1.0" encoding="UTF-8"?>
<eFinanceira xmlns="http://www.eFinanceira.gov.br/schemas/evtFechamentoeFinanceira/v1_5_0">
  <evtFechamentoeFinanceira id="ID{{ declarante.eventId }}">
    <ideEvento>
      <indRetificacao>{{ system.indRetificacao }}</indRetificacao>
{%- if system.nrRecibo %}
      <nrRecibo>{{ system.nrRecibo }}</nrRecibo>
{%- endif %}
      <tpAmb>{{ declarante.tpAmb }}</tpAmb>
      <aplicEmi>{{ declarante.aplicEmi }}</aplicEmi>
      <verAplic>{{ declarante.verAplic }}</verAplic>
    </ideEvento>
    <ideDeclarante>
      <cnpjDeclarante>{{ declarante.cnpj }}</cnpjDeclarante>
    </ideDeclarante>
    <infoFechamento>
{%- if system.dtInicio %}
      <dtInicio>{{ system.dtInicio }}</dtInicio>
{%- else %}
      <dtInicio>{{ system.periods.semestre.start }}</dtInicio>
{%- endif %}
{%- if system.dtFim %}
      <dtFim>{{ system.dtFim }}</dtFim>
{%- else %}
      <dtFim>{{ system.periods.semestre.end }}</dtFim>
{%- endif %}
      <sitEspecial>{{ system.sitEspecial }}</sitEspecial>
    </infoFechamento>
    <FechamentoMovOpFin>
      <FechamentoMovOpFin>{{ system.fechamentoMovOpFin }}</FechamentoMovOpFin>
{%- if system.contasAReportarCRS == "0" %}
      <ContasAReportarCRS>0</ContasAReportarCRS>
{%- endif %}
{%- if system.contasAReportarFATCA == "0" %}
      <ContasAReportarFATCA>0</ContasAReportarFATCA>
{%- endif %}
    </FechamentoMovOpFin>
  </evtFechamentoeFinanceira>
</eFinanceira>
