"""Roadmap 3.7.0 Gate: QR encoder (decoded with a reference decoder) + short pairing code contract.

The reference decode uses zbar (pyzbar + Pillow). CI Linux installs them and sets AIWB_REQUIRE_QR_DECODER=1,
so the decode test cannot be silently skipped there.
"""
from __future__ import annotations

import json
import os
import random
import string
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aiwb.companion import crypto, pairing  # noqa: E402
from aiwb.companion.service import CompanionService, DeviceRegistry  # noqa: E402
from aiwb.ui import qr  # noqa: E402

VECTORS = Path(__file__).resolve().parents[3] / "packages/contracts/vectors/companion-pairing.v2.json"

try:
    from PIL import Image
    from pyzbar.pyzbar import decode as zbar_decode
except Exception:  # noqa: BLE001 - decoder is optional outside CI
    Image = zbar_decode = None


def render(matrix, scale=4, quiet=4):
    n = len(matrix)
    img = Image.new("L", ((n + 2 * quiet) * scale,) * 2, 255)
    px = img.load()
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                for dy in range(scale):
                    for dx in range(scale):
                        px[(x + quiet) * scale + dx, (y + quiet) * scale + dy] = 0
    return img


class QrEncoderTests(unittest.TestCase):
    def test_reed_solomon_known_vector(self):
        # ISO/IEC 18004 Annex I example: "01234567" 1-M data codewords -> 10 EC codewords
        data = [0x10, 0x20, 0x0C, 0x56, 0x61, 0x80, 0xEC, 0x11, 0xEC, 0x11, 0xEC, 0x11, 0xEC, 0x11, 0xEC, 0x11]
        self.assertEqual(qr.rs_remainder(data, 10), [0xA5, 0x24, 0xD4, 0xC1, 0xED, 0x36, 0xC7, 0x87, 0x2C, 0x55])

    def test_structure(self):
        m = qr.encode("aiwb://pair?h=192.168.1.20&p=47821&k=AAISEM2EKVTHPCEZ")
        n = len(m)
        self.assertEqual((n - 17) % 4, 0)
        for cx, cy in ((0, 0), (n - 7, 0), (0, n - 7)):   # finder patterns
            self.assertTrue(all(m[cy][cx + i] and m[cy + 6][cx + i] for i in range(7)))
            self.assertTrue(m[cy + 3][cx + 3])
        self.assertTrue(m[n - 8][8], "dark module")
        self.assertEqual([m[6][i] for i in range(8, n - 8)], [i % 2 == 0 for i in range(8, n - 8)], "timing")

    def test_version_selection_and_limits(self):
        self.assertEqual(len(qr.encode("a" * 14, "M")), 21)
        self.assertEqual(len(qr.encode("a" * 15, "M")), 25)
        with self.assertRaises(qr.QrError):
            qr.encode("a" * 400, "H")
        with self.assertRaises(qr.QrError):
            qr.encode("x", "Z")

    @unittest.skipIf(zbar_decode is None and not os.environ.get("AIWB_REQUIRE_QR_DECODER"), "zbar not installed")
    def test_reference_decoder_reads_every_version_level_and_mask(self):
        self.assertIsNotNone(zbar_decode, "AIWB_REQUIRE_QR_DECODER is set but pyzbar/Pillow are missing")
        rnd = random.Random(37)
        alphabet = string.ascii_letters + string.digits + ":/?=&-_.%"
        checked = set()
        for level in "LMQH":
            for n in (1, 10, 20, 40, 60, 90, 120, 160, 200, 260):
                text = "".join(rnd.choice(alphabet) for _ in range(n))
                try:
                    qr.encode(text, level)
                except qr.QrError:
                    continue
                for mask in range(8):
                    m = qr.encode(text, level, mask=mask)
                    got = zbar_decode(render(m))
                    self.assertTrue(got, f"{level} n={n} mask={mask} not decoded")
                    self.assertEqual(got[0].data.decode("utf-8"), text)
                    checked.add((len(m) - 17) // 4)
        self.assertEqual(checked, set(range(1, 11)), "versions 1-10 all exercised")
        uri = pairing.build_uri("192.168.1.20", 47821, bytes(10))
        self.assertEqual(zbar_decode(render(qr.encode(uri)))[0].data.decode(), uri)

    def test_canvas_draw(self):
        class FakeCanvas:
            def __init__(self):
                self.rects = []

            def delete(self, tag):
                self.rects.clear()

            def create_rectangle(self, *xy, **kw):
                self.rects.append((xy, kw))

        c = FakeCanvas()
        m = qr.encode("hello")
        side = qr.draw(c, m, module=5)
        self.assertEqual(side, (21 + 8) * 5)
        self.assertEqual(c.rects[0][1]["fill"], "#ffffff")
        dark = sum((xy[2] - xy[0] + 1) // 5 for xy, kw in c.rects[1:])
        self.assertEqual(dark, sum(map(sum, m)), "every dark module drawn (runs merged)")


class PairingCodeContractTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(VECTORS.read_text(encoding="utf-8"))

    def test_vectors(self):
        self.assertEqual(self.doc["ttl_seconds"], 600)
        self.assertEqual(self.doc["max_failed_attempts"], 5)
        for c in self.doc["cases"]:
            raw = bytes.fromhex(c["secret_hex"])
            self.assertEqual(pairing.code_from_secret(raw), c["code"])
            self.assertEqual(len(c["code"]), 16)
            self.assertEqual(pairing.format_code(c["code"]), c["formatted"])
            self.assertEqual(pairing.build_uri(c["host"], c["port"], raw), c["uri"])
            self.assertEqual(pairing.parse_uri(c["uri"]), (c["host"], c["port"], raw))
            self.assertEqual(pairing.pairing_id(raw), c["pairing_id"])
            self.assertEqual(crypto.b64e(pairing.master_key(raw)), c["master_key_b64url"])
            self.assertEqual(pairing.secret_from_code(c["formatted"]), raw)

    def test_normalize_and_invalid(self):
        for n in self.doc["normalize"]:
            self.assertEqual(pairing.normalize_code(n["input"]), n["code"])
        for bad in self.doc["invalid_codes"]:
            with self.assertRaises(pairing.PairingCodeError, msg=bad):
                pairing.normalize_code(bad)
        for bad in self.doc["invalid_uris"]:
            with self.assertRaises(pairing.PairingCodeError, msg=bad):
                pairing.parse_uri(bad)

    def test_eighty_bits(self):
        self.assertEqual(pairing.SECRET_BYTES * 8, 80)
        self.assertEqual(len({pairing.code_from_secret(pairing.new_secret()) for _ in range(200)}), 200)


class ServiceLockoutTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [1_800_000_000.0]
        self.svc = CompanionService(DeviceRegistry(Path(self.tmp.name) / "d.json"), controller=lambda: None,
                                    clock=lambda: self.now[0])

    def tearDown(self):
        self.tmp.cleanup()

    def send(self, kid, key, req):
        env = crypto.seal(key, kid, req, ts=int(self.now[0]))
        return self.svc.handle(json.dumps(env).encode())

    def test_manual_code_round_trip(self):
        uri = self.svc.start_pairing("192.168.1.20", 47821)
        code = self.svc.pairing_code()
        self.assertRegex(code, r"^[A-Z2-7]{4}-[A-Z2-7]{4}-[A-Z2-7]{4}-[A-Z2-7]{4}$")
        raw = pairing.secret_from_code(code)
        self.assertEqual(pairing.parse_uri(uri)[2], raw, "QR and manual code carry the same secret")
        st, out = self.send(pairing.pairing_id(raw), pairing.master_key(raw), {"op": "pair_status"})
        self.assertEqual(st, 200)
        self.assertEqual(crypto.open_json(pairing.master_key(raw), out, now=self.now[0])["status"], "pending")
        self.assertEqual(self.svc.pairing_state()["state"], "active")
        self.assertEqual(self.svc.pairing_state()["seconds_left"], 600)
        self.now[0] += 601
        self.assertEqual(self.svc.pairing_state()["state"], "expired")

    def test_five_wrong_attempts_cancel_the_code(self):
        self.svc.start_pairing("192.168.1.20", 47821)
        good = pairing.secret_from_code(self.svc.pairing_code())
        for i in range(4):
            wrong = pairing.new_secret()
            st, _ = self.send(pairing.pairing_id(wrong), pairing.master_key(wrong), {"op": "pair_status"})
            self.assertEqual(st, 403)
            self.assertEqual(self.svc.pairing_state()["state"], "active", i)
        # a forged envelope with the right id but a wrong key also counts
        st, _ = self.send(pairing.pairing_id(good), os.urandom(32), {"op": "pair_status"})
        self.assertEqual(st, 401)
        self.assertEqual(self.svc.pairing_state()["state"], "locked")
        st, _ = self.send(pairing.pairing_id(good), pairing.master_key(good), {"op": "pair_status"})
        self.assertEqual(st, 403, "even the right code is refused after the lockout")
        self.svc.start_pairing("192.168.1.20", 47821)
        self.assertEqual(self.svc.pairing_state()["state"], "active")


if __name__ == "__main__":
    unittest.main()
