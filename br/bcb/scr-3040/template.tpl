{# SCR Documento 3040 - Dados Individualizados de Risco de Crédito. #}
{# Define a forma de saída. Formato, domínio e grão vivem no contrato; de onde vem cada valor vive no binding. #}
{# Aninhamento Doc3040 > Cli > Op > Venc, Gar, Inf: ver knownGaps sem-xsd-aninhamento no contrato. #}
{# Parte=1 e TpArq=F: o documento não é particionado (I p.8). TotalCli conta os Cli do arquivo: ver cli-por-holder. #}
{# Cd e IPOC: o cliente PJ leva a raiz do CNPJ e o PF leva o CPF inteiro (I p.17-18). DetCli é o CNPJ inteiro, só do PJ. #}
{# NatuOp: 01 para a operação concedida, 03 para a recompra de consignado; a adquirida fica sem (q4-natuop-ccb-comprada). #}
{# Indx 11 e PercIndx 0 só na taxa prefixada (I p.50); na flutuante os dois ficam de fora (indx-pos-fixado). #}
{# TpVlrGar 01 escreve VlrOrig e 02 escreve PercGar (I p.79). Ident é o CPF ou CNPJ do garantidor, senão a identificação da garantia real. #}
{# CaracEspecial chega como o texto do array do Postgres, {01,25}: sai 01;25. #}
<?xml version="1.0" encoding="UTF-8"?>
<Doc3040 DtBase="{{ system.dataBase }}" CNPJ="{{ Doc3040.cnpj8 }}" Remessa="{{ system.remessa }}" Parte="1" TpArq="F" NomeResp="{{ Doc3040.NomeResp }}" EmailResp="{{ Doc3040.EmailResp }}" TelResp="{{ Doc3040.TelResp }}" TotalCli="{{ Cli|length }}" MetodApPE="{{ Doc3040.MetodApPE }}" MetodDifTJE="{{ Doc3040.MetodDifTJE }}">
{%- for cli in Cli %}
  <Cli Cd="{% if cli.Tp == "2" %}{{ cli.cnpjRoot }}{% else %}{{ cli.document }}{% endif %}" Tp="{{ cli.Tp }}" Autorzc="{{ cli.Autorzc }}" PorteCli="{{ cli.PorteCli }}"{% if cli.TpCtrl %} TpCtrl="{{ cli.TpCtrl }}"{% endif %} IniRelactCli="{{ cli.IniRelactCli }}" FatAnual="{{ cli.FatAnual }}"{% if cli.CongEcon %} CongEcon="{{ cli.CongEcon }}"{% endif %}>
{%- for op in cli.Op %}
    <Op{% if cli.Tp == "2" %} DetCli="{{ cli.document }}"{% endif %} IPOC="{{ Doc3040.cnpj8 }}{{ op.Mod }}{{ cli.Tp }}{% if cli.Tp == "2" %}{{ cli.cnpjRoot }}{% else %}{{ cli.document }}{% endif %}{{ op.Contrt }}" Contrt="{{ op.Contrt }}" Mod="{{ op.Mod }}" OrigemRec="{{ op.OrigemRec }}"{% if op.rate_mode == "fixed" %} Indx="11" PercIndx="{{ op.PercIndx }}"{% endif %} VarCamb="790" CEP="{{ op.CEP }}" TaxEft="{{ op.TaxEft }}" DtContr="{{ op.DtContr }}" VlrContr="{{ op.VlrContr }}"{% if op.origin == "granted" %} NatuOp="01"{% elif op.origin == "consignado_repurchase" %} NatuOp="03"{% endif %}{% if op.DtVencOp %} DtVencOp="{{ op.DtVencOp }}"{% endif %} ProvConsttd="{{ op.ProvConsttd }}"{% if op.DiaAtraso != "0" %} DiaAtraso="{{ op.DiaAtraso }}"{% endif %}{% if op.CaracEspecial != "{}" %} CaracEspecial="{{ op.CaracEspecial|replace:"{:"|replace:"}:"|replace:",:;" }}"{% endif %}{% if op.DtaProxParcela %} DtaProxParcela="{{ op.DtaProxParcela }}"{% endif %}{% if op.VlrProxParcela %} VlrProxParcela="{{ op.VlrProxParcela }}"{% endif %} QtdParcelas="{{ op.QtdParcelas }}">
{%- if op.Venc %}
      <Venc{% for v in op.Venc %} v{{ v.vcod }}="{{ v.amount }}"{% endfor %}/>
{%- endif %}
{%- for g in op.Gar %}
      <Gar SitGar="{{ g.SitGar }}" Tp="{{ g.Tp }}"{% if g.guarantorDocument %} Ident="{{ g.guarantorDocument }}"{% elif g.identification %} Ident="{{ g.identification }}"{% endif %} TpVlrGar="{{ g.TpVlrGar }}"{% if g.TpVlrGar == "01" %} VlrOrig="{{ g.VlrOrig }}"{% else %} PercGar="{{ g.PercGar }}"{% endif %}{% if g.VlrData %} VlrData="{{ g.VlrData }}"{% endif %}{% if g.PercData %} PercData="{{ g.PercData }}"{% endif %}{% if g.DtReav %} DtReav="{{ g.DtReav }}"{% endif %}{% if g.Compart %} Compart="{{ g.Compart }}"{% endif %}/>
{%- endfor %}
{%- for a in op.Inf1002 %}
      <Inf Tp="{{ a.Tp }}" Cd="{{ a.Cd }}" Ident="{{ a.Ident }}" Valor="{{ a.Valor }}"/>
{%- endfor %}
{%- for r in op.Inf1701 %}
      <Inf Tp="{{ r.Tp }}" Cd="{{ r.Cd }}"/>
{%- endfor %}
    </Op>
{%- endfor %}
  </Cli>
{%- endfor %}
</Doc3040>
