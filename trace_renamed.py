"""
Trace a sample of renamed tests through the pipeline.

For each sampled test prints:
  - original source
  - transformed (renamed) source
  - tokenised input (first 40 tokens, decoded)
  - number of tokens, and whether truncation occurred
  - predicted label on the original
  - predicted label on the transformed version
  - expected (true) label

Run from /app/src:
    python3 trace_renamed.py > /output/session5_trace.txt 2>&1
"""
import re
import torch
import pandas as pd

from utils import codebert_model_define
from codebert_model import BERT_Arch

FOLD = 1
MAX_LEN = 512
N_SAMPLES = 5
WEIGHTS = f'../models/per_project_model_weights_on__dataset_project_group_{FOLD}.pt'
PERT = (f'FlakyLens_Categorization_PerProject-Data/'
        f'X_test_project_group{FOLD}variableDeclare_perturbation_Most_important_features.csv')
DATASET = '/app/dataset/FlakyLens/FlakyLens_dataset_with_nonflaky_indented.csv'

LABELS = {0: 'Async', 1: 'Conc', 2: 'Time', 3: 'UC', 4: 'OD', 5: 'Non-flaky'}


def method_name(src):
    m = re.search(
        r'(?:public|private|protected)?\s*(?:static\s+)?\w[\w<>\[\],\s]*\s+(\w+)\s*\(',
        str(src))
    return m.group(1) if m else None


def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print('device:', device)

    _, tokenizer, auto_model = codebert_model_define()
    model = BERT_Arch(auto_model, 6)
    model.load_state_dict(torch.load(WEIGHTS, map_location=device))
    model.to(device)
    model.eval()
    print('weights:', WEIGHTS)
    print()

    d = pd.read_csv(DATASET)
    p = pd.read_csv(PERT)
    d['sig'] = d.full_code.map(method_name)
    p['sig'] = p.full_code.map(method_name)

    orig_code = dict(zip(d.sig, d.full_code))
    orig_label = dict(zip(d.sig, d.label))

    def norm(s):
        return re.sub(r'\s+', ' ', str(s)).strip()

    # keep only flaky tests whose content actually changed
    rows = []
    for _, r in p.iterrows():
        o = orig_code.get(r.sig)
        if o is None:
            continue
        lab = orig_label.get(r.sig)
        if lab == 5:                      # skip non-flaky
            continue
        if norm(o) == norm(r.full_code):  # skip unchanged
            continue
        rows.append((r.sig, o, r.full_code, lab))
        if len(rows) >= N_SAMPLES:
            break

    print(f'sampled {len(rows)} renamed flaky tests from fold {FOLD}')
    print('=' * 78)

    def predict(src):
        enc = tokenizer.batch_encode_plus(
            [src], max_length=MAX_LEN, pad_to_max_length=True, truncation=True)
        ids = torch.tensor(enc['input_ids']).to(device)
        mask = torch.tensor(enc['attention_mask']).to(device)
        with torch.no_grad():
            out = model(ids, mask)
        logits = out[0] if isinstance(out, tuple) else out
        probs = torch.softmax(logits, dim=1)
        pred = int(torch.argmax(logits, dim=1)[0])
        conf = float(probs[0][pred])
        n_real = int(mask.sum())
        return pred, conf, ids[0], n_real

    for sig, o, t, lab in rows:
        print()
        print(f'### {sig}   true label = {lab} ({LABELS.get(lab)})')
        print()
        print('--- ORIGINAL ---')
        print(o)
        print()
        print('--- TRANSFORMED ---')
        print(t)
        print()

        po, co, ids_o, no = predict(o)
        pt, ct, ids_t, nt = predict(t)

        toks = tokenizer.convert_ids_to_tokens(ids_t[:40].tolist())
        print('--- TOKENISED (transformed, first 40) ---')
        print(' '.join(toks))
        print()
        print(f'tokens used: original {no}, transformed {nt} '
              f'(truncated at {MAX_LEN}: '
              f'{"yes" if no >= MAX_LEN else "no"} / '
              f'{"yes" if nt >= MAX_LEN else "no"})')
        print(f'prediction on original    : {po} ({LABELS.get(po)})  conf={co:.4f}')
        print(f'prediction on transformed : {pt} ({LABELS.get(pt)})  conf={ct:.4f}')
        print(f'expected                  : {lab} ({LABELS.get(lab)})')
        print('=' * 78)


if __name__ == '__main__':
    main()
