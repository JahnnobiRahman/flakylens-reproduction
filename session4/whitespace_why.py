"""
Why does whitespace flip the prediction?

Three questions, in order:

  1. What does the tokeniser actually do? How much of the input becomes
     whitespace tokens before and after each transformation, and what
     fraction of the 512-token budget they occupy.

  2. Where does the attribution go? Running Integrated Gradients on the
     original and on the transformed version of the same test, and asking
     how much attribution mass sits on whitespace tokens in each.

  3. Does the shift track the flip? Comparing tests that flipped against
     tests that did not.

Run from /app/src:
    python3 whitespace_why.py

Writes:
    /output/session4/whitespace_tokens_fold{FOLD}.csv   per test per transform
    /output/session4/whitespace_attrib_fold{FOLD}.csv   attribution mass split
    stdout                                              summary tables
"""
import torch
import pandas as pd
from captum.attr import LayerIntegratedGradients

from utils import codebert_model_define
from codebert_model import BERT_Arch

FOLD = 1
MAX_LEN = 512
N_ATTRIB = 20          # tests to run IG on; IG is slow, so keep this small
SEED = 42

BASE = '/output/session2/FlakyLens_Categorization_PerProject-Data/'
TEST_SET = BASE + f'test_set_{FOLD}.csv'
WEIGHTS = f'../models/per_project_model_weights_on__dataset_project_group_{FOLD}.pt'
OUT_TOK = f'/output/session4/whitespace_tokens_fold{FOLD}.csv'
OUT_ATT = f'/output/session4/whitespace_attrib_fold{FOLD}.csv'


def t_indent4(src):
    return '\n    '.join(str(src).splitlines())


def t_strip_indent(src):
    return '\n'.join(ln.lstrip() for ln in str(src).splitlines())


def t_trailing_spaces(src):
    return '\n'.join(ln + ' ' for ln in str(src).splitlines())


def t_remove_blank(src):
    return '\n'.join(ln for ln in str(src).splitlines() if ln.strip())


TRANSFORMS = [
    ('indent +4',       t_indent4),        # destroys flaky
    ('strip indent',    t_strip_indent),   # destroys non-flaky
    ('trailing spaces', t_trailing_spaces),# partial
    ('remove blank lines', t_remove_blank),# harmless control
]


