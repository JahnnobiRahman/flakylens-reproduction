"""
Formatting robustness: how many semantics-preserving whitespace changes flip
the prediction, and by how much does confidence move.

Each transformation below changes only whitespace. No identifier is renamed, no
token is added or removed, no code is reordered. A compiler would produce
identical bytecode for every variant.

Run from /app/src:
    python3 format_robustness.py

Config below: FOLD, and SAMPLE_NONFLAKY (all flaky tests are always used; the
non-flaky class is sampled because there are ~2000 of them and they dominate
the runtime).

Writes:
    /output/session4/format_robustness_fold{FOLD}.csv   one row per test per transform
    stdout                                              summary tables
"""
import re
import random
import torch
import pandas as pd

from utils import codebert_model_define
from codebert_model import BERT_Arch

FOLD = 1
MAX_LEN = 512
SAMPLE_NONFLAKY = 300
SEED = 42

BASE = '/output/session2/FlakyLens_Categorization_PerProject-Data/'
TEST_SET = BASE + f'test_set_{FOLD}.csv'
WEIGHTS = f'../models/per_project_model_weights_on__dataset_project_group_{FOLD}.pt'
OUT = f'/output/session4/format_robustness_fold{FOLD}.csv'


# ---------------------------------------------------------------- transforms

def t_indent2(src):
    """Add two spaces to every line after the first."""
    return '\n  '.join(str(src).splitlines())


def t_indent4(src):
    """Add four spaces. This is what variableRenaming_perturbation does."""
    return '\n    '.join(str(src).splitlines())


def t_indent8(src):
    """Add eight spaces."""
    return '\n        '.join(str(src).splitlines())


