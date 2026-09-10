"""The 20 flaky tests in fold 1 whose code did not change but whose
prediction did. Checks whether truncation explains the flip."""
import pandas as pd

d = pd.read_csv('/output/session3/predictions_fold1_rename.csv')
f = d[(d.true_category != 5) & (~d.code_changed)]

print(f'flaky tests with unchanged content: {len(f)}')
print(f'of those, prediction flipped: {f.flipped.sum()}')
print()
cols = ['test_name','true_category','pred_original','conf_original',
        'pred_renamed','conf_renamed','tokens_original','tokens_renamed']
print(f[cols].to_string(index=False))
print()
print('token growth:')
print((f.tokens_renamed - f.tokens_original).describe())
print()
print(f'hit the 512 limit after renaming: {(f.tokens_renamed >= 512).sum()} of {len(f)}')
print(f'hit the 512 limit before renaming: {(f.tokens_original >= 512).sum()} of {len(f)}')
