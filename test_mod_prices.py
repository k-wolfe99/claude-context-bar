#!/usr/bin/env python3
"""
The mod keeps its own copy of the price table (mod/hooks/format.ts), because a
mod can't import Python. check_pricing.py only checks claude-context-bar.py, so
this test fails if the two copies disagree.

    python3 test_mod_prices.py
"""
import ast, os, re, unittest

import check_pricing

HERE = os.path.dirname(os.path.abspath(__file__))
FORMAT_TS = os.path.join(HERE, "mod", "hooks", "format.ts")
REGISTER_TSX = os.path.join(HERE, "mod", "hooks", "register.tsx")

# [['fable-5-1', 'fable 5.1'], 10.0, 0.025], or tiers: [[100_000, 0.1], [null, 0.5]]
ROW = re.compile(r"\[\[([^\]]*)\],\s*(\[\[.*?\]\]|[\d.]+),\s*([\d.]+)\]")
NEEDLE = re.compile(r"'([^']*)'")
# const writeMult = ttlMs > 300_000 ? 2 : 1.25
WRITE = re.compile(r"writeMult\s*=\s*ttlMs\s*>\s*300_000\s*\?\s*([\d.]+)\s*:\s*([\d.]+)")


def rate(value):
    """A rate as a float, or tiers as ((limit or None, float), ...), from
    either side: the script's literal or the TypeScript source text."""
    if isinstance(value, str):
        value = ast.literal_eval(value.replace("null", "None"))
    if isinstance(value, (list, tuple)):
        return tuple((limit, float(r)) for limit, r in value)
    return float(value)


def mod_prices():
    src = open(FORMAT_TS).read()
    table = src[src.index("export const PRICES"):]
    table = table[:table.index("\n]")]
    return [(tuple(NEEDLE.findall(needles)), rate(r), float(read))
            for needles, r, read in ROW.findall(table)]


class ModPricesMatchScript(unittest.TestCase):
    def setUp(self):
        self.prices, self.write_5m, self.write_1h = check_pricing.load_script(check_pricing.SCRIPT)

    def test_same_rows_in_the_same_order(self):
        # Order matters as much as the rates: lookup is first match wins.
        self.assertEqual(mod_prices(), [(tuple(n), rate(r), float(m)) for n, r, m in self.prices])

    def test_same_cache_write_multipliers(self):
        match = WRITE.search(open(REGISTER_TSX).read())
        self.assertIsNotNone(match, "writeMult not found in register.tsx")
        self.assertEqual((float(match[2]), float(match[1])), (self.write_5m, self.write_1h))


if __name__ == "__main__":
    unittest.main()
