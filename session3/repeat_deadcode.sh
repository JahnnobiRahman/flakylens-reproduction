#!/bin/bash
LABEL=$1
N=$2
OUT=/output/session3
mkdir -p $OUT

echo "=== $LABEL : $N runs of deadcode_perturbation ===" | tee $OUT/deadcode_${LABEL}.txt

for i in $(seq 1 $N); do
    echo "--- run $i ---" | tee -a $OUT/deadcode_${LABEL}.txt
    rm -f ../results/per_Category_Evaluation_BERT-FlakyLens.txt
    bash per_project_prediction.sh FlakyLens "BERT" "deadcode_perturbation" \
        > $OUT/raw_${LABEL}_run${i}.log 2>&1
    cp ../results/per_Category_Evaluation_BERT-FlakyLens.txt \
       $OUT/perfold_${LABEL}_run${i}.txt
    (cd ../results/scripts && \
     bash per_category_parse_result.sh ../per_Category_Evaluation_BERT-FlakyLens.txt) \
        | tee -a $OUT/deadcode_${LABEL}.txt
    echo "" | tee -a $OUT/deadcode_${LABEL}.txt
done

echo "done. results in $OUT/deadcode_${LABEL}.txt"
