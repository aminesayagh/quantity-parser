# quantity-parser

Strict parser that turns a **complete** English numeric phrase into an exact, typed quantity.
Experiment v0.1, built from `text-to-number-experiment.md` (26 Oct 2026). Not publication-ready.

```python
from quantity_parser import parse_quantity

r = parse_quantity("two and a half times")
r.status                # "resolved"
r.quantity.value        # Fraction(5, 2)
r.quantity.form         # "mixed_number"
r.quantity.kind         # "multiplier"
r.to_dict()             # JSON-ready, see contract below

parse_quantity("one hundredth").status                          # "ambiguous" (1/100 or 100th)
parse_quantity("one hundredth", expected_kind="ordinal").quantity.value   # Fraction(100)
parse_quantity("third row").status                              # "unsupported" (unknown word "row")
```

## Contract

| Field | Meaning |
|---|---|
| `status` | `resolved` (exactly one reading), `ambiguous` (several; listed in `interpretations`, never picked), `unsupported` (out of scope: unknown word, other language, no reading of `expected_kind`), `invalid` (in-vocabulary but malformed: incomplete, zero denominator, limits) |
| `quantity.value` | exact `fractions.Fraction`, lowest terms, positive denominator. Percentages are ratios: `15%` → `3/20` |
| `quantity.form` | `integer`, `decimal`, `fraction`, `mixed_number`, `ordinal` (how it was written) |
| `quantity.kind` | `number`, `ordinal`, `multiplier`, `percentage` (how it is meant). Form and kind are independent. |
| `span` | zero-based, end-exclusive offsets into the original string. For token-level failures it points at the offending token. |

`quantity` is `None` unless the status is `resolved`. If the backend fails for any reason other than "not a cardinal", the parser raises an exception instead of returning `unsupported`.

## Supported forms

- **Integers**: `25`, `1,500` (en-US grouping), `twenty-five`, `one hundred and twenty`, `a hundred`, up to the billions. Malformed grouping such as `1,50` or `12,3456` is `invalid`.
- **Decimals**: `1.25`, `1,250.50`, `.5`, `two point zero five`. Values never pass through `float`.
- **Signs**: one outer `minus` / `negative` / `-` / `−` / `plus` / `+`. `minus two and a half` → `-5/2`.
- **Fractions**:
  - `half`, `a third`, `one half`, `three fifths`, `three over eight`, `3/8`.
  - Compound denominators: `three twenty-fifths`, `seven hundredths`.
- **Mixed numbers**: `two and a half`, `2 1/2`, `two and 1/2`. The fractional part must be proper.
- **Multipliers**: `once`, `twice`, `thrice`, `double`, `triple`, `quadruple`, `halve` / `halves` / `halved` / `halving` (1/2), `<any value> times`, and `2.5x` / `3 x` (digits only). A bare `halves` is the verb; `three halves` is still the fraction 3/2.
- **Percentages**: `15%`, `fifteen percent`, `2.5 per cent`, `half a percent`, `a quarter of a percent`.
- **Ordinals**: `third`, `twenty first`, `one hundred and third`, `21st`. The suffix is checked, so `3th` is invalid.

### Strictness rules worth knowing

- **Whole input only.** One unknown word makes the result `unsupported`. Examples: `double room`, `the first half of the year`.
- **Number agreement.** `one thirds` and `three fifth` are invalid.
- **`and` only after a scale word.** text2num accepts `fifty and two` (= 52). Without this rule, `fifty and two thirds` would also read as 52/3.
- **Real ambiguity is reported, not resolved.** Examples:
  - `one hundred and two thirds` (100⅔ or 102/3).
  - `two hundred fifths` (40 or 2/105).
  - `one hundredth` (1/100 or the ordinal 100).
- **`expected_kind` filters but never coerces.** `third` with `expected_kind="number"` is `unsupported`; it is not turned into ⅓.
- **Limits.** 256 characters, 48 tokens, 64 parse trees, and a magnitude of 10¹⁵. Breaking a limit gives `invalid` with a `limit_exceeded:` reason.

## Not supported yet

