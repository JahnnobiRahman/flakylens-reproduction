"""One-off checks used in the report. Run from /app/src."""
import pandas as pd, glob, re
from collections import defaultdict

DATASET = '/app/dataset/FlakyLens/FlakyLens_dataset_with_nonflaky_indented.csv'
PERT_DIR = 'FlakyLens_Categorization_PerProject-Data/'

def norm(s): return re.sub(r'\s+', ' ', str(s)).strip()
def sig(s):
    m = re.search(r'(?:public|private|protected)?\s*(?:static\s+)?\w[\w<>\[\],\s]*\s+(\w+)\s*\(', str(s))
    return m.group(1) if m else None

# 1. which branch runs: deadcode token markers
print('=== branch check: deadcode ===')
for f in sorted(glob.glob(PERT_DIR + '*deadcode*')):
    t = ' '.join(pd.read_csv(f).full_code.astype(str))
    print(f.split('/')[-1][:40], 'job.schedule:', t.count('job.schedule'), 'crashID:', t.count('crashID'))

# 2. which branch runs: renaming name counts
print('\n=== branch check: renaming ===')
most = ['concurrenct','automic','latch','timestamp','dictionary','hashmap','linkedlist','lookup','dirPath','clusterPath','sharedKey','booleans','serialize']
least = ['runtime','checkpoint','vo','etlbatch','stlset','zkw','unirest','wildfly','mojo','referenceable','greeter','tomcat']
orig = ' '.join(pd.read_csv(DATASET).full_code.astype(str))
pert = ' '.join(' '.join(pd.read_csv(f).full_code.astype(str)) for f in sorted(glob.glob(PERT_DIR + '*variableDeclare*')))
for name, words in [('most', most), ('least', least)]:
    o = sum(len(re.findall(r'\b'+w+r'\b', orig)) for w in words)
    p = sum(len(re.findall(r'\b'+w+r'\b', pert)) for w in words)
    print(f'{name:6} original: {o:6}  perturbed: {p:6}  delta: {p-o:+6}')

# 3. error split: changed vs unchanged per category, fold 1
print('\n=== error split, fold 1 ===')
d = pd.read_csv(DATASET); p = pd.read_csv(PERT_DIR + 'X_test_project_group1variableDeclare_perturbation_Most_important_features.csv')
d['sig'] = d.full_code.map(sig); p['sig'] = p.full_code.map(sig)
lut_lab = dict(zip(d.sig, d.category)); lut_code = dict(zip(d.sig, d.full_code.map(norm)))
p['label'] = p.sig.map(lut_lab)
p['changed'] = [lut_code.get(s) != norm(c) for s, c in zip(p.sig, p.full_code)]
print('rows:', len(p), 'matched:', p.label.notna().sum())
print(pd.crosstab(p.label, p.changed))

# 4. exact vs whitespace-normalised match against original
print('\n=== reformatting check ===')
exact = set(d.full_code); nrm = set(d.full_code.map(norm))
te = tn = tot = 0
for f in sorted(glob.glob(PERT_DIR + '*variableDeclare*')):
    q = pd.read_csv(f)
    te += q.full_code.isin(exact).sum()
    tn += q.full_code.map(norm).isin(nrm).sum()
    tot += len(q)
print(f'exact matches: {te} of {tot}   whitespace-normalised matches: {tn} of {tot}')
