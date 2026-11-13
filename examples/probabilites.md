# Probabilités : les bases

## 1. Vocabulaire
- **Expérience aléatoire** : résultat imprévisible (lancer un dé)
- ==Univers S== = tous les résultats possibles -> dé : S = {1, 2, 3, 4, 5, 6}
- Événement = sous-ensemble de S
  - simple : une seule issue, ex. {3}
  - composé : plusieurs issues, ex. « pair » = {2, 4, 6}
- A et B **disjoints** si A ∩ B = ∅ (impossibles en même temps)

## 2. Lois de De Morgan
- (A ∩ B)ᶜ = Aᶜ ∪ Bᶜ -> « pas (A et B) » = « pas A ou pas B »
- (A ∪ B)ᶜ = Aᶜ ∩ Bᶜ -> « ni A ni B »

## 3. Axiomes de Kolmogorov
1. P(A) ≥ 0 pour tout A
2. P(S) = 1
3. A₁, A₂, ... disjoints deux à deux ⇒ P(∪ Aᵢ) = Σ P(Aᵢ)
> Nouveau : marche aussi pour une infinité ==dénombrable== d'événements

!! Méthode de TOUTES les preuves : découper en morceaux disjoints, puis axiome 3
- P(A ∪ B) = P(A) + P(B) − P(A ∩ B)

[ ] Refaire l'exemple corrigé (37 % / 40 %)
[x] Relire le cours 1-2
