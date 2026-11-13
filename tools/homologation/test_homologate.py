#!/usr/bin/env python3
# Copyright (c) 2026 Lerian Studio Ltd.
# Use of this source code is governed by the Elastic License 2.0
# that can be found in the LICENSE file.
"""How homologate.py puts an entry's binding on a subscription, against a fake
Reporter: no Midaz and no Reporter are needed.

    python3 tools/homologation/test_homologate.py
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
