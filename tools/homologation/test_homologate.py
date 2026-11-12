#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""How homologate.py puts an entry's binding on a subscription, and which path an
e-Financeira event entry takes (an original to look up, or a document without a
remittance that is just generated), against a fake Reporter: no Midaz and no
Reporter are needed.

    python3 tools/homologation/test_homologate.py
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import homologate  # noqa: E402

DOCUMENT = "br.rfb.efinanceira-cad-declarante"
SUBSCRIPTION = "sub-1"
REFERENCE = (ROOT / "br" / "rfb" / "efinanceira-cad-declarante" / "binding.example.yaml").read_text(encoding="utf-8")
FILLS = json.loads((HERE / "scenario" / "j-efinanceira-completo.json").read_text(encoding="utf-8"))["fills"][DOCUMENT]
APOSTROPHE = {"declarante.nome": {"from": "constant", "value": "Declarante D'Oeste e-Financeira S.A."}}


class FakeReporter:
    """Holds one binding per subscription and answers GET/PUT on it."""

    def __init__(self, bindings):
        self.bindings = {k: v.encode("utf-8") for k, v in bindings.items()}

    def raw(self, method, path, body=None, headers=None, ok=(200, 201)):
        subscription = path.split("/")[4]
        if method == "PUT":
            self.bindings[subscription] = body
        return 200, {"ETag": "x"}, self.bindings[subscription]

    def binding(self, subscription=SUBSCRIPTION):
        return self.bindings[subscription].decode("utf-8")


class EntryBinding(unittest.TestCase):
    def test_a_replacement_does_not_leak_into_the_next_entry(self):
        rep = FakeReporter({SUBSCRIPTION: REFERENCE})
        bases = {}
        homologate.apply_filled_binding(rep, SUBSCRIPTION, None, FILLS, APOSTROPHE, bases)
        self.assertIn("D'Oeste", rep.binding())

        homologate.apply_filled_binding(rep, SUBSCRIPTION, None, FILLS, None, bases)
        self.assertNotIn("D'Oeste", rep.binding(), "the previous entry's nome stayed on the subscription")
        self.assertEqual(rep.binding(), homologate.fill_binding(REFERENCE, FILLS))

    def test_the_run_puts_back_the_binding_it_found(self):
        rep = FakeReporter({SUBSCRIPTION: REFERENCE})
        bases = {}
        homologate.apply_filled_binding(rep, SUBSCRIPTION, None, FILLS, APOSTROPHE, bases)
        with contextlib.redirect_stdout(io.StringIO()):
            homologate.restore_bindings(rep, bases)
        self.assertEqual(rep.binding(), REFERENCE)

    def test_a_restore_that_fails_does_not_stop_the_others(self):
        class Failing(FakeReporter):
            def raw(self, method, path, body=None, headers=None, ok=(200, 201)):
                if "/broken/" in path:
                    homologate.fail("PUT %s -> 500" % path)
                return super().raw(method, path, body, headers, ok)

        rep = Failing({"broken": "x\n", SUBSCRIPTION: "changed\n"})
        err, out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            homologate.restore_bindings(rep, {"broken": "a\n", SUBSCRIPTION: REFERENCE})
        self.assertIn("não voltou ao original", err.getvalue())
        self.assertEqual(rep.binding(), REFERENCE)

    def test_with_bindings_the_checkout_file_is_the_base(self):
        rep = FakeReporter({SUBSCRIPTION: "anything\n"})
        path = str(ROOT / "br" / "rfb" / "efinanceira-cad-declarante" / "binding.example.yaml")
        bases = {}
        homologate.apply_filled_binding(rep, SUBSCRIPTION, path, FILLS, None, bases)
        self.assertEqual(rep.binding(), homologate.fill_binding(REFERENCE, FILLS))

    def test_with_bindings_the_run_also_puts_back_the_binding_it_found(self):
        rep = FakeReporter({SUBSCRIPTION: "before the run\n"})
        path = str(ROOT / "br" / "rfb" / "efinanceira-cad-declarante" / "binding.example.yaml")
        bases = {}
        homologate.apply_filled_binding(rep, SUBSCRIPTION, path, FILLS, APOSTROPHE, bases)
        self.assertIn("D'Oeste", rep.binding())
        with contextlib.redirect_stdout(io.StringIO()):
            homologate.restore_bindings(rep, bases)
        self.assertEqual(rep.binding(), "before the run\n", "the last entry's replacement stayed on the subscription")


