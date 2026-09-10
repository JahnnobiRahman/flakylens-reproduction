"""
Per-test predicted vs actual labels, before and after variable renaming. Fold 1.

The artifact does not write per-test predictions anywhere; the confusion matrix
only gives counts. This script loads fold 1's checkpoint directly and runs
prediction on both the original and the renamed version of every test in that
fold's test set.

Ground truth comes from the artifact's own split file, test_set_1.csv, which has
the same 2432 rows in the same order as the perturbed CSV (verified: method names
match by position on all 2432 rows). So the join is by index, with no matching
heuristic involved.

Run from /app/src:
    python3 dump_predictions.py

Writes /output/session3/predictions_fold1_rename.csv
"""
import torch
import pandas as pd

from utils import codebert_model_define
from codebert_model import BERT_Arch

FOLD = 1
MAX_LEN = 512
BASE = '/output/session2/FlakyLens_Categorization_PerProject-Data/'
TEST_SET = BASE + f'test_set_{FOLD}.csv'
PERT = BASE + (f'X_test_project_group{FOLD}'
               f'variableDeclare_perturbation_Most_important_features.csv')
WEIGHTS = f'../models/per_project_model_weights_on__dataset_project_group_{FOLD}.pt'
OUT = '/output/session3/predictions_fold1_rename.csv'


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
    p = pd.read_csv(PERT)
    assert len(t) == len(p), f'row count mismatch: {len(t)} vs {len(p)}'
    print(f'rows: {len(t)}')

    def predict(src):
        enc = tokenizer.batch_encode_plus(
            [src], max_length=MAX_LEN, pad_to_max_length=True, truncation=True)
        ids = torch.tensor(enc['input_ids']).to(device)
        mask = torch.tensor(enc['attention_mask']).to(device)
        with torch.no_grad():
            out = model(ids, mask)
        logits = out[0] if isinstance(out, tuple) else out
        probs = torch.exp(logits)          # forward already applies LogSoftmax
        k = int(torch.argmax(logits, dim=1)[0])
        return k, float(probs[0][k]), int(mask.sum())

    rows = []
    for i in range(len(t)):
        orig = t.full_code.iloc[i]
        pert = p.full_code.iloc[i]
        cat = int(t.category.iloc[i])
        po, co, no = predict(orig)
        pt, ct, nt = predict(pert)
        rows.append({
            'id': t.id.iloc[i],
            'project': t.project.iloc[i],
            'test_name': t.test_name.iloc[i],
            'true_category': cat,
            'true_label': t.label.iloc[i],
            'pred_original': po,
            'conf_original': round(co, 4),
            'pred_renamed': pt,
            'conf_renamed': round(ct, 4),
            'correct_original': po == cat,
            'correct_renamed': pt == cat,
            'flipped': po != pt,
            'code_changed': ' '.join(str(orig).split()) != ' '.join(str(pert).split()),
            'tokens_original': no,
            'tokens_renamed': nt,
        })
        if (i + 1) % 200 == 0:
            print('processed', i + 1, flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f'\nwrote {len(out)} rows to {OUT}\n')

    flaky = out[out.true_category != 5]
    print(f'flaky tests in this fold: {len(flaky)}')

    print('\n=== predictions on ORIGINAL code (flaky only) ===')
    print(pd.crosstab(flaky.true_label, flaky.pred_original))

    print('\n=== predictions on RENAMED code (flaky only) ===')
    print(pd.crosstab(flaky.true_label, flaky.pred_renamed))

    print('\n=== correct before vs after, per category ===')
    print(flaky.groupby('true_label')[['correct_original', 'correct_renamed']].sum())
    print('\ncounts per category:')
    print(flaky.true_label.value_counts())

    print('\n=== flipped, split by whether the code actually changed ===')
    print(pd.crosstab(flaky.code_changed, flaky.flipped))

    print('\n=== non-flaky tests ===')
    nf = out[out.true_category == 5]
    print(f'correct on original: {nf.correct_original.sum()} of {len(nf)}')
    print(f'correct on renamed : {nf.correct_renamed.sum()} of {len(nf)}')

    print('\n=== truncation at 512 tokens ===')
    print(f'original: {(out.tokens_original >= MAX_LEN).sum()} of {len(out)}')
    print(f'renamed : {(out.tokens_renamed >= MAX_LEN).sum()} of {len(out)}')


if __name__ == '__main__':
    main()