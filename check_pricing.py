#!/usr/bin/env python3
"""
Compare the prices in claude-context-bar.py against Anthropic's live pricing
page, and report every model whose rates have drifted or that the script has
no entry for.

    python3 check_pricing.py                 # fetch the live page
    python3 check_pricing.py --file page.md  # check a saved copy

Exit status: 0 in sync, 1 drift found (report on stdout), 2 the page could not
be fetched or its layout was not recognised (reason on stderr).

Standard library only, so it runs anywhere the status line does.
"""
import argparse, ast, os, re, sys, urllib.request

PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing.md"
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-context-bar.py")

# Page columns this check reads, by header text.
COLUMNS = {
    "input": "base input tokens",
    "write_5m": "5m cache writes",
    "write_1h": "1h cache writes",
    "read": "cache hits and refreshes",
}

PRICE = re.compile(r"^\$(\d+(?:\.\d+)?)\s*/\s*MTok$")
LINK_ASIDE = re.compile(r"\s*\(\[[^\]]*\]\([^)]*\)\)")  # " ([retired, ...](url))"
SUP = re.compile(r"<sup>.*?</sup>")

TOLERANCE = 0.0005  # $/MTok; page prices are quoted to the cent at most


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_price(cell, model, column):
    m = PRICE.match(SUP.sub("", cell).strip())
    if not m:
        raise ValueError(f"unrecognised {column} price for {model!r}: {cell!r}")
    return float(m.group(1))


def parse_page(md):
    """Current models from the page's main pricing table, as dicts with
    name, input, write_5m, write_1h and read in $/MTok.

    Retired models are skipped: Claude Code cannot select them. Raises
    ValueError if the table is missing or a price is not in the expected form,
    so a page redesign fails loudly instead of reading as zero drift.
    """
    lines = md.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|"):
            header = [c.lower() for c in cells(line)]
            if all(col in header for col in COLUMNS.values()):
                break
    else:
        raise ValueError("pricing table not found (no row with the expected column headers)")

    index = {key: header.index(col) for key, col in COLUMNS.items()}
    rows = []
    for line in lines[i + 2:]:  # skip the header and its :--- separator
        if not line.lstrip().startswith("|"):
            break
        row = cells(line)
        if "retired" in row[0].lower():
            continue
        name = LINK_ASIDE.sub("", row[0]).strip()
        rows.append({"name": name,
                     **{key: parse_price(row[j], name, key) for key, j in index.items()}})
    if not rows:
        raise ValueError("pricing table found but it has no current models")
    return rows


def load_script(path):
    """(PRICES, 5m write multiplier, 1h write multiplier) read from the
    script's source. The script consumes stdin at import time, so it is parsed
    rather than imported."""
    tree = ast.parse(open(path).read(), path)
    prices = write = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = getattr(node.targets[0], "id", None)
            if target == "PRICES":
                prices = ast.literal_eval(node.value)
            elif target == "CACHE_WRITE_MULT":
                write = node.value
    if prices is None or not isinstance(write, ast.IfExp):
        raise ValueError(f"PRICES or CACHE_WRITE_MULT not found in {path}")
    # CACHE_WRITE_MULT = <1h> if TTL_SECONDS > 300 else <5m>
    return prices, ast.literal_eval(write.orelse), ast.literal_eval(write.body)


def match(name, prices):
    """The script's first-match lookup, applied to a page model name."""
    ident = name.lower()
    for needles, rate, read_mult in prices:
        if any(n in ident for n in needles):
            return rate, read_mult
    return None


def compare(rows, prices, write_5m, write_1h):
    """Human-readable discrepancies, one per mismatched figure."""
    found = []
    for row in rows:
        name = row["name"]
        hit = match(name, prices)
        if hit is None:
            found.append(f"{name}: no entry in PRICES, so the status line shows no price "
                         f"(page: ${row['input']:g} input, ${row['read']:g} cache read)")
            continue
        rate, read_mult = hit
        expected = {
            "input": rate,
            "cache read": rate * read_mult,
            "5m cache write": rate * write_5m,
            "1h cache write": rate * write_1h,
        }
        actual = {
            "input": row["input"],
            "cache read": row["read"],
            "5m cache write": row["write_5m"],
            "1h cache write": row["write_1h"],
        }
        for label, want in expected.items():
            if abs(actual[label] - want) > TOLERANCE:
                found.append(f"{name}: {label} is ${actual[label]:g}/MTok on the page, "
                             f"${want:g}/MTok in the script")
    return found


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "claude-context-bar pricing check"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--file", help="check a saved copy of the page instead of fetching it")
    args = ap.parse_args(argv)

    try:
        md = open(args.file).read() if args.file else fetch(PRICING_URL)
        rows = parse_page(md)
        found = compare(rows, *load_script(SCRIPT))
    except Exception as e:  # network, layout, or script changes all mean "can't tell"
        print(f"check_pricing: {e}", file=sys.stderr)
        return 2

    if not found:
        print(f"Prices in sync with {PRICING_URL} ({len(rows)} current models checked).")
        return 0
    print(f"Prices in claude-context-bar.py differ from {PRICING_URL}:\n")
    for line in found:
        print(f"- {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