EXCLUSIONS = ("br.rfb.efinanceira-exclusao", "br.rfb.efinanceira-exclusao-efinanceira")


class EventDocuments(unittest.TestCase):
    def test_every_event_document_points_at_its_schema_and_template(self):
        for document_id, spec in homologate.EVENT_DOCUMENTS.items():
            folder = ROOT / homologate.document_dir(document_id)
            schema = (folder / spec["schema"]).read_text(encoding="utf-8-sig")
            self.assertIn('targetNamespace="%s"' % spec["namespace"], schema, document_id)
            template = (folder / "template.tpl").read_text(encoding="utf-8")
            self.assertIn('<eFinanceira xmlns="%s">' % spec["namespace"], template, document_id)
            self.assertIn("<%s id=" % spec["event"], template, document_id)

    def test_an_exclusion_has_no_original(self):
        for document_id in EXCLUSIONS:
            self.assertNotIn("original", homologate.EVENT_DOCUMENTS[document_id])
            self.assertFalse(homologate.is_event_original(document_id, {"nrReciboEvento": "1-01-001-2026-1"}))
            self.assertFalse(homologate.is_event_original(document_id, {}))

    def test_the_registration_original_is_still_its_remittance(self):
        self.assertTrue(homologate.is_event_original(DOCUMENT, {"indRetificacao": "1"}))
        self.assertFalse(homologate.is_event_original(DOCUMENT, {"indRetificacao": "2", "nrRecibo": "1-01-001-2026-1"}))


ABERTURA = "br.rfb.efinanceira-abertura"
FECHAMENTO = "br.rfb.efinanceira-fechamento"
ABERTURA_REFERENCE = (ROOT / "br" / "rfb" / "efinanceira-abertura" / "binding.example.yaml").read_text(encoding="utf-8")
CONTACTS = [
    {"cpf": "52998224725", "nome": "Ana", "uf": "SP", "email": "ana@x.com.br"},
    {"cpf": "16899535009", "nome": "Bruno D'Ávila", "uf": "RJ", "email": "bruno@x.com.br"},
]


