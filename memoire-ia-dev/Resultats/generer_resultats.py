"""Build cross-repository tables, figures, and a thesis-ready results note."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import matplotlib.pyplot as plt
import pandas as pd

from memoire_ia_dev.analysis import compare_periods
from memoire_ia_dev.prs import tag_prs


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUTPUT = Path(__file__).resolve().parent
V2_GRAPHS = ROOT / "Graphes_V2"
START = "2020-06-01"
END = "2026-08-25"

REPOSITORIES = {
    "microsoft/vscode": {"prefix": "microsoft_vscode", "bascule": "2024-11-28", "groupe": "adoption", "echantillon": "principal"},
    "home-assistant/core": {"prefix": "home-assistant_core", "bascule": "2025-02-19", "groupe": "adoption", "echantillon": "principal"},
    "vercel/next.js": {"prefix": "vercel_next.js", "bascule": "2026-01-05", "groupe": "adoption", "echantillon": "principal"},
    "godotengine/godot": {"prefix": "godotengine_godot", "bascule": None, "groupe": "temoin", "echantillon": "principal"},
    "redis/redis": {"prefix": "redis_redis", "bascule": None, "groupe": "temoin", "echantillon": "principal"},
    "django/django": {"prefix": "django_django", "bascule": None, "groupe": "temoin", "echantillon": "principal"},
    "ppy/osu": {"prefix": "osu", "commits_file": "osu_commits_2020_2026.csv", "prs_file": "osu_prs_2020_2026.csv", "bascule": None, "groupe": "exploratoire", "echantillon": "exploratoire"},
    "oven-sh/bun": {"prefix": "bun", "commits_file": "bun_commits_2020_2026.csv", "prs_file": "bun_prs_2020_2026.csv", "bascule": None, "groupe": "exploratoire", "echantillon": "exploratoire"},
}

def load_channel(
    path: Path, date_column: str, repository: str, detector_version: str | None = None,
) -> pd.DataFrame:
    frame = pd.read_csv(path, low_memory=False)
    if detector_version is not None:
        frame = tag_prs(frame, version=detector_version)
    frame[date_column] = pd.to_datetime(frame[date_column], utc=True)
    frame = frame.loc[frame[date_column].between(pd.Timestamp(START, tz="UTC"), pd.Timestamp(END, tz="UTC"))].copy()
    frame["depot"] = repository
    frame["annee_trimestre"] = frame[date_column].dt.tz_localize(None).dt.to_period("Q").astype(str)
    frame["ai_attribue"] = frame["ai_attribue"].fillna(False).astype(bool)
    return frame


def rate(frame: pd.DataFrame) -> float:
    return float(frame["ai_attribue"].mean() * 100) if len(frame) else 0.0


def build_results() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    repository_rows = []
    comparison_rows = []
    quarterly_rows = []
    for repository, metadata in REPOSITORIES.items():
        prefix = metadata["prefix"]
        commits = load_channel(RAW / metadata.get("commits_file", f"{prefix}_commits.csv"), "date", repository)
        prs = load_channel(
            RAW / metadata.get("prs_file", f"{prefix}_prs.csv"), "created_at", repository, "v2",
        )
        repository_rows.append({
            "depot": repository,
            "groupe": metadata["groupe"],
            "echantillon": metadata["echantillon"],
            "date_bascule": metadata["bascule"],
            "commits": len(commits),
            "commits_ia": int(commits["ai_attribue"].sum()),
            "taux_commits_ia_pct": rate(commits),
            "prs": len(prs),
            "prs_ia": int(prs["ai_attribue"].sum()),
            "taux_prs_ia_pct": rate(prs),
        })
        for quarter in sorted(set(commits["annee_trimestre"]) | set(prs["annee_trimestre"])):
            commit_quarter = commits.loc[commits["annee_trimestre"] == quarter]
            pr_quarter = prs.loc[prs["annee_trimestre"] == quarter]
            quarterly_rows.append({
                "depot": repository, "groupe": metadata["groupe"], "echantillon": metadata["echantillon"],
                "annee_trimestre": quarter,
                "commits": len(commit_quarter), "commits_ia": int(commit_quarter["ai_attribue"].sum()),
                "taux_commits_ia_pct": rate(commit_quarter), "prs": len(pr_quarter),
                "prs_ia": int(pr_quarter["ai_attribue"].sum()), "taux_prs_ia_pct": rate(pr_quarter),
            })
        if metadata["bascule"]:
            threshold = pd.Timestamp(metadata["bascule"], tz="UTC")
            for channel, frame, date_column in (("commits", commits, "date"), ("prs", prs, "created_at")):
                periods = frame.copy()
                periods["periode"] = periods[date_column].ge(threshold).map({True: "apres", False: "avant"})
                period_rates = periods.groupby("annee_trimestre", as_index=False).agg(
                    periode=("periode", "first"), taux_ia_pct=("ai_attribue", lambda series: series.mean() * 100)
                )
                statistics = compare_periods(period_rates, "taux_ia_pct")
                comparison_rows.append({
                    "depot": repository, "canal": channel, "date_bascule": metadata["bascule"],
                    "taux_avant_pct": rate(periods.loc[periods["periode"] == "avant"]),
                    "taux_apres_pct": rate(periods.loc[periods["periode"] == "apres"]),
                    **statistics,
                })
    return pd.DataFrame(repository_rows), pd.DataFrame(comparison_rows), pd.DataFrame(quarterly_rows)


def build_detector_comparison() -> pd.DataFrame:
    rows = []
    for repository, metadata in REPOSITORIES.items():
        path = RAW / metadata.get("prs_file", f"{metadata['prefix']}_prs.csv")
        source = pd.read_csv(path, low_memory=False)
        v1 = tag_prs(source, version="v1")
        v2 = tag_prs(source, version="v2")
        rows.append({
            "depot": repository,
            "prs": len(source),
            "detectees_v1": int(v1["ai_attribue"].sum()),
            "detectees_v2": int(v2["ai_attribue"].sum()),
            "gain_v2": int(v2["ai_attribue"].sum() - v1["ai_attribue"].sum()),
            "taux_v1_pct": rate(v1),
            "taux_v2_pct": rate(v2),
        })
    return pd.DataFrame(rows)


def plot_results(repository_summary: pd.DataFrame, quarterly: pd.DataFrame) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    figure, axis = plt.subplots(figsize=(10, 5))
    positions = range(len(repository_summary))
    axis.bar([position - 0.2 for position in positions], repository_summary["taux_commits_ia_pct"], width=0.4, label="Commits")
    axis.bar([position + 0.2 for position in positions], repository_summary["taux_prs_ia_pct"], width=0.4, label="Pull requests")
    axis.set_xticks(list(positions), repository_summary["depot"], rotation=25, ha="right")
    axis.set_ylabel("Attributions explicites IA (%)")
    axis.legend()
    figure.tight_layout()
    figure.savefig(OUTPUT / "taux_attribution_par_depot.png", dpi=180)
    plt.close(figure)

    global_quarterly = quarterly.groupby("annee_trimestre", as_index=False).agg(
        taux_prs_ia_pct=("taux_prs_ia_pct", "mean"),
    )
    figure, axis = plt.subplots(figsize=(12, 6))
    axis.plot(
        global_quarterly["annee_trimestre"], global_quarterly["taux_prs_ia_pct"],
        marker="o", color="#287271", linewidth=2, label="Moyenne des huit depots",
    )
    axis.set_ylabel("Attributions explicites IA dans les PR (%)")
    axis.set_xlabel("Trimestre")
    axis.set_title("Evolution trimestrielle moyenne des PR attribuees a l'IA")
    axis.tick_params(axis="x", rotation=45)
    axis.legend()
    figure.text(
        0.5, 0.01,
        "Moyenne arithmetique des taux des huit depots (meme poids); 2026Q3 incomplet au 25 aout.",
        ha="center", fontsize=9,
    )
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    figure.savefig(OUTPUT / "evolution_trimestrielle_prs.png", dpi=180)
    plt.close(figure)


def normalize_tool(value: str) -> str:
    return {
        "Claude_Code": "claude_code", "Copilot": "copilot", "Cursor": "cursor",
        "Devin": "devin", "Google_Jules": "google_jules", "OpenAI_Codex": "codex",
    }.get(value, value.lower())


def build_aidev_results() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    report = json.loads((ROOT / "data" / "processed" / "aidev_full_report.json").read_text(encoding="utf-8"))
    performance = pd.DataFrame(report["rappel_par_outil"])
    performance["outil"] = performance["outil_reference"].map(normalize_tool)
    performance["rappel_pct"] = performance["rappel"] * 100
    performance["rappel_si_donnees_commit_pct"] = performance["rappel_si_donnees_commit"] * 100

    aidev_composition = performance[["outil", "n_reference"]].rename(columns={"n_reference": "nombre"})
    aidev_composition["corpus"] = "AIDev (positifs de reference)"
    detected = []
    for repository, metadata in REPOSITORIES.items():
        prs = pd.read_csv(RAW / metadata.get("prs_file", f"{metadata['prefix']}_prs.csv"), low_memory=False)
        prs = tag_prs(prs, version="v2")
        tools = prs.loc[prs["ai_attribue"].fillna(False).astype(bool), "outil"].dropna().map(normalize_tool)
        detected.extend({"outil": tool, "nombre": count, "corpus": "Depots etudies (detections)"} for tool, count in tools.value_counts().items())
    detected_composition = pd.DataFrame(detected).groupby(["corpus", "outil"], as_index=False)["nombre"].sum()
    composition = pd.concat([aidev_composition, detected_composition], ignore_index=True)
    composition["part_pct"] = composition["nombre"] / composition.groupby("corpus")["nombre"].transform("sum") * 100
    return performance, composition, report


def plot_aidev(performance: pd.DataFrame, composition: pd.DataFrame) -> None:
    figure, axis = plt.subplots(figsize=(9, 5))
    ordered = performance.sort_values("rappel_pct")
    bars = axis.barh(ordered["outil"], ordered["rappel_pct"], color="#287271")
    axis.bar_label(bars, fmt="%.1f %%", padding=3)
    global_recall = performance["n_detecte"].sum() / performance["n_reference"].sum() * 100
    axis.axvline(
        global_recall, color="#d1495b", linestyle="--",
        label=f"Rappel global V2: {global_recall:.2f} %".replace(".", ","),
    )
    axis.set_xlim(0, 105)
    axis.set_xlabel("Rappel sur les PR positives AIDev (%)")
    axis.set_title("Performance du detecteur par outil sur AIDev")
    axis.legend(loc="lower right")
    figure.tight_layout()
    figure.savefig(OUTPUT / "performance_aidev_par_outil.png", dpi=180)
    plt.close(figure)

    pivot = composition.pivot(index="corpus", columns="outil", values="part_pct").fillna(0)
    preferred = [tool for tool in ["codex", "copilot", "cursor", "claude_code", "devin", "google_jules"] if tool in pivot.columns]
    remaining = [tool for tool in pivot.columns if tool not in preferred]
    pivot = pivot[preferred + remaining]
    figure, axis = plt.subplots(figsize=(11, 5))
    pivot.plot(kind="barh", stacked=True, ax=axis, colormap="tab20c")
    axis.set_xlabel("Repartition des outils parmi les cas positifs/detectes (%)")
    axis.set_ylabel("")
    axis.set_title("Composition des outils: AIDev vs detections dans les depots")
    axis.legend(title="Outil", bbox_to_anchor=(1.02, 1), loc="upper left")
    figure.tight_layout()
    figure.savefig(OUTPUT / "composition_outils_aidev_vs_depots.png", dpi=180)
    plt.close(figure)


def export_v2_graphs(detector_comparison: pd.DataFrame) -> None:
    V2_GRAPHS.mkdir(exist_ok=True)
    graph_names = (
        "taux_attribution_par_depot.png",
        "evolution_trimestrielle_prs.png",
        "performance_aidev_par_outil.png",
        "composition_outils_aidev_vs_depots.png",
    )
    for graph_name in graph_names:
        shutil.copy2(OUTPUT / graph_name, V2_GRAPHS / graph_name)

    figure, (rate_axis, gain_axis) = plt.subplots(
        1, 2, figsize=(15, 6), gridspec_kw={"width_ratios": [2.3, 1]},
    )
    positions = range(len(detector_comparison))
    bars_v1 = rate_axis.bar(
        [position - 0.2 for position in positions], detector_comparison["taux_v1_pct"],
        width=0.4, color="#8b9aa3", label="V1",
    )
    bars_v2 = rate_axis.bar(
        [position + 0.2 for position in positions], detector_comparison["taux_v2_pct"],
        width=0.4, color="#287271", label="V2",
    )
    rate_axis.set_xticks(list(positions), detector_comparison["depot"], rotation=30, ha="right")
    rate_axis.set_ylabel("PR avec attribution explicite IA (%)")
    rate_axis.set_title("Taux de detection")
    rate_axis.legend()
    rate_axis.bar_label(bars_v1, fmt="%.3f", padding=2, fontsize=7, rotation=90)
    rate_axis.bar_label(bars_v2, fmt="%.3f", padding=2, fontsize=7, rotation=90)

    gains = detector_comparison.sort_values("gain_v2")
    gain_bars = gain_axis.barh(gains["depot"], gains["gain_v2"], color="#d1495b")
    gain_axis.bar_label(gain_bars, fmt="%+d", padding=3)
    gain_axis.set_xlim(0, max(2.5, float(gains["gain_v2"].max()) + 0.7))
    gain_axis.set_xlabel("Nouvelles PR detectees par V2")
    gain_axis.set_title("Gain V2")
    figure.suptitle("Comparaison des detecteurs V1 et V2 sur les huit depots")
    figure.tight_layout()
    figure.savefig(V2_GRAPHS / "comparaison_v1_v2_par_depot.png", dpi=180)
    plt.close(figure)


def write_note(
    repository_summary: pd.DataFrame, comparisons: pd.DataFrame,
    aidev_performance: pd.DataFrame, aidev_report: dict[str, object],
    external_report: dict[str, object], detector_comparison: pd.DataFrame,
    v2_validation: dict[str, object],
) -> None:
    primary = repository_summary.loc[repository_summary["echantillon"] == "principal"]
    exploratory = repository_summary.loc[repository_summary["echantillon"] == "exploratoire"]
    total_commits = int(primary["commits"].sum())
    total_prs = int(primary["prs"].sum())
    total_commits_ia = int(primary["commits_ia"].sum())
    total_prs_ia = int(primary["prs_ia"].sum())
    rows = "\n".join(
        f"| {row.depot} | {row.echantillon} | {row.groupe} | {int(row.commits):,} | {int(row.commits_ia):,} | {row.taux_commits_ia_pct:.2f} | {int(row.prs):,} | {int(row.prs_ia):,} | {row.taux_prs_ia_pct:.2f} |"
        for row in repository_summary.itertuples()
    )
    comparison_lines = "\n".join(
        f"| {row.depot} | {row.canal} | {row.taux_avant_pct:.2f} | {row.taux_apres_pct:.2f} | {row.p_value:.4g} | {row.effet_rang_biseriel:.3f} | {int(row.n_avant)} | {int(row.n_apres)} |"
        for row in comparisons.itertuples()
    )
    aidev_lines = "\n".join(
        f"| {row.outil} | {int(row.n_reference):,} | {int(row.n_detecte):,} | {row.rappel_pct:.2f} | {row.couverture_donnees_commit * 100:.2f} |"
        for row in aidev_performance.itertuples()
    )
    agenticflict_v1 = external_report["v1"]["agenticflict"]
    agenticflict = external_report["v2"]["agenticflict"]
    test_coverage_v1 = external_report["v1"]["test_coverage_positifs"]
    test_coverage = external_report["v2"]["test_coverage_positifs"]
    test_coverage_humans = external_report["test_coverage_humains"]
    detector_lines = "\n".join(
        f"| {row.depot} | {int(row.detectees_v1):,} | {int(row.detectees_v2):,} | {int(row.gain_v2):+,} | {row.taux_v1_pct:.2f} | {row.taux_v2_pct:.2f} |"
        for row in detector_comparison.itertuples()
    )
    (OUTPUT / "RESULTATS.md").write_text(f"""# Resultats

