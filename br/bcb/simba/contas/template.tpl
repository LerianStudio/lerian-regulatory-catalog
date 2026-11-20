{% comment %}
SIMBA - arquivo II CONTAS (IN BCB 636/2025, Anexo I, campos 1 a 12; normas/IN-BCB-636-2025.md:116-132).
Comentario em bloco (comment) e nao em linhas: no .txt cada linha de comentario deixava uma quebra de linha antes do 1o registro.
So a forma: sem cabecalho, TAB entre colunas, CR LF no fim de cada linha (IN art. 3o, :59-61).
Formato e dominio de cada campo estao no contrato; de onde vem, no binding.
autoescape off: sem ele o render escreve & < > aspas como entidades HTML.
Macro ascii: tira acentos (texto em ASCII) e troca TAB, CR e LF por espaco: um
valor com quebra de linha partiria o registro (IN art. 3o, CR LF no fim de cada linha). CR e LF saem de 13 e 10 por
stringformat, porque o pongo2 nao aceita quebra de linha num literal.
Campo 7: 1 com lancamento no periodo, 2 sem (contas do caso); 3 conta que transacionou com uma do caso (IN :126).
Campos 10 e 11: centavos sem separador (IN :73); o contrato escreve 2 casas e aqui sai o ponto. Sem lancamento ate a data: 000.
Campo 12: sempre em branco, conta nativa (IN :132); nenhuma aplicacao registra sucessao.
Conta das outras pernas que tambem e do caso nao se repete (marca jaListada).
{% endcomment -%}
{%- autoescape off %}{% macro ascii(s) %}{% with lf=10|stringformat:"%c"|add:": " %}{% with cr=13|stringformat:"%c"|add:": " %}{{ s|replace:"á:a"|replace:"à:a"|replace:"â:a"|replace:"ã:a"|replace:"ä:a"|replace:"é:e"|replace:"è:e"|replace:"ê:e"|replace:"ë:e"|replace:"í:i"|replace:"ì:i"|replace:"î:i"|replace:"ï:i"|replace:"ó:o"|replace:"ò:o"|replace:"ô:o"|replace:"õ:o"|replace:"ö:o"|replace:"ú:u"|replace:"ù:u"|replace:"û:u"|replace:"ü:u"|replace:"ç:c"|replace:"ñ:n"|replace:"Á:A"|replace:"À:A"|replace:"Â:A"|replace:"Ã:A"|replace:"Ä:A"|replace:"É:E"|replace:"È:E"|replace:"Ê:E"|replace:"Ë:E"|replace:"Í:I"|replace:"Ì:I"|replace:"Î:I"|replace:"Ï:I"|replace:"Ó:O"|replace:"Ò:O"|replace:"Ô:O"|replace:"Õ:O"|replace:"Ö:O"|replace:"Ú:U"|replace:"Ù:U"|replace:"Û:U"|replace:"Ü:U"|replace:"Ç:C"|replace:"Ñ:N"|replace:"º:o"|replace:"ª:a"|replace:"	: "|replace:cr|replace:lf }}{% endwith %}{% endwith %}{% endmacro %}
{%- for c in contas_investigadas %}{{ instituicao.compe }}	{{ c.numeroAgencia }}	{{ c.numeroConta }}	{{ c.tipoConta }}	{% if c.dataAbertura %}{{ c.dataAbertura|date:"02012006" }}{% endif %}	{% if c.dataEncerramento %}{{ c.dataEncerramento|date:"02012006" }}{% else %}31129999{% endif %}	{% if c.volumePeriodo %}1{% else %}2{% endif %}	{{ instituicao.cnpj }}	{{ ascii(instituicao.nomeUnicad)|slice:":50" }}	{% if c.saldoInicial %}{{ c.saldoInicial|replace:".:"|replace:"-:" }}{% else %}000{% endif %}	{% if c.saldoFinal %}{{ c.saldoFinal|replace:".:"|replace:"-:" }}{% else %}000{% endif %}	
{% endfor %}
{%- for t in contas_contraparte %}{% with id=t.contaId %}{% with chave=id|stringformat:"contaId:%s" %}{% if not contas_investigadas|where:chave %}{{ instituicao.compe }}	{{ t.numeroAgencia }}	{{ t.numeroConta }}	{{ t.tipoConta }}	{% if t.dataAbertura %}{{ t.dataAbertura|date:"02012006" }}{% endif %}	{% if t.dataEncerramento %}{{ t.dataEncerramento|date:"02012006" }}{% else %}31129999{% endif %}	3	{{ instituicao.cnpj }}	{{ ascii(instituicao.nomeUnicad)|slice:":50" }}	{% if t.saldoInicial %}{{ t.saldoInicial|replace:".:"|replace:"-:" }}{% else %}000{% endif %}	{% if t.saldoFinal %}{{ t.saldoFinal|replace:".:"|replace:"-:" }}{% else %}000{% endif %}	
{% endif %}{% endwith %}{% endwith %}{% endfor %}
{%- endautoescape -%}