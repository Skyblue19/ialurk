# Resultats

## 1. Methode et perimetre

La synthese couvre six depots GitHub dans l'echantillon principal et deux depots exploratoires, du 2020-06-01 au 2026-08-25. Les commits sont dates par date auteur et les pull requests par `created_at`. Les canaux commits et PR restent separes. Une attribution ne mesure que des signaux explicites et observables (compte d'agent, convention de branche, lien d'agent ou auto-declaration), pas la part de code ecrite par IA.

Trois depots ont une bascule d'adoption documentee : Microsoft VS Code (2024-11-28), Home Assistant Core (2025-02-19) et Next.js (2026-01-05). Godot et Redis sont des temoins sans bascule identifiee. Django est traite comme temoin : son fichier Copilot est classe `rejet`, pas adoption. osu! et Bun, analyses avant la constitution du manifeste final, sont reintegres comme cohorte exploratoire : ils enrichissent la description mais ne modifient pas les tests confirmatoires du plan principal.

## 2. Resultats descriptifs

Les resultats PR ci-dessous utilisent le detecteur V2; les commits conservent les regles existantes. L'echantillon principal contient 282,415 commits, dont 7,303 attributions explicites (2.59 %), et 220,460 PR, dont 3,186 attributions explicites (1.45 %). La cohorte exploratoire ajoute 64,753 commits et 26,307 PR.

| Depot | Echantillon | Groupe | Commits | Commits IA | Taux commits IA (%) | PR | PR IA | Taux PR IA (%) |
|---|---|---|---:|---:|---:|---:|---:|---:|
| microsoft/vscode | principal | adoption | 97,341 | 4,974 | 5.11 | 54,888 | 2,458 | 4.48 |
| home-assistant/core | principal | adoption | 88,323 | 2,155 | 2.44 | 83,434 | 358 | 0.43 |
| vercel/next.js | principal | adoption | 29,257 | 148 | 0.51 | 31,682 | 321 | 1.01 |
| godotengine/godot | principal | temoin | 57,203 | 1 | 0.00 | 37,507 | 18 | 0.05 |
| redis/redis | principal | temoin | 3,868 | 22 | 0.57 | 4,670 | 16 | 0.34 |
| django/django | principal | temoin | 6,423 | 3 | 0.05 | 8,279 | 15 | 0.18 |
| ppy/osu | exploratoire | exploratoire | 47,207 | 0 | 0.00 | 10,077 | 0 | 0.00 |
| oven-sh/bun | exploratoire | exploratoire | 17,546 | 693 | 3.95 | 16,230 | 226 | 1.39 |

### Comparaison des detecteurs PR

La V1 reste reproductible et les CSV bruts ne sont pas modifies. La V2 ajoute des URL de taches Cursor/Codex et des formulations d'auto-declaration strictes.

| Depot | Detectees V1 | Detectees V2 | Gain V2 | Taux V1 (%) | Taux V2 (%) |
|---|---:|---:|---:|---:|---:|
| microsoft/vscode | 2,458 | 2,458 | +0 | 4.48 | 4.48 |
| home-assistant/core | 356 | 358 | +2 | 0.43 | 0.43 |
| vercel/next.js | 320 | 321 | +1 | 1.01 | 1.01 |
| godotengine/godot | 18 | 18 | +0 | 0.05 | 0.05 |
| redis/redis | 16 | 16 | +0 | 0.34 | 0.34 |
| django/django | 13 | 15 | +2 | 0.16 | 0.18 |
| ppy/osu | 0 | 0 | +0 | 0.00 | 0.00 |
| oven-sh/bun | 225 | 226 | +1 | 1.39 | 1.39 |

Le test d'integration V2 a traite 246,767 PR dans les 8 depots. Son statut global est `reussi` : 3,406 detections V1 et 3,412 detections V2, soit 6 ajouts sans perte d'une detection V1. Le detail auditable se trouve dans `validation_v2_huit_depots.json`.