## 1. Methode et perimetre

La synthese couvre six depots GitHub dans l'echantillon principal et deux depots exploratoires, du {START} au {END}. Les commits sont dates par date auteur et les pull requests par `created_at`. Les canaux commits et PR restent separes. Une attribution ne mesure que des signaux explicites et observables (compte d'agent, convention de branche, lien d'agent ou auto-declaration), pas la part de code ecrite par IA.

Trois depots ont une bascule d'adoption documentee : Microsoft VS Code (2024-11-28), Home Assistant Core (2025-02-19) et Next.js (2026-01-05). Godot et Redis sont des temoins sans bascule identifiee. Django est traite comme temoin : son fichier Copilot est classe `rejet`, pas adoption. osu! et Bun, analyses avant la constitution du manifeste final, sont reintegres comme cohorte exploratoire : ils enrichissent la description mais ne modifient pas les tests confirmatoires du plan principal.

## 2. Resultats descriptifs

Les resultats PR ci-dessous utilisent le detecteur V2; les commits conservent les regles existantes. L'echantillon principal contient {total_commits:,} commits, dont {total_commits_ia:,} attributions explicites ({total_commits_ia / total_commits * 100:.2f} %), et {total_prs:,} PR, dont {total_prs_ia:,} attributions explicites ({total_prs_ia / total_prs * 100:.2f} %). La cohorte exploratoire ajoute {int(exploratory['commits'].sum()):,} commits et {int(exploratory['prs'].sum()):,} PR.

