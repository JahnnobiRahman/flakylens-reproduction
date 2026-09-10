"""
Indentation alone: per-test predictions before and after adding four spaces
to every line. Fold 1.

This repeats the earlier re-indentation experiment, but measured per test
rather than through the printed macro_f1 (which is not the mean of the
per-category values and did not detect the change).

Nothing but whitespace differs between the two versions of each test. No
identifiers are renamed, no code is added or removed.

Run from /app/src:
    python3 indent_only.py

Writes /output/session3/predictions_fold4_indent.csv
"""
import torch
import pandas as pd

from utils import codebert_model_define
from codebert_model import BERT_Arch

FOLD = 4
MAX_LEN = 512
TEST_SET = f'/output/session2/FlakyLens_Categorization_PerProject-Data/test_set_{FOLD}.csv'
WEIGHTS = f'../models/per_project_model_weights_on__dataset_project_group_{FOLD}.pt'
OUT = '/output/session3/predictions_fold4_indent.csv'


def reindent(src):
    """Exactly what variableRenaming_perturbation does to every line."""
    return '\n    '.join(str(src).splitlines())


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
    print(f'rows: {len(t)}')

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
    for i in range(len(t)):
        orig = t.full_code.iloc[i]
        ind = reindent(orig)
        cat = int(t.category.iloc[i])
        po, co, no = predict(orig)
        pi, ci, ni = predict(ind)
        rows.append({
            'id': t.id.iloc[i],
            'project': t.project.iloc[i],
            'test_name': t.test_name.iloc[i],
            'true_category': cat,
            'true_label': t.label.iloc[i],
            'pred_original': po,
            'conf_original': round(co, 4),
            'pred_indented': pi,
            'conf_indented': round(ci, 4),
            'correct_original': po == cat,
            'correct_indented': pi == cat,
            'flipped': po != pi,
            'tokens_original': no,
            'tokens_indented': ni,
        })
        if (i + 1) % 200 == 0:
            print('processed', i + 1, flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f'\nwrote {len(out)} rows to {OUT}\n')

    flaky = out[out.true_category != 5]
    nf = out[out.true_category == 5]

    print(f'flaky tests: {len(flaky)}   non-flaky: {len(nf)}')

    print('\n=== flaky: predictions on ORIGINAL ===')
    print(pd.crosstab(flaky.true_label, flaky.pred_original))

    print('\n=== flaky: predictions on RE-INDENTED ===')
    print(pd.crosstab(flaky.true_label, flaky.pred_indented))

    print('\n=== correct before vs after (flaky) ===')
    print(flaky.groupby('true_label')[['correct_original', 'correct_indented']].sum())

    print('\n=== flipped ===')
    print(f'flaky flipped     : {flaky.flipped.sum()} of {len(flaky)}')
    print(f'non-flaky flipped : {nf.flipped.sum()} of {len(nf)}')

    print('\n=== non-flaky accuracy ===')
    print(f'original  : {nf.correct_original.sum()} of {len(nf)}')
    print(f'indented  : {nf.correct_indented.sum()} of {len(nf)}')

    print('\n=== truncation ===')
    print(f'original hitting {MAX_LEN}: {(out.tokens_original >= MAX_LEN).sum()}')
    print(f'indented hitting {MAX_LEN}: {(out.tokens_indented >= MAX_LEN).sum()}')

    print('\n=== flipped tests that were NOT truncated ===')
    clean = flaky[(flaky.flipped) & (flaky.tokens_indented < MAX_LEN)]
    print(f'{len(clean)} of {flaky.flipped.sum()} flipped flaky tests stayed under the limit')


if __name__ == '__main__':
    main()