def is_whitespace_token(tok):
    """CodeBERT marks a leading space with Ġ and a newline with Ċ. A token
    made only of those, or only of those plus nothing else, carries no
    lexical content."""
    if tok in ('<s>', '</s>', '<pad>'):
        return False
    stripped = tok.replace('Ġ', '').replace('Ċ', '')
    return stripped == ''


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
    flaky = t[t.category != 5].reset_index(drop=True)
    nonflaky = t[t.category == 5].sample(100, random_state=SEED).reset_index(drop=True)
    print(f'fold {FOLD}: {len(flaky)} flaky, {len(nonflaky)} non-flaky sampled\n')

    # ------------------------------------------------------ part 1: tokens

    def tokenise(src):
        enc = tokenizer.batch_encode_plus(
            [src], max_length=MAX_LEN, pad_to_max_length=True, truncation=True)
        ids = enc['input_ids'][0]
        mask = enc['attention_mask'][0]
        n_real = sum(mask)
        toks = tokenizer.convert_ids_to_tokens(ids[:n_real])
        ws = sum(1 for x in toks if is_whitespace_token(x))
        return toks, n_real, ws

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
        return k, float(probs[0][k])

    rows = []
    pool = pd.concat([flaky, nonflaky]).reset_index(drop=True)
    for i in range(len(pool)):
        src = pool.full_code.iloc[i]
        cat = int(pool.category.iloc[i])
        _, n0, ws0 = tokenise(src)
        p0, c0 = predict(src)
        for name, fn in TRANSFORMS:
            var = fn(src)
            _, n1, ws1 = tokenise(var)
            p1, c1 = predict(var)
            rows.append({
                'test_name': pool.test_name.iloc[i],
                'true_category': cat,
                'true_label': pool.label.iloc[i],
                'transform': name,
                'tokens_before': n0, 'tokens_after': n1,
                'ws_tokens_before': ws0, 'ws_tokens_after': ws1,
                'ws_frac_before': round(ws0 / n0, 4) if n0 else 0,
                'ws_frac_after': round(ws1 / n1, 4) if n1 else 0,
                'truncated_before': n0 >= MAX_LEN,
                'truncated_after': n1 >= MAX_LEN,
                'pred_before': p0, 'pred_after': p1,
                'conf_before': round(c0, 4), 'conf_after': round(c1, 4),
                'flipped': p0 != p1,
            })
        if (i + 1) % 50 == 0:
            print('tokenised', i + 1, 'of', len(pool), flush=True)

    tok = pd.DataFrame(rows)
    tok.to_csv(OUT_TOK, index=False)
    print(f'\nwrote {len(tok)} rows to {OUT_TOK}\n')

    names = [n for n, _ in TRANSFORMS]

    print('=' * 76)
    print('TOKEN BUDGET: how much of the input becomes whitespace')
    print('=' * 76)
    print(f'{"transform":<20}{"class":<12}{"ws% before":>12}{"ws% after":>12}'
          f'{"tokens before":>15}{"tokens after":>14}')
    for n in names:
        for lab, sel in (('flaky', tok.true_category != 5),
                         ('non-flaky', tok.true_category == 5)):
            s = tok[(tok['transform'] == n) & sel]
            print(f'{n:<20}{lab:<12}{s.ws_frac_before.mean()*100:>11.1f}%'
                  f'{s.ws_frac_after.mean()*100:>11.1f}%'
                  f'{s.tokens_before.mean():>15.0f}{s.tokens_after.mean():>14.0f}')

    print()
    print('=' * 76)
    print('TRUNCATION')
    print('=' * 76)
    print(f'{"transform":<20}{"truncated before":>18}{"truncated after":>18}')
    for n in names:
        s = tok[tok['transform'] == n]
        print(f'{n:<20}{s.truncated_before.sum():>18}{s.truncated_after.sum():>18}')

    print()
    print('=' * 76)
    print('DID THE FLIPPED TESTS GAIN MORE WHITESPACE THAN THE REST?')
    print('=' * 76)
    print(f'{"transform":<20}{"flipped: ws% gain":>20}{"not flipped: ws% gain":>24}')
    for n in names:
        s = tok[(tok['transform'] == n) & (tok.true_category != 5)]
        a = s[s.flipped]
        b = s[~s.flipped]
        ga = (a.ws_frac_after - a.ws_frac_before).mean() * 100 if len(a) else float('nan')
        gb = (b.ws_frac_after - b.ws_frac_before).mean() * 100 if len(b) else float('nan')
        print(f'{n:<20}{ga:>19.1f}%{gb:>23.1f}%')

    # -------------------------------------------- part 2: attribution mass

    print()
    print('=' * 76)
    print(f'ATTRIBUTION: running IG on {N_ATTRIB} flaky tests, before and after')
    print('=' * 76)

    lig = LayerIntegratedGradients(
        lambda ids, mask: model(ids, mask), model.bert.embeddings)

    def attribution_split(src, target):
        """Return (total abs attribution, fraction sitting on whitespace tokens)."""
        enc = tokenizer.batch_encode_plus(
            [src], max_length=MAX_LEN, pad_to_max_length=True, truncation=True)
        ids = torch.tensor(enc['input_ids']).to(device)
        mask = torch.tensor(enc['attention_mask']).to(device)
        base = torch.zeros_like(ids).to(device)
        attr = lig.attribute(inputs=ids, baselines=base,
                             additional_forward_args=(mask,),
                             target=target, n_steps=20)
        a = attr.sum(dim=-1).squeeze(0).abs()
        toks = tokenizer.convert_ids_to_tokens(ids[0].tolist())
        n_real = int(mask.sum())
        a = a[:n_real]
        toks = toks[:n_real]
        total = float(a.sum())
        ws = float(sum(v for v, tk in zip(a.tolist(), toks)
                       if is_whitespace_token(tk)))
        return total, (ws / total if total else 0)

    arows = []
    sample = flaky.head(N_ATTRIB)
    for i in range(len(sample)):
        src = sample.full_code.iloc[i]
        cat = int(sample.category.iloc[i])
        p0, _ = predict(src)
        try:
            tot0, wsf0 = attribution_split(src, p0)
        except Exception as e:
            print('  attribution failed on', sample.test_name.iloc[i], ':', e)
            continue
        for name, fn in TRANSFORMS:
            var = fn(src)
            p1, _ = predict(var)
            try:
                tot1, wsf1 = attribution_split(var, p1)
            except Exception:
                continue
            arows.append({
                'test_name': sample.test_name.iloc[i],
                'true_category': cat,
                'transform': name,
                'pred_before': p0, 'pred_after': p1,
                'flipped': p0 != p1,
                'ws_attrib_frac_before': round(wsf0, 4),
                'ws_attrib_frac_after': round(wsf1, 4),
                'total_attrib_before': tot0,
                'total_attrib_after': tot1,
            })
        print('  attributed', i + 1, 'of', len(sample), flush=True)

    if arows:
        att = pd.DataFrame(arows)
        att.to_csv(OUT_ATT, index=False)
        print(f'\nwrote {len(att)} rows to {OUT_ATT}\n')

        print('=' * 76)
        print('ATTRIBUTION MASS ON WHITESPACE TOKENS')
        print('=' * 76)
        print(f'{"transform":<20}{"before":>12}{"after":>12}{"change":>12}')
        for n in names:
            s = att[att['transform'] == n]
            if not len(s):
                continue
            b = s.ws_attrib_frac_before.mean() * 100
            a = s.ws_attrib_frac_after.mean() * 100
            print(f'{n:<20}{b:>11.1f}%{a:>11.1f}%{a-b:>11.1f}%')
    else:
        print('no attribution rows produced')


if __name__ == '__main__':
    main()