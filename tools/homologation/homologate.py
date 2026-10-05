#!/usr/bin/env python3
"""Homologação dos documentos do catálogo contra um Midaz real.

Monta, SÓ PELA API do Midaz, uma contabilidade fictícia descrita num arquivo de
cenário (organização, ledger com rotas validadas, BRL, tipos de conta, contas,
rotas contábeis COSIF e lançamentos) e confere o razão que ela produziu.

Nunca escreve no banco do Midaz: o Midaz mantém relações próprias (saldos, cache
de rotas, contas externas) que um INSERT esqueceria, e foi um seed SQL que
escondeu, no e2e do Reporter, que o Midaz não grava status na operação.

Idempotente: cada recurso é procurado (por nome, alias, keyValue ou título) antes
de ser criado, e cada lançamento leva X-Idempotency e fica registrado no arquivo
de estado, então rodar de novo não duplica nada.

Só biblioteca padrão, Python 3.9+.

    python3 tools/homologation/homologate.py setup  tools/homologation/scenario/a-pagare-ip.json
    python3 tools/homologation/homologate.py ledger tools/homologation/scenario/a-pagare-ip.json
"""

import argparse
import calendar
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

DEFAULT_MIDAZ = os.environ.get("MIDAZ_URL", "https://ledger.sandbox.lerian.net")

# Pesos do dígito verificador COSIF, conferidos contra as 30 rubricas oficiais do
# conjunto do 4111: DV = soma(dígito_i * peso_i) mod 10 sobre os nove dígitos.
COSIF_WEIGHTS = (9, 3, 7, 9, 3, 7, 9, 3, 7)

# Toda rota é bidirecional e carrega a MESMA rubrica no débito e no crédito de
# cada ação. É o que faz o par do hold (e o do cancel) se anular no razão, de modo
# que só o commit move saldo contábil; e o estorno só é aceito pelo Midaz numa rota
# bidirecional.
ROUTE_ACTIONS = ("direct", "hold", "commit", "cancel", "revert")


def fail(message):
    print("ERRO: " + message, file=sys.stderr)
    sys.exit(1)


def cosif_check(code):
    if len(code) != 10 or not code.isdigit():
        return False

    digit = sum(int(d) * w for d, w in zip(code[:9], COSIF_WEIGHTS)) % 10

    return digit == int(code[9])


