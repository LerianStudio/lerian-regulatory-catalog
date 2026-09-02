{# reporter:output-encoding=ISO-8859-1 #}
{#  #}
{# DIMP v10 — fluxo mensal ordinário (finalidade 1). Pipe inicial e final, CRLF, #}
{# ISO 8859-1 (L p.3). Este arquivo define APENAS posição e sintaxe; formato, #}
{# domínio e condicionais vivem no contrato; origem vive no binding. #}
{#  #}
{# HIERARQUIA: um conjunto childOf é alcançado como lista aninhada em cada linha do #}
{# pai ({% for d in r.operacoesDiarias %}). Os loops aninhados realizam a adjacência #}
{# que o leiaute exige (1100 seguido imediatamente dos seus 1110; 1110 dos seus 1115 #}
{# — L pp.28, 32-33). #}
{#  #}
{# TOTALIZADORES: derivados do próprio render com {% counter %}/{% counter_show %} — #}
{# nada de contagem digitada à mão (o template anterior tinha OITO). Cada linha #}
{# incrementa o contador do seu bloco e o do seu tipo. As assimetrias do leiaute #}
{# estão marcadas onde acontecem: #}
{# · 0000 conta no bloco 0 "mesmo não pertencendo ao bloco 0" (L p.27) #}
{# · 9990 conta o 9999, que vem DEPOIS dele — por isso o incremento antecipado #}
{# na própria linha do 9990 (L p.53) #}
{# · o 9999 conta a si próprio (L p.54) #}
{# Contagens estruturalmente fixas neste template (uma linha de 0000, quinze tipos #}
{# de registro etc.) são constantes, como o leiaute permite e o template sabe. #}
{#  #}
{# CONFERIR ANTES DE PUBLICAR (status draft): o indicador dos registros de abertura #}
{# 0001/1001/9001 — o template interno usava "1"; validar contra L p.13. #}
{#  #}
{%- counter "b0" -%}|0000|10|1|{{ system.ufFisco }}|{{ declarante.cnpj }}|{{ declarante.razaoSocial }}|{{ escrituracao.dtIni }}|{{ escrituracao.dtFin }}|{{ system.tipoAmbiente }}|{{ escrituracao.mesValidacao }}|
{%- counter "b0" %}
|0001|1|
{%- counter "b0" %}
|0005|{{ declarante.nomeContato }}|{{ declarante.endereco }}|{{ declarante.cep }}|{{ declarante.codigoMunicipio }}|{{ declarante.uf }}|{{ declarante.nomeResponsavel }}|{{ declarante.telefone }}|{{ declarante.email }}|
{%- for t in titulares %}
{%- counter "b0" -%}{%- counter "0100" %}
|0100|{{ t.codCliente }}|{{ t.cnpj }}|{{ t.cpf }}|{{ t.nomeFantasia }}|{{ t.endereco }}|{{ t.cep }}|{{ t.codigoMunicipio }}|{{ t.uf }}|{{ t.nomeResponsavel }}|{{ t.telefone }}|{{ t.email }}|{{ t.dtCredenciamento }}|{{ t.indSubadquirencia }}|
{%- endfor %}
{%- for m in meiosCaptura %}
{%- counter "b0" -%}{%- counter "0200" %}
|0200|{{ m.codMeioCaptura }}|{{ m.numeroLogico }}|{{ m.tipoTecnologia }}|{{ m.terminalProprio }}|{{ m.marca }}|{{ m.smartpos }}|
{%- endfor %}
{%- counter "b0" %}
|0990|{% counter_show "b0" %}|
{%- counter "b1" %}
|1001|1|
{%- for r in resumosMensais %}
{#- Segundo campo VAZIO de propósito: é o COD_IP_PAR (instituição parceira), #}
{# declarado fora do escopo deste contrato. Um posicional vazio sem justificativa #}
{# convida à "correção" que desloca todas as colunas seguintes.-#}
{%- counter "b1" -%}{%- counter "1100" %}
|1100||{{ r.codCliente }}|{{ r.indComex }}|{{ r.indExtemporaneo }}|{{ r.dtIni }}|{{ r.dtFin }}|{{ r.valor }}|{{ r.qtd }}|
{%- for d in r.operacoesDiarias %}
{%- counter "b1" -%}{%- counter "1110" %}
|1110|{{ d.codMeioCaptura }}|{{ d.dtOperacao }}|{{ d.valor }}|{{ d.qtd }}|{{ d.cnpjLiquidante }}|
{%- for c in d.detalhesOperacao %}
{%- counter "b1" -%}{%- counter "1115" %}
|1115|{{ c.nsu }}|{{ c.codAutorizacao }}|{{ c.idTransacao }}|{{ c.indSplit }}|{{ c.bandeira }}|{{ c.hora }}|{{ c.valor }}|{{ c.naturezaOperacao }}|{{ c.geolocalizacao }}|{{ c.indNaturezaJuridica }}|{{ c.indTipoPix }}|
{%- endfor %}
{%- endfor %}
{%- endfor %}
{%- counter "b1" %}
|1990|{% counter_show "b1" %}|
{#- BLOCO 9 — um totalizador por tipo PRESENTE (L p.52), não uma lista fixa. #}
{# Emitir totalizador de tipo ausente com contagem 0 declara ao fisco um registro #}
{# que o arquivo não tem, e faz a linha do próprio 9900 mentir sobre a quantidade #}
{# de linhas 9900. #}
{#  #}
{# A contagem do próprio 9900 tem de ser conhecida ANTES da primeira linha sair — #}
{# ela conta "inclusive os posteriores a este registro". counter_show soma #}
{# contadores mas não faz aritmética, então todas as contagens acontecem primeiro, #}
{# aqui: incrementar não emite nada. #}
{#  #}
{# Sempre presentes: 0000, 0001, 0005, 0990, 1001, 1990, 9001, 9900, 9990, 9999. #}
{# Condicionais: 0100, 0200, 1100, 1110, 1115.-#}
{%- counter "n9900" %}{%- counter "n9900" %}{%- counter "n9900" %}{%- counter "n9900" %}{%- counter "n9900" %}
{%- counter "n9900" %}{%- counter "n9900" %}{%- counter "n9900" %}{%- counter "n9900" %}{%- counter "n9900" %}
{%- if titulares %}{%- counter "n9900" %}{%- endif %}
{%- if meiosCaptura %}{%- counter "n9900" %}{%- endif %}
{#- 1100, 1110 e 1115 andam juntos NESTE escopo: o leiaute só admite 1100 com #}
{# valor "0" e filhas omitidas na finalidade 3 (L p.32), e este contrato cobre a #}
{# finalidade 1. Então resumosMensais não-vazio implica 1110 e 1115 presentes, e #}
{# os três totalizadores são condicionados ao mesmo teste. Se a finalidade 3 #}
{# entrar no escopo, esta equivalência deixa de valer e os três precisam de #}
{# testes próprios.-#}
{%- if resumosMensais %}{%- counter "n9900" %}{%- counter "n9900" %}{%- counter "n9900" %}{%- endif %}
{%- counter "b9" %}
|9001|1|
{%- counter "b9" %}
|9900|0000|1|
{%- counter "b9" %}
|9900|0001|1|
{%- counter "b9" %}
|9900|0005|1|
{%- if titulares %}
{%- counter "b9" %}
|9900|0100|{% counter_show "0100" %}|
{%- endif %}
{%- if meiosCaptura %}
{%- counter "b9" %}
|9900|0200|{% counter_show "0200" %}|
{%- endif %}
{%- counter "b9" %}
|9900|0990|1|
{%- counter "b9" %}
|9900|1001|1|
{%- if resumosMensais %}
{%- counter "b9" %}
|9900|1100|{% counter_show "1100" %}|
{%- counter "b9" %}
|9900|1110|{% counter_show "1110" %}|
{%- counter "b9" %}
|9900|1115|{% counter_show "1115" %}|
{%- endif %}
{%- counter "b9" %}
|9900|1990|1|
{%- counter "b9" %}
|9900|9001|1|
{%- counter "b9" %}
|9900|9900|{% counter_show "n9900" %}|
{%- counter "b9" %}
|9900|9990|1|
{%- counter "b9" %}
|9900|9999|1|
{#- O 9990 conta o próprio 9990 E o 9999, que vem DEPOIS dele (L p.53): o segundo #}
{# incremento abaixo é o 9999 antecipado. A linha do 9999 já não incrementa nada.-#}
{%- counter "b9" -%}{%- counter "b9" %}
|9990|{% counter_show "b9" %}|
|9999|{% counter_show "b0" "b1" "b9" %}|
