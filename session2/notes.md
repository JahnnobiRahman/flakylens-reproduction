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

**Hypothesis, not verified.** The post-processing described in Sections 5.1.2 and
5.1.4 (subword merging, stop-word removal, multiplication by model confidence and
by log token frequency) and the normalisation mentioned in Section 6.3 do not
appear to have been applied to this output. The `ĊĊ` token in the non-flaky row
is a raw CodeBERT newline marker, which detokenisation should have removed.
`calculate_most_and_least_imp_tokens.py` and `detokenization.py` are present in
`/app/src` but have not been inspected yet.



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
- **The 559 renaming errors cause the renaming collapse.** Rejected. 6.5% of
  tests, and the result is uniformly zero.
- **The perturbed code is structurally damaged (wrapper class leakage).**
  Rejected. Sampled transformed tests are well-formed Java with no leftover
  scaffolding.

Note on my own process: I initially proposed the `"Most"` / `"Most_Imp"`
explanation, then withdrew it on the basis of a `grep -l` search for
`Thread.sleep(1000);  job.schedule`. That search was unsound, because
`Thread.sleep(1000)` occurs naturally throughout the corpus and `grep -l` reports
presence rather than count. The counting check in section 1 is the correct test
and reinstates the original explanation.



## Still to do

- Split the 559 error cases from the successfully renamed tests and score each
  group separately.
- Control all random seeds in the deadcode path, run several repetitions, and
  report mean and standard deviation per category.
- Open `calculate_most_and_least_imp_tokens.py` and `detokenization.py` and trace
  where aggregation, weighting and detokenisation occur; compare raw Integrated
  Gradients output against the final values.
- Verify that the expected model checkpoint and tokeniser are being loaded.
- Trace a sample of renamed tests all the way through: transformed source,
  tokenised input, predicted label, expected label.