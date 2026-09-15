# Resultats

## 1. Perimetre

La synthese couvre huit depots GitHub du 2020-06-01 au 2026-08-25. Le dernier trimestre, 2026Q3, est incomplet au 25 aout. Les commits sont dates par date auteur et les pull requests par `created_at`. Ces deux canaux restent separes.

Une attribution designe uniquement un signal explicite et observable dans les metadonnees Git ou GitHub : identite dediee, convention de branche ou auto-declaration. Elle ne mesure ni la part de code ecrite par IA, ni l'usage non declare d'un outil.

## 2. Resultats globaux par depot

Le corpus contient 347,168 commits, dont 7,992 avec attribution explicite (2.30 %), et 246,767 pull requests, dont 3,412 avec attribution explicite (1.38 %).

| Depot | Commits | Commits IA | Taux commits IA (%) | PR | PR IA | Taux PR IA (%) |
|---|---:|---:|---:|---:|---:|---:|
| microsoft/vscode | 97,341 | 4,974 | 5.11 | 54,888 | 2,458 | 4.48 |
| home-assistant/core | 88,323 | 2,155 | 2.44 | 83,434 | 358 | 0.43 |
| vercel/next.js | 29,257 | 148 | 0.51 | 31,682 | 321 | 1.01 |
| godotengine/godot | 57,203 | 1 | 0.00 | 37,507 | 18 | 0.05 |
| redis/redis | 3,868 | 21 | 0.54 | 4,670 | 16 | 0.34 |
| django/django | 6,423 | 0 | 0.00 | 8,279 | 15 | 0.18 |
| ppy/osu | 47,207 | 0 | 0.00 | 10,077 | 0 | 0.00 |
| oven-sh/bun | 17,546 | 693 | 3.95 | 16,230 | 226 | 1.39 |

Le graphique `attribution_par_depot.png` represente simultanement les taux des deux canaux pour chacun des huit depots.

## 3. Evolution temporelle commits / PR

Pour chaque depot et chaque trimestre, le taux correspond au nombre de contributions attribuees divise par le nombre total de contributions du meme canal. La courbe globale est ensuite la moyenne arithmetique des huit taux. Elle ne correspond donc pas au rapport entre les sommes globales, qui donnerait davantage de poids aux gros depots.

`evolution_trimestrielle_commits_prs.png` presente deux panneaux avec le meme axe temporel et la meme echelle verticale. Les valeurs correspondantes sont dans `evolution_globale_par_canal.csv`. 2026Q3 y est signale comme incomplet.

## 4. Repartition par type de preuve

Les detections sont reparties entre identites structurelles, conventions de branche et auto-declarations. Chaque contribution detectee appartient a une seule categorie, selon le premier signal retenu par le detecteur.

| Canal | Type de preuve | Detections | Part des detections (%) |
|---|---|---:|---:|
| Commits | Identité structurelle | 3 | 0.04 |
| Commits | Convention de branche | 0 | 0.00 |
| Commits | Auto-déclaration | 7,989 | 99.96 |
| Pull requests | Identité structurelle | 2,174 | 63.72 |
| Pull requests | Convention de branche | 786 | 23.04 |
| Pull requests | Auto-déclaration | 452 | 13.25 |

`evolution_types_preuve.png` montre la contribution de chaque type au taux total, et non sa seule proportion parmi les detections. Les donnees detaillees figurent dans `types_preuve_trimestriels.csv` et les totaux dans `types_preuve_globaux.csv`.

## 5. Cas Bun

| Trimestre | PR totales | PR IA | Taux (%) | Structurelle | Convention de branche | Auto-declaration |
|---|---:|---:|---:|---:|---:|---:|
| 2025Q1 | 1,007 | 0 | 0.00 | 0 | 0 | 0 |
| 2025Q2 | 822 | 128 | 15.57 | 1 | 124 | 3 |
| 2025Q3 | 1,150 | 31 | 2.70 | 1 | 4 | 26 |
| 2025Q4 | 1,052 | 53 | 5.04 | 0 | 0 | 53 |
| 2026Q1 | 1,721 | 4 | 0.23 | 0 | 0 | 4 |
| 2026Q2 | 2,466 | 6 | 0.24 | 0 | 4 | 2 |
| 2026Q3 | 2,494 | 4 | 0.16 | 0 | 3 | 1 |

`bun_types_preuve_trimestriels.png` montre que l'evolution du taux depend a la fois du nombre de traces detectees, de leur nature et du volume total de PR. Une baisse du taux observe ne suffit pas a conclure a une baisse de l'usage reel de l'IA.

## 6. Validation AIDev

AIDev contient 2,743,854 PR positives deja associees a un agent. Le detecteur final en retrouve 2,611,375, soit un rappel global de 95.17 %. La precision n'est pas calculable sur ce corpus seul, faute de PR negatives certifiees.

| Outil | Positifs AIDev | Detectes | Rappel (%) | Couverture commits (%) |
|---|---:|---:|---:|---:|
| claude_code | 18,232 | 16,759 | 91.92 | 10.49 |
| copilot | 349,695 | 345,028 | 98.67 | 6.71 |
| cursor | 212,544 | 185,325 | 87.19 | 1.91 |
| devin | 43,298 | 43,298 | 100.00 | 14.24 |
| google_jules | 50,490 | 50,449 | 99.92 | 0.96 |
| codex | 2,069,595 | 1,970,516 | 95.21 | 1.72 |

Les six categories du tableau proviennent de la configuration `all_pull_request` du corpus AIDev. Elles ne constituent pas la liste exhaustive des outils reconnus par le detecteur. Selon le canal, celui-ci contient aussi des regles pour Aider, Replit, Codegen, Terragon ou Wildcard. La provenance locale disponible est enregistree dans `provenance_aidev.json`; aucun hash de revision n'a ete trouve dans les metadonnees locales.

## 7. Limites d'interpretation

Les resultats decrivent la visibilite des attributions explicites, pas l'usage reel de l'IA. L'absence de signal ne prouve pas l'absence d'utilisation. Les differences entre depots peuvent provenir des politiques de contribution, des conventions de branche, des outils ou des pratiques de declaration. La moyenne non ponderee donne le meme poids aux huit depots et doit etre lue comme une moyenne de projets, pas comme un taux global pondere par le nombre de contributions. Enfin, AIDev mesure le rappel sur des cas positifs mais ne permet pas d'estimer la precision du detecteur.
