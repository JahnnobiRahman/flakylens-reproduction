"""
Renaming without indentation: the third cell of the 2x2.

Takes the renamed code from the artifact's perturbed CSV and removes the four
spaces that variableRenaming_perturbation added to every line, restoring the
original formatting while keeping the substituted identifiers.

So the comparison across three runs is:

    run                     identifiers   indentation
    ---------------------   -----------   -----------
    full perturbation       renamed       +4 spaces
    indent_only             original      +4 spaces
    this one                renamed       original

If fold 4's 278 non-flaky misclassifications reappear here, the identifier
substitution is responsible for them. If they do not, something else is.

Run from /app/src:
    python3 rename_only.py

Change FOLD below to switch folds. Writes
/output/session3/predictions_fold{FOLD}_renameonly.csv
"""
import re
import torch
import pandas as pd

from utils import codebert_model_define
from codebert_model import BERT_Arch

FOLD = 4
MAX_LEN = 512
BASE = '/output/session2/FlakyLens_Categorization_PerProject-Data/'
TEST_SET = BASE + f'test_set_{FOLD}.csv'
PERT = BASE + (f'X_test_project_group{FOLD}'
               f'variableDeclare_perturbation_Most_important_features.csv')
WEIGHTS = f'../models/per_project_model_weights_on__dataset_project_group_{FOLD}.pt'
OUT = f'/output/session3/predictions_fold{FOLD}_renameonly.csv'


def deindent(src):
    """Undo the four spaces variableRenaming_perturbation prepends to each line
    after the first. Only strips exactly four leading spaces, so genuine
    indentation inside the method body is preserved relative to the rest."""
    lines = str(src).splitlines()
    if not lines:
        return str(src)
    out = [lines[0]]
    for ln in lines[1:]:
        out.append(ln[4:] if ln.startswith('    ') else ln)
    return '\n'.join(out)


def norm(s):
    return re.sub(r'\s+', ' ', str(s)).strip()


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

    # sanity check: after de-indenting, tests that were never renamed should
    # match the original exactly
    di = p.full_code.map(deindent)
    exact = sum(a == b for a, b in zip(t.full_code, di))
    print(f'de-indented rows matching the original exactly: {exact} of {len(t)}')

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
        ren = di.iloc[i]
        cat = int(t.category.iloc[i])
        po, co, no = predict(orig)
        pr, cr, nr = predict(ren)
        rows.append({
            'id': t.id.iloc[i],
            'project': t.project.iloc[i],
            'test_name': t.test_name.iloc[i],
            'true_category': cat,
            'true_label': t.label.iloc[i],
            'pred_original': po,
            'conf_original': round(co, 4),
            'pred_renameonly': pr,
            'conf_renameonly': round(cr, 4),
            'correct_original': po == cat,
            'correct_renameonly': pr == cat,
            'flipped': po != pr,
            'identifiers_changed': norm(orig) != norm(ren),
            'tokens_original': no,
            'tokens_renameonly': nr,
        })
        if (i + 1) % 200 == 0:
            print('processed', i + 1, flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f'\nwrote {len(out)} rows to {OUT}\n')

    flaky = out[out.true_category != 5]
    nf = out[out.true_category == 5]
    print(f'flaky: {len(flaky)}   non-flaky: {len(nf)}')

    print('\n=== flaky: predictions on ORIGINAL ===')
    print(pd.crosstab(flaky.true_label, flaky.pred_original))

    print('\n=== flaky: predictions with RENAMING ONLY (no added indentation) ===')
    print(pd.crosstab(flaky.true_label, flaky.pred_renameonly))

    print('\n=== correct before vs after (flaky) ===')
    print(flaky.groupby('true_label')[['correct_original', 'correct_renameonly']].sum())

    print('\n=== non-flaky ===')
    print(f'correct on original    : {nf.correct_original.sum()} of {len(nf)}')
    print(f'correct with rename only: {nf.correct_renameonly.sum()} of {len(nf)}')
    print(f'non-flaky misclassified as flaky: '
          f'{(~nf.correct_renameonly).sum()} of {len(nf)}')

    print('\n=== where the misclassified non-flaky tests went ===')
    bad = nf[~nf.correct_renameonly]
    if len(bad):
        print(bad.pred_renameonly.value_counts().sort_index())
    else:
        print('none')

    print('\n=== flipped ===')
    print(f'flaky flipped     : {flaky.flipped.sum()} of {len(flaky)}')
    print(f'non-flaky flipped : {nf.flipped.sum()} of {len(nf)}')

    print('\n=== truncation ===')
    print(f'original   hitting {MAX_LEN}: {(out.tokens_original >= MAX_LEN).sum()}')
    print(f'renameonly hitting {MAX_LEN}: {(out.tokens_renameonly >= MAX_LEN).sum()}')


if __name__ == '__main__':
    main()