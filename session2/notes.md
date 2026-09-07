# Findings

Reproduction notes for the FlakyLens artifact (Rahman, Dutta, Shi, *Understanding
and Improving Flaky Test Classification*, OOPSLA 2025, Article 320).

Environment: RTX 3050, 8 GB VRAM, 15 GB RAM, Windows 11 with Docker and WSL2.
The paper used an RTX A5000 with 48 GB VRAM and 125 GB RAM (Section 6.6).
RQ1, RQ3 and RQ4 all ran. RQ2 was not attempted, since the 7B to 16B models do
not fit in 8 GB without quantisation, which would make the numbers
non-comparable to Table 3.



## 1. Established: the perturbation code runs the least-important branch

`Testing_per_project.py` passes `feature_types="Most"` on lines 434, 438, 442,
446 and 452, once for each of the five perturbations. Every comparison inside
`perturbation.py` tests `if feature_types == "Most_Imp"`. The two strings never
match, so all five perturbations fall through to the `else` branch, which
selects least-important tokens.

Three independent checks agree.

**Token markers in the deadcode output.** `job.schedule` appears only in the
`Most_Imp` branch of `deadcode_perturbation_with_async`; `crashID` appears only
in the `else` branch.

| Fold | `job.schedule` | `crashID` |
|---|---|---|
| 1 | 0 | 634 |
| 2 | 0 | 479 |
| 3 | 0 | 553 |
| 4 | 0 | 511 |

**Injected variable names, before and after renaming.** Counting the two name
lists across the whole corpus:

| List | Original dataset | After renaming | Delta |
|---|---|---|---|
| Most-important names | 689 | 589 | −100 |
| Least-important names | 75 | 13,399 | **+13,324** |

The least-important names go from near-absent to pervasive. The most-important
names do not rise at all; they fall slightly, which is consistent with renaming
overwriting some naturally-occurring identifiers.

**Sampled transformed tests.** In `session2/renamed_samples_fold1.txt`, four
tests drawn from four different categories each received names from the head of
the corresponding `else` list, in list order:

| Row | Original name | New name | Source list |
|---|---|---|---|
| 0 | `tfs` | `runtime` | Concurrency, else, position 1 |
| 1 | `ts`, `tags` | `checkpoint`, `vo` | Time, else, positions 1 and 2 |
| 3 | (two vars) | `mode`, `unit` | Non-flaky, else, positions 1 and 2 |
| 4 | `jobId`, `assigned` | `protocol`, `signature` | OD, else, positions 1 and 2 |

### Consequence

My numbers should be compared against **Table 6** (least-important tokens), not
Table 5. Under that comparison, four of the five perturbations line up:

| Perturbation | My avg ∇ | Table 6 | Table 5 |
|---|---|---|---|
| Print | −1.73 | −1.76 | −8.32 |
| Single-line | −3.32 | −3.58 | −12.18 |
| Multi-line | −5.35 | −8.70 | −10.46 |
| Deadcode | −11.07 / −11.90 | −7.91 | −18.37 |
| **Variable rename** | **−49.56** | **−5.24** | −10.98 |

Print matches to within 0.03pp; single-line to within 0.26pp. The apparent
"roughly half the reported degradation" pattern I saw initially was an artefact
of comparing against the wrong table.

Variable renaming remains an order of magnitude off and is unexplained.



## 2. Established: renaming collapses every flaky category to zero

Under `variableDeclare_perturbation`, all five flaky categories report exactly
0.00 F1. Non-flaky holds at 96.63 against a reported 99.48.

The confusion matrices (`cm_rename.txt`, last four blocks) show the shape of the
failure. In folds 1, 2 and 3 every flaky test is predicted non-flaky. Predictions
are not scattered across categories; they are constant.

```
Fold 1, after renaming
[[   0    0    0    0    0   35]    <- 35 Async, all predicted non-flaky
 [   0    0    0    0    0   21]
 [   0    0    0    0    0    9]
 [   0    0    0    0    0   16]
 [   0    0    0    0    0   27]
 [   0    0    0    0    0 2324]]
```

Fold 4 fails differently. The flaky rows collapse as above, but the non-flaky row
also breaks: 278 genuinely non-flaky tests are predicted flaky, 207 of them as
Test Order Dependency. In the clean run that same row was `[0,0,0,0,7,1921]`.
Each fold trains its own model, so the four models degrading differently is
possible, but it is worth noting that three folds fail one way and one fails
another.

### The renaming errors are not the cause

The run prints 559 `Error during renaming` messages. Two kinds appear:
`'in <string>' requires string as left operand, not NoneType`, and an empty
message (probably a `javalang` parse failure, or the `ValueError` raised when
`new_variable_names` is shorter than `most_used_variables`). In both cases
`renaming_variable` catches the exception and returns the original code
unchanged.