class RowsFill(unittest.TestCase):
    """A fill keyed by a set's name writes the rows the client types in the mapping."""

    def test_the_rows_replace_the_pending_set_in_order(self):
        import yaml

        text = homologate.fill_binding(ABERTURA_REFERENCE, {"respeFin": CONTACTS, "declarante.tpAmb": "2"})
        loaded = yaml.safe_load(text)
        respefin = loaded["datasets"]["respeFin"]
        self.assertEqual(respefin, {"rows": CONTACTS}, "the pendingReason must go: the engine refuses it beside rows")
        self.assertEqual(loaded["datasets"]["declarante"]["fields"]["tpAmb"]["value"], "2")
        # The other sets are untouched.
        self.assertEqual(loaded["datasets"]["represLegal"], yaml.safe_load(ABERTURA_REFERENCE)["datasets"]["represLegal"])

    def test_writing_the_rows_twice_gives_the_same_binding(self):
        once = homologate.fill_binding(ABERTURA_REFERENCE, {"respeFin": CONTACTS})
        self.assertEqual(homologate.fill_binding(once, {"respeFin": CONTACTS}), once)

    def test_block_rows_with_a_comment_inside_are_replaced_whole(self):
        import yaml

        block = (
            "  respeFin:\n"
            "    rows:\n"
            "      - cpf: \"11144477735\"\n"
            "        nome: Antigo\n"
            "    # a segunda pessoa, escrita depois\n"
            "      - cpf: \"39053344705\"\n"
            "        nome: Outro\n"
        )
        pending = ABERTURA_REFERENCE[ABERTURA_REFERENCE.index("  respeFin:\n"):ABERTURA_REFERENCE.index("\n\n", ABERTURA_REFERENCE.index("  respeFin:\n")) + 1]
        text = ABERTURA_REFERENCE.replace(pending, block)
        self.assertEqual(yaml.safe_load(text)["datasets"]["respeFin"]["rows"][1]["nome"], "Outro")
        filled = homologate.fill_binding(text, {"respeFin": CONTACTS})
        loaded = yaml.safe_load(filled)
        self.assertEqual(loaded["datasets"]["respeFin"], {"rows": CONTACTS},
                         "the old rows after the comment must go with the rows they belong to")
        self.assertNotIn("Antigo", filled)
        self.assertNotIn("Outro", filled)
        self.assertEqual(loaded["datasets"]["represLegal"], yaml.safe_load(ABERTURA_REFERENCE)["datasets"]["represLegal"])

    def test_row_keys_are_quoted(self):
        import yaml

        rows = [{"cpf": "52998224725", "nome: x": "Ana"}]
        loaded = yaml.safe_load(homologate.fill_binding(ABERTURA_REFERENCE, {"respeFin": rows}))
        self.assertEqual(loaded["datasets"]["respeFin"]["rows"], rows)

    def test_an_empty_or_malformed_list_stops_the_run(self):
        for rows in ([], [{}], ["52998224725"], {"cpf": "1"}):
            with self.subTest(rows=rows), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                homologate.fill_binding(ABERTURA_REFERENCE, {"respeFin": rows})

    def test_a_value_nobody_writes_by_hand_stops_the_run(self):
        for value in (None, True, False, {"a": "b"}, ["x"]):
            with self.subTest(value=value), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                homologate.fill_binding(ABERTURA_REFERENCE, {"respeFin": [{"cpf": "52998224725", "nome": value}]})

    def test_a_set_not_filled_by_rows_stops_the_run(self):
        for name in ("represLegal", "naoExiste"):
            with self.subTest(set=name), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                homologate.fill_binding(ABERTURA_REFERENCE, {name: CONTACTS})


