"""
Which whitespace tokens carry the attribution weight?

The previous run showed that whitespace tokens hold 10.4% of attribution mass on
unmodified code, rising to ~30% after adding indentation or trailing spaces.
This script asks which tokens specifically.

CodeBERT encodes a leading space as the character G-dot and a newline as C-dot.
A run of four spaces may tokenise as one long token, or as several, depending on
what precedes it. The question is whether the weight concentrates on a few
distinctive tokens (long runs, doubled newlines) or spreads evenly.

Run from /app/src:
    python3 whitespace_tokens_detail.py

Writes:
    /output/session4/ws_token_breakdown_fold{FOLD}.csv
    stdout summary tables
"""
import torch
import pandas as pd
from collections import defaultdict
from captum.attr import LayerIntegratedGradients

from utils import codebert_model_define
from codebert_model import BERT_Arch

FOLD = 1
MAX_LEN = 512
N_TESTS = 25
SEED = 42

BASE = '/output/session2/FlakyLens_Categorization_PerProject-Data/'
TEST_SET = BASE + f'test_set_{FOLD}.csv'
WEIGHTS = f'../models/per_project_model_weights_on__dataset_project_group_{FOLD}.pt'
OUT = f'/output/session4/ws_token_breakdown_fold{FOLD}.csv'

GDOT = 'Ġ'   # CodeBERT's leading-space marker
CDOT = 'Ċ'   # CodeBERT's newline marker


def t_indent4(src):
    return '\n    '.join(str(src).splitlines())


def t_strip_indent(src):
    return '\n'.join(ln.lstrip() for ln in str(src).splitlines())


TRANSFORMS = [('original', lambda s: str(s)),
              ('indent +4', t_indent4),
              ('strip indent', t_strip_indent)]


def classify(tok):
    """Bucket a token. Returns None for tokens with lexical content."""
    if tok in ('<s>', '</s>', '<pad>'):
        return None
    stripped = tok.replace(GDOT, '').replace(CDOT, '')
    if stripped != '':
        return None                      # has real content
    n_g = tok.count(GDOT)
    n_c = tok.count(CDOT)
    if n_c and n_g:
        return f'mixed (C×{n_c}, G×{n_g})'
    if n_c:
        return f'newline ×{n_c}'
    return f'spaces ×{n_g}'


def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print('device:', device)

    _, tokenizer, auto_model = codebert_model_define()
    model = BERT_Arch(auto_model, 6)
    model.load_state_dict(torch.load(WEIGHTS, map_location=device))
    model.to(device)
    model.eval()
    print('weights:', WEIGHTS)

    t = pd.read_csv(TEST_SET)
    flaky = t[t.category != 5].head(N_TESTS).reset_index(drop=True)
    print(f'running on {len(flaky)} flaky tests from fold {FOLD}\n')

    lig = LayerIntegratedGradients(
        lambda ids, mask: model(ids, mask), model.bert.embeddings)

    def predict(src):
        enc = tokenizer.batch_encode_plus(
            [src], max_length=MAX_LEN, pad_to_max_length=True, truncation=True)
        ids = torch.tensor(enc['input_ids']).to(device)
        mask = torch.tensor(enc['attention_mask']).to(device)
        with torch.no_grad():
            out = model(ids, mask)
        logits = out[0] if isinstance(out, tuple) else out
        return int(torch.argmax(logits, dim=1)[0])

    def attribute(src, target):
        enc = tokenizer.batch_encode_plus(
            [src], max_length=MAX_LEN, pad_to_max_length=True, truncation=True)
        ids = torch.tensor(enc['input_ids']).to(device)
        mask = torch.tensor(enc['attention_mask']).to(device)
        base = torch.zeros_like(ids).to(device)
        attr = lig.attribute(inputs=ids, baselines=base,
                             additional_forward_args=(mask,),
                             target=target, n_steps=20)
        a = attr.sum(dim=-1).squeeze(0).abs()
        n_real = int(mask.sum())
        toks = tokenizer.convert_ids_to_tokens(ids[0].tolist())[:n_real]
        return toks, a[:n_real].tolist()

    rows = []
    for i in range(len(flaky)):
        src = flaky.full_code.iloc[i]
        for tname, fn in TRANSFORMS:
            variant = fn(src)
            pred = predict(variant)
            try:
                toks, attrs = attribute(variant, pred)
            except Exception as e:
                print('  failed:', flaky.test_name.iloc[i], tname, e)
                continue
            total = sum(attrs)
            if total == 0:
                continue
            for tk, av in zip(toks, attrs):
                bucket = classify(tk)
                if bucket is None:
                    continue
                rows.append({
                    'test_name': flaky.test_name.iloc[i],
                    'true_category': int(flaky.category.iloc[i]),
                    'transform': tname,
                    'prediction': pred,
                    'token_repr': repr(tk),
                    'bucket': bucket,
                    'attribution': av,
                    'share_of_total': av / total,
                })
        print('  done', i + 1, 'of', len(flaky), flush=True)

    d = pd.DataFrame(rows)
    d.to_csv(OUT, index=False)
    print(f'\nwrote {len(d)} whitespace-token rows to {OUT}\n')

    if not len(d):
        print('no rows produced')
        return

    for tname, _ in TRANSFORMS:
        s = d[d['transform'] == tname]
        if not len(s):
            continue
        print('=' * 76)
        print(f'{tname.upper()}  —  top whitespace tokens by total attribution share')
        print('=' * 76)
        g = (s.groupby(['bucket', 'token_repr'])
               .agg(count=('attribution', 'size'),
                    total_share=('share_of_total', 'sum'),
                    mean_attrib=('attribution', 'mean'))
               .sort_values('total_share', ascending=False)
               .head(15))
        # total_share is summed across tests, so normalise per test
        g['pct_of_all_attrib_per_test'] = (g.total_share / s.test_name.nunique() * 100).round(2)
        print(g[['count', 'mean_attrib', 'pct_of_all_attrib_per_test']].to_string())
        print()

    print('=' * 76)
    print('BY BUCKET: share of each test\'s total attribution, averaged')
    print('=' * 76)
    piv = (d.groupby(['transform', 'bucket'])
             .share_of_total.sum()
             .unstack(0)
             .fillna(0))
    n_tests = d.test_name.nunique()
    print((piv / n_tests * 100).round(2).to_string())

    print()
    print('=' * 76)
    print('CONCENTRATION: how much of the whitespace attribution the top '
          'few tokens hold')
    print('=' * 76)
    for tname, _ in TRANSFORMS:
        s = d[d['transform'] == tname]
        if not len(s):
            continue
        by_tok = s.groupby('token_repr').attribution.sum().sort_values(ascending=False)
        tot = by_tok.sum()
        if tot == 0:
            continue
        top1 = by_tok.iloc[0] / tot * 100
        top3 = by_tok.iloc[:3].sum() / tot * 100
        print(f'{tname:<16} distinct ws tokens: {len(by_tok):<5} '
              f'top 1 holds {top1:5.1f}%   top 3 hold {top3:5.1f}%')
        print(f'{"":<16} top 3: {list(by_tok.index[:3])}')


if __name__ == '__main__':
    main()