559 of 8574 tests is 6.5%. Those tests keep their original code and should
classify roughly as they did in RQ1, so at least some correct predictions should
survive. None do. The collapse therefore comes from the successfully renamed
tests, not the failed ones.

### Observation: renaming is not confined to variables

`renaming_variable` performs its substitution with a regular expression over the
whole method body:

```python
java_code = re.sub(rf'\b{original_name}\b', new_name, java_code)
```

This replaces every occurrence of the identifier, including ones that are not
variables. In `testToMetricResponse` (label 3, Unordered Collections), renaming
`tags` to `vo` produced:

| | Original | After renaming |
|---|---|---|
| variable declaration | `List<Tag> tags` | `List<Tag> vo` |
| **method call** | `.tags(tags)` | `.vo(vo)` |
| **JSON string literal** | `\"tags\":` | `\"vo\":` |

`.tags()` is a builder method on `Metric`, not a variable, and `"tags"` inside
the expected-JSON string is a key that the assertion compares against. Section
5.2.3 describes renaming as keeping the program semantically the same without
introducing syntax errors; this transformation does neither.

Whether this explains the collapse is **not established**. The model reads code
rather than executing it, so a non-compiling transformation is not automatically
fatal. It is recorded here as an observation, not a cause.


### Splitting the failed renames from the successful ones

Nothing in the pipeline records which tests errored, so I matched perturbed rows
back to the original dataset by test method name, which renaming does not touch.
All 2432 rows in fold 1 matched. Comparing the code with whitespace normalised:

| Category | Content unchanged | Changed |
|---|---|---|
| Async | 5 | 28 |
| Conc | 4 | 17 |
| Time | 2 | 7 |
| UC | 2 | 14 |
| OD | 6 | 16 |
| Non-flaky | 863 | 1468 |

Roughly 80 percent of flaky tests were genuinely renamed. The rest came back
content-identical, which includes the errored tests and tests with no variables
to rename. The confusion matrix shows zero correct predictions in every flaky
category, so the unchanged group is misclassified too. This confirms with counts
what section 2 argued from proportions.

### Reformatting ruled out

`variableRenaming_perturbation` wraps each test in a `WrapperClass` before
parsing, re-indenting every line by four spaces, and the regex that strips the
wrapper afterwards does not undo the indentation. This affects all 8574 tests,
including those where no variable was renamed: exact string matches against the
original dataset are 0 of 8574, while whitespace-normalised matches are 3483.
None of the other four perturbations alter formatting.

To test whether indentation alone breaks the model, I rebuilt the dataset with
four spaces added to every line and nothing else changed, then ran plain
prediction on it:

| Category | RQ1 baseline | Re-indented only |
|---|---|---|
| Async | 59.91 | 60.79 |
| Conc | 34.17 | 35.97 |
| Time | 66.00 | 70.36 |
| UC | 75.54 | 75.37 |
| OD | 58.38 | 63.43 |
| Non-flaky | 100.00 | 100.00 |
| Macro | 67.50 | 67.50 |

Indentation is not the cause. The model is unaffected by it.

Incidentally, this run reproduced the artifact's shipped
`FlakyLens_Result_Found_By_Author.csv` exactly, to all sixteen decimal places,
where my original RQ1 run had matched only on the macro. I have no explanation
for that.

Evidence: `session3/session4_indent_result.txt`, `session3/perfold_indent_test.txt`.

### What remains

Ruled out so far: the 559 renaming errors, structural damage, wrapper-class
leakage, and reformatting. What remains is the renamed identifiers themselves.
The cause of the collapse is still open.



## 3. Established: deadcode results vary between runs

`rq4.sh` run twice in the same container session, no changes between runs:

| Category | Run 1 | Run 2 | Difference |
|---|---|---|---|
| Async | 54.14 | 51.50 | 2.64 |
| Conc | 25.62 | 19.51 | **6.11** |
| Time | 63.33 | 63.12 | 0.21 |
| UC | 52.71 | 54.76 | 2.05 |
| OD | 31.80 | 33.74 | 1.94 |
| Non-flaky | 100.00 | 100.00 | 0 |

The macro is stable (55.04 vs 54.92) but the per-category numbers are not, and
the two runs would give slightly different rankings of which categories are most
fragile.

In `deadcode_insertion`:

```python
if perturb_cats:
    perturb_cat = perturb_cats[idx]
else:
    perturb_cat = generate_random_number(label)

perturb_cat = generate_random_number(label)   # unconditional, overwrites above
```

