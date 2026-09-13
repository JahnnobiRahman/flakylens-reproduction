import pandas as pd

FOLD = 1
d = pd.read_csv(f'/output/session4/format_robustness_fold{FOLD}.csv')
names = list(dict.fromkeys(d['transform']))
fl = d[d.true_category != 5]
nf = d[d.true_category == 5]

print(f'rows: {len(d)}   flaky rows: {len(fl)}   non-flaky rows: {len(nf)}')
print(f'variants differing by more than whitespace: {(~d.whitespace_identical).sum()}\n')

print('=' * 74)
print('FLIP RATE BY TRANSFORMATION')
print('=' * 74)
print(f'{"transformation":<22}{"flaky flipped":>18}{"non-flaky flipped":>22}')
for n in names:
    f = fl[fl['transform'] == n]; g = nf[nf['transform'] == n]
    print(f'{n:<22}{f.flipped.sum():>8} / {len(f):<7}{g.flipped.sum():>12} / {len(g):<7}')

print()
print('=' * 74)
print('FLAKY ACCURACY BEFORE AND AFTER')
print('=' * 74)
base = fl[fl['transform'] == names[0]].correct_original.sum()
print(f'{"transformation":<22}{"correct before":>16}{"correct after":>16}')
for n in names:
    f = fl[fl['transform'] == n]
    print(f'{n:<22}{base:>16}{f.correct_transformed.sum():>16}')

print()
print('=' * 74)
print('CONFIDENCE AND TOKEN SHIFT (flaky only)')
print('=' * 74)
print(f'{"transformation":<22}{"mean conf delta":>18}{"mean token delta":>19}')
for n in names:
    f = fl[fl['transform'] == n]
    print(f'{n:<22}{f.conf_delta.mean():>18.4f}{f.token_delta.mean():>19.1f}')

print()
print('=' * 74)
print('WHERE FLIPPED FLAKY TESTS END UP  (5 = non-flaky)')
print('=' * 74)
for n in names:
    f = fl[(fl['transform'] == n) & (fl.flipped)]
    print(f'{n:<22}{dict(f.pred_transformed.value_counts().sort_index()) if len(f) else "no flips"}')

print()
print('=' * 74)
print('FLIPS BY CATEGORY (flaky)')
print('=' * 74)
print(fl.pivot_table(index='true_label', columns='transform',
                     values='flipped', aggfunc='sum').to_string())
