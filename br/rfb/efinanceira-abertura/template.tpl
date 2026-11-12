{# e-Financeira — evtAberturaeFinanceira (Abertura da e-Financeira), leiaute v1.5.0. #}
{# Define APENAS a forma de saída, na ordem do XSD. Tamanho, domínio e forma vivem #}
{# no contrato; de onde vem cada valor vive no binding. Elemento opcional vazio é #}
{# omitido (A II: campo não preenchido não é informado). As datas são as do semestre #}
{# (system.periods.semestre), salvo a data de abertura ou de encerramento que a #}
{# geração informa. Telefone e endereço, campos de cada conjunto, são aninhados aqui. #}
{# O grupo AberturaMovOpFin sai sempre: a Previdência Privada (AberturaPP) está fora. #}
{# Sem ds:Signature: a borda que transmite o arquivo o assina. O id é "ID" + os 18 #}
{# dígitos que o motor gera. #}
<?xml version="1.0" encoding="UTF-8"?>
<eFinanceira xmlns="http://www.eFinanceira.gov.br/schemas/evtAberturaeFinanceira/v1_5_0">
  <evtAberturaeFinanceira id="ID{{ declarante.eventId }}">
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
    <infoAbertura>
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
    </infoAbertura>
    <AberturaMovOpFin>
      <ResponsavelRMF>
        <CNPJ>{{ responsavelRMF.cnpj }}</CNPJ>
        <CPF>{{ responsavelRMF.cpf }}</CPF>
        <Nome>{{ responsavelRMF.nome }}</Nome>
        <Setor>{{ responsavelRMF.setor }}</Setor>
        <Telefone>
          <DDD>{{ responsavelRMF.ddd }}</DDD>
          <Numero>{{ responsavelRMF.telefone }}</Numero>
{%- if responsavelRMF.ramal %}
          <Ramal>{{ responsavelRMF.ramal }}</Ramal>
{%- endif %}
        </Telefone>
        <Endereco>
          <Logradouro>{{ responsavelRMF.logradouro }}</Logradouro>
          <Numero>{{ responsavelRMF.numero }}</Numero>
{%- if responsavelRMF.complemento %}
          <Complemento>{{ responsavelRMF.complemento }}</Complemento>
{%- endif %}
          <Bairro>{{ responsavelRMF.bairro }}</Bairro>
          <CEP>{{ responsavelRMF.cep }}</CEP>
          <Municipio>{{ responsavelRMF.municipio }}</Municipio>
          <UF>{{ responsavelRMF.uf }}</UF>
        </Endereco>
      </ResponsavelRMF>
{%- for r in declarante.respeFin %}
      <RespeFin>
        <CPF>{{ r.cpf }}</CPF>
        <Nome>{{ r.nome }}</Nome>
        <Setor>{{ r.setor }}</Setor>
        <Telefone>
          <DDD>{{ r.ddd }}</DDD>
          <Numero>{{ r.telefone }}</Numero>
{%- if r.ramal %}
          <Ramal>{{ r.ramal }}</Ramal>
{%- endif %}
        </Telefone>
        <Endereco>
          <Logradouro>{{ r.logradouro }}</Logradouro>
          <Numero>{{ r.numero }}</Numero>
{%- if r.complemento %}
          <Complemento>{{ r.complemento }}</Complemento>
{%- endif %}
          <Bairro>{{ r.bairro }}</Bairro>
          <CEP>{{ r.cep }}</CEP>
          <Municipio>{{ r.municipio }}</Municipio>
          <UF>{{ r.uf }}</UF>
        </Endereco>
        <Email>{{ r.email }}</Email>
      </RespeFin>
{%- endfor %}
{%- if represLegal.cpf or represLegal.setor or represLegal.ddd or represLegal.telefone or represLegal.ramal %}
      <RepresLegal>
        <CPF>{{ represLegal.cpf }}</CPF>
        <Setor>{{ represLegal.setor }}</Setor>
        <Telefone>
          <DDD>{{ represLegal.ddd }}</DDD>
          <Numero>{{ represLegal.telefone }}</Numero>
{%- if represLegal.ramal %}
          <Ramal>{{ represLegal.ramal }}</Ramal>
{%- endif %}
        </Telefone>
      </RepresLegal>
{%- endif %}
    </AberturaMovOpFin>
  </evtAberturaeFinanceira>
</eFinanceira>