class ApprovedOriginal(unittest.TestCase):
    """Which approved original stands for an entry: same declarant and, for a
    document with a filing period, the same period; never one marked excluded."""

    def lookup(self, document_id, parameters, reports):
        rep = mock.Mock()
        rep.items.return_value = reports
        return homologate.approved_event_original(rep, document_id, "EF9J2K7A000114", parameters)

    @staticmethod
    def report(ident, semestre=None, **extra):
        out = {"id": ident, "status": "Final", "remittance": "original",
               "institution": {"cnpj": "EF9J2K7A000114"}, "parameters": {"indRetificacao": "1"}}
        if semestre:
            out["parameters"]["semestre"] = semestre
        out.update(extra)
        return out

    def test_the_opening_is_found_by_its_semester(self):
        reports = [self.report("dez", "2026-12"), self.report("jun", "2026-06")]
        self.assertEqual(self.lookup(ABERTURA, {"indRetificacao": "1", "semestre": "2026-06"}, reports)["id"], "jun")
        self.assertIsNone(self.lookup(ABERTURA, {"indRetificacao": "1", "semestre": "2027-06"}, reports))

    def test_a_report_marked_excluded_is_not_the_original(self):
        reports = [self.report("old", "2026-06", excludedAt="2026-11-12T00:00:00Z"), self.report("new", "2026-06")]
        self.assertEqual(self.lookup(ABERTURA, {"indRetificacao": "1", "semestre": "2026-06"}, reports)["id"], "new")

    def test_the_registration_has_one_original_per_declarant(self):
        reports = [self.report("cad")]
        self.assertEqual(self.lookup(DOCUMENT, {"indRetificacao": "1"}, reports)["id"], "cad")

    def test_the_opening_original_is_its_remittance(self):
        self.assertTrue(homologate.is_event_original(ABERTURA, {"indRetificacao": "1", "semestre": "2026-06"}))
        self.assertFalse(homologate.is_event_original(ABERTURA, {"indRetificacao": "2", "semestre": "2026-06"}))

    def test_the_closing_is_found_by_its_semester_not_by_the_opening(self):
        reports = [self.report("dez", "2026-12"), self.report("jun", "2026-06")]
        self.assertEqual(self.lookup(FECHAMENTO, {"indRetificacao": "1", "semestre": "2026-12"}, reports)["id"], "dez")
        self.assertIsNone(self.lookup(FECHAMENTO, {"indRetificacao": "1", "semestre": "2027-06"}, reports))
        self.assertTrue(homologate.is_event_original(FECHAMENTO, {"indRetificacao": "1", "semestre": "2026-06"}))
        self.assertFalse(homologate.is_event_original(FECHAMENTO, {"indRetificacao": "2", "semestre": "2026-06"}))

    def test_every_event_document_mirrors_its_contract_filing(self):
        """`original` and `period` are the contract's filing.remittance and
        filing.period: a mismatch would judge another period's approved original."""
        import yaml

        for document_id, spec in homologate.EVENT_DOCUMENTS.items():
            with self.subTest(document=document_id):
                contract = yaml.safe_load((ROOT / homologate.document_dir(document_id) / "contract.yaml")
                                          .read_text(encoding="utf-8"))
                filing = contract.get("filing") or {}
                remittance = filing.get("remittance")
                if remittance is None:
                    self.assertNotIn("original", spec)
                else:
                    self.assertEqual(spec.get("original"), (remittance["parameter"], remittance["original"]))
                    self.assertEqual(tuple(spec.get("period") or ()), tuple(filing.get("period") or ()))


