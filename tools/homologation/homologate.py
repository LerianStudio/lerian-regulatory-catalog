#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
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

Um cenário sem ledger é só de organização (o cadastro do declarante da
e-Financeira lê dela CNPJ, nome e endereço): o setup a cria com o endereço.

Só biblioteca padrão, Python 3.9+, e xmllint para o XSD.

    python3 tools/homologation/homologate.py setup  tools/homologation/scenario/a-pagare-ip.json
    python3 tools/homologation/homologate.py ledger tools/homologation/scenario/a-pagare-ip.json
"""

import argparse
import atexit
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
from zoneinfo import ZoneInfo

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
            # Sem `page` na primeira: as listas por cursor (relatórios) recusam o
            # parâmetro, e as por página começam na primeira sem ele.
            query = "limit=100" + ("&cursor=" + urllib.parse.quote(cursor) if cursor
                                   else "&page=%d" % page if page > 1 else "")
            _, payload = self.get(path + sep + query)
            batch = payload.get("items") or []
            out.extend(batch)
            cursor = payload.get("next_cursor") or payload.get("nextCursor")

            if cursor:
                continue

            # A listing by cursor answers no `page`: with no next cursor it is over,
            # even on a full last batch (asking `page` of it is refused).
            if "page" not in payload or len(batch) < 100:
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

    def ensure_organization(self, create=True):
        wanted = self.sc["organization"]
        found = [o for o in self.midaz.items("/v1/organizations") if o.get("legalName") == wanted["legalName"]]

        if found:
            self.org = found[0]["id"]
        elif not create:
            fail("a organização '%s' não existe neste Midaz; rode setup antes" % wanted["legalName"])
        else:
            _, created = self.midaz.call("POST", "/v1/organizations", wanted)
            self.org = created["id"]

        print("organização  %s  %s" % (self.org, wanted["legalName"]))

    def ensure_ledger(self, create=True):
        name = self.sc["ledger"]
        base = "/v1/organizations/%s/ledgers" % self.org
        found = [l for l in self.midaz.items(base) if l.get("name") == name]

        if found:
            self.ledger = found[0]["id"]
        elif not create:
            fail("o ledger '%s' não existe neste Midaz; rode setup antes" % name)
        else:
            _, created = self.midaz.call("POST", base, {"name": name})
            self.ledger = created["id"]

        # Rotas validadas: sem isso o Midaz não grava route_code nenhum. Tipos de
        # conta validados: um tipo digitado errado vira erro na criação da conta, e
        # não uma rubrica que nunca aparece. Só o setup escreve; reports e ledger
        # apenas conferem.
        if create:
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

    def ensure_balances(self):
        """Create the additional balances an account declares (a `bloqueio` key, say).

        A balance is a bucket of the same account, under the same rubric: moving an
        amount between two of them changes what can be spent, not what is owed.
        """
        for a in self.sc["accounts"]:
            wanted = a.get("balances") or []
            if not wanted:
                continue
            account = self.account(a["alias"])
            existing = {b.get("key") for b in self.midaz.items("%s/accounts/%s/balances" % (self.lp, account["id"]))}
            for key in wanted:
                if key not in existing:
                    self.midaz.call("POST", "%s/accounts/%s/balances" % (self.lp, account["id"]),
                                    {"key": key, "allowSending": True, "allowReceiving": True})
            print("saldos       %s  %s" % (a["alias"], ", ".join(["default"] + wanted)))

    def ensure_overdraft(self):
        """Turn on the overdraft of every account that declares one.

        Midaz keeps it on the BALANCE, not the account: the default balance gets
        allowOverdraft (and a limit, when declared), and Midaz creates the internal
        `overdraft` companion balance on its own. A debit beyond what is available
        then splits: the covered part stays on the account's rubric and the draw is
        a companion operation (type OVERDRAFT) on the route's `overdraft` rubric.
        """
        for a in self.sc["accounts"]:
            od = a.get("overdraft")
            if not od:
                continue
            account = self.account(a["alias"])
            balances = self.midaz.items("%s/accounts/%s/balances" % (self.lp, account["id"]))
            default = next((b for b in balances if b.get("key") == "default"), None)
            if default is None:
                fail("a conta %s não tem o saldo default" % a["alias"])
            settings = {"allowOverdraft": True, "overdraftLimitEnabled": bool(od.get("limit"))}
            if od.get("limit"):
                settings["overdraftLimit"] = od["limit"]
            current = default.get("settings") or {}
            if not all(current.get(k) == v for k, v in settings.items()):
                self.midaz.call("PATCH", "%s/balances/%s" % (self.lp, default["id"]), {"settings": settings})
            print("cheque esp.  %s  rubrica %s%s" % (a["alias"], od["rubric"],
                                                    ("  limite " + od["limit"]) if od.get("limit") else ""))

    @staticmethod
    def route_key(account):
        return ("type:" + account["type"]) if account.get("routeByType") else account["alias"]

    def ensure_operation_routes(self):
        existing = {r.get("title"): r["id"] for r in self.midaz.items(self.lp + "/operation-routes")}
        planned = {}

        for a in self.sc["accounts"]:
            if not cosif_check(a["code"]):
                fail("conta %s: %s não é uma rubrica COSIF de dez dígitos com DV válido" % (a["alias"], a["code"]))
            od = (a.get("overdraft") or {}).get("rubric")
            if od and not cosif_check(od):
                fail("conta %s: a rubrica do cheque especial %s não é COSIF de dez dígitos com DV válido" % (a["alias"], od))

            key = self.route_key(a)
            if key in planned and planned[key]["code"] != a["code"]:
                fail("o tipo %s leva duas rubricas (%s, %s)" % (a["type"], planned[key]["code"], a["code"]))
            if key in planned and planned[key].get("overdraft") != a.get("overdraft"):
                # One route serves every account of the type: two cheque-especial
                # rubrics on it would leave one account's draw on the other's rubric.
                fail("o tipo %s leva dois cheques especiais diferentes (%s, %s); declare as contas por alias"
                     % (a["type"], planned[key].get("overdraft"), a.get("overdraft")))
            planned[key] = a

        for key, a in planned.items():
            od = a.get("overdraft")
            title = "%s %s%s" % (a["code"], key, (" +od " + od["rubric"]) if od else "")

            if title not in existing:
                description = a["name"].split(" — ")[-1]
                rubric = {"code": a["code"], "description": description}
                rule = ({"ruleType": "account_type", "validIf": [a["type"]]} if a.get("routeByType")
                        else {"ruleType": "alias", "validIf": a["alias"]})
                entries = {x: {"debit": rubric, "credit": rubric} for x in ROUTE_ACTIONS}
                if od:
                    # Where the draw is booked: with validateRoutes, Midaz refuses a
                    # debit that needs the overdraft when the route has no rubric for
                    # it (0492). Use and repayment land on the same rubric.
                    od_rubric = {"code": od["rubric"], "description": od["description"]}
                    entries["overdraft"] = {"debit": od_rubric, "credit": od_rubric}
                _, created = self.midaz.call("POST", self.lp + "/operation-routes", {
                    "title": title,
                    "description": description,
                    "operationType": "bidirectional",
                    "account": rule,
                    "accountingEntries": entries,
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
        # The operation routes' ids are in the title: an operation route replaced
        # (a cheque-especial rubric changed, say) makes a new transaction route,
        # instead of the old one going on pointing at the old rubric.
        debit_route, credit_route = self.routes[debit_key], self.routes[credit_key]
        title = "%s -> %s [%s %s]" % (debit_key, credit_key, debit_route[-8:], credit_route[-8:])
        cache = self.state.setdefault("transactionRoutes", {})

        if title not in cache:
            found = [r for r in self.midaz.items(self.lp + "/transaction-routes") if r.get("title") == title]

            if found:
                cache[title] = found[0]["id"]
            else:
                _, created = self.midaz.call("POST", self.lp + "/transaction-routes", {
                    "title": title,
                    "operationRoutes": [debit_route, credit_route],
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
                source = {"accountAlias": debit_alias, "chartOfAccounts": "",
                          "amount": {"asset": "BRL", "value": t["amount"]}, "routeId": self.routes[debit_key]}
                target = {"accountAlias": credit_alias, "chartOfAccounts": "",
                          "amount": {"asset": "BRL", "value": t["amount"]}, "routeId": self.routes[credit_key]}
                # A leg may name a balance of its account other than `default`: a
                # block moves an amount from `default` to `bloqueio` and back.
                if t.get("debitBalance"):
                    source["balanceKey"] = t["debitBalance"]
                if t.get("creditBalance"):
                    target["balanceKey"] = t["creditBalance"]
                body = {
                    "description": t["description"],
                    "routeId": self.transaction_route(debit_key, credit_key),
                    "metadata": {"homologacao": key},
                    "send": {
                        "asset": "BRL", "value": t["amount"],
                        "source": {"from": [source]},
                        "distribute": {"to": [target]},
                    },
                }
                if t.get("pending"):
                    body["pending"] = True
                if not t.get("now"):
                    body["transactionDate"] = t["date"]
                # An ANNOTATION (NOTED) is a transaction that moves no balance: Midaz
                # writes its operations with balance_affected = false, rubric and
                # amount included, so a document must leave them out.
                endpoint = "/transactions/annotation" if t.get("annotation") else "/transactions/json"
                # A BLOCK or UNBLOCK is a plain transaction whose operations Midaz
                # types BLOCK/UNBLOCK: available moves between two balances.
                if t.get("kind") in ("block", "unblock"):
                    endpoint = "/transactions/" + t["kind"]
                _, created = self.midaz.call("POST", self.lp + endpoint, body,
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


def operations(lg, attempts=15):
    """Every operation of every account the scenario touches, read through the API.

    Midaz writes a transaction's operations ASYNCHRONOUSLY: right after setup posts,
    the last transactions may not be listed yet, and a ledger read then does not
    close. The read is repeated until every transaction setup recorded shows up.
    """
    posted = {t.get("id") for t in (lg.state.get("transactions") or {}).values() if t.get("id")}
    previous = None
    for attempt in range(attempts):
        out = read_operations(lg)
        ids = {o.get("id") for o in out}
        # Every transaction listed is not enough — one leg of a transaction can be
        # listed while another (an overdraft companion) is not yet — so the read
        # is accepted when it also comes back identical twice in a row.
        if posted <= {o.get("transactionId") for o in out} and ids == previous:
            return out
        previous = ids
        time.sleep(2)
    missing = posted - {o.get("transactionId") for o in out}
    fail("%d lançamento(s) registrados pelo setup ainda sem operações no Midaz depois de %ds: %s"
         % (len(missing), 2 * attempts, ", ".join(sorted(missing))[:300]))


def read_operations(lg):
    """One read of every operation of every account the scenario touches."""
    # readAlso: accounts the scenario does not declare but Midaz posts to — the
    # @external/BRL that closes each part of a cross-ledger entry.
    aliases = {a["alias"] for a in lg.sc["accounts"]} | set(lg.sc.get("readAlso", []))
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
    # An annotation (NOTED) moves no balance and is no entry of a document; the
    # ledger check leaves it out the way every binding must.
    annotations = [o for o in ops if o.get("balanceAffected") is False]
    ops = [o for o in ops if o.get("balanceAffected") is not False]
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

    print("\n%d operações, %d sem routeCode, %d anotações (NOTED) deixadas de fora" % (len(ops), len(missing), len(annotations)))
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
STALE_SCHEMA = set()  # the 4111 XSD the catalog keeps is the one in force since 02/01/2025


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


def ensure_institution(rep, sc, org_id):
    """The scenario's institution: the Midaz ORGANIZATION, whatever ledgers it keeps.

    The organization is the institution and carries its CNPJ; every ledger in it is
    one of that institution's books, so the scope is the organization alone and a
    ledger added later is filed without touching the institution. A scenario that
    has to be posted again goes to a new organization, never to a second ledger of
    the same one: that second ledger would be read into the same documents.
    """
    cnpj = sc["organization"]["legalDocument"]
    conditions = {"organization_id": {"eq": [org_id]}}
    # The declarant's CNPJ is read from the organization itself (onboarding's
    # organization.legal_document), so the scope covers that table too: its own row.
    scope = {"midaz_transaction": {"tables": {"operation": {"conditions": conditions}}},
             "midaz_onboarding": {"tables": {"organization": {"conditions": {"id": {"eq": [org_id]}}}}}}
    body = {"name": sc["organization"]["legalName"], "cnpj": cnpj, "scope": scope}
    for i in rep.items("/v1/institutions"):
        if i.get("cnpj") != cnpj:
            continue
        if (i.get("scope") or {}) != scope:
            if i.get("version") is None:
                fail("a instituição %s não informa 'version', e o PUT exige If-Match com ela" % i["id"])
            rep.call("PUT", "/v1/institutions/" + i["id"], body, headers={"If-Match": '"%s"' % i["version"]})
        return i["id"]
    _, created = rep.call("POST", "/v1/institutions", body)
    return created["id"]


def ensure_subscription(rep, document_id, institution, version=None):
    """The active subscription of a document for the institution, pinned to `version`.

    A subscription made by an earlier run stays pinned to what it adopted then: the
    Reporter never moves a pin on its own. Homologating a checkout means judging
    THAT checkout's contract, so a pin on another version is replaced: deactivated
    (kept, with its reports) and subscribed afresh, which pins the newest version the
    origin serves. Adopting would keep the subscription, but adoption is signed by a
    person, and a stack with authentication off has nobody to sign it.
    """
    _, listed = rep.get("/v1/regulatory/subscriptions?status=active")
    current = None
    for s in listed.get("items") or []:
        if s.get("documentId") == document_id and s.get("institutionId") == institution:
            if not version or s.get("adoptedVersion") == version:
                return s["id"]
            current = s

    # Nothing is deactivated before the Reporter is known to carry the checkout's
    # version: a run that cannot homologate this checkout leaves the subscription
    # in force as it found it.
    if version:
        # The LIST answers the catalog the deployment carries, subscribed or not;
        # GET /documents/{id} is the tenant's view and 404s with no subscription.
        _, listed_docs = rep.get("/v1/regulatory/documents")
        carried = next((d.get("version") for d in listed_docs.get("items") or [] if d.get("id") == document_id), None)
        if carried != version:
            fail("%s: o Reporter carrega a %s e o checkout declara %s; a origem do Reporter não serve este checkout "
                 "(monte-o em REGULATORY_CATALOG_DIR). Nenhuma assinatura foi alterada"
                 % (document_id, carried or "nenhuma", version))

    if current:
        rep.raw("DELETE", "/v1/regulatory/subscriptions/" + current["id"])
        print("substituída %s em %s" % (document_id, current.get("adoptedVersion")))

    try:
        _, created = rep.call("POST", "/v1/regulatory/subscriptions", {"documentId": document_id, "institution": institution})
    except (SystemExit, Exception):
        # The replacement was not made (refused, or the connection dropped): the
        # subscription this run deactivated comes back before the run stops.
        restore_subscription(rep, document_id, current)
        raise
    pinned = created["subscription"].get("adoptedVersion")
    if version and pinned != version:
        # The origin pinned another version after all: the new subscription goes,
        # the one this run replaced comes back as it was.
        restored = restore_subscription(rep, document_id, current, created["subscription"]["id"])
        fail("%s assinado em %s, e o checkout declara %s; %s" % (
            document_id, pinned, version,
            "a assinatura anterior foi restaurada" if restored else "a assinatura anterior NÃO pôde ser restaurada (ver acima)"))
    return created["subscription"]["id"]


def restore_subscription(rep, document_id, current, replacement=None):
    """Undo a replacement: deactivate the new subscription, reactivate the old one.

    Answers whether the old one is back in force. A failure here is reported on its
    own line and never raised: the caller is already stopping for another reason,
    and that reason is the one the run ends with.
    """
    if replacement:
        try:
            rep.raw("DELETE", "/v1/regulatory/subscriptions/" + replacement)
        except (SystemExit, Exception) as removing:
            # The replacement stays in force, pinned to the version this run
            # refused; the old one cannot come back beside it (one active
            # subscription per document), so it is not tried.
            print("ERRO: a assinatura nova %s (%s) continua ATIVA, presa à versão errada, e não pôde ser desativada: %s"
                  % (replacement, document_id, removing), file=sys.stderr)
            if current:
                print("ERRO: a assinatura anterior %s (%s) continua desativada" % (current["id"], document_id),
                      file=sys.stderr)
            return False
    if current:
        try:
            rep.call("POST", "/v1/regulatory/subscriptions/%s/reactivate" % current["id"], {})
        except (SystemExit, Exception) as restoring:
            print("ERRO: a assinatura anterior %s (%s) ficou desativada e não pôde ser reativada: %s"
                  % (current["id"], document_id, restoring), file=sys.stderr)
            return False
        print("restaurada  %s em %s" % (document_id, current.get("adoptedVersion")))
    return True


def document_dir(document):
    """Where a document lives in a catalog checkout: br.rfb.efinanceira-cad-declarante
    is br/rfb/efinanceira-cad-declarante; a bare CADOC number (4010) is br/bcb/cadoc-4010."""
    if "." not in document:
        document = "br.bcb.cadoc-" + document
    return os.path.join(*document.split(".", 2))


def contract_version(root, number):
    """The version a catalog checkout declares for a document's contract (a CADOC number or a document id)."""
    with open(os.path.join(root, document_dir(number), "contract.yaml")) as fh:
        # metadata.version, quoted or not: `version: "1.0.0"` is the same 1.0.0.
        found = re.search(r"""^  version:\s*["']?([^"'\s#]+)["']?""", fh.read(), re.M)
    return found.group(1) if found else None


