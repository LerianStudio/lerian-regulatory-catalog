{# e-Financeira — evtCadDeclarante (Cadastro do Declarante), leiaute v1.5.0. #}
{# Define APENAS a forma de saída, na ordem do XSD. Tamanho, domínio e forma vivem #}
{# no contrato; de onde vem cada valor vive no binding. Elemento opcional vazio é #}
{# omitido (A II: campo não preenchido não é informado). O enderecoLivre é montado no #}
{# formato do Anexo II, endereço/cep/cidade/UF. Sem ds:Signature: a borda #}
{# que transmite o arquivo o assina. O id é "ID" + os 18 dígitos que o motor gera. #}
<?xml version="1.0" encoding="UTF-8"?>
<eFinanceira xmlns="http://www.eFinanceira.gov.br/schemas/evtCadDeclarante/v1_5_0">
  <evtCadDeclarante id="ID{{ declarante.eventId }}">
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
    <infoCadastro>
      <inDeclaranteCRS>{{ declarante.inDeclaranteCRS }}</inDeclaranteCRS>
      <inDeclaranteFATCA>{{ declarante.inDeclaranteFATCA }}</inDeclaranteFATCA>
{%- for t in declarante.tiposEntidade %}
      <tpEntidade>{{ t.tpEntidade }}</tpEntidade>
{%- endfor %}
{%- if declarante.giin %}
      <GIIN>{{ declarante.giin }}</GIIN>
{%- endif %}
{%- if declarante.categoriaDeclarante %}
      <CategoriaDeclarante>{{ declarante.categoriaDeclarante }}</CategoriaDeclarante>
{%- endif %}
{%- for n in declarante.nifs %}
      <NIF>
        <NumeroNIF>{{ n.numeroNIF }}</NumeroNIF>
        <PaisEmissao>{{ n.paisEmissao }}</PaisEmissao>
{%- if n.tpNIF %}
        <tpNIF>{{ n.tpNIF }}</tpNIF>
{%- endif %}
      </NIF>
{%- endfor %}
      <nome>{{ declarante.nome }}</nome>
{%- if declarante.tpNome %}
      <tpNome>{{ declarante.tpNome }}</tpNome>
{%- endif %}
      <enderecoLivre>{{ declarante.logradouro }}/{{ declarante.cep }}/{{ declarante.cidade }}/{{ declarante.uf }}</enderecoLivre>
{%- if declarante.tpEndereco %}
      <tpEndereco>{{ declarante.tpEndereco }}</tpEndereco>
{%- endif %}
      <municipio>{{ declarante.municipio }}</municipio>
      <UF>{{ declarante.uf }}</UF>
      <CEP>{{ declarante.cep }}</CEP>
      <Pais>{{ declarante.pais }}</Pais>
{%- for r in declarante.residenciasFiscais %}
      <paisResid>
        <Pais>{{ r.pais }}</Pais>
      </paisResid>
{%- endfor %}
    </infoCadastro>
  </evtCadDeclarante>
</eFinanceira>