class EventRun(unittest.TestCase):
    """run_event against stubs: which path an entry takes, not what the file says."""

    def run_entry(self, document_id, doc, final=None, earlier=None, report=None, answer=None):
        """Runs one entry; `earlier` pre-seeds the reports remembered by the run,
        `report` is what GET /v1/reports/<id> answers and `answer` what the
        generation request answers (for a refused entry)."""
        rep = mock.Mock()
        rep.get.return_value = (200, report if report is not None else {"status": "Draft", "openGaps": []})
        rep.raw.return_value = (200, {}, b"<?xml version='1.0'?><x/>")
        rep.call.return_value = answer or (500, {})
        lg = types.SimpleNamespace(sc={"organization": {"legalDocument": "EF9J2K7A000114"}})
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        args = types.SimpleNamespace(bindings=None, catalog=str(ROOT), out=folder.name)
        run = {"subscriptions": {document_id: "sub-1"}, "ids": [], "bases": {}, "reports": dict(earlier or {})}
        out = io.StringIO()
        with mock.patch.object(homologate, "apply_filled_binding", return_value="inalterado"), \
                mock.patch.object(homologate, "approved_event_original", return_value=final) as lookup, \
                mock.patch.object(homologate, "request_report", return_value=("rep-1", {"status": "Draft"})) as request, \
                mock.patch.object(homologate, "judge_event", return_value=([], 7)), \
                mock.patch.object(homologate, "approve", return_value="Final") as approve, \
                contextlib.redirect_stdout(out):
            failures = homologate.run_event(rep, lg, args, doc, "inst-1", run)
        self.stdout = out.getvalue()
        return failures, lookup, request, approve, run

    def test_an_exclusion_marked_approve_is_generated_and_never_looked_up_as_an_original(self):
        for document_id in EXCLUSIONS:
            doc = {"documentId": document_id, "label": "x", "approve": True,
                   "parameters": {"nrReciboEvento": "1-01-001-2026-1"}, "elements": {}}
            failures, lookup, request, approve, _ = self.run_entry(document_id, doc, final={"id": "old"})
            self.assertEqual(failures, 0)
            lookup.assert_not_called()
            request.assert_called_once()
            approve.assert_called_once()

    def test_the_registration_original_still_judges_the_approved_one(self):
        doc = {"documentId": DOCUMENT, "label": "original", "approve": True,
               "parameters": {"indRetificacao": "1"}, "elements": {}}
        failures, lookup, request, approve, _ = self.run_entry(DOCUMENT, doc, final={"id": "old", "status": "Final"})
        self.assertEqual(failures, 0)
        lookup.assert_called_once()
        request.assert_not_called()
        approve.assert_not_called()

    def test_an_entry_is_remembered_by_its_document_and_label(self):
        doc = {"documentId": EXCLUSIONS[0], "label": "primeira",
               "parameters": {"nrReciboEvento": "1-01-001-2026-1"}, "elements": {}}
        _, _, _, _, run = self.run_entry(EXCLUSIONS[0], doc)
        self.assertEqual(run["reports"], {(EXCLUSIONS[0], "primeira"): "rep-1"})

    def superseding(self, superseded_by):
        doc = {"documentId": EXCLUSIONS[0], "label": "segunda", "supersedes": "primeira",
               "parameters": {"nrReciboEvento": "1-01-001-2026-1"}, "elements": {}}
        return self.run_entry(EXCLUSIONS[0], doc, earlier={(EXCLUSIONS[0], "primeira"): "rep-0"},
                              report={"status": "Draft", "openGaps": [], "supersededBy": superseded_by})

    def test_supersedes_fails_when_the_earlier_draft_names_another_report(self):
        failures, _, _, _, _ = self.superseding("rep-other")
        self.assertEqual(failures, 1)
        self.assertIn("supersededBy rep-other, esperado rep-1", self.stdout)

    def test_supersedes_passes_when_the_earlier_draft_names_the_new_report(self):
        failures, _, _, _, run = self.superseding("rep-1")
        self.assertEqual(failures, 0, self.stdout)
        self.assertEqual(run["reports"][(EXCLUSIONS[0], "segunda")], "rep-1")

    def test_a_refused_entry_prints_its_own_event_name(self):
        doc = {"documentId": EXCLUSIONS[0], "label": "recusa", "parameters": {"nrReciboEvento": "x"},
               "refused": {"status": 400, "code": "RPT-0140", "detailContains": ["nrReciboEvento"]}}
        failures, _, request, _, _ = self.run_entry(EXCLUSIONS[0], doc,
                                                    answer=(400, {"code": "RPT-0140", "detail": "nrReciboEvento: formato"}))
        self.assertEqual(failures, 0, self.stdout)
        request.assert_not_called()
        self.assertRegex(self.stdout, r"^OK\s+evtExclusao\s+recusa\s")
        self.assertNotIn("evtCadDeclarante", self.stdout)