`generate_random_number` has no seed, and the `perturb_cats` mechanism that
exists to hold the injection category fixed is overwritten on the following line.
Section 8 states that a fixed random seed was used and the evaluation script was
run ten times to confirm consistent output, so a configuration step may be
missing here.


## 3b. Session 3 follow-up: the cause is a commented-out seed call

### The symptom

`rq4.sh` run three times(ran this again in session 2) in the same container session, no changes between runs:

| Category | Run 1 | Run 2 | Run 3 | Mean | SD | Range |
|---|---|---|---|---|---|---|
| Async | 53.75 | 53.61 | 55.07 | 54.14 | 0.80 | 1.46 |
| Conc | 23.68 | 20.54 | 21.19 | 21.80 | 1.65 | 3.14 |
| Time | 63.70 | 64.67 | 63.70 | 64.02 | 0.56 | 0.97 |
| UC | 49.39 | 54.34 | 51.85 | 51.86 | 2.48 | 4.95 |
| **OD** | 27.42 | 33.94 | 39.61 | **33.66** | **6.10** | **12.19** |
| Non-flaky | 100.00 | 100.00 | 100.00 | 100.00 | 0.00 | 0.00 |
| Macro | 53.25 | 56.62 | 55.42 | 55.10 | 1.71 | 3.38 |

The macro is comparatively stable, but Test Order Dependency spans 12.19 points
across three identical invocations. For reference, Table 5 reports OD deadcode at
39.66 and Table 6 at 40.46. Run 3 lands at 39.61, essentially on the reported
value; run 1 at 27.42 is twelve points below it. Whether the artifact appears to
reproduce the paper on this category depends on the draw.

Non-flaky is the only category with zero variance across all runs.

### The cause

`generate_random_number` in `perturbation.py` selects the injection category per
test using `random.choice`, with no seed of its own.

`utils.py` line 593 defines a seeding function that would cover it:

```python
def set_seed(seed_value=42):
    np.random.seed(seed_value)
    torch.manual_seed(seed_value)
    random.seed(seed_value)     # line 597 — the module generate_random_number uses
```

`Testing_per_project.py` line 667 defines `initialize_environment`, which calls
`set_seed`. But its only call site is line 678:

```python
    #initialize_environment(42)
```

It is commented out. `grep -n "seed_value\|initialize_environment"` across the
file returns only lines 667, 669 and 678, so there is no other call. The seeding
machinery is present and never executes on the testing path.

By contrast, `Bert_train_per_project.py` does seed, at lines 145 and 146. The
training path is seeded; the testing path is not.

### Confirmation

Uncommenting line 678 and running three more times:

| Category | Seeded run 1 | Seeded run 2 | Seeded run 3 |
|---|---|---|---|
| Async | 52.78 | 52.78 | 52.78 |
| Conc | 19.14 | 19.14 | 19.14 |
| Time | 62.33 | 62.33 | 62.33 |
| UC | 42.73 | 42.73 | 42.73 |
| OD | 30.83 | 30.83 | 30.83 |
| Non-flaky | 100.00 | 100.00 | 100.00 |
| Macro | 52.00 | 52.00 | 52.00 |

All three are identical to every printed digit, including the full-precision
precision and recall values. Enabling the one commented line makes the pipeline
deterministic.

Section 8 states that a fixed random seed was used and that the evaluation script
was run ten times to confirm consistent output. That behaviour is reproducible
only with line 678 enabled.

### Note on interpretation

The seeded macro of 52.00 sits below the unseeded mean of 55.10 and below all
three unseeded runs. Seed 42 happens to produce a harsher draw than average.
Seeding fixes reproducibility, not accuracy, and 52.00 should not be read as the
"correct" value that the unseeded runs were scattering around.

### Files

- `session3/deadcode_unseeded.txt`, `session3/deadcode_seeded.txt` — parsed output
- `session3/perfold_*_run*.txt` — per-fold evaluation files for each run
- `session3/raw_*_run*.log` — full console output
- `session3/Testing_per_project_ORIGINAL.py` — file as shipped
- `session3/Testing_per_project_SEEDED.py` — with line 678 uncommented

The artifact file was restored to its original state after these runs.



## 4. Established: RQ3 output does not match Table 4

| Category | Table 4 top-5 | My top-5 |
|---|---|---|
| Async | sleep, topic, wait, get, Interrupted | Epoch, Contain, await, Aggregate, Injector |
| Conc | **Duration**, new, Interrupted, verify, Subscriber | **Duration**, executor, Service, Assertions, Sticky |
| Time | Time, Network, when, Run, wait | long, Timestamp, min, Local, 10 |
| UC | List, Equals, Enum, JSON, set | Unirest, Days, Capture, headers, Resource |
| OD | Permission, naming, Action, Name, **Composite** | Stream, **Composite**, Received, Sharding, rebind |
| Non-flaky | Exception, get, That, Equals, expected | false, throws, ĊĊ, Until, Context |