class Midaz:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def call(self, method, path, body=None, idempotency=None, ok=(200, 201), headers=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base + path, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            request.add_header(k, v)

        if idempotency:
            request.add_header("X-Idempotency", idempotency)

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as err:
            status, raw = err.code, err.read()

        payload = json.loads(raw) if raw else None

        if status not in ok:
            fail("%s %s -> %d %s" % (method, path, status, json.dumps(payload, ensure_ascii=False)[:800]))

        return status, payload

    def get(self, path, ok=(200,)):
        return self.call("GET", path, ok=ok)

    def items(self, path):
        """Every item of a listing, following page or cursor."""
        out, page, cursor = [], 1, None

        while True:
            sep = "&" if "?" in path else "?"
            query = "limit=100&" + ("cursor=" + urllib.parse.quote(cursor) if cursor else "page=%d" % page)
            _, payload = self.get(path + sep + query)
            batch = payload.get("items") or []
            out.extend(batch)
            cursor = payload.get("next_cursor") or payload.get("nextCursor")

            if cursor:
                continue

            if len(batch) < 100:
                return out

            page += 1


class Ledger:
    """One scenario's organization and ledger, resolved or created."""

    def __init__(self, midaz, scenario, state):
        self.midaz, self.sc, self.state = midaz, scenario, state
        self.org = self.ledger = None
        self.routes = {}
        self.accounts = {}

    @property
    def lp(self):
        return "/v1/organizations/%s/ledgers/%s" % (self.org, self.ledger)

    def ensure_organization(self):
        wanted = self.sc["organization"]
        found = [o for o in self.midaz.items("/v1/organizations") if o.get("legalName") == wanted["legalName"]]

        if found:
            self.org = found[0]["id"]
        else:
            _, created = self.midaz.call("POST", "/v1/organizations", wanted)
            self.org = created["id"]

        print("organização  %s  %s" % (self.org, wanted["legalName"]))

    def ensure_ledger(self):
        name = self.sc["ledger"]
        base = "/v1/organizations/%s/ledgers" % self.org
        found = [l for l in self.midaz.items(base) if l.get("name") == name]

        if found:
            self.ledger = found[0]["id"]
        else:
            _, created = self.midaz.call("POST", base, {"name": name})
            self.ledger = created["id"]

        # Rotas validadas: sem isso o Midaz não grava route_code nenhum. Tipos de
        # conta validados: um tipo digitado errado vira erro na criação da conta, e
        # não uma rubrica que nunca aparece.
        self.midaz.call("PATCH", self.lp + "/settings",
                        {"accounting": {"validateRoutes": True, "validateAccountType": True}})
        _, settings = self.midaz.get(self.lp + "/settings")
        accounting = (settings or {}).get("accounting") or {}

        if not (accounting.get("validateRoutes") and accounting.get("validateAccountType")):
            fail("o ledger não ficou com validateRoutes e validateAccountType ligados: %s" % settings)

        print("ledger       %s  %s  (validateRoutes, validateAccountType)" % (self.ledger, name))

    def ensure_asset(self):
        assets = self.midaz.items(self.lp + "/assets")

        if not any(a.get("code") == "BRL" for a in assets):
            self.midaz.call("POST", self.lp + "/assets", {"name": "Real", "type": "currency", "code": "BRL"})

        print("ativo        BRL (e @external/BRL)")

    def ensure_account_types(self):
        existing = {t.get("keyValue") for t in self.midaz.items(self.lp + "/account-types")}

        for t in self.sc["accountTypes"]:
            if t["keyValue"] not in existing:
                self.midaz.call("POST", self.lp + "/account-types", t)

        print("tipos        %d" % len(self.sc["accountTypes"]))

    def account(self, alias):
        if alias not in self.accounts:
            # Through the listing: the alias path loses an encoded slash behind the
            # sandbox proxy, so @external/BRL is never found by it.
            listed = {a.get("alias"): a for a in self.midaz.items(self.lp + "/accounts")}
            self.accounts.update(listed)
            self.accounts.setdefault(alias, None)

        return self.accounts[alias]

    def ensure_accounts(self):
        for a in self.sc["accounts"]:
            if self.account(a["alias"]) is None:
                _, created = self.midaz.call("POST", self.lp + "/accounts", {
                    "name": a["name"], "assetCode": "BRL", "type": a["type"], "alias": a["alias"]})
                self.accounts[a["alias"]] = created

        print("contas       %d" % len(self.sc["accounts"]))

    @staticmethod
    def route_key(account):
        return ("type:" + account["type"]) if account.get("routeByType") else account["alias"]

    def ensure_operation_routes(self):
        existing = {r.get("title"): r["id"] for r in self.midaz.items(self.lp + "/operation-routes")}
        planned = {}

        for a in self.sc["accounts"]:
            if not cosif_check(a["code"]):
                fail("conta %s: %s não é uma rubrica COSIF de dez dígitos com DV válido" % (a["alias"], a["code"]))

            key = self.route_key(a)
            if key in planned and planned[key]["code"] != a["code"]:
                fail("o tipo %s leva duas rubricas (%s, %s)" % (a["type"], planned[key]["code"], a["code"]))
            planned[key] = a

        for key, a in planned.items():
            title = "%s %s" % (a["code"], key)

            if title not in existing:
                description = a["name"].split(" — ")[-1]
                rubric = {"code": a["code"], "description": description}
                rule = ({"ruleType": "account_type", "validIf": [a["type"]]} if a.get("routeByType")
                        else {"ruleType": "alias", "validIf": a["alias"]})
                _, created = self.midaz.call("POST", self.lp + "/operation-routes", {
                    "title": title,
                    "description": description,
                    "operationType": "bidirectional",
                    "account": rule,
                    "accountingEntries": {x: {"debit": rubric, "credit": rubric} for x in ROUTE_ACTIONS},
                })
                existing[title] = created["id"]

            self.routes[key] = existing[title]

        print("rotas op.    %d" % len(planned))

    def leg_route(self, alias):
        for a in self.sc["accounts"]:
            if a["alias"] == alias:
                return self.route_key(a)

        fail("lançamento numa conta que o cenário não declara: %s" % alias)

    def transaction_route(self, debit_key, credit_key):
        title = "%s -> %s" % (debit_key, credit_key)
        cache = self.state.setdefault("transactionRoutes", {})

        if title not in cache:
            found = [r for r in self.midaz.items(self.lp + "/transaction-routes") if r.get("title") == title]

            if found:
                cache[title] = found[0]["id"]
            else:
                _, created = self.midaz.call("POST", self.lp + "/transaction-routes", {
                    "title": title,
                    "operationRoutes": [self.routes[debit_key], self.routes[credit_key]],
                })
                cache[title] = created["id"]

        return cache[title]

    def post_transactions(self):
        done = self.state.setdefault("transactions", {})
        slug = self.sc["organization"]["legalDocument"]

        for t in self.sc["transactions"]:
            key = t["key"]

            if key in done and done[key].get("finished"):
                continue

            entry = done.setdefault(key, {})

            if "revert" in t:
                origin = done.get(t["revert"], {}).get("id")
                if not origin:
                    fail("%s estorna %s, que ainda não foi lançado" % (key, t["revert"]))
                _, reverted = self.midaz.call("POST", "%s/transactions/%s/revert" % (self.lp, origin),
                                              idempotency="%s-%s" % (slug, key))
                entry.update(id=reverted["id"], finished=True)
                save_state(self.state)
                print("lançamento   %s  estorno de %s -> %s" % (key, t["revert"], reverted["id"]))
                continue

            if "id" not in entry:
                debit_alias, credit_alias = t["debit"], t["credit"]
                debit_key, credit_key = self.leg_route(debit_alias), self.leg_route(credit_alias)
                body = {
                    "description": t["description"],
                    "routeId": self.transaction_route(debit_key, credit_key),
                    "metadata": {"homologacao": key},
                    "send": {
                        "asset": "BRL", "value": t["amount"],
                        "source": {"from": [{"accountAlias": debit_alias, "chartOfAccounts": "",
                                             "amount": {"asset": "BRL", "value": t["amount"]},
                                             "routeId": self.routes[debit_key]}]},
                        "distribute": {"to": [{"accountAlias": credit_alias, "chartOfAccounts": "",
                                               "amount": {"asset": "BRL", "value": t["amount"]},
                                               "routeId": self.routes[credit_key]}]},
                    },
                }
                if t.get("pending"):
                    body["pending"] = True
                if not t.get("now"):
                    body["transactionDate"] = t["date"]
                _, created = self.midaz.call("POST", self.lp + "/transactions/json", body,
                                             idempotency="%s-%s" % (slug, key))
                entry["id"] = created["id"]
                # Saved before the follow-up runs: if the commit or cancel fails, the
                # next run must find the transaction and not post the hold again —
                # the idempotency key does not outlive Midaz's retention of it.
                save_state(self.state)

            if t.get("then"):
                self.midaz.call("POST", "%s/transactions/%s/%s" % (self.lp, entry["id"], t["then"]),
                                idempotency="%s-%s-%s" % (slug, key, t["then"]))

            entry["finished"] = True
            print("lançamento   %s  %s%s" % (key, entry["id"], ("  -> " + t["then"]) if t.get("then") else ""))
            save_state(self.state)


def operations(lg):
    """Every operation of every account the scenario touches, read through the API."""
    aliases = {a["alias"] for a in lg.sc["accounts"]}
    seen, out = set(), []

    for alias in sorted(aliases):
        account = lg.account(alias)
        if account is None:
            fail("a conta %s não existe; rode setup antes" % alias)
        # The date range is explicit: without it Midaz lists only recent entries, and
        # a scenario dated months back would read as an empty ledger.
        for op in lg.midaz.items("%s/accounts/%s/operations?start_date=2000-01-01&end_date=%s"
                                 % (lg.lp, account["id"], (datetime.date.today() + datetime.timedelta(days=1)).isoformat())):
            if op["id"] not in seen:
                seen.add(op["id"])
                out.append(op)

    return out


def report_ledger(lg):
    ops = operations(lg)
    missing = [o for o in ops if not o.get("routeCode")]
    by_code = {}

    for o in ops:
        code = o.get("routeCode") or "<sem rubrica>"
        amount = Decimal(str((o.get("amount") or {}).get("value") or "0"))
        signed = amount if o.get("direction") == "credit" else -amount
        row = by_code.setdefault(code, {"debit": Decimal(0), "credit": Decimal(0), "net": Decimal(0), "n": 0,
                                        "types": set(), "statuses": set()})
        row[o.get("direction") or "?"] = row.get(o.get("direction") or "?", Decimal(0)) + amount
        row["net"] += signed
        row["n"] += 1
        row["types"].add(o.get("type"))
        row["statuses"].add(((o.get("status") or {}).get("code")) or "")

    print("\n%d operações, %d sem routeCode" % (len(ops), len(missing)))
    print("%-12s %5s %14s %14s %14s  %s" % ("rubrica", "ops", "débitos", "créditos", "créd-déb", "tipos / status"))

    for code in sorted(by_code):
        r = by_code[code]
        print("%-12s %5d %14s %14s %14s  %s / %s" % (
            code, r["n"], r["debit"], r["credit"], r["net"], ",".join(sorted(t or "" for t in r["types"])),
            ",".join(sorted(repr(s) for s in r["statuses"]))))

    total = sum(r["net"] for r in by_code.values())
    print("\nsoma créd-déb de todas as rubricas: %s (zero = partidas dobradas fecham)" % total)

    return ops



DEFAULT_REPORTER = os.environ.get("REPORTER_URL", "http://localhost:4005")
SCHEMA_OF = {"4010": "cadoc-4010/schema/XSD_4010_v0.xsd", "4016": "cadoc-4010/schema/XSD_4010_v0.xsd",
             "4111": "cadoc-4111/schema/XSD_4111.xsd"}
# The 4111 XSD the catalog keeps is v1.0 of 30/03/2023 and contradicts the
# instructions in force (knownGap in the contract): 8-digit codes, at most 25
# accounts, saldoDia >= 0. The 4111 file is judged by the instructions instead.
STALE_SCHEMA = {"4111"}


class Reporter(Midaz):
    def raw(self, method, path, body=None, headers=None, ok=(200, 201)):
        request = urllib.request.Request(self.base + path, data=body, method=method)
        for k, v in (headers or {}).items():
            request.add_header(k, v)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as err:
            if err.code not in ok:
                fail("%s %s -> %d %s" % (method, path, err.code, err.read()[:800]))
            return err.code, dict(err.headers), err.read()


def ensure_institution(rep, sc, org_id, ledger_id):
    """The scenario's institution, scoped to its organization AND its ledger.

    The ledger is part of the scope because an organization can keep more than one:
    a scenario that had to be posted again lives in a ledger of its own, and the
    documents must read that ledger alone.
    """
    cnpj = sc["organization"]["legalDocument"]
    conditions = {"organization_id": {"eq": [org_id]}, "ledger_id": {"eq": [ledger_id]}}
    body = {"name": sc["organization"]["legalName"], "cnpj": cnpj,
            "scope": {"midaz_transaction": {"tables": {"operation": {"conditions": conditions}}}}}
    for i in rep.items("/v1/institutions"):
        if i.get("cnpj") != cnpj:
            continue
        current = (((i.get("scope") or {}).get("midaz_transaction") or {}).get("tables") or {}).get("operation") or {}
        if current.get("conditions") != conditions:
            if i.get("version") is None:
                fail("a instituição %s não informa 'version', e o PUT exige If-Match com ela" % i["id"])
            rep.call("PUT", "/v1/institutions/" + i["id"], body, headers={"If-Match": '"%s"' % i["version"]})
        return i["id"]
    _, created = rep.call("POST", "/v1/institutions", body)
    return created["id"]


def ensure_subscription(rep, document_id, institution):
    _, listed = rep.get("/v1/regulatory/subscriptions?status=active")
    for s in listed.get("items") or []:
        if s.get("documentId") == document_id and s.get("institutionId") == institution:
            return s["id"]
    _, created = rep.call("POST", "/v1/regulatory/subscriptions", {"documentId": document_id, "institution": institution})
    return created["subscription"]["id"]


def structural(line):
    """Whether a line carries YAML structure: not blank, not a comment on its own."""
    stripped = line.strip()

    return bool(stripped) and not stripped.startswith("#")


def inside_block(lines, i, indent):
    """Whether line i still belongs to a mapping whose entries are indented `indent`.

    A blank line or a standalone comment — YAML allows one at any indentation —
    carries no structure of its own: it belongs to the block while the mapping goes
    on after it, and is kept as written either way.
    """
    if structural(lines[i]):
        return len(lines[i]) - len(lines[i].lstrip()) >= indent

    for later in lines[i + 1:]:
        if structural(later):
            return len(later) - len(later.lstrip()) >= indent

    return False


def with_natures(binding, natures):
    """The binding with the scenario's own natures in every natureByPrefix.

    Nature is a property of the client's chart of accounts, not of the catalog: a
    contra-account (a provision, credit-natured inside the asset group) is declared
    by a longer prefix, and the engine takes the longest prefix that matches.

    Idempotent on the text: a prefix the block already declares is left alone when
    its side agrees and rewritten when it does not, so running twice adds nothing
    twice and a binding the scenario already shaped comes back unchanged.
    """
    if not natures:
        return binding

    lines = binding.decode().splitlines(keepends=True)
    out, i = [], 0

    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1

        if line.strip() != "natureByPrefix:":
            continue

        pad = " " * (len(line) - len(line.lstrip()) + 2)
        declared = {}

        # The block's own entries: every following line indented deeper, blank
        # lines included while the mapping goes on after them.
        while i < len(lines) and inside_block(lines, i, len(pad)):
            entry = re.match(r'^\s*"([^"]+)":\s*(\w+)(.*)$', lines[i])
            if entry and entry.group(1) in natures and entry.group(2) != natures[entry.group(1)]:
                lines[i] = '%s"%s": %s%s\n' % (pad, entry.group(1), natures[entry.group(1)], entry.group(3).rstrip("\n"))
            if entry:
                declared[entry.group(1)] = natures.get(entry.group(1), entry.group(2))
            out.append(lines[i])
            i += 1

        out.extend('%s"%s": %s    # natureza do plano de contas deste cenário\n' % (pad, k, v)
                   for k, v in sorted(natures.items()) if k not in declared)

    return "".join(out).encode()


def apply_binding(rep, subscription, binding_path, natures=None):
    """Puts the catalog working tree's binding on the subscription, when it differs."""
    wanted = with_natures(open(binding_path, "rb").read(), natures)
    _, headers, current = rep.raw("GET", "/v1/regulatory/subscriptions/%s/binding" % subscription)
    if current == wanted:
        return "inalterado"
    etag = {k.lower(): v for k, v in headers.items()}.get("etag", "")
    rep.raw("PUT", "/v1/regulatory/subscriptions/%s/binding" % subscription, wanted,
            {"Content-Type": "application/yaml", "If-Match": etag})
    return "aplicado"


def apply_natures_in_force(rep, subscription, natures):
    """Adds the scenario's natures to the binding the subscription already has.

    The reference binding knows the natures by COSIF group; a contra-account
    (the SCFI's provision, credit-natured inside the asset group) is a fact of
    the client's own chart and is what a client adds to the reference. Done here
    whether the binding came from a checkout or from the release, so the answers
    can be judged on either origin.
    """
    if not natures:
        return "em vigor"

    _, headers, current = rep.raw("GET", "/v1/regulatory/subscriptions/%s/binding" % subscription)
    wanted = with_natures(current, natures)
    if wanted == current:
        return "em vigor"

    etag = {k.lower(): v for k, v in headers.items()}.get("etag", "")
    rep.raw("PUT", "/v1/regulatory/subscriptions/%s/binding" % subscription, wanted,
            {"Content-Type": "application/yaml", "If-Match": etag})

    return "em vigor + naturezas"


def expect_refusal(rep, subscription, number, doc):
    """A generation the document must refuse while the caller waits: 400, RPT-0140."""
    status, answer = rep.call("POST", "/v1/regulatory/reports", {
        "subscriptionId": subscription,
        "parameters": {"dataBase": doc["dataBase"], "tipoRemessa": doc.get("tipoRemessa", "I")}}, ok=(200, 201, 400))
    detail = (answer or {}).get("detail", "")
    refused = status == 400 and (answer or {}).get("code") == "RPT-0140"
    print("%-6s %-4s %-10s recusa esperada: %s" % ("OK" if refused else "FALHOU", number, doc["dataBase"],
                                                  detail[:150] if refused else "respondeu %d" % status))
    return 0 if refused else 1


def generate(rep, subscription, data_base, kind="I"):
    _, created = rep.call("POST", "/v1/regulatory/reports", {
        "subscriptionId": subscription, "parameters": {"dataBase": data_base, "tipoRemessa": kind}})
    report = created["report"]["id"]
    for _ in range(60):
        _, got = rep.get("/v1/reports/" + report)
        if got.get("status") != "Processing":
            break
        time.sleep(2)
    status = got.get("status")
    if status in ("Error", "Partial", "Processing"):
        # Processing after the wait is a timeout: downloading would judge an
        # error body as a malformed file.
        return report, status, None
    _, _, artifact = rep.raw("GET", "/v1/reports/%s/download" % report)
    return report, status, artifact


def parsed_lines(artifact):
    """Each account line of a generated file, or None when it is not XML (judge says why)."""
    try:
        root = ET.fromstring(artifact)
    except ET.ParseError:
        return None
    return {c.get("codigoConta"): c.get("saldo") or c.get("saldoDia") for c in root.iter("conta")}


def judge(document, artifact, expected, catalog_root, cnpj8=None):
    """Every problem with one generated file, as a list of sentences."""
    problems = []
    try:
        root = ET.fromstring(artifact)
    except ET.ParseError as err:
        return ["não é XML bem formado: %s" % err]

    # The header identifies the filing: which document, who files it, for when,
    # and whether it is the first remittance or a substitute.
    header = {"codigoDocumento": document, "dataBase": expected["dataBase"],
              "tipoRemessa": expected.get("tipoRemessa", "I")}
    if cnpj8:
        header["cnpj"] = cnpj8
    for attribute, want in header.items():
        if root.get(attribute) != want:
            problems.append("cabeçalho %s=%r, esperado %r" % (attribute, root.get(attribute), want))

    if not artifact.lstrip(b"\xef\xbb\xbf").startswith(b"<?xml"):
        problems.append("o arquivo não começa pela declaração XML")

    schema = os.path.join(catalog_root, "br/bcb", SCHEMA_OF[document])
    if document not in STALE_SCHEMA and shutil.which("xmllint"):
        with tempfile.NamedTemporaryFile(suffix=".xml") as fh:
            fh.write(artifact)
            fh.flush()
            run = subprocess.run(["xmllint", "--noout", "--schema", schema, fh.name], capture_output=True, text=True)
        if run.returncode != 0:
            said = (run.stderr or run.stdout).strip().splitlines()
            problems.append("o XSD oficial recusa: " + (said[0] if said else "xmllint saiu com %d" % run.returncode))

    got = {c.get("codigoConta"): c.get("saldo") or c.get("saldoDia") for c in root.iter("conta")}
    for code in got:
        if not cosif_check(code):
            problems.append("%s não é uma rubrica COSIF de dez dígitos com DV válido" % code)
    if document == "4016":
        for code in got:
            if code[0] in "78":
                problems.append("%s é do grupo %s, que o 4016 não carrega" % (code, code[0]))

    want = expected["lines"]
    for code, value in sorted(want.items()):
        if code not in got:
            problems.append("falta a linha %s (esperado %s)" % (code, value))
        elif Decimal(got[code]) != Decimal(value) or got[code] != value:
            problems.append("%s: gerado %s, esperado %s" % (code, got[code], value))
    for code, value in sorted(got.items()):
        if code in want:
            continue
        if expected.get("complete"):
            problems.append("linha a mais %s = %s" % (code, value))
        elif Decimal(value) != 0:
            problems.append("%s: gerado %s, esperado 0.00" % (code, value))

    return problems


def run_reports(lg, args):
    rep = Reporter(args.reporter)
    with open(args.expected) as fh:
        expected = json.load(fh)

    institution = ensure_institution(rep, lg.sc, lg.org, lg.ledger)
    print("\ninstituição  %s" % institution)
    failures = 0
    generated = {}

    for doc in expected["documents"]:
        number = doc["document"]
        subscription = ensure_subscription(rep, "br.bcb.cadoc-" + number, institution)
        if args.bindings:
            how = apply_binding(rep, subscription, os.path.join(args.bindings, "br/bcb/cadoc-%s/binding.example.yaml" % number),
                                lg.sc.get("natures"))
        else:
            how = apply_natures_in_force(rep, subscription, lg.sc.get("natures"))
        if doc.get("refused"):
            failures += expect_refusal(rep, subscription, number, doc)
            continue

        kind = doc.get("tipoRemessa", "I")
        report, status, artifact = generate(rep, subscription, doc["dataBase"], kind)
        if artifact is None:
            problems = ["a geração terminou em %s" % status]
        else:
            problems = judge(number, artifact, doc, args.catalog, lg.sc["organization"]["legalDocument"][:8])
            lines = parsed_lines(artifact)
            # The cross-check compares the initial remittances; a substitute of the
            # same filing is judged on its own.
            if lines is not None and kind == "I":
                generated[(number, doc["dataBase"])] = lines
            out = os.path.join(args.out, "%s-%s-%s%s.xml" % (lg.sc["organization"]["legalDocument"][:8], number, doc["dataBase"],
                                                            "" if kind == "I" else "-" + kind))
            with open(out, "wb") as fh:
                fh.write(artifact)
        verdict = "OK" if not problems else "FALHOU"
        failures += bool(problems)
        print("%-6s %-4s %-10s %s binding %-10s %-6s report %s" % (verdict, number, doc["dataBase"], kind, how, status, report))
        for p in problems:
            print("         - " + p)

    failures += cross_check(generated)

    return failures


def cosif_prefix(code):
    """The significant prefix of a COSIF code: its levels (1-1-1-2-2-2) without trailing zero levels or the DV."""
    widths, pos, groups = (1, 1, 1, 2, 2, 2), 0, []
    for w in widths:
        groups.append(code[pos:pos + w])
        pos += w
    while groups and set(groups[-1]) == {"0"}:
        groups.pop()
    return "".join(groups)


def non_business_days():
    """The days the catalog's calendar lists, read with the standard library."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "br", "bcb", "cadoc-4111", "dias-nao-uteis.yaml")
    if not os.path.exists(path):
        return set()
    return set(re.findall(r'date:\s*"(\d{4}-\d{2}-\d{2})"', open(path).read()))


def last_business_day(year, month):
    """The last business day of a month: the instructions compare the 4111 of that day with the 4010."""
    holidays = non_business_days()
    day = calendar.monthrange(year, month)[1]
    while True:
        moment = datetime.date(year, month, day)
        if moment.weekday() < 5 and moment.isoformat() not in holidays:
            return day
        day -= 1


def cross_check(generated):
    """The 4111 of a month's last day against that month's 4010, on every rubric both carry.

    The 4111 instructions (§4.2.2.b) require it: on the last day of the month the
    balance — and the volume of a 3.0.9.70 flow account — must match the same
    account in the 4010. Each file can match its own answer and still break this,
    so it is judged between the two files the engine produced.
    """
    failures = 0

    for (number, base), lines in sorted(generated.items()):
        if number != "4111":
            continue
        year, month, day = (int(x) for x in base.split("-"))
        if day != last_business_day(year, month):
            continue
        balancete = generated.get(("4010", "%04d-%02d" % (year, month)))
        if balancete is None:
            continue
        common = set(lines) & set(balancete)
        broken = []
        # A 4111 line with a balance has to be in the 4010 too: the 4010 may omit an
        # account only when its balance is zero (leiaute §3.2.2.a). A parent the
        # ledger never posts to — Disponibilidades — is exactly the line it omits.
        for code in sorted(set(lines) - set(balancete)):
            if Decimal(lines[code]) == 0:
                continue
            children = sorted(c for c in balancete if c.startswith(cosif_prefix(code)))
            why = (" — conta-mãe das rubricas %s do razão" % ", ".join(children)) if children else ""
            broken.append("%s: 4111 %s, ausente do 4010%s" % (code, lines[code], why))
        for code in sorted(common):
            if Decimal(lines[code]) == Decimal(balancete[code]):
                continue
            children = sorted(c for c in balancete if c != code and c.startswith(cosif_prefix(code)))
            why = (" — o 4010 não traz a conta-mãe somada: %s tem filhas no razão (%s), e as instruções pedem que o "
                   "saldo da conta coincida com o 4111" % (code, ", ".join(children))) if children else ""
            broken.append("%s: 4111 %s, 4010 %s%s" % (code, lines[code], balancete[code], why))
        verdict = "OK" if not broken else "FALHOU"
        failures += bool(broken)
        print("%-6s 4111 %s x 4010 %04d-%02d: mesmo saldo nas %d rubricas em comum, e toda linha com saldo do 4111 no 4010" % (
            verdict, base, year, month, len(common)))
        for b in broken:
            print("         - " + b)

    return failures

def state_belongs_to(lg, state):
    """Whether a state with no recorded ledger was written against the ledger found.

    Every transaction it recorded has to exist there: a state can mix transactions
    of two ledgers (an old run's, then a new run's), and one found is not proof of
    the rest.
    """
    if "ledger" in state:
        return True

    posted = [t.get("id") for t in (state.get("transactions") or {}).values() if t.get("id")]

    for transaction in posted:
        status, _ = lg.midaz.call("GET", "%s/transactions/%s" % (lg.lp, transaction), ok=(200, 404))
        if status != 200:
            return False

    return True


STATE_PATH = None


def save_state(state):
    with open(STATE_PATH, "w") as fh:
        json.dump(state, fh, indent=2, sort_keys=True)


def main():
    global STATE_PATH

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["setup", "ledger", "reports"])
    parser.add_argument("scenario")
    parser.add_argument("--midaz", default=DEFAULT_MIDAZ)
    parser.add_argument("--reporter", default=DEFAULT_REPORTER)
    parser.add_argument("--expected", help="gabarito (padrão: expected/<cenário>.json)")
    parser.add_argument("--bindings", help="raiz de um catálogo cujos binding.example.yaml são aplicados às assinaturas antes de gerar")
    parser.add_argument("--catalog", default=os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..")))
    parser.add_argument("--out", default=tempfile.gettempdir(), help="onde guardar os arquivos gerados")
    args = parser.parse_args()

    with open(args.scenario) as fh:
        scenario = json.load(fh)

    STATE_PATH = os.path.splitext(args.scenario)[0] + ".state.json"
    state = json.load(open(STATE_PATH)) if os.path.exists(STATE_PATH) else {}

    lg = Ledger(Midaz(args.midaz), scenario, state)
    lg.ensure_organization()
    lg.ensure_ledger()

    # The state is one ledger's: a scenario moved to a new ledger posts everything
    # again there, instead of skipping what it posted in the old one. A state
    # written before it recorded its ledger is adopted only when a transaction it
    # recorded exists in the ledger found; otherwise it is another ledger's.
    if state.get("ledger", lg.ledger) != lg.ledger or not state_belongs_to(lg, state):
        state.clear()
    state["ledger"] = lg.ledger

    if args.command == "setup":
        lg.ensure_asset()
        lg.ensure_account_types()
        lg.ensure_accounts()
        lg.ensure_operation_routes()
        lg.post_transactions()
        save_state(state)

    if args.command == "reports":
        args.expected = args.expected or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.scenario))),
                                                      "expected", os.path.basename(args.scenario))
        sys.exit(1 if run_reports(lg, args) else 0)

    report_ledger(lg)


if __name__ == "__main__":
    main()