def t_spaces_to_tabs(src):
    """Convert leading four-space groups to tabs."""
    out = []
    for ln in str(src).splitlines():
        stripped = ln.lstrip(' ')
        n = len(ln) - len(stripped)
        out.append('\t' * (n // 4) + ' ' * (n % 4) + stripped)
    return '\n'.join(out)


def t_tabs_to_spaces(src):
    """Convert leading tabs to four spaces each."""
    out = []
    for ln in str(src).splitlines():
        stripped = ln.lstrip('\t')
        n = len(ln) - len(stripped)
        out.append('    ' * n + stripped)
    return '\n'.join(out)


def t_strip_indent(src):
    """Remove all leading whitespace from every line."""
    return '\n'.join(ln.lstrip() for ln in str(src).splitlines())


def t_add_blank_lines(src):
    """Insert a blank line after every line."""
    return '\n\n'.join(str(src).splitlines())


def t_remove_blank_lines(src):
    """Drop every blank line."""
    return '\n'.join(ln for ln in str(src).splitlines() if ln.strip())


def t_trailing_newline(src):
    """Append a single trailing newline."""
    return str(src) + '\n'


def t_trailing_spaces(src):
    """Add one trailing space to every line."""
    return '\n'.join(ln + ' ' for ln in str(src).splitlines())


def t_crlf(src):
    """Windows line endings."""
    return str(src).replace('\n', '\r\n')


TRANSFORMS = [
    ('indent +2',        t_indent2),
    ('indent +4',        t_indent4),
    ('indent +8',        t_indent8),
    ('spaces to tabs',   t_spaces_to_tabs),
    ('tabs to spaces',   t_tabs_to_spaces),
    ('strip indent',     t_strip_indent),
    ('add blank lines',  t_add_blank_lines),
    ('remove blank lines', t_remove_blank_lines),
    ('trailing newline', t_trailing_newline),
    ('trailing spaces',  t_trailing_spaces),
    ('CRLF endings',     t_crlf),
]


# ---------------------------------------------------------------------- main

def main():
    random.seed(SEED)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print('device:', device)

    _, tokenizer, auto_model = codebert_model_define()
    model = BERT_Arch(auto_model, 6)
    model.load_state_dict(torch.load(WEIGHTS, map_location=device))
    model.to(device)
    model.eval()
    print('weights:', WEIGHTS)

    t = pd.read_csv(TEST_SET)
    flaky = t[t.category != 5]
    nonflaky = t[t.category == 5]
    if len(nonflaky) > SAMPLE_NONFLAKY:
        nonflaky = nonflaky.sample(SAMPLE_NONFLAKY, random_state=SEED)
    sub = pd.concat([flaky, nonflaky]).reset_index(drop=True)
    print(f'fold {FOLD}: {len(flaky)} flaky, {len(nonflaky)} non-flaky sampled, '
          f'{len(sub)} total, {len(TRANSFORMS)} transformations')
    print(f'{len(sub) * (len(TRANSFORMS) + 1)} predictions to run\n')

    def predict(src):
        enc = tokenizer.batch_encode_plus(
            [src], max_length=MAX_LEN, pad_to_max_length=True, truncation=True)
        ids = torch.tensor(enc['input_ids']).to(device)
        mask = torch.tensor(enc['attention_mask']).to(device)
        with torch.no_grad():
            out = model(ids, mask)
        logits = out[0] if isinstance(out, tuple) else out
        probs = torch.exp(logits)
        k = int(torch.argmax(logits, dim=1)[0])
        return k, float(probs[0][k]), int(mask.sum())

    rows = []
    for i in range(len(sub)):
        src = sub.full_code.iloc[i]
        cat = int(sub.category.iloc[i])
        p0, c0, n0 = predict(src)

        for name, fn in TRANSFORMS:
            variant = fn(src)
            p1, c1, n1 = predict(variant)
            rows.append({
                'test_name': sub.test_name.iloc[i],
                'true_category': cat,
                'true_label': sub.label.iloc[i],
                'transform': name,
                'pred_original': p0,
                'conf_original': round(c0, 4),
                'pred_transformed': p1,
                'conf_transformed': round(c1, 4),
                'flipped': p0 != p1,
                'correct_original': p0 == cat,
                'correct_transformed': p1 == cat,
                'tokens_original': n0,
                'tokens_transformed': n1,
                'token_delta': n1 - n0,
                'conf_delta': round(c1 - c0, 4),
                'whitespace_identical': (
                    re.sub(r'\s+', ' ', str(src)).strip()
                    == re.sub(r'\s+', ' ', str(variant)).strip()),
            })

        if (i + 1) % 50 == 0:
            print('processed', i + 1, 'of', len(sub), flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f'\nwrote {len(out)} rows to {OUT}\n')

    # sanity: every variant should be content-identical to the original
    bad = (~out.whitespace_identical).sum()
    print(f'variants that differ by more than whitespace: {bad} '
          f'(should be 0)\n')

    fl = out[out.true_category != 5]
    nf = out[out.true_category == 5]

    print('=' * 72)
    print('FLIP RATE BY TRANSFORMATION')
    print('=' * 72)
    print(f'{"transformation":<20} {"flaky flipped":>16} {"non-flaky flipped":>20}')
    for name, _ in TRANSFORMS:
        f = fl[fl.transform == name]
        n = nf[nf.transform == name]
        print(f'{name:<20} {f.flipped.sum():>7} / {len(f):<6} '
              f'{n.flipped.sum():>9} / {len(n):<6}')

    print()
    print('=' * 72)
    print('FLAKY ACCURACY BEFORE AND AFTER')
    print('=' * 72)
    base = fl[fl.transform == TRANSFORMS[0][0]].correct_original.sum()
    print(f'{"transformation":<20} {"correct before":>15} {"correct after":>14}')
    for name, _ in TRANSFORMS:
        f = fl[fl.transform == name]
        print(f'{name:<20} {base:>15} {f.correct_transformed.sum():>14}')

    print()
    print('=' * 72)
    print('CONFIDENCE AND TOKEN COUNT SHIFT (flaky only)')
    print('=' * 72)
    print(f'{"transformation":<20} {"mean conf delta":>16} {"mean token delta":>18}')
    for name, _ in TRANSFORMS:
        f = fl[fl.transform == name]
        print(f'{name:<20} {f.conf_delta.mean():>16.4f} {f.token_delta.mean():>18.1f}')

    print()
    print('=' * 72)
    print('WHERE FLIPPED FLAKY TESTS END UP')
    print('=' * 72)
    for name, _ in TRANSFORMS:
        f = fl[(fl.transform == name) & (fl.flipped)]
        if len(f):
            counts = f.pred_transformed.value_counts().sort_index().to_dict()
            print(f'{name:<20} {counts}')
        else:
            print(f'{name:<20} no flips')

    print()
    print('=' * 72)
    print('FLIP RATE BY CATEGORY (flaky)')
    print('=' * 72)
    pivot = fl.pivot_table(index='true_label', columns='transform',
                           values='flipped', aggfunc='sum')
    print(pivot.to_string())


if __name__ == '__main__':
    main()