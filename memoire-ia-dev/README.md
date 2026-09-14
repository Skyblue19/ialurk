# Memoire IA Dev

Pipeline Python reproductible pour mesurer les **attributions explicites** a des outils IA dans les metadonnees de commits et de pull requests. Il ne conclut jamais que du code a ete produit par IA.

## Installation

```powershell
cd C:\Users\Baptiste\Desktop\Memoire\Dev\memoire-ia-dev
.\.venv\Scripts\python.exe -m pip install -e ".[all]"
Copy-Item .env.example .env
```

Ajoutez votre token GitHub dans `.env`. Le token est requis pour une collecte API fiable; les analyses de commits locaux n'en ont pas besoin.

## Premier pilote

1. Ajouter un depot documente a `config/repos.csv` avec une date et une source de bascule.
2. Cloner ce depot dans un emplacement hors de `data/`.
3. Detecter les bascules internes :

```powershell
.\.venv\Scripts\memoire-ia-dev.exe bascules C:\chemin\vers\clone
```

4. Extraire les commits et leurs attributions explicites :

```powershell
.\.venv\Scripts\memoire-ia-dev.exe commits C:\chemin\vers\clone data\raw\pilote_commits.csv
```

5. Extraire les PR (apres avoir renseigne `GITHUB_TOKEN`) :

```powershell
.\.venv\Scripts\memoire-ia-dev.exe prs organisation depot data\raw\pilote_prs.csv
```

Pour recuperer les identites de committer lorsque les autres signaux n'ont rien attribue, ajoutez `--commit-identities` :

```powershell
.\.venv\Scripts\memoire-ia-dev.exe prs organisation depot data\raw\pilote_prs.csv --commit-identities
```

Cette option appelle l'API des commits uniquement pour les PR sans attribution prealable et peut donc consommer beaucoup de quota sur un grand depot. Le choix est enregistre dans le checkpoint et doit rester identique lors d'une reprise.

Pour la premiere collecte de l'echantillon retenu, `--commit-identities` est active afin de ne pas devoir recollecter les PR plus tard pour les identites de committer. Il faut surveiller le quota GitHub et utiliser `--max-pages` avec `--resume` pour les grands depots.

## Collecte de l'echantillon

La commande batch lit `config/repos.csv`, clone ou actualise chaque depot dans `.work/`, puis affiche une progression globale en pourcentage et l'avancement des pages PR :

```powershell
.\.venv\Scripts\memoire-ia-dev.exe batch config\repos.csv --since 2020-06-01 --until 2026-08-25
```

Les PR sont collectees par tranches de 50 pages par defaut. La progression affiche le nombre de PR collectees sur le total GitHub pour la fenetre de dates. En cas d'interruption, relancer exactement la meme commande: chaque depot reprend depuis son checkpoint, tandis qu'un depot dont l'analyse est terminee est ignore. Pour que le batch attende la reinitialisation du quota GitHub puis reprenne automatiquement, ajoutez `--wait-for-rate-limit`. Les commits, details de bascule, tableaux, rapports et graphiques sont ecrits dans `data/raw/` et `data/processed/`. `--commit-identities` est active par defaut; utiliser `--no-commit-identities` uniquement pour une collecte moins couteuse.

L'API GitHub accepte au maximum 100 PR par page. Pour conserver tout le contenu avec `--commit-identities`, les recherches de committers sont executees en parallele avec trois workers et chaque page est ajoutee au CSV au lieu de reecrire tout l'historique. Les champs, filtres, detections et checkpoints restent inchanges.

## Validation AIDev

`memoire_ia_dev.validation.load_aidev()` telecharge la table PR `all_pull_request` de `hao-li/AIDev` uniquement a l'appel. `normalize_aidev_pull_requests()` adapte le schema verifie le 25 aout 2026 (`number`, `repo_url`, `agent`) en `identifiant`, `depot`, `outil_reference`, directement compatible avec `compare_to_reference()`. Passez une autre configuration explicite (`pr_commits`, `pr_reviews`, etc.) lorsque necessaire.

Les comptes non labellises par le dataset de reference sont des negatifs presumes. Cette limite est conservee dans le code et devra etre rapportee dans le memoire.

## Trois niveaux de preuve

`detect_pr_attribution()` renseigne `type_preuve` avec trois valeurs distinctes, a ne jamais fusionner dans le memoire :

| Niveau | Signal | Outils concernes |
|---|---|---|
| `structurelle` | Compte GitHub dedie (`author_login`, `committer_login`, `type: Bot`, GitHub App) | Copilot, Devin, Google Jules, Cursor, Claude Code |
| `convention_branche` | Prefixe de branche cree par l'agent (`head_ref`) | Codex, Cursor, Copilot |
| `auto_declaration` | Trailer ou mention dans le titre / corps | Claude Code, Replit, Aider |

Les fichiers de configuration sont un canal distinct du comptage de commits et de PR. Leur contenu est lu a la revision d'ajout: une formule de rejet explicite, telle que `Do not review` ou `Do not request`, produit `statut_config = rejet` et ne constitue pas une bascule d'adoption. La commande suivante affiche aussi les rejets, le commit et le chemin concernes :

```powershell
.\.venv\Scripts\memoire-ia-dev.exe bascules C:\chemin\vers\clone --details
```

La convention de branche a ete verifiee le 25 aout 2026 sur des PR reelles : `codex/` 7/7, `cursor/` 8/8, `copilot/` 8/8. Elle reste une convention modifiable : un humain peut nommer une branche `codex/...`. C'est une preuve plus faible qu'une identite de compte, d'ou son niveau distinct.

Codex n'a aucun compte dedie : les logins contenant `codex` sont des humains. Sans `head_ref`, il est indetectable. Ce champ n'existe pas dans AIDev mais est collecte par `get_pull_requests()`.

Pour executer le test sur **toute la table AIDev** et enregistrer les resultats :

```powershell
.\.venv\Scripts\memoire-ia-dev.exe eval-aidev data\processed\aidev_full_report.json --records-output data\processed\aidev_full_records.csv --detector-version v2 --comparison-output data\processed\aidev_detector_comparison.json
```

Le rapport JSON contient `n_reference`, `n_detecte`, `rappel_global`, `rappel_par_outil` et la version du detecteur. Le rapport comparatif conserve V1 et V2. AIDev etant un corpus de cas positifs, `precision` reste volontairement `null`: il faudrait un echantillon de PR GitHub non presentes dans AIDev pour calculer les faux positifs. Le CSV conserve le resultat ligne par ligne (`number`, `agent`, `detected`) pour auditer les desaccords.

## Analyse

- `cleaning.clean_commits()` ajoute des drapeaux `bot_automation` et `taille_aberrante` sans supprimer de donnees, pour que les exclusions restent auditables.
- `cleaning.classify_task()` applique des regles explicites pour `feat`, `fix`, `refactor`, `docs`, `test` ou `other`.
- `analysis.compare_periods()` calcule Mann-Whitney U, les medianes et la taille d'effet rank-biserial pour une metrique avant/apres.
- `policies.classify_policy()` implemente le volet optionnel de disclosure par regles deterministes. `find_policy_files()` recupere les fichiers candidats via GitHub.

## Verification locale

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```