- **Locales other than en-US** (`1.000,5`, `1 000`). The plan's Babel phase is skipped; `locale` is not a parameter yet.
- **Large scales and alternative zeros**: `trillion` (text2num 3.1.0 rejects it), `nought`, `oh`.
- **Unicode vulgar fractions**: `½`.
- **Other multiplier forms**: `two x` (word + x), `one time`, `N-fold`, `doubled` / `tripled`, and signed multipliers.
- **Bare `quarter`** (only `a quarter` / `one quarter` are accepted). Also unsupported: `X out of Y`, `a dozen`, and digit-sequence readings like `five five`.
- **Extraction from sentences, currencies, units, dates, and languages other than English.** These are out of scope by design.

## How it works

```
text ─► tokenize (offsets kept) ─► vocab check ─► Lark Earley forest (explicit ambiguity)
     ─► expand every tree ─► evaluate with text2num adapter + exact Fraction ─► dedupe ─► status
```

| File | Role |
|---|---|
| `grammar.lark` | Structure only: number / percentage / multiplier / ordinal, fractions, mixed numbers |
| `en.py` | Word lists. They generate the grammar's word rules and the evaluator's tables |
| `cardinal.py` | The only module that calls text2num, with a bounded `lru_cache` |
| `parser.py` | Tokenizer, evaluator, `parse_quantity` |
| `models.py` | `Quantity`, `ParseResult`, serialization |

### The text2num ↔ Lark integration (the plan's main open question)

**The approach.** Cardinal spans are loose word sequences in the grammar. Earley with `ambiguity="explicit"` keeps every possible boundary, so `three twenty fifths` yields both `three | twenty fifths` and `three twenty | fifths`. Each tree is then evaluated, and its cardinal segments go through text2num as complete spans. Trees with an invalid segment are dropped. If several distinct readings survive, the result is `ambiguous`.

**Why Lark over a custom parser.** The grammar is 40 lines and readable. Ambiguity comes from the parser itself, not from hidden regex matching. Latency is in the low milliseconds (see below).

**Kept simple on purpose:**

- The whole forest is expanded instead of being pruned lazily. The token cap keeps that small.
- The `docs/` and the separate `normalize`/`literals`/`evaluator` modules from the plan's layout are folded into fewer files. Split them when they grow.

## Using it from another project

Add it as a uv path dependency: `quantity-parser = { path = "../text_to_number" }` under `[tool.uv.sources]` (or run `uv add ../text_to_number`). The wheel ships `grammar.lark`.

**Threads.** The Lark parser is built once at import and reused. Each `parse()` keeps its state in local variables, and the adapter cache is a thread-safe `lru_cache`. A 16-thread stress test (52,000 parses) matched the single-threaded results exactly.

## Tests

```bash
uv sync
uv run pytest -q          # 114 passed
```

- `tests/fixtures/required_examples.jsonl`: the plan's required-examples table, verbatim.
- `tests/test_parser.py`:
  - every supported form;
  - the rejections;
  - ambiguity;
  - `expected_kind`;
  - spans;
  - the JSON contract;
  - backend failure raising instead of returning a status.
- `tests/test_properties.py` (Hypothesis): integers in words and digits, ratio normalization and round-trip, outer sign on mixed numbers, percentage = value/100, whitespace invariance, extra words blocking resolution, span correctness. It uses an independent number-to-words renderer. On its first run it found the `fifty and two thirds` ambiguity described above.

## Performance

`uv run python benchmarks/latency.py`, measured on 2026-10-26:

```
python 3.13.13 | Linux 6.18 WSL2 x86_64 | i9-13900H (20 threads)
lark 1.3.1 | text2num 3.1.0 | 20 cases x 200 rounds
cold start (import + first parse): 55 ms
warm, adapter cache hot:   p50 1.23 ms  p95 2.56 ms
warm, adapter cache clear: p50 1.18 ms  p95 2.44 ms
```

The adapter cache makes almost no difference, so the cost is in Earley parsing. No latency budget has been agreed yet. If one is set below this, try LALR or pruning first, and profile before anything else.

## Plan status

| Step | State |
|---|---|
| E0 baseline | **Not done.** The application's 52 development and 21 held-out cases are not in this repo. Nothing was invented in their place. Import them to get a baseline comparison. |
| E1 literals + adapter | Done |
| E2 fractions + mixed | Done |
| E3 multipliers, percentages, ordinals | Done |
| E4 strictness + performance | Limits and latency done. Babel/locale skipped. |
| E5 application integration | Not started (needs the application) |

Environment: Python 3.13.13 through uv. Dependencies are pinned to `lark==1.3.1` and `text2num==3.1.0`, and the lock is in `uv.lock`.
