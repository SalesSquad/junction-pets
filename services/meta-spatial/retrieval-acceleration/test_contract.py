import unittest
from contract import ContractError, strict_json_loads


class StrictJSONTest(unittest.TestCase):
    def test_rejects_duplicate_keys_and_nonfinite_literals(self):
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":-1e999}'):
            with self.subTest(raw=raw), self.assertRaises(ContractError):
                strict_json_loads(raw)

    def test_accepts_finite_json_and_rejects_non_utf8(self):
        self.assertEqual(strict_json_loads(b'{"x":1e-9,"ok":false}'), {"x":1e-9,"ok":False})
        with self.assertRaises(ContractError):
            strict_json_loads('{"x":1}'.encode("utf-16"))

    def test_excessive_nesting_is_a_contract_error(self):
        self.assertIsInstance(strict_json_loads("[" * 64 + "0" + "]" * 64), list)
        for count in (65, 2000):
            with self.subTest(depth=count), self.assertRaises(ContractError):
                strict_json_loads("[" * count + "0" + "]" * count)


if __name__ == "__main__":
    unittest.main()