def apply_binding(rep, subscription, binding_path):
    """Puts the catalog working tree's binding on the subscription, when it differs."""
    wanted = open(binding_path, "rb").read()
    _, headers, current = rep.raw("GET", "/v1/regulatory/subscriptions/%s/binding" % subscription)
    if current == wanted:
        return "inalterado"
    etag = {k.lower(): v for k, v in headers.items()}.get("etag", "")
    rep.raw("PUT", "/v1/regulatory/subscriptions/%s/binding" % subscription, wanted,
            {"Content-Type": "application/yaml", "If-Match": etag})
    return "aplicado"


def period_closed(data_base, now=None):
    """Whether a data-base names a period already over in Brasília, the regulatory day.

    The contracts declare `closed: true`: a month is generable from the first day of
    the next, a day from the day after. A scenario dated ahead of today is then an
    expected refusal, and the same scenario generates and is judged once it closes.
    """
    from zoneinfo import ZoneInfo
    now = now or datetime.datetime.now(ZoneInfo("America/Sao_Paulo"))
    if len(data_base) == 7:
        year, month = int(data_base[:4]), int(data_base[5:])
        closes = datetime.date(year + month // 12, month % 12 + 1, 1)
    else:
        closes = datetime.date.fromisoformat(data_base) + datetime.timedelta(days=1)
    return now.date() >= closes


def expect_refusal(rep, subscription, number, doc, reason=None):
    """A generation the document must refuse while the caller waits: 400, RPT-0140."""
    status, answer = rep.call("POST", "/v1/regulatory/reports", {
        "subscriptionId": subscription,
        "parameters": {"dataBase": doc["dataBase"], "tipoRemessa": doc.get("tipoRemessa", "I")}}, ok=(200, 201, 400))
    detail = (answer or {}).get("detail", "")
    refused = status == 400 and (answer or {}).get("code") == "RPT-0140" and (reason is None or reason in detail)
    print("%-6s %-4s %-10s recusa esperada: %s" % ("OK" if refused else "FALHOU", number, doc["dataBase"],
                                                  detail[:150] if refused else "respondeu %d" % status))
    return 0 if refused else 1


def worker_log_since(started):
    """What the worker logged since `started`, or None when its log cannot be read.

    The Reporter records only a generic message on an errored report; the refusal
    itself is in the worker's log. REPORTER_WORKER_CONTAINER names the container
    (the local stack's by default).
    """
    container = os.environ.get("REPORTER_WORKER_CONTAINER", "midaz-reporter-worker")
    since = (started - datetime.timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        done = subprocess.run(["docker", "logs", "--since", since, container], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout + done.stderr if done.returncode == 0 else None


def recorded_refusal(rep, report):
    """The refusal the Reporter recorded on an errored report (code and message), or ''.

    A refusal the engine wrote — a rule of the contract, a read that answered
    nothing — is kept in the report's metadata (error_code, error); a technical
    failure keeps only a generic line there, and the worker's log is where to look.
    """
    if rep is None:
        return ""
    _, got = rep.get("/v1/reports/" + report)
    metadata = (got or {}).get("metadata") or {}
    return " ".join(str(metadata.get(k) or "") for k in ("error_code", "error"))


def expect_error(number, doc, status, report, started, rep=None):
    """A generation the worker must refuse, for the reason the gabarito names.

    The reason is looked for first in what the Reporter recorded on the report,
    then in the worker's log.
    """
    wanted = doc.get("errorContains") or []
    problem = None
    if status != "Error":
        problem = "terminou em %s" % status
    elif wanted and all(w in recorded_refusal(rep, report) for w in wanted):
        problem = None
    elif wanted:
        logged = worker_log_since(started)
        if logged is None:
            problem = "terminou em Error, e o log do worker não pôde ser lido para confirmar o motivo"
        else:
            # The refusal line does not carry the report id, but it carries the
            # trace of the generation, and other lines of that trace do carry the
            # id: only a refusal on THIS report's trace counts.
            traces = set()
            for line in logged.splitlines():
                if report in line:
                    traces.update(re.findall(r'"trace_id": "([0-9a-f]+)"', line))
            refusals = [line for line in logged.splitlines()
                        if all(w in line for w in wanted) and any(t in line for t in traces)]
            if not refusals:
                problem = "terminou em Error, mas não pelo motivo esperado (%s)" % " + ".join(wanted)
    print("%-6s %-4s %-10s erro esperado: %s, report %s" % ("OK" if not problem else "FALHOU", number,
                                                           doc.get("dataBase") or doc.get("label", ""),
                                                           problem or "Error, " + " + ".join(wanted), report))
    return 0 if not problem else 1


def request_report(rep, subscription, parameters):
    """Asks the Reporter for a generation with these parameters and waits for it to leave Processing.

    Answers the report id and the report as last read (Processing after the wait
    is a timeout).
    """
    _, created = rep.call("POST", "/v1/regulatory/reports", {"subscriptionId": subscription, "parameters": parameters})
    report = created["report"]["id"]
    for _ in range(60):
        _, got = rep.get("/v1/reports/" + report)
        if got.get("status") != "Processing":
            break
        time.sleep(2)
    return report, got


def generate(rep, subscription, data_base, kind="I"):
    report, got = request_report(rep, subscription, {"dataBase": data_base, "tipoRemessa": kind})
    status = got.get("status")
    if status in ("Error", "Partial", "Processing"):
        # Processing after the wait is a timeout: downloading would judge an
        # error body as a malformed file.
        return report, status, None
    _, _, artifact = rep.raw("GET", "/v1/reports/%s/download" % report)
    return report, status, artifact


def approved_original(rep, subscription, data_base):
    """The original of a period an earlier run approved, or None."""
    for r in rep.items("/v1/reports?regulatory=true&subscription_id=%s" % subscription):
        if (r.get("status") == "Final" and r.get("remittance") == "original"
                and (r.get("parameters") or {}).get("dataBase") == data_base):
            return r
    return None


def approve(rep, report):
    """Approves a draft at the version it is in, and answers its new status."""
    _, got = rep.get("/v1/reports/" + report)
    rep.call("POST", "/v1/regulatory/reports/%s/approve" % report,
             headers={"If-Match": '"%s"' % got.get("draftVersion")})
    _, got = rep.get("/v1/reports/" + report)
    return got.get("status")


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


def load_expected(args):
    """The gabarito, checked and with its dates filled, before anything is generated.

    Every refusal here (an ambiguous event entry, a date the setup did not record)
    stops the run before the Reporter is asked for anything.
    """
    with open(args.expected) as fh:
        expected = json.load(fh)
    check_event_entries(expected["documents"])
    for doc in expected["documents"]:
        if "dataBase" not in doc:
            # A document with no period (an e-Financeira event) is generated by its
            # parameters alone, and has no date to fill in.
            continue
        for token, value in (getattr(args, "dates", None) or {}).items():
            doc["dataBase"] = doc["dataBase"].replace(token, value)
        if "{" in doc["dataBase"]:
            fail("o gabarito usa %s e o setup não registrou a data dos lançamentos cross-ledger; rode setup antes"
                 % doc["dataBase"])
    return expected


def run_reports(lg, args):
    expected = load_expected(args)
    rep = Reporter(args.reporter)

    institution = ensure_institution(rep, lg.sc, lg.org)
    print("\ninstituição  %s" % institution)
    failures = 0
    generated = {}
    events = {"subscriptions": {}, "ids": [], "bases": {}, "reports": {}}
    # The bindings an entry replaced go back when the run ends, however it ends
    # (fail() exits): the next run starts from the binding this one found.
    atexit.register(restore_bindings, rep, events["bases"])

    for doc in expected["documents"]:
        if doc.get("documentId") in EVENT_DOCUMENTS:
            failures += run_event(rep, lg, args, doc, institution, events)
            continue
        number = doc["document"]
        subscription = ensure_subscription(rep, "br.bcb.cadoc-" + number, institution,
                                           contract_version(args.bindings, number) if args.bindings else None)
        # A natureza de cada rubrica é regra do contrato, não do cenário: o binding
        # em vigor (da release ou do checkout) é o que a assinatura usa.
        how = "em vigor"
        if args.bindings:
            how = apply_binding(rep, subscription, os.path.join(args.bindings, "br/bcb/cadoc-%s/binding.example.yaml" % number))
        if doc.get("refused"):
            failures += expect_refusal(rep, subscription, number, doc)
            continue
        if not period_closed(doc["dataBase"]):
            # Not closed yet: refused today, generated and judged once it closes.
            failures += expect_refusal(rep, subscription, number, doc, reason="has not closed")
            continue

        kind = doc.get("tipoRemessa", "I")
        started = datetime.datetime.now(datetime.timezone.utc)
        # A SUBSTITUIÇÃO SÓ EXISTE DEPOIS DA ORIGINAL APROVADA (RPT-0198), e uma
        # original aprovada não se gera de novo (RPT-0197). Quando o gabarito traz a
        # substituição de um período, a original é aprovada depois de julgada; numa
        # execução seguinte, a já aprovada é a que se julga.
        replaced = kind == "I" and any(
            other["document"] == number and other["dataBase"] == doc["dataBase"]
            and other.get("tipoRemessa", "I") != "I" for other in expected["documents"])
        final = approved_original(rep, subscription, doc["dataBase"]) if replaced else None
        if final:
            report, status = final["id"], "Final"
            _, _, artifact = rep.raw("GET", "/v1/reports/%s/download" % report)
        else:
            report, status, artifact = generate(rep, subscription, doc["dataBase"], kind)
        if doc.get("errored"):
            # Refused by the worker: the read answered nothing the document can be
            # filed from. An Error alone proves nothing — any failure ends there —
            # so the refusal the gabarito names has to be in the report's recorded
            # refusal or, failing that, in the worker's log.
            failures += expect_error(number, doc, status, report, started, rep)
            continue
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
        if replaced and not final and artifact is not None and not problems:
            status = approve(rep, report)
        verdict = "OK" if not problems else "FALHOU"
        failures += bool(problems)
        print("%-6s %-4s %-10s %s binding %-10s %-6s report %s" % (verdict, number, doc["dataBase"], kind, how, status, report))
        for p in problems:
            print("         - " + p)

    failures += cross_check(generated)

    return failures


# ---------------------------------------------------------------------------
# Eventos da e-Financeira: sem data-base, gerados por parâmetros.
#
# O evtCadDeclarante não tem data-base nem tipoRemessa: cada geração é a mesma
# entrega da instituição (`filing.period: []`), original (`indRetificacao` 1) ou
# retificação (2 ou 3, com o `nrRecibo` do evento retificado). As exclusões
# (evtExclusao, evtExclusaoeFinanceira) não têm remessa: cada recibo excluído é a
# sua entrega (`filing.period: [nrReciboEvento]`), e não há original a aprovar
# antes. O gabarito traz, por entrada, os parâmetros da geração e o valor esperado
# de cada elemento.
# ---------------------------------------------------------------------------

EVENT_DOCUMENTS = {
    "br.rfb.efinanceira-cad-declarante": {
        "schema": "schema/evtCadDeclarante-v1_5_0.xsd",
        "namespace": "http://www.eFinanceira.gov.br/schemas/evtCadDeclarante/v1_5_0",
        "event": "evtCadDeclarante",
        # O parâmetro da remessa e o valor do original (filing.remittance do contrato).
        "original": ("indRetificacao", "1"),
    },
    # As exclusões não declaram filing.remittance: sem `original`, nenhuma entrada
    # é tratada como original (nem procurada aprovada, nem julgada antes de outra).
    "br.rfb.efinanceira-exclusao": {
        "schema": "schema/evtExclusao-v1_5_0.xsd",
        "namespace": "http://www.eFinanceira.gov.br/schemas/evtExclusao/v1_5_0",
        "event": "evtExclusao",
    },
    "br.rfb.efinanceira-exclusao-efinanceira": {
        "schema": "schema/evtExclusaoeFinanceira-v1_5_0.xsd",
        "namespace": "http://www.eFinanceira.gov.br/schemas/evtExclusaoeFinanceira/v1_5_0",
        "event": "evtExclusaoeFinanceira",
    },
}


def is_event_original(document_id, parameters):
    """Whether an entry's parameters make the document's original remittance.

    A document without a remittance (no `original` in EVENT_DOCUMENTS) has no
    original: every generation is just generated, and an approved one is never
    looked up to be judged in its place.
    """
    original = EVENT_DOCUMENTS[document_id].get("original")
    if original is None:
        return False
    parameter, value = original
    return (parameters or {}).get(parameter) == value

# O id do evento: "ID" + os 18 dígitos que o motor gera. Conferido pela forma e,
# ao longo da execução, maior que os anteriores — nunca pelo valor, que muda a cada
# geração. O número começa pelos milissegundos da geração, e as gerações da
# execução são uma depois da outra; com mais de um worker, isso vale enquanto os
# relógios deles concordam.
EVENT_ID = re.compile(r"^ID[0-9]{18}$")

# A assinatura no XSD oficial: o import do XMLDSig e a referência ao elemento.
# O Reporter entrega o evento sem assinatura (assinar é da borda que transmite),
# então o arquivo é validado contra uma cópia do XSD oficial sem as duas.
SIGNATURE_IMPORT = re.compile(r'[ \t]*<xs:import\s+namespace="http://www\.w3\.org/2000/09/xmldsig#"[^>]*/>\r?\n?')
SIGNATURE_ELEMENT = re.compile(r'[ \t]*<xs:element\s+ref="ds:Signature"\s*/>\r?\n?')

_RELAXED = {}


def relaxed_schema(official):
    """A copy of the official XSD without the signature, derived now.

    The shipped file never changes: the copy is written to a temporary directory
    on every run, so it cannot drift from the official one. Removed are the
    import of the XMLDSig schema and the `ds:Signature` element — each exactly
    once; an official file of another shape stops the run instead of being
    half-derived.
    """
    if official in _RELAXED:
        return _RELAXED[official]
    with open(official, encoding="utf-8-sig") as fh:
        text = fh.read()
    for name, pattern in (("o import do xmldsig", SIGNATURE_IMPORT), ("o elemento ds:Signature", SIGNATURE_ELEMENT)):
        found = len(pattern.findall(text))
        if found != 1:
            fail("%s: esperava %s uma vez no XSD oficial e achei %d; o XSD mudou de forma" % (official, name, found))
        text = pattern.sub("", text)
    folder = tempfile.mkdtemp(prefix="xsd-sem-assinatura-")
    atexit.register(shutil.rmtree, folder, True)
    derived = os.path.join(folder, os.path.basename(official))
    with open(derived, "w", encoding="utf-8") as fh:
        fh.write(text)
    _RELAXED[official] = derived
    return derived


def xsd_problems(schema, artifact, who):
    """What xmllint says against a schema, as a list with at most one sentence."""
    if not shutil.which("xmllint"):
        return ["xmllint não está instalado: o arquivo não foi conferido contra o XSD"]
    with tempfile.NamedTemporaryFile(suffix=".xml") as fh:
        fh.write(artifact)
        fh.flush()
        run = subprocess.run(["xmllint", "--noout", "--schema", schema, fh.name], capture_output=True, text=True)
    if run.returncode == 0:
        return []
    said = [line for line in (run.stderr or run.stdout).strip().splitlines() if "fails to validate" not in line]
    return ["%s recusa: %s" % (who, said[0] if said else "xmllint saiu com %d" % run.returncode)]


def leaf_paths(element, ns, prefix=""):
    """Every leaf element under `element`, as (path without namespace, text), in document order."""
    out = []
    for child in element:
        tag = child.tag[len(ns) + 2:] if child.tag.startswith("{%s}" % ns) else child.tag
        path = prefix + tag
        if len(child):
            out.extend(leaf_paths(child, ns, path + "/"))
        else:
            out.append((path, child.text or ""))
    return out


def judge_event(document_id, artifact, expected, catalog_root, previous_ids):
    """Every problem with one generated e-Financeira event, as a list of sentences.

    `expected["elements"]` maps each path under the event element (the
    namespace left out, "infoCadastro/paisResid/Pais") to what the file carries:
    a string for exactly one element with that text; null for no element at all
    (an optional element the generation must leave out); a list for every
    element of the path, in that order; {"unordered": [...]} for the same
    elements in any order. Every leaf of the file must be covered by a path of
    the gabarito (itself or an ancestor): nothing extra goes unjudged.

    `previous_ids` are the event numbers judged before in this run: the id must
    be ID + 18 digits and greater than all of them. Answers the problems and the
    event number (None when the id could not be read).
    """
    spec = EVENT_DOCUMENTS[document_id]
    ns = spec["namespace"]
    problems = []

    if not artifact.startswith(b"<?xml"):
        problems.append("o arquivo não começa pela declaração XML no primeiro byte")
    try:
        root = ET.fromstring(artifact)
    except ET.ParseError as err:
        return problems + ["não é XML bem formado: %s" % err], None

    official = os.path.join(catalog_root, document_dir(document_id), spec["schema"])
    problems += xsd_problems(relaxed_schema(official), artifact, "o XSD oficial (sem a assinatura)")

    if root.tag != "{%s}eFinanceira" % ns:
        return problems + ["a raiz é %s, esperado {%s}eFinanceira" % (root.tag, ns)], None
    events = root.findall("{%s}%s" % (ns, spec["event"]))
    if len(events) != 1:
        return problems + ["esperava um %s dentro de eFinanceira, há %d" % (spec["event"], len(events))], None
    event = events[0]

    number = None
    event_id = event.get("id") or ""
    if not EVENT_ID.match(event_id):
        problems.append("id=%r não tem a forma ID + 18 dígitos" % event_id)
    else:
        number = int(event_id[2:])
        if previous_ids and number <= max(previous_ids):
            problems.append("id %s não é maior que o do evento julgado antes nesta execução (ID%018d)"
                            % (event_id, max(previous_ids)))

    leaves = leaf_paths(event, ns)
    got = {}
    for path, text in leaves:
        got.setdefault(path, []).append(text)
    present = {path for path, _ in leaves}
    # A path the gabarito names covers it and everything under it.
    for path in sorted(present):
        parts = path.split("/")
        if not any("/".join(parts[:n]) in expected["elements"] for n in range(1, len(parts) + 1)):
            problems.append("elemento a mais %s = %s" % (path, got[path]))

    for path, want in sorted(expected["elements"].items()):
        under = [p for p in present if p == path or p.startswith(path + "/")]
        values = got.get(path, [])
        if want is None:
            if under:
                problems.append("%s deveria estar ausente, e o arquivo traz %s" % (path, ", ".join(sorted(under))))
        elif isinstance(want, str):
            if values != [want]:
                problems.append("%s: gerado %s, esperado %r" % (path, values or "ausente", want))
        elif isinstance(want, list):
            if values != want:
                problems.append("%s: gerado %s, esperado %s nesta ordem" % (path, values or "ausente", want))
        elif isinstance(want, dict) and "unordered" in want:
            if sorted(values) != sorted(want["unordered"]):
                problems.append("%s: gerado %s, esperado %s em qualquer ordem" % (path, values or "ausente",
                                                                               want["unordered"]))
        else:
            problems.append("o gabarito de %s não é texto, null, lista nem {\"unordered\": [...]}" % path)

    return problems, number


BINDING_KEY = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*):\s*(#.*)?$")


def fill_binding(text, fills):
    """The binding with the client's fills written into its manual fields.

    `fills` maps "dataset.field" to a value (a scalar field: `value:`) or to a
    list (a list the client fills: `values: [...]`). Only a field the binding
    declares `from: manual` is filled — the way a client fills it once in the
    mapping, which keeps its pendingReason and its origin. A fill for a field the
    binding does not have, or that is not manual, stops the run: a scenario that
    fills nothing would judge the reference's pending draft as if it were filled.
    The YAML is edited line by line (standard library only), on the layout of the
    reference binding: datasets at two spaces, fields at six, keys at eight.
    """
    lines = text.splitlines()
    for key, value in sorted(fills.items()):
        dataset, _, field = key.partition(".")
        span = yaml_block(lines, [(0, "datasets"), (2, dataset), (4, "fields"), (6, field)])
        if span is None:
            fail("o binding não declara o campo %s em datasets, e o cenário o preenche" % key)
        start, end = span
        body = lines[start + 1:end]
        if not any(re.match(r"^\s{8}from:\s*manual\s*(#.*)?$", line) for line in body):
            fail("o campo %s do binding não é `from: manual`; o cenário só preenche campos manuais" % key)
        kept, skipping = [], False
        for line in body:
            if re.match(r"^\s{8}values?:", line):
                # A block-style list continues on deeper lines: they go with it.
                skipping = True
                continue
            # Os itens de uma lista em bloco ficam mais fundo, ou no mesmo recuo
            # começando por "- " (forma compacta, válida em YAML).
            if skipping and (not line.strip() or len(line) - len(line.lstrip()) > 8
                             or re.match(r"^\s{8}- ", line)):
                continue
            skipping = False
            kept.append(line)
        if isinstance(value, list):
            written = "        values: [%s]" % ", ".join(json.dumps(str(v), ensure_ascii=False) for v in value)
        else:
            written = "        value: %s" % json.dumps(str(value), ensure_ascii=False)
        at = next(i for i, line in enumerate(kept) if re.match(r"^\s{8}from:", line))
        kept.insert(at + 1, written)
        lines[start + 1:end] = kept
    return "\n".join(lines) + "\n"


def yaml_block(lines, steps):
    """The (header, end) line indexes of a nested YAML mapping key, or None.

    `steps` are (indent, key) from the outermost: each key is looked for inside
    the block of the one before it. A block ends at the next line, not blank nor
    a comment, indented at or left of its key.
    """
    start, end = -1, len(lines)
    for indent, key in steps:
        found = None
        for i in range(start + 1, end):
            m = BINDING_KEY.match(lines[i])
            if m and len(m.group(1)) == indent and m.group(2) == key:
                found = i
                break
        if found is None:
            return None
        start = found
        for i in range(found + 1, end):
            line = lines[i]
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if len(line) - len(line.lstrip()) <= indent:
                end = i
                break
    # Trailing blank and comment lines belong to what follows, not to the block.
    while end - 1 > start and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return start, end


def replace_binding_fields(text, fields):
    """The binding with whole field mappings replaced, for one gabarito entry.

    `fields` maps "dataset.field" to the mapping that takes the field's place
    (`{"from": "constant", "value": "..."}`): every key the binding had under the
    field goes, these are written in their place. It is how an entry proves a
    pattern of the contract on a field the Midaz fills (the name, the address)
    without registering another organization: the value comes from the binding
    as a constant. A field the binding does not declare stops the run.
    """
    lines = text.splitlines()
    for key, mapping in sorted(fields.items()):
        dataset, _, field = key.partition(".")
        span = yaml_block(lines, [(0, "datasets"), (2, dataset), (4, "fields"), (6, field)])
        if span is None:
            fail("o binding não declara o campo %s em datasets, e a entrada o substitui" % key)
        if not isinstance(mapping, dict) or "from" not in mapping:
            fail("a substituição de %s não é um mapeamento com `from`" % key)
        start, end = span
        written = []
        for k, v in mapping.items():
            if isinstance(v, list):
                written.append("        %s: [%s]" % (k, ", ".join(json.dumps(str(i), ensure_ascii=False) for i in v)))
            else:
                written.append("        %s: %s" % (k, json.dumps(str(v), ensure_ascii=False)))
        lines[start + 1:end] = written
    return "\n".join(lines) + "\n"


def apply_filled_binding(rep, subscription, base_path, fills, replaced=None, bases=None):
    """Puts the binding with the scenario's fills on the subscription, when it differs.

    `bases` (subscription -> binding text) keeps the binding the subscription had
    when the run first touched it, with or without `--bindings`: restore_bindings
    puts it back at exit, so a run leaves no entry's replacement behind. The base
    is the checkout's binding.example.yaml (`--bindings`) or, without it, that
    first-read binding, so an entry's replacement never becomes the base of the
    entries after it. `replaced` (an entry's `binding`) swaps whole field
    mappings after the fills.
    """
    if bases is not None and subscription not in bases:
        _, _, current = rep.raw("GET", "/v1/regulatory/subscriptions/%s/binding" % subscription)
        bases[subscription] = current.decode("utf-8")
    if base_path:
        with open(base_path, encoding="utf-8") as fh:
            base = fh.read()
    elif bases is not None:
        base = bases[subscription]
    else:
        _, _, current = rep.raw("GET", "/v1/regulatory/subscriptions/%s/binding" % subscription)
        base = current.decode("utf-8")
    wanted = fill_binding(base, fills)
    if replaced:
        wanted = replace_binding_fields(wanted, replaced)
    return put_binding(rep, subscription, wanted)


def put_binding(rep, subscription, text):
    """Puts `text` as the subscription's binding, when it differs from the current one."""
    wanted = text.encode("utf-8")
    _, headers, current = rep.raw("GET", "/v1/regulatory/subscriptions/%s/binding" % subscription)
    if current == wanted:
        return "inalterado"
    etag = {k.lower(): v for k, v in headers.items()}.get("etag", "")
    rep.raw("PUT", "/v1/regulatory/subscriptions/%s/binding" % subscription, wanted,
            {"Content-Type": "application/yaml", "If-Match": etag})
    return "preenchido"


def restore_bindings(rep, bases):
    """Puts back on each subscription the binding the run found on it (`bases`)."""
    for subscription, text in sorted(bases.items()):
        try:
            how = put_binding(rep, subscription, text)
        except (Exception, SystemExit) as err:  # noqa: BLE001 - rep.raw fail()s; at exit, report and carry on
            print("AVISO: o binding da assinatura %s não voltou ao original: %s" % (subscription, err),
                  file=sys.stderr)
            continue
        if how != "inalterado":
            print("binding da assinatura %s restaurado" % subscription)


def approved_event_original(rep, document_id, cnpj):
    """The approved original of the declarant's filing, from any subscription, or None.

    The Reporter holds one original per declarant (document and the institution's
    CNPJ), whichever subscription approved it: a subscription replaced by a run
    on another version still has the original an earlier run approved.
    """
    def plain(value):
        return re.sub(r"[^0-9A-Za-z]", "", value or "").upper()

    for r in rep.items("/v1/reports?regulatory=true&document_id=%s" % urllib.parse.quote(document_id)):
        if (r.get("status") == "Final" and r.get("remittance") == "original"
                and plain((r.get("institution") or {}).get("cnpj")) == plain(cnpj)):
            return r
    return None


def expect_generation_refusal(rep, subscription, doc, name):
    """A generation the Reporter must refuse while the caller waits, as the gabarito says.

    `refused` carries the HTTP status and the code (400 RPT-0140 by default) and,
    optionally, `detailContains`: what the refusal has to say.
    """
    refusal = doc["refused"] if isinstance(doc["refused"], dict) else {}
    want_status, want_code = refusal.get("status", 400), refusal.get("code", "RPT-0140")
    status, answer = rep.call("POST", "/v1/regulatory/reports",
                              {"subscriptionId": subscription, "parameters": doc["parameters"]},
                              ok=(200, 201, 400, 409, 422))
    answer = answer if isinstance(answer, dict) else {}
    detail = answer.get("detail", "") or answer.get("message", "")
    wanted = refusal.get("detailContains") or []
    ok = status == want_status and answer.get("code") == want_code and all(w in detail for w in wanted)
    if ok:
        said = "%d %s %s" % (status, want_code, detail[:150])
    elif status in (200, 201):
        said = "foi aceita (report %s), esperado %d %s" % (((answer.get("report") or {}).get("id")), want_status, want_code)
    else:
        said = "respondeu %d %s, esperado %d %s%s: %s" % (status, answer.get("code"), want_status, want_code,
                                                          (" dizendo " + " + ".join(wanted)) if wanted else "",
                                                          detail[:150])
    print("%-6s %-22s %-28s recusa esperada: %s" % ("OK" if ok else "FALHOU", name, doc["label"], said))
    return 0 if ok else 1


def correct_event(rep, report, document_id, doc, args, number, cnpj, name, label):
    """Corrects a judged draft and judges the file it becomes. Answers the problems.

    `correct` carries the `overrides` sent to POST /v1/regulatory/reports/{id}/overrides
    (with If-Match on the draft version read) and the `elements` of the corrected
    file, written by hand like any other. A correction re-renders the SAME frozen
    rows, so the event id must not move: the corrected file carries the number the
    generation drew (and the report's generatedIds still name it).
    """
    spec = doc["correct"]
    _, got = rep.get("/v1/reports/" + report)
    before = got.get("draftVersion")
    status, answer = rep.call("POST", "/v1/regulatory/reports/%s/overrides" % report,
                              {"overrides": spec["overrides"]},
                              headers={"If-Match": '"%s"' % before}, ok=(200, 400, 409, 422))
    if status != 200:
        return ["a correção respondeu %d %s" % (status, json.dumps(answer, ensure_ascii=False)[:300])]
    _, got = rep.get("/v1/reports/" + report)
    problems = []
    if got.get("status") != "Draft":
        problems.append("corrigido, o relatório ficou em %s" % got.get("status"))
    if str(got.get("draftVersion")) == str(before):
        problems.append("a correção não mudou a versão do rascunho (%s)" % before)
    _, _, artifact = rep.raw("GET", "/v1/reports/%s/download" % report)
    with open(os.path.join(args.out, "%s-%s-%s-corrigido.xml" % (cnpj, name, label)), "wb") as fh:
        fh.write(artifact)
    judged, after = judge_event(document_id, artifact, spec, args.catalog, None)
    problems += ["corrigido: " + p for p in judged]
    if after != number:
        problems.append("a correção mudou o id do evento: ID%018d antes, %s depois"
                        % (number, "ID%018d" % after if after is not None else "ilegível"))
    drawn = [g.get("value") for g in (got.get("generatedIds") or []) if g.get("field", "").endswith(".eventId")]
    if number is not None and drawn != ["%018d" % number]:
        problems.append("generatedIds do relatório %s não é o id do arquivo ID%018d" % (drawn, number))
    print("         corrigido: rascunho %s -> %s, id antes ID%s, depois ID%s" % (
        before, got.get("draftVersion"), "%018d" % number if number is not None else "?",
        "%018d" % after if after is not None else "?"))
    return problems


def check_event_entries(documents):
    """Stops the run when the gabarito's event entries cannot be told apart.

    A label names one entry of the scenario, and `supersedes` names an entry of
    the SAME document listed before it: the generated reports are remembered by
    (documentId, label), so a repeated label or a `supersedes` across documents
    would judge the wrong draft.
    """
    seen = {}
    for doc in documents:
        if doc.get("documentId") not in EVENT_DOCUMENTS:
            continue
        label = doc.get("label")
        if label in seen:
            fail("o gabarito repete o label %r (%s e %s): cada entrada precisa de um label só dela"
                 % (label, seen[label]["documentId"], doc["documentId"]))
        earlier = doc.get("supersedes")
        if earlier is not None:
            if earlier not in seen:
                fail("%r: supersedes nomeia %r, que não é uma entrada listada antes no gabarito" % (label, earlier))
            if seen[earlier]["documentId"] != doc["documentId"]:
                fail("%r: supersedes nomeia %r, que é de outro documento (%s, não %s)"
                     % (label, earlier, seen[earlier]["documentId"], doc["documentId"]))
            # A refused or errored entry is never generated: there is no draft of it
            # for this one to supersede.
            for outcome in ("refused", "errored"):
                if seen[earlier].get(outcome):
                    fail("%r: supersedes nomeia %r, que é marcada %s e nunca é gerada" % (label, earlier, outcome))
        seen[label] = doc


def superseded_problems(rep, run, document_id, earlier_label, report):
    """What is wrong with an earlier entry's draft, now that `report` is the same filing.

    `supersedes` names the label of an entry of the same document generated before
    in this run with the same filing period (a document without a remittance: the
    same receipt). Both drafts stay; the earlier one is still a Draft and answers
    `supersededBy` with the newer report — while both are drafts, the newest
    generation of a filing is the one that counts.
    """
    earlier = run["reports"].get((document_id, earlier_label))
    if earlier is None:
        return ["supersedes nomeia %r, que não foi gerada antes nesta execução" % earlier_label]
    _, got = rep.get("/v1/reports/" + earlier)
    problems = []
    if got.get("status") != "Draft":
        problems.append("o rascunho anterior (%s, %s) ficou em %s" % (earlier_label, earlier, got.get("status")))
    if got.get("supersededBy") != report:
        problems.append("o rascunho anterior (%s, %s) diz supersededBy %s, esperado %s"
                        % (earlier_label, earlier, got.get("supersededBy"), report))
    return problems


def run_event(rep, lg, args, doc, institution, run):
    """One gabarito entry of an e-Financeira event: generated, refused or errored, and judged.

    The binding the subscription carries is the reference's with the scenario's
    fills (`fills` of the scenario, for this document) and the entry's own on top
    — a rule of the contract is proved by a fill that breaks it.
    """
    document_id = doc["documentId"]
    label = doc["label"]
    name = EVENT_DOCUMENTS[document_id]["event"]
    cnpj = lg.sc["organization"]["legalDocument"]

    subscription = run["subscriptions"].get(document_id)
    if subscription is None:
        subscription = ensure_subscription(rep, document_id, institution,
                                           contract_version(args.bindings, document_id) if args.bindings else None)
        run["subscriptions"][document_id] = subscription

    fills = dict((lg.sc.get("fills") or {}).get(document_id) or {})
    fills.update(doc.get("fills") or {})
    base = os.path.join(args.bindings, document_dir(document_id), "binding.example.yaml") if args.bindings else None
    how = apply_filled_binding(rep, subscription, base, fills, doc.get("binding"),
                               run.setdefault("bases", {}))

    if doc.get("refused"):
        return expect_generation_refusal(rep, subscription, doc, name)

    started = datetime.datetime.now(datetime.timezone.utc)
    # UM ORIGINAL POR DECLARANTE: aprovado, não se gera outro (RPT-0197). Numa
    # execução seguinte, o original que uma anterior aprovou é o que se julga. Só
    # o original: uma retificação aprovada se gera de novo a cada execução. Um
    # documento sem remessa (as exclusões) não tem original: toda entrada é gerada.
    is_original = is_event_original(document_id, doc["parameters"])
    final = approved_event_original(rep, document_id, cnpj) if doc.get("approve") and is_original else None
    if final:
        report, got = final["id"], final
    else:
        report, got = request_report(rep, subscription, doc["parameters"])
    status = got.get("status")

    if doc.get("errored"):
        return expect_error(name, doc, status, report, started, rep)

    problems, artifact = [], None
    if status not in ("Draft", "Final"):
        problems.append("a geração terminou em %s" % status)
    if status == "Draft":
        # A Draft with a required gap cannot be approved nor downloaded: the
        # scenario's fills did not reach the binding.
        _, got = rep.get("/v1/reports/" + report)
        gaps = [g.get("field") for g in (got.get("openGaps") or []) if g.get("required")]
        if gaps:
            problems.append("o rascunho tem pendência obrigatória: %s" % ", ".join(gaps))
    if not problems:
        # Julga o arquivo ANTES de aprovar, como nos CADOCs: o Reporter guarda uma
        # original por declarante, e uma original errada aprovada ficaria Final para
        # sempre naquele CNPJ — toda execução seguinte julgaria aquele arquivo.
        _, _, artifact = rep.raw("GET", "/v1/reports/%s/download" % report)
        judged, number = judge_event(document_id, artifact, doc, args.catalog, run["ids"])
        problems += judged
        if number is not None:
            run["ids"].append(number)
        out = os.path.join(args.out, "%s-%s-%s.xml" % (cnpj, name, label))
        with open(out, "wb") as fh:
            fh.write(artifact)
        if not problems and doc.get("correct"):
            if status != "Draft":
                problems.append("a correção pede um rascunho, e o relatório está em %s" % status)
            else:
                problems += correct_event(rep, report, document_id, doc, args, number, cnpj, name, label)
        if not problems and status == "Draft" and doc.get("approve"):
            status = approve(rep, report)
            if status != "Final":
                problems.append("aprovado, o relatório ficou em %s" % status)
        if doc.get("supersedes"):
            problems += superseded_problems(rep, run, document_id, doc["supersedes"], report)

    run["reports"][(document_id, label)] = report
    failures = bool(problems)
    print("%-6s %-22s %-28s binding %-10s %-6s report %s" % ("OK" if not problems else "FALHOU", name, label,
                                                             how, status, report))
    for p in problems:
        print("         - " + p)
    return int(failures)


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

def setup_missing(lg, state):
    """The scenario's transactions setup has not finished, or that Midaz does not have.

    An organization and a ledger found by name prove nothing about the entries: a
    setup interrupted after the accounts leaves a ledger the documents would be
    generated from as if it were complete. Every transaction the scenario declares
    has to be recorded as finished and answer in Midaz.
    """
    recorded = state.get("transactions") or {}
    missing = []
    for t in lg.sc["transactions"]:
        entry = recorded.get(t["key"]) or {}
        if not entry.get("finished") or not entry.get("id"):
            missing.append(t["key"])
            continue
        status, _ = lg.midaz.call("GET", "%s/transactions/%s" % (lg.lp, entry["id"]), ok=(200, 404))
        if status != 200:
            missing.append(t["key"])
    return missing


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


ROOT_STATE = None


def save_state(state):
    # A scenario of several ledgers keeps one state per ledger inside a root one;
    # whichever part is saved, the file holds the root.
    with open(STATE_PATH, "w") as fh:
        json.dump(ROOT_STATE if ROOT_STATE is not None else state, fh, indent=2, sort_keys=True)


class Books:
    """An organization with several ledgers: the institution is the organization.

    Every ledger is one book of the same institution (one CNPJ). Entries within a
    ledger post through v1, dated; entries between ledgers post through the v2
    cross-ledger API, which Midaz splits into one balanced transaction per ledger,
    each closed against that ledger's @external/BRL with the bridge route's rubric
    (`accountingEntries.crossLedger`). v2 takes no transactionDate: a cross-ledger
    entry is dated when it is posted.
    """

    def __init__(self, midaz, scenario, state, create):
        self.midaz, self.sc, self.state = midaz, scenario, state
        self.parts = {}
        for name, book in scenario["ledgers"].items():
            sub = {"organization": scenario["organization"], "ledger": name,
                   "accountTypes": book.get("accountTypes", []), "accounts": book.get("accounts", []),
                   "transactions": [t for t in scenario.get("transactions", []) if t.get("ledger") == name],
                   "readAlso": ["@external/BRL"]}
            lg = Ledger(midaz, sub, state.setdefault("ledgers", {}).setdefault(name, {}))
            lg.ensure_organization(create=create)
            lg.ensure_ledger(create=create)
            if lg.state.get("ledger", lg.ledger) != lg.ledger:
                if not create:
                    fail("o ledger %s não é o que o setup registrou (o Midaz foi recriado?); rode setup antes" % name)
                lg.state.clear()
            lg.state["ledger"] = lg.ledger
            self.parts[name] = lg
        self.org = next(iter(self.parts.values())).org
        self.op = "/v2/organizations/%s" % self.org

        # The organization's own state — cross-ledger entries, organization routes —
        # belongs to ONE organization. A Midaz recreated from scratch (the sandbox
        # is reset) gives the scenario a new one, and entries recorded as finished
        # in the old one would be skipped instead of posted again.
        # A state written before it recorded its organization is judged by its
        # entries: kept only when every part it recorded answers in this Midaz.
        stale = state.get("organization", self.org) != self.org or (
            "organization" not in state and state.get("cross") and self.missing_cross())
        if stale:
            if not create:
                fail("a organização não é a que o setup registrou (o Midaz foi recriado?); rode setup antes")
            for key in ("cross", "crossDate", "orgRoutes", "orgTransactionRoutes"):
                state.pop(key, None)
        state["organization"] = self.org

    def first(self):
        return next(iter(self.parts.values()))

    def setup(self):
        for name, lg in self.parts.items():
            self.midaz.call("PATCH", "/v2/organizations/%s/ledgers/%s/settings" % (self.org, lg.ledger),
                            {"crossLedger": {"enabled": True},
                             "accounting": {"validateRoutes": True, "validateAccountType": True}})
            lg.ensure_asset()
            lg.ensure_account_types()
            lg.ensure_accounts()
            lg.ensure_operation_routes()
            lg.post_transactions()
            print("livro        %s pronto, cross-ledger ligado" % name)
        self.ensure_org_routes()
        self.post_cross()
        save_state(self.state)

    def ensure_org_routes(self):
        """Organization-level routes for the cross-ledger entries: one per account, and the bridge.

        The bridge route carries the crossLedger entry and nothing else; Midaz takes
        crossLedger.credit where value leaves a ledger and crossLedger.debit where it
        arrives. The same rubric on both sides: for one institution the bridge is an
        internal account that must net to zero across its books.
        """
        existing = {r.get("title"): r["id"] for r in self.midaz.items(self.op + "/operation-routes")}
        routes = self.state.setdefault("orgRoutes", {})
        for name, book in self.sc["ledgers"].items():
            for a in book.get("accounts", []):
                title = "org %s %s" % (a["code"], a["alias"])
                if title not in existing:
                    rubric = {"code": a["code"], "description": a["name"].split(" — ")[-1]}
                    _, created = self.midaz.call("POST", self.op + "/operation-routes", {
                        "title": title, "description": rubric["description"], "operationType": "bidirectional",
                        "account": {"ruleType": "alias", "validIf": a["alias"]},
                        "accountingEntries": {x: {"debit": rubric, "credit": rubric} for x in ROUTE_ACTIONS}})
                    existing[title] = created["id"]
                routes[a["alias"]] = existing[title]
        bridge = self.sc["bridge"]
        if not cosif_check(bridge["code"]):
            fail("a rubrica da ponte %s não é COSIF de dez dígitos com DV válido" % bridge["code"])
        title = "org ponte %s" % bridge["code"]
        if title not in existing:
            rubric = {"code": bridge["code"], "description": bridge["description"]}
            _, created = self.midaz.call("POST", self.op + "/operation-routes", {
                "title": title, "description": bridge["description"], "operationType": "bidirectional",
                "accountingEntries": {"crossLedger": {"debit": rubric, "credit": rubric}}})
            existing[title] = created["id"]
        routes["#bridge"] = existing[title]
        print("rotas org.   %d contas + ponte %s" % (len(routes) - 1, bridge["code"]))

    def transaction_route(self, debit_alias, credit_alias):
        routes = self.state["orgRoutes"]
        legs = [routes[debit_alias], routes[credit_alias], routes["#bridge"]]
        title = "org %s -> %s [%s]" % (debit_alias, credit_alias, " ".join(r[-8:] for r in legs))
        cache = self.state.setdefault("orgTransactionRoutes", {})
        if title not in cache:
            found = [r for r in self.midaz.items(self.op + "/transaction-routes") if r.get("title") == title]
            if found:
                cache[title] = found[0]["id"]
            else:
                _, created = self.midaz.call("POST", self.op + "/transaction-routes",
                                             {"title": title, "operationRoutes": legs})
                cache[title] = created["id"]
        return cache[title]

    def where(self, alias):
        for name, book in self.sc["ledgers"].items():
            if any(a["alias"] == alias for a in book.get("accounts", [])):
                return name
        fail("lançamento numa conta que o cenário não declara: %s" % alias)

    def post_cross(self):
        done = self.state.setdefault("cross", {})
        slug = self.sc["organization"]["legalDocument"]
        for t in self.sc.get("crossTransactions", []):
            key = t["key"]
            if done.get(key, {}).get("finished"):
                continue
            debit_book, credit_book = self.where(t["debit"]), self.where(t["credit"])
            if debit_book == credit_book:
                fail("%s não cruza ledgers (%s nos dois lados); declare-o em transactions" % (key, debit_book))
            routes = self.state["orgRoutes"]
            leg = lambda alias, book: {"alias": alias, "amount": t["amount"], "organizationId": self.org,
                                       "ledgerId": self.parts[book].ledger, "operationRouteId": routes[alias]}
            _, created = self.midaz.call("POST", "/v2/transactions/direct", {
                "description": t["description"], "asset": "BRL", "amount": t["amount"],
                "routeId": self.transaction_route(t["debit"], t["credit"]),
                "metadata": {"homologacao": key},
                "debits": [leg(t["debit"], debit_book)], "credits": [leg(t["credit"], credit_book)]},
                idempotency="%s-%s" % (slug, key))
            parts = created.get("transactions") or []
            # One part per ledger the entry touches, each in a book of the scenario:
            # anything else is not the group that was asked for, and recording it as
            # finished would skip it on every later run.
            by_ledger = {lg.ledger: n for n, lg in self.parts.items()}
            books_hit = [by_ledger.get(part.get("ledgerId")) for part in parts]
            if None in books_hit:
                fail("%s: o Midaz respondeu uma parte num ledger que o cenário não declara: %s"
                     % (key, [p.get("ledgerId") for p in parts]))
            if sorted(books_hit) != sorted({debit_book, credit_book}):
                fail("%s: esperava uma parte em %s e em %s, e o Midaz respondeu %s"
                     % (key, debit_book, credit_book, books_hit or "nenhuma"))
            for part, book in zip(parts, books_hit):
                self.parts[book].state.setdefault("transactions", {})["%s@%s" % (key, book)] = {
                    "id": part["id"], "finished": True}
            done[key] = {"groupId": created.get("groupId"), "finished": True, "parts": len(parts)}
            # v2 dates an entry when it posts: the day, in Brasília, the documents
            # of this scenario are cut on.
            self.state["crossDate"] = datetime.datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
            save_state(self.state)
            print("cross        %s  grupo %s  %d partes" % (key, created.get("groupId"), len(parts)))

    def report(self):
        """Each book's rubrics, and the institution's: the bridge must net to zero across the books."""
        total = {}
        for name, lg in self.parts.items():
            print("\n== livro %s" % name)
            for o in report_ledger(lg):
                if o.get("balanceAffected") is False:
                    continue
                amount = Decimal(str((o.get("amount") or {}).get("value") or "0"))
                code = o.get("routeCode") or "<sem rubrica>"
                total[code] = total.get(code, Decimal(0)) + (amount if o.get("direction") == "credit" else -amount)
        print("\n== instituição (todos os livros), créd-déb por rubrica")
        for code in sorted(total):
            print("%-12s %14s" % (code, total[code]))
        print("soma: %s (zero = a instituição fecha em partidas dobradas)" % sum(total.values()))
        code = self.sc["bridge"]["code"]
        bridge = total.get(code, Decimal(0))
        # Zero over no bridge operation at all proves nothing: a scenario that
        # declares cross-ledger entries has to show them on the bridge.
        if self.sc.get("crossTransactions") and code not in total:
            print("ponte %s: NENHUMA operação, e o cenário declara lançamentos cross-ledger" % code)
            return False
        print("ponte %s somada nos livros: %s (%s)" % (code, bridge, "zera" if bridge == 0 else "NÃO ZERA"))
        return bridge == 0

    def missing_cross(self):
        """The cross-ledger entries setup has not finished, or whose parts Midaz does not have."""
        done = self.state.get("cross") or {}
        missing = []
        for t in self.sc.get("crossTransactions", []):
            key = t["key"]
            if not done.get(key, {}).get("finished"):
                missing.append(key)
                continue
            # Each book's part under its exact key, never by prefix: keys are free
            # text, and "G02" must not collect the parts of "G02@refund".
            parts = {name: (lg.state.get("transactions") or {}).get("%s@%s" % (key, name))
                     for name, lg in self.parts.items()}
            parts = {name: v for name, v in parts.items() if v}
            if not parts or len(parts) != done[key].get("parts", -1):
                missing.append(key)
                continue
            for name, v in parts.items():
                lg = self.parts[name]
                status, _ = lg.midaz.call("GET", "%s/transactions/%s" % (lg.lp, v["id"]), ok=(200, 404))
                if status != 200:
                    missing.append("%s@%s" % (key, name))
        return missing


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

    if "ledgers" in scenario:
        run_books(args, scenario, state)
        return

    if "ledger" not in scenario:
        run_organization(args, scenario)
        return

    lg = Ledger(Midaz(args.midaz), scenario, state)
    # Only setup builds. reports and ledger read what setup built, and finding
    # nothing is a refusal: creating an empty organization there judged a file
    # generated from no data at all.
    lg.ensure_organization(create=args.command == "setup")
    lg.ensure_ledger(create=args.command == "setup")

    # The state is one ledger's: a scenario moved to a new ledger posts everything
    # again there, instead of skipping what it posted in the old one. A state
    # written before it recorded its ledger is adopted only when a transaction it
    # recorded exists in the ledger found; otherwise it is another ledger's.
    if state.get("ledger", lg.ledger) != lg.ledger or not state_belongs_to(lg, state):
        if args.command != "setup":
            fail("o ledger encontrado não tem os lançamentos que o setup registrou (o Midaz foi recriado?); rode setup antes")
        state.clear()
    state["ledger"] = lg.ledger

    if args.command != "setup":
        missing = setup_missing(lg, state)
        if missing:
            fail("o setup não terminou neste ledger: %d lançamento(s) do cenário sem registro ou fora do Midaz (%s); "
                 "rode setup antes" % (len(missing), ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")))

    if args.command == "setup":
        lg.ensure_asset()
        lg.ensure_account_types()
        lg.ensure_accounts()
        lg.ensure_balances()
        lg.ensure_overdraft()
        lg.ensure_operation_routes()
        lg.post_transactions()
        save_state(state)

    if args.command == "reports":
        args.expected = args.expected or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.scenario))),
                                                      "expected", os.path.basename(args.scenario))
        sys.exit(1 if run_reports(lg, args) else 0)

    report_ledger(lg)


def read_organization(midaz, org_id, attempts=15):
    """A organização, relida até aparecer: o Midaz lê de uma réplica, e logo depois
    de criar (ou de mudar o endereço) a leitura ainda responde 404 por alguns
    segundos. Desiste dizendo isso depois de `attempts` segundos."""
    for _ in range(attempts):
        status, body = midaz.call("GET", "/v1/organizations/" + org_id, ok=(200, 404))
        if status == 200:
            return body
        time.sleep(1)
    fail("a organização %s não apareceu na leitura do Midaz em %ds" % (org_id, attempts))


def run_organization(args, scenario):
    """A scenario of an organization alone: no ledger, no account, no entry.

    A document that reads only the organization (the e-Financeira declarant
    registration: CNPJ, name, address) needs nothing else from Midaz. setup creates
    the organization with its address, or puts the scenario's address on the one
    found by name; reports and ledger only read it. There is no state to keep.
    """
    lg = Ledger(Midaz(args.midaz), scenario, {})
    lg.ensure_organization(create=args.command == "setup")
    found = read_organization(lg.midaz, lg.org)
    wanted = scenario["organization"].get("address") or {}
    current = (found or {}).get("address") or {}
    differs = {k: v for k, v in wanted.items() if current.get(k) != v}
    if differs and args.command == "setup":
        lg.midaz.call("PATCH", "/v1/organizations/" + lg.org, {"address": wanted})
        found = read_organization(lg.midaz, lg.org)
        current = (found or {}).get("address") or {}
        differs = {k: v for k, v in wanted.items() if current.get(k) != v}
    if differs:
        fail("o endereço da organização no Midaz difere do cenário em %s (Midaz: %s)%s"
             % (", ".join(sorted(differs)), json.dumps({k: current.get(k) for k in differs}, ensure_ascii=False),
                "" if args.command == "setup" else "; rode setup antes"))
    print("endereço     %s" % json.dumps(current, ensure_ascii=False))
    print("CNPJ         %s" % (found or {}).get("legalDocument"))
    if args.command == "reports":
        args.expected = args.expected or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.scenario))),
                                                      "expected", os.path.basename(args.scenario))
        sys.exit(1 if run_reports(lg, args) else 0)


def run_books(args, scenario, state):
    global ROOT_STATE
    ROOT_STATE = state
    books = Books(Midaz(args.midaz), scenario, state, create=args.command == "setup")
    if args.command == "setup":
        books.setup()
    else:
        for name, lg in books.parts.items():
            missing = setup_missing(lg, lg.state)
            if missing:
                fail("o setup não terminou no livro %s: %s; rode setup antes" % (name, ", ".join(missing[:8])))
        missing = books.missing_cross()
        if missing:
            fail("lançamentos cross-ledger sem registro ou fora do Midaz: %s; rode setup antes" % ", ".join(missing))
    if args.command == "reports":
        args.expected = args.expected or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(args.scenario))),
                                                      "expected", os.path.basename(args.scenario))
        # The gabarito names the day the cross-ledger entries posted as {crossDay}
        # and its month as {crossMonth}: v2 does not backdate, so the documents
        # that carry them are cut on whatever day setup ran.
        day = state.get("crossDate")
        if day:
            args.dates = {"{crossDay}": day, "{crossMonth}": day[:7]}
        sys.exit(1 if run_reports(books.first(), args) else 0)
    sys.exit(0 if books.report() else 1)


if __name__ == "__main__":
    main()