`evolution_trimestrielle_prs.png` contient une seule courbe globale. Pour chaque depot et chaque trimestre, un taux individuel est d'abord calcule : `PR attribuees a l'IA / toutes les PR du depot`. Le point global est ensuite la moyenne arithmetique des huit taux individuels. Chaque depot a donc le meme poids, quelle que soit sa quantite de PR. Ce choix correspond a une moyenne des comportements des depots; il ne faut pas le confondre avec le taux pondere `somme(PR IA) / somme(PR)`, dans lequel les plus gros depots domineraient.

Les groupes Adoption, Temoin et Exploratoire restent utiles pour definir le protocole et les tests, mais ne sont plus representes dans cette figure. La courbe mesure la frequence moyenne des attributions explicites, pas la performance du detecteur ni la proportion exacte de code produit par IA.

La baisse apparente de Bun apres 2025 ne permet pas de conclure a une baisse de son usage reel de l'IA. Elle correspond d'abord a la disparition de signaux explicites detectables : 124 PR identifiees par une convention de branche au deuxieme trimestre 2025, puis 53 auto-declarations Claude au quatrieme trimestre 2025, contre seulement 4 a 5 PR detectees par trimestre en 2026. Simultanement, le denominateur augmente fortement, d'environ 800-1 050 PR par trimestre en 2025 a 1 721, 2 466 et 2 494 PR lors des trois trimestres observes de 2026. Le taux passe donc de 15,57 % en 2025Q2 et 5,04 % en 2025Q4 a 0,23 %, 0,20 % et 0,16 % en 2026. Le dernier trimestre, 2026Q3, est en outre incomplet puisque la collecte s'arrete au 25 aout. L'interpretation defendable est une baisse des attributions explicites observees, possiblement liee a un changement d'outil, de convention de branche ou de pratique de declaration; les donnees ne permettent pas de choisir entre ces causes ni d'affirmer que l'usage non declare a diminue.

## 3. Comparaisons avant/apres

Les tests Mann-Whitney U sont appliques aux taux trimestriels, pas aux PR ou commits individuels. Le tableau ci-dessous est descriptif et inferentiel a la fois; les tres petites periodes post-bascule, notamment Next.js, limitent la puissance.

| Depot | Canal | Taux avant (%) | Taux apres (%) | p-value | Effet rang-biseriel | Trimestres avant | Trimestres apres |
|---|---|---:|---:|---:|---:|---:|---:|
| microsoft/vscode | commits | 0.00 | 13.71 | 5.698e-05 | -0.750 | 18 | 8 |
| microsoft/vscode | prs | 0.00 | 8.85 | 5.698e-05 | -0.750 | 18 | 8 |
| home-assistant/core | commits | 0.00 | 8.62 | 9.735e-06 | -0.857 | 19 | 7 |
| home-assistant/core | prs | 0.00 | 1.48 | 9.735e-06 | -0.857 | 19 | 7 |
| vercel/next.js | commits | 0.03 | 4.35 | 7.323e-05 | -1.000 | 23 | 3 |
| vercel/next.js | prs | 0.07 | 6.74 | 0.0002197 | -1.000 | 23 | 3 |

## 4. Interpretation et limites

### Validation externe avec AIDev

AIDev est un corpus de 2,743,854 PR positives deja associees a un agent. Le detecteur en retrouve 2,611,681, soit un rappel global de 95.18 %. La precision n'est pas calculable sur ce corpus seul, faute de PR negatives certifiees.

| Outil | Positifs AIDev | Detectes | Rappel (%) | Couverture commits (%) |
|---|---:|---:|---:|---:|
| claude_code | 18,232 | 17,065 | 93.60 | 10.49 |
| copilot | 349,695 | 345,028 | 98.67 | 6.71 |
| cursor | 212,544 | 185,325 | 87.19 | 1.91 |
| devin | 43,298 | 43,298 | 100.00 | 14.24 |
| google_jules | 50,490 | 50,449 | 99.92 | 0.96 |
| codex | 2,069,595 | 1,970,516 | 95.21 | 1.72 |

`performance_aidev_par_outil.png` compare le rappel par outil. `composition_outils_aidev_vs_depots.png` compare uniquement la repartition des outils parmi les positifs AIDev et parmi les detections des huit depots. Cette seconde comparaison renseigne sur les differences de composition des corpus, pas sur leur prevalence d'usage IA : AIDev vaut 100 % positif par construction.

La validation Bun fournit un controle supplementaire sur une fenetre commune : 182 vrais positifs sur 182 cas AIDev apparies (rappel 100 %) et une precision apparente de 96,81 %. Cette precision reste qualifiee d'apparente, car les PR non labellisees par AIDev ne sont pas des negatifs humains certifies.

### Jeux de donnees complementaires

Plusieurs corpus publics peuvent completer AIDev, mais ils ne repondent pas tous a la meme question :

| Corpus | Apport possible | Limite pour cette etude | Priorite |
|---|---|---|---|
| [DevGPT v10](https://doi.org/10.5281/zenodo.16392320) | 17 913 echanges ChatGPT relies a des artefacts GitHub, dont des commits et des PR; les liens partages constituent des positifs explicites d'un type absent d'AIDev | Ancien et limite a ChatGPT; un adaptateur de schema et une deduplication des snapshots sont necessaires | Haute |
| [PatchTrack](https://doi.org/10.5281/zenodo.16945106) | 338 PR de 255 depots avec usage ChatGPT auto-declare, 645 suggestions IA et 3 486 patches developpeur | Petit corpus et possible recouvrement avec DevGPT a verifier avant de le qualifier d'independant | Haute pour un audit manuel |
| [AgenticFlict](https://doi.org/10.5281/zenodo.19396916) | Plus de 142 000 PR agentiques dans plus de 59 000 depots, avec identifiants et donnees de conflits | Il faut auditer la construction des labels et mesurer le recouvrement avec AIDev; le volume seul ne garantit pas une validation independante | Moyenne |
| [Test Coverage of AI-Generated PRs](https://doi.org/10.5281/zenodo.18019124) | 2 314 PR pretraitees, groupes IA, co-auteur et humain, plus une evaluation manuelle a trois annotateurs | Corpus concu pour la couverture de tests, pas pour certifier l'attribution IA; les PR humaines ne sont pas automatiquement des negatifs certifies pour notre detecteur | Moyenne |

AgenticFlict et Test Coverage ont aussi ete evalues en reutilisant les metadonnees de PR d'AIDev comme cache hors ligne. Sur AgenticFlict, 129,491 des 142,652 PR ont pu etre hydratees : le rappel passe de 86.14 % en V1 a 87.34 % en V2. Sur les groupes IA et co-auteur de Test Coverage, 7,048 des 7,190 PR ont ete hydratees : le rappel passe de 71.91 % a 72.23 %.

Ces deux scores ne constituent pas des validations independantes d'AIDev : les corpus sont derives de sa population et les champs servant au detecteur proviennent de sa table. En outre, la table AIDev utilisee ne contient ni branche de PR ni identite de commit. Cela penalise surtout Cursor (34,71 % sur AgenticFlict et 4,08 % sur Test Coverage) et Codex (86,68 % et 65,65 %), dont une partie des signaux depend de ces champs. Parmi les 1,402 PR humaines de Test Coverage, seules 10 figurent dans AIDev; la precision ne peut donc pas etre calculee hors ligne sur ce groupe.

DevGPT eprouve un autre mode d'auto-declaration : les liens `chat.openai.com/share/...`. Le detecteur actuel ne traite pas ce lien generique comme une attribution. Toute extension de cette regle doit etre evaluee sur un jeu reserve ou par validation croisee afin d'eviter d'adapter puis de tester le detecteur sur les memes observations.

Les resultats decrivent la visibilite des attributions explicites, non l'usage reel de l'IA. L'absence de signal ne prouve donc pas l'absence d'utilisation. Les differences entre depots peuvent aussi refleter les politiques de contribution, les conventions de branche, la composition des comptes automatises et les pratiques de revue.

Les comparaisons avant/apres ne permettent pas a elles seules une inference causale : les bascules ne sont pas assignees aleatoirement et les changements temporels peuvent avoir d'autres causes. Les temoins servent a contextualiser les tendances, mais ne garantissent pas le parallelisme des trajectoires. Enfin, la precision ne peut pas etre deduite du corpus AIDev, qui est compose de cas positifs; la validation V2 disponible etablit un rappel global de 95.18 %.
