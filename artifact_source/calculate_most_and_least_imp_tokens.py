import pandas as pd
from collections import defaultdict

# === Step 1: List all CSV file paths ===
def find_most_and_least_imp_tokens():
    file_paths = [
        "Attributions_scores/FlakyLens_attributions_project_group_1.csv",
        "Attributions_scores/FlakyLens_attributions_project_group_2.csv",
        "Attributions_scores/FlakyLens_attributions_project_group_3.csv",
        "Attributions_scores/FlakyLens_attributions_project_group_4.csv"
    ]
    
    # === Step 2: Load and concatenate all DataFrames ===
    df_list = [pd.read_csv(fp) for fp in file_paths]
    df = pd.concat(df_list, ignore_index=True)
    
    # === Step 3: Initialize token attribution dictionary per class ===
    category_tokens = {i: defaultdict(float) for i in range(6)}  # 5 categories: 0–4
    
    # === Step 4: Aggregate scores for rows where prediction == true class ===
    for _, row in df.iterrows():
        true_class = row['True_Class']
        predicted_class = row['Predicted_Class']
        
        if true_class == predicted_class and true_class in category_tokens:
            try:
                tokens = [t.strip() for t in row['Tokens(Sorted by Importance)'].split(';')]
                scores = list(map(float, row['Attribution_Scores(Sorted)'].split(';')))
                if len(tokens) != len(scores):
                    continue
            except Exception:
                continue
            
            for token, score in zip(tokens, scores):
                category_tokens[true_class][token] += score
    
    # === Step 5: Save per-class attribution summaries ===
    for cat, token_dict in category_tokens.items():
        token_score_df = pd.DataFrame(list(token_dict.items()), columns=['Token', 'Attribution_Score'])
    
        # Split positive and negative attribution scores
        pos_df = token_score_df[token_score_df['Attribution_Score'] >= 0].sort_values(by='Attribution_Score', ascending=False)
        neg_df = token_score_df[token_score_df['Attribution_Score'] < 0].sort_values(by='Attribution_Score', ascending=True)
    
        # Concatenate: positives first, then negatives
        final_df = pd.concat([pos_df, neg_df], ignore_index=True)
    
        output_path = f'Attributions_scores/category_{cat}_attributions.csv'
        final_df.to_csv(output_path, index=False)
    
