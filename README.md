\# FlakyLens artifact reproduction



Notes from running the FlakyLens artifact (OOPSLA 2025, Zenodo 15761937)

as part of a research screening exercise.



\## Setup

RTX 3050, 8 GB VRAM, 15 GB RAM. Windows 11, Docker + WSL2.

RQ1, RQ3, RQ4 completed. RQ2 not attempted (7B-16B models exceed 8 GB).



\## Session log

\- Session 1 (Sep 1): initial artifact run. RQ1, RQ3, RQ4, all five

&#x20; perturbations rather than only the deadcode one in rq4.sh.

\- Session 2 (Sep 7): confusion matrices before and after variable

&#x20; renaming, verification of which perturbation branch executes,

&#x20; sample transformed tests.



\## Files

\- `cm\_clean.txt`, `cm\_rename.txt` — confusion matrices

\- `session2/branch\_check\_\*.txt` — token counts establishing which

&#x20; perturbation branch runs

\- `session2/renamed\_samples\_fold1.txt` — first five transformed tests

\- `\*\_result.txt` — per-category F1 output

\- `notes.md` — findings and open questions



Perturbed CSVs are not committed. They are regenerable by rerunning

the artifact.



\## Status

Work in progress. Several conclusions have been revised as evidence

came in. See notes.md for what is established versus what is still

hypothesis.