Two tokens overlap in total. `sleep`, the paper's running example for Async Wait
in Section 2, is absent from my top five.

Attribution magnitudes differ by eight to nine orders. My scores fall between
1e-7 and 1e-9; Table 4 ranges 1.252–0.853 for Async and 41.09–20.34 for
non-flaky.

RQ3 was run twice in the same session and the output was byte-identical, so this
gap is systematic rather than run-to-run variance. This also means that any
attribution shift observed after a transformation would be attributable to the
transformation rather than to noise.


**Established: the post-processing runs but is incomplete.** Both helper
modules are imported and called from `Testing_per_project.py`:
`combine_tokens` at line 60 and used at line 114,
`find_most_and_least_imp_tokens` at line 61 and called at line 665.
So detokenisation and aggregation do execute.

However, `find_most_and_least_imp_tokens` performs only a raw sum:

    category_tokens[true_class][token] += score

Grepping that file for `confidence`, `log`, `normal` and `*` returns
nothing. The confidence weighting and log-frequency weighting described
in Section 5.1.4, and the normalisation mentioned in Section 6.3, are
absent from this path. `Test_confidence_score` is written into the
per-test CSV at line 108 and is present in the files the function reads,
but the function never accesses that column.

This accounts for the magnitude gap: raw summed attribution stays in the
1e-7 range, while the weighting steps are what would lift it to the
1.252 and 41.09 ranges reported in Table 4.

**On the `ĊĊ` token.** `is_special_character` in `detokenization.py`
excludes `Ċ`, but `ĊĊ` is two characters, so it fails the `len(token)==1`
test, and `Ċ` is not ASCII punctuation so the `string.punctuation` test
also fails. The token passes the filter unchanged.



## 5. Smaller observations

**`macro_f1` is not the mean of the per-category values printed beside it.** In
my RQ1 run the six F1 values average 65.67 while the printed `macro_f1` is 67.50.
Section 6.5 defines macro-average as the unweighted mean of per-category scores.
The artifact's shipped `FlakyLens_Result_Found_By_Author.csv` reports
`macro_f1 = 0.6749999999999999`, identical to my run to the last digit, while its
per-category columns differ from mine. The two figures appear to come from
different aggregations.

**Non-flaky is unaffected by four of the five perturbations**, sitting at exactly
100.00 in my runs and in Table 5. I checked whether code length separates it and
it does not: its median is 470 characters, close to OD at 487 and UC at 673.
Class imbalance (8294 of 8574) is the obvious explanation, but complete immunity
still seems worth asking about.



## 6. Hypotheses tested and rejected

- **Non-flaky is separable by code length.** Rejected. Median lengths overlap
  with OD and UC.
- **Truncation at 512 tokens explains Concurrency's poor performance.** Not
  supported. Rough estimate of tests over 512 tokens: Async 23.7%, Conc 18.9%,
  Time 15.2%, UC 4.9%, OD 3.2%, Non-flaky 7.2%. Async truncates most and performs
  well; OD truncates least and performs middling. (Estimate used 3.5 characters
  per token, not a real tokeniser, so treat as indicative.)
- **Attribution varies run to run.** Rejected. Byte-identical across two runs.
- **The 559 renaming errors cause the collapse.** Rejected with counts, not just
  proportions. See the split table in section 2.
- **The perturbed code is structurally damaged (wrapper class leakage).**
  Rejected. Sampled transformed tests are well-formed Java with no leftover
  scaffolding.
- **Re-indentation by the renaming wrapper causes the collapse.** Rejected.
  Adding four spaces to every line of all 8574 tests leaves macro F1 unchanged
  at 67.50.

Note on my own process: I initially proposed the `"Most"` / `"Most_Imp"`
explanation, then withdrew it on the basis of a `grep -l` search for
`Thread.sleep(1000);  job.schedule`. That search was unsound, because
`Thread.sleep(1000)` occurs naturally throughout the corpus and `grep -l` reports
presence rather than count. The counting check in section 1 is the correct test
and reinstates the original explanation.



## Completed

- Split the failed renames from the successful ones and compared the groups
  (section 2).
- Controlled random seeds in the deadcode path and ran repetitions with and
  without seeding (section 3b).
- Traced where aggregation, weighting and detokenisation occur (section 4b).

## Still to do

- Verify that the expected model checkpoint and tokeniser are being loaded.
- Trace a sample of renamed tests all the way through: transformed source,
  tokenised input, predicted label, expected label.