| Depot | Echantillon | Groupe | Commits | Commits IA | Taux commits IA (%) | PR | PR IA | Taux PR IA (%) |
|---|---|---|---:|---:|---:|---:|---:|---:|
{rows}

### Comparaison des detecteurs PR

La V1 reste reproductible et les CSV bruts ne sont pas modifies. La V2 ajoute des URL de taches Cursor/Codex et des formulations d'auto-declaration strictes.

| Depot | Detectees V1 | Detectees V2 | Gain V2 | Taux V1 (%) | Taux V2 (%) |
|---|---:|---:|---:|---:|---:|
{detector_lines}

Le test d'integration V2 a traite {int(v2_validation['prs_testees']):,} PR dans les {int(v2_validation['nombre_depots_testes'])} depots. Son statut global est `{v2_validation['statut_global']}` : {int(v2_validation['detectees_v1']):,} detections V1 et {int(v2_validation['detectees_v2']):,} detections V2, soit {int(v2_validation['nouvelles_v2']):,} ajouts sans perte d'une detection V1. Le detail auditable se trouve dans `validation_v2_huit_depots.json`.

`evolution_trimestrielle_prs.png` contient une seule courbe globale. Pour chaque depot et chaque trimestre, un taux individuel est d'abord calcule : `PR attribuees a l'IA / toutes les PR du depot`. Le point global est ensuite la moyenne arithmetique des huit taux individuels. Chaque depot a donc le meme poids, quelle que soit sa quantite de PR. Ce choix correspond a une moyenne des comportements des depots; il ne faut pas le confondre avec le taux pondere `somme(PR IA) / somme(PR)`, dans lequel les plus gros depots domineraient.

Les groupes Adoption, Temoin et Exploratoire restent utiles pour definir le protocole et les tests, mais ne sont plus representes dans cette figure. La courbe mesure la frequence moyenne des attributions explicites, pas la performance du detecteur ni la proportion exacte de code produit par IA.

La baisse apparente de Bun apres 2025 ne permet pas de conclure a une baisse de son usage reel de l'IA. Elle correspond d'abord a la disparition de signaux explicites detectables : 124 PR identifiees par une convention de branche au deuxieme trimestre 2025, puis 53 auto-declarations Claude au quatrieme trimestre 2025, contre seulement 4 a 5 PR detectees par trimestre en 2026. Simultanement, le denominateur augmente fortement, d'environ 800-1 050 PR par trimestre en 2025 a 1 721, 2 466 et 2 494 PR lors des trois trimestres observes de 2026. Le taux passe donc de 15,57 % en 2025Q2 et 5,04 % en 2025Q4 a 0,23 %, 0,20 % et 0,16 % en 2026. Le dernier trimestre, 2026Q3, est en outre incomplet puisque la collecte s'arrete au 25 aout. L'interpretation defendable est une baisse des attributions explicites observees, possiblement liee a un changement d'outil, de convention de branche ou de pratique de declaration; les donnees ne permettent pas de choisir entre ces causes ni d'affirmer que l'usage non declare a diminue.

## 3. Comparaisons avant/apres

Les tests Mann-Whitney U sont appliques aux taux trimestriels, pas aux PR ou commits individuels. Le tableau ci-dessous est descriptif et inferentiel a la fois; les tres petites periodes post-bascule, notamment Next.js, limitent la puissance.

| Depot | Canal | Taux avant (%) | Taux apres (%) | p-value | Effet rang-biseriel | Trimestres avant | Trimestres apres |
|---|---|---:|---:|---:|---:|---:|---:|
{comparison_lines}

## 4. Interpretation et limites

### Validation externe avec AIDev

AIDev est un corpus de {int(aidev_report['n_reference']):,} PR positives deja associees a un agent. Le detecteur en retrouve {int(aidev_report['n_detecte']):,}, soit un rappel global de {float(aidev_report['rappel_global']) * 100:.2f} %. La precision n'est pas calculable sur ce corpus seul, faute de PR negatives certifiees.

| Outil | Positifs AIDev | Detectes | Rappel (%) | Couverture commits (%) |
|---|---:|---:|---:|---:|
{aidev_lines}

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

AgenticFlict et Test Coverage ont aussi ete evalues en reutilisant les metadonnees de PR d'AIDev comme cache hors ligne. Sur AgenticFlict, {int(agenticflict['hydratation']['n_hydrate']):,} des {int(agenticflict['hydratation']['n_reference']):,} PR ont pu etre hydratees : le rappel passe de {float(agenticflict_v1['rappel_global']) * 100:.2f} % en V1 a {float(agenticflict['rappel_global']) * 100:.2f} % en V2. Sur les groupes IA et co-auteur de Test Coverage, {int(test_coverage['hydratation']['n_hydrate']):,} des {int(test_coverage['hydratation']['n_reference']):,} PR ont ete hydratees : le rappel passe de {float(test_coverage_v1['rappel_global']) * 100:.2f} % a {float(test_coverage['rappel_global']) * 100:.2f} %.

Ces deux scores ne constituent pas des validations independantes d'AIDev : les corpus sont derives de sa population et les champs servant au detecteur proviennent de sa table. En outre, la table AIDev utilisee ne contient ni branche de PR ni identite de commit. Cela penalise surtout Cursor (34,71 % sur AgenticFlict et 4,08 % sur Test Coverage) et Codex (86,68 % et 65,65 %), dont une partie des signaux depend de ces champs. Parmi les {int(test_coverage_humans['n_reference']):,} PR humaines de Test Coverage, seules {int(test_coverage_humans['n_hydrate']):,} figurent dans AIDev; la precision ne peut donc pas etre calculee hors ligne sur ce groupe.

DevGPT eprouve un autre mode d'auto-declaration : les liens `chat.openai.com/share/...`. Le detecteur actuel ne traite pas ce lien generique comme une attribution. Toute extension de cette regle doit etre evaluee sur un jeu reserve ou par validation croisee afin d'eviter d'adapter puis de tester le detecteur sur les memes observations.

Les resultats decrivent la visibilite des attributions explicites, non l'usage reel de l'IA. L'absence de signal ne prouve donc pas l'absence d'utilisation. Les differences entre depots peuvent aussi refleter les politiques de contribution, les conventions de branche, la composition des comptes automatises et les pratiques de revue.

Les comparaisons avant/apres ne permettent pas a elles seules une inference causale : les bascules ne sont pas assignees aleatoirement et les changements temporels peuvent avoir d'autres causes. Les temoins servent a contextualiser les tendances, mais ne garantissent pas le parallelisme des trajectoires. Enfin, la precision ne peut pas etre deduite du corpus AIDev, qui est compose de cas positifs; la validation V2 disponible etablit un rappel global de {float(aidev_report['rappel_global']) * 100:.2f} %.
""", encoding="utf-8")


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    repository_summary, comparisons, quarterly = build_results()
    repository_summary.to_csv(OUTPUT / "synthese_par_depot.csv", index=False)
    comparisons.to_csv(OUTPUT / "comparaisons_avant_apres.csv", index=False)
    quarterly.to_csv(OUTPUT / "synthese_trimestrielle.csv", index=False)
    detector_comparison = build_detector_comparison()
    detector_comparison.to_csv(OUTPUT / "comparaison_detecteurs_v1_v2.csv", index=False)
    v2_validation = json.loads((OUTPUT / "validation_v2_huit_depots.json").read_text(encoding="utf-8"))
    plot_results(repository_summary, quarterly)
    aidev_performance, tool_composition, aidev_report = build_aidev_results()
    external_report = json.loads((ROOT / "data" / "processed" / "external_dataset_validation_report.json").read_text(encoding="utf-8"))
    aidev_performance.to_csv(OUTPUT / "performance_aidev.csv", index=False)
    tool_composition.to_csv(OUTPUT / "composition_outils_aidev_vs_depots.csv", index=False)
    plot_aidev(aidev_performance, tool_composition)
    export_v2_graphs(detector_comparison)
    write_note(
        repository_summary, comparisons, aidev_performance, aidev_report,
        external_report, detector_comparison, v2_validation,
    )
    (OUTPUT / "manifest_resultats.json").write_text(json.dumps({"start": START, "end": END, "repositories": REPOSITORIES}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()