class EventEntries(unittest.TestCase):
    """check_event_entries: what makes the gabarito's event entries ambiguous."""

    def refuses(self, documents):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            homologate.check_event_entries(documents)
        return err.getvalue()

    def entry(self, document_id, label, supersedes=None):
        doc = {"documentId": document_id, "label": label, "parameters": {}}
        if supersedes:
            doc["supersedes"] = supersedes
        return doc

    def test_a_repeated_label_stops_the_run(self):
        said = self.refuses([self.entry(EXCLUSIONS[0], "a"), self.entry(EXCLUSIONS[1], "a")])
        self.assertIn("repete o label 'a'", said)

    def test_supersedes_of_another_document_stops_the_run(self):
        said = self.refuses([self.entry(EXCLUSIONS[0], "a"), self.entry(EXCLUSIONS[1], "b", supersedes="a")])
        self.assertIn("de outro documento", said)

    def test_supersedes_of_an_entry_not_listed_before_stops_the_run(self):
        said = self.refuses([self.entry(EXCLUSIONS[0], "b", supersedes="a"), self.entry(EXCLUSIONS[0], "a")])
        self.assertIn("listada antes", said)

    def test_supersedes_of_a_refused_or_errored_entry_stops_the_run(self):
        for outcome in ("refused", "errored"):
            with self.subTest(outcome=outcome):
                earlier = self.entry(EXCLUSIONS[0], "a")
                earlier[outcome] = True
                said = self.refuses([earlier, self.entry(EXCLUSIONS[0], "b", supersedes="a")])
                self.assertIn("marcada %s" % outcome, said)

    def test_run_reports_checks_the_entries_before_generating(self):
        documents = [self.entry(EXCLUSIONS[0], "a"), self.entry(EXCLUSIONS[1], "a")]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gabarito.json"
            path.write_text(json.dumps({"documents": documents}), encoding="utf-8")
            args = types.SimpleNamespace(expected=str(path), reporter="http://reporter.invalid")
            err = io.StringIO()
            with mock.patch.object(homologate, "Reporter") as reporter, \
                    mock.patch.object(homologate, "ensure_institution") as institution, \
                    mock.patch.object(homologate, "run_event") as event, \
                    mock.patch.object(homologate, "generate") as generate, \
                    contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                homologate.run_reports(mock.Mock(), args)
        self.assertIn("repete o label 'a'", err.getvalue())
        for called in (reporter, institution, event, generate):
            called.assert_not_called()

    def test_supersedes_within_the_same_document_passes(self):
        homologate.check_event_entries([self.entry(EXCLUSIONS[0], "a"), {"document": "4111"},
                                        self.entry(EXCLUSIONS[0], "b", supersedes="a")])

    def test_every_gabarito_has_unique_labels(self):
        for path in sorted((HERE / "expected").glob("*.json")):
            documents = json.loads(path.read_text(encoding="utf-8"))["documents"]
            labels = [d["label"] for d in documents if "label" in d]
            self.assertEqual(len(labels), len(set(labels)), path.name)
            homologate.check_event_entries(documents)


class Superseded(unittest.TestCase):
    def rep(self, answer):
        rep = mock.Mock()
        rep.get.return_value = (200, answer)
        return rep

    def run_with(self, reports):
        return {"reports": {(EXCLUSIONS[0], label): report for label, report in reports.items()}}

    def test_the_earlier_draft_names_the_newer_one(self):
        rep = self.rep({"status": "Draft", "supersededBy": "rep-2"})
        self.assertEqual(homologate.superseded_problems(rep, self.run_with({"a": "rep-1"}), EXCLUSIONS[0], "a", "rep-2"), [])
        rep.get.assert_called_once_with("/v1/reports/rep-1")

    def test_an_earlier_draft_not_superseded_fails(self):
        problems = homologate.superseded_problems(self.rep({"status": "Draft"}), self.run_with({"a": "rep-1"}),
                                                  EXCLUSIONS[0], "a", "rep-2")
        self.assertEqual(len(problems), 1)
        self.assertIn("supersededBy None", problems[0])

    def test_an_earlier_report_that_left_draft_fails(self):
        problems = homologate.superseded_problems(self.rep({"status": "Final", "supersededBy": "rep-2"}),
                                                  self.run_with({"a": "rep-1"}), EXCLUSIONS[0], "a", "rep-2")
        self.assertEqual(len(problems), 1)
        self.assertIn("ficou em Final", problems[0])

    def test_a_label_not_generated_before_fails(self):
        problems = homologate.superseded_problems(self.rep({}), self.run_with({}), EXCLUSIONS[0], "a", "rep-2")
        self.assertIn("não foi gerada antes", problems[0])

    def test_the_same_label_of_another_document_is_not_the_earlier_entry(self):
        run = {"reports": {(EXCLUSIONS[1], "a"): "rep-1"}}
        problems = homologate.superseded_problems(self.rep({}), run, EXCLUSIONS[0], "a", "rep-2")
        self.assertIn("não foi gerada antes", problems[0])


if __name__ == "__main__":
    unittest.main(verbosity=1)
