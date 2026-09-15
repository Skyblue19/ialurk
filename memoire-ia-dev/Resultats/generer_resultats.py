"""Build cross-repository tables, figures, and a thesis-ready results note."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from memoire_ia_dev.prs import tag_prs


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUTPUT = Path(__file__).resolve().parent
START = "2020-06-01"
END = "2026-08-25"
QUARTERS = pd.period_range("2020Q2", "2026Q3", freq="Q").astype(str).tolist()
EVIDENCE_TYPES = ("structurelle", "convention_branche", "auto_declaration")
EVIDENCE_LABELS = {
    "structurelle": "Identité structurelle",
    "convention_branche": "Convention de branche",
    "auto_declaration": "Auto-déclaration",
}
EXPECTED_TOTALS = {"commits": 347_168, "commits_ia": 7_996, "prs": 246_767, "prs_ia": 3_412}

REPOSITORIES = {
    "microsoft/vscode": {"prefix": "microsoft_vscode"},
    "home-assistant/core": {"prefix": "home-assistant_core"},
    "vercel/next.js": {"prefix": "vercel_next.js"},
    "godotengine/godot": {"prefix": "godotengine_godot"},
    "redis/redis": {"prefix": "redis_redis"},
    "django/django": {"prefix": "django_django"},
    "ppy/osu": {"prefix": "osu", "commits_file": "osu_commits_2020_2026.csv", "prs_file": "osu_prs_2020_2026.csv"},
    "oven-sh/bun": {"prefix": "bun", "commits_file": "bun_commits_2020_2026.csv", "prs_file": "bun_prs_2020_2026.csv"},
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


def build_results() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
    repository_rows = []
    quarterly_rows = []
    channels: dict[str, list[pd.DataFrame]] = {"commits": [], "prs": []}
    for repository, metadata in REPOSITORIES.items():
        prefix = metadata["prefix"]
        commits = load_channel(RAW / metadata.get("commits_file", f"{prefix}_commits.csv"), "date", repository)
        prs = load_channel(
            RAW / metadata.get("prs_file", f"{prefix}_prs.csv"), "created_at", repository, "v2",
        )
        channels["commits"].append(commits)
        channels["prs"].append(prs)
        repository_rows.append({
            "depot": repository,
            "commits": len(commits),
            "commits_ia": int(commits["ai_attribue"].sum()),
            "taux_commits_ia_pct": rate(commits),
            "prs": len(prs),
            "prs_ia": int(prs["ai_attribue"].sum()),
            "taux_prs_ia_pct": rate(prs),
        })
        for quarter in QUARTERS:
            commit_quarter = commits.loc[commits["annee_trimestre"] == quarter]
            pr_quarter = prs.loc[prs["annee_trimestre"] == quarter]
            quarterly_rows.append({
                "depot": repository, "annee_trimestre": quarter,
                "commits": len(commit_quarter), "commits_ia": int(commit_quarter["ai_attribue"].sum()),
                "taux_commits_ia_pct": rate(commit_quarter), "prs": len(pr_quarter),
                "prs_ia": int(pr_quarter["ai_attribue"].sum()), "taux_prs_ia_pct": rate(pr_quarter),
            })
    return (
        pd.DataFrame(repository_rows),
        pd.DataFrame(quarterly_rows),
        {name: pd.concat(frames, ignore_index=True) for name, frames in channels.items()},
    )


def build_global_channel_evolution(quarterly: pd.DataFrame) -> pd.DataFrame:
    return quarterly.groupby("annee_trimestre", as_index=False).agg(
        taux_commits_ia_pct=("taux_commits_ia_pct", "mean"),
        taux_prs_ia_pct=("taux_prs_ia_pct", "mean"),
    )


def build_evidence_type_summary(channels: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    global_rows = []
    for channel, frame in channels.items():
        detected = frame.loc[frame["ai_attribue"]]
        assert detected["type_preuve"].notna().all(), f"Attribution {channel} sans type_preuve"
        unknown = set(detected["type_preuve"].unique()) - set(EVIDENCE_TYPES)
        assert not unknown, f"Types de preuve inconnus pour {channel}: {sorted(unknown)}"
        counts = detected["type_preuve"].value_counts()
        assert int(counts.sum()) == int(frame["ai_attribue"].sum())
        for evidence_type in EVIDENCE_TYPES:
            evidence_count = int(counts.get(evidence_type, 0))
            global_rows.append({
                "canal": channel,
                "type_preuve": evidence_type,
                "detections": evidence_count,
                "part_des_detections_pct": evidence_count / len(detected) * 100 if len(detected) else 0.0,
            })
        for repository in REPOSITORIES:
            repository_frame = frame.loc[frame["depot"] == repository]
            for quarter in QUARTERS:
                quarter_frame = repository_frame.loc[repository_frame["annee_trimestre"] == quarter]
                total = len(quarter_frame)
                for evidence_type in EVIDENCE_TYPES:
                    detections = int(
                        (quarter_frame["ai_attribue"] & quarter_frame["type_preuve"].eq(evidence_type)).sum()
                    )
                    rows.append({
                        "depot": repository,
                        "annee_trimestre": quarter,
                        "canal": channel,
                        "type_preuve": evidence_type,
                        "contributions_total": total,
                        "detections_type": detections,
                        "taux_type_pct": detections / total * 100 if total else 0.0,
                    })
    detail = pd.DataFrame(rows)
    global_summary = pd.DataFrame(global_rows)
    for channel, frame in channels.items():
        assert int(global_summary.loc[global_summary["canal"] == channel, "detections"].sum()) == int(frame["ai_attribue"].sum())
    return detail, global_summary


def build_bun_evidence_case(prs: pd.DataFrame) -> pd.DataFrame:
    bun = prs.loc[
        prs["depot"].eq("oven-sh/bun") & prs["annee_trimestre"].between("2025Q1", "2026Q3")
    ]
    rows = []
    for quarter in pd.period_range("2025Q1", "2026Q3", freq="Q").astype(str):
        quarter_frame = bun.loc[bun["annee_trimestre"] == quarter]
        row = {
            "annee_trimestre": quarter,
            "prs_total": len(quarter_frame),
            "prs_ia": int(quarter_frame["ai_attribue"].sum()),
            "taux_prs_ia_pct": rate(quarter_frame),
        }
        for evidence_type in EVIDENCE_TYPES:
            row[evidence_type] = int(
                (quarter_frame["ai_attribue"] & quarter_frame["type_preuve"].eq(evidence_type)).sum()
            )
        assert sum(row[evidence_type] for evidence_type in EVIDENCE_TYPES) == row["prs_ia"]
        rows.append(row)
    return pd.DataFrame(rows)


def _mark_incomplete_quarter(axes: list[plt.Axes]) -> None:
    for axis in axes:
        axis.axvspan(len(QUARTERS) - 1.45, len(QUARTERS) - 0.55, color="#f4a261", alpha=0.16)
        axis.text(
            len(QUARTERS) - 1, axis.get_ylim()[1] * 0.96, "Incomplet\nau 25 août",
            ha="center", va="top", fontsize=8, color="#9c4f18",
        )


def plot_repository_attribution(repository_summary: pd.DataFrame) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    figure, axis = plt.subplots(figsize=(10, 5))
    positions = range(len(repository_summary))
    axis.bar([position - 0.2 for position in positions], repository_summary["taux_commits_ia_pct"], width=0.4, label="Commits")
    axis.bar([position + 0.2 for position in positions], repository_summary["taux_prs_ia_pct"], width=0.4, label="Pull requests")
    axis.set_xticks(list(positions), repository_summary["depot"], rotation=25, ha="right")
    axis.set_ylabel("Attributions explicites IA (%)")
    axis.legend()
    figure.tight_layout()
    figure.savefig(OUTPUT / "attribution_par_depot.png", dpi=180)
    figure.savefig(OUTPUT / "taux_attribution_par_depot.png", dpi=180)
    plt.close(figure)


def plot_global_channel_evolution(evolution: pd.DataFrame) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, sharey=True)
    specifications = (
        ("taux_commits_ia_pct", "Commits", "#287271"),
        ("taux_prs_ia_pct", "Pull requests", "#e76f51"),
    )
    for axis, (column, title, color) in zip(axes, specifications):
        axis.plot(evolution["annee_trimestre"], evolution[column], marker="o", color=color, linewidth=2)
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_ylabel("Taux moyen (%)")
        axis.grid(axis="x", alpha=0.25)
    axes[-1].set_xlabel("Trimestre")
    axes[-1].tick_params(axis="x", rotation=45)
    _mark_incomplete_quarter(list(axes))
    figure.text(
        0.5, 0.015,
        "Moyenne arithmétique des taux des huit dépôts, avec un poids identique par dépôt.",
        ha="center", fontsize=9,
    )
    figure.suptitle("Évolution trimestrielle des attributions explicites à l’IA")
    figure.tight_layout(rect=(0, 0.045, 1, 0.97))
    figure.savefig(OUTPUT / "evolution_trimestrielle_commits_prs.png", dpi=180)
    plt.close(figure)


def plot_evidence_type_evolution(detail: pd.DataFrame, quarterly: pd.DataFrame) -> None:
    global_types = detail.groupby(["canal", "annee_trimestre", "type_preuve"], as_index=False).agg(
        taux_type_pct=("taux_type_pct", "mean")
    )
    global_rates = build_global_channel_evolution(quarterly).set_index("annee_trimestre")
    colors = {"structurelle": "#287271", "convention_branche": "#e9c46a", "auto_declaration": "#e76f51"}
    figure, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=True, sharey=True)
    for axis, channel, title, rate_column in (
        (axes[0], "commits", "Commits", "taux_commits_ia_pct"),
        (axes[1], "prs", "Pull requests", "taux_prs_ia_pct"),
    ):
        pivot = global_types.loc[global_types["canal"] == channel].pivot(
            index="annee_trimestre", columns="type_preuve", values="taux_type_pct"
        ).reindex(index=QUARTERS, columns=EVIDENCE_TYPES, fill_value=0.0)
        assert (pivot.sum(axis=1) - global_rates[rate_column]).abs().max() < 1e-9
        axis.stackplot(
            QUARTERS,
            *[pivot[evidence_type] for evidence_type in EVIDENCE_TYPES],
            labels=[EVIDENCE_LABELS[evidence_type] for evidence_type in EVIDENCE_TYPES],
            colors=[colors[evidence_type] for evidence_type in EVIDENCE_TYPES],
            alpha=0.9,
        )
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_ylabel("Contribution au taux moyen (%)")
    axes[0].legend(loc="upper left", ncols=3)
    axes[-1].set_xlabel("Trimestre")
    axes[-1].tick_params(axis="x", rotation=45)
    _mark_incomplete_quarter(list(axes))
    figure.suptitle("Évolution des attributions explicites par type de preuve")
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    figure.savefig(OUTPUT / "evolution_types_preuve.png", dpi=180)
    plt.close(figure)


def plot_bun_evidence_case(bun: pd.DataFrame) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    positions = list(range(len(bun)))
    bottoms = pd.Series(0, index=bun.index, dtype=float)
    colors = {"structurelle": "#287271", "convention_branche": "#e9c46a", "auto_declaration": "#e76f51"}
    for evidence_type in EVIDENCE_TYPES:
        axes[0].bar(
            positions, bun[evidence_type], bottom=bottoms,
            label=EVIDENCE_LABELS[evidence_type], color=colors[evidence_type],
        )
        bottoms += bun[evidence_type]
    axes[0].set_ylabel("PR détectées")
    axes[0].set_title("A. Nombre de PR par type de preuve", loc="left", fontweight="bold")
    axes[0].legend(ncols=3)
    bars = axes[1].bar(positions, bun["taux_prs_ia_pct"], color="#287271")
    axes[1].bar_label(
        bars,
        labels=[f"{row.prs_ia} / {row.prs_total} PR" for row in bun.itertuples()],
        padding=3, fontsize=8, rotation=90,
    )
    axes[1].set_ylabel("PR attribuées à l’IA (%)")
    axes[1].set_title("B. Taux parmi toutes les PR de Bun", loc="left", fontweight="bold")
    axes[1].set_xticks(positions, bun["annee_trimestre"], rotation=35, ha="right")
    axes[1].set_ylim(0, max(float(bun["taux_prs_ia_pct"].max()) * 1.3, 1.0))
    for axis in axes:
        axis.axvspan(len(bun) - 1.45, len(bun) - 0.55, color="#f4a261", alpha=0.16)
    figure.text(0.88, 0.02, "2026Q3 incomplet au 25 août", ha="right", fontsize=9, color="#9c4f18")
    figure.suptitle("Bun : évolution trimestrielle des traces explicites dans les pull requests")
    figure.tight_layout(rect=(0, 0.04, 1, 0.97))
    figure.savefig(OUTPUT / "bun_types_preuve_trimestriels.png", dpi=180)
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
        label=f"Rappel global : {global_recall:.2f} %".replace(".", ","),
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


def write_aidev_provenance(aidev_report: dict[str, object]) -> None:
    report_path = ROOT / "data" / "processed" / "aidev_full_report.json"
    provenance = {
        "dataset": "hao-li/AIDev",
        "configuration": "all_pull_request",
        "dataset_revision": None,
        "dataset_revision_note": "Aucun hash de revision verifiable dans les metadonnees locales.",
        "evaluation_report_modified_at_utc": datetime.fromtimestamp(
            report_path.stat().st_mtime, tz=timezone.utc
        ).isoformat(),
        "nombre_pr": int(aidev_report["n_reference"]),
        "categories": {
            row["outil_reference"]: int(row["n_reference"])
            for row in aidev_report["rappel_par_outil"]
        },
    }
    (OUTPUT / "provenance_aidev.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_note(
    repository_summary: pd.DataFrame,
    evolution: pd.DataFrame,
    evidence_global: pd.DataFrame,
    bun: pd.DataFrame,
    aidev_performance: pd.DataFrame,
    aidev_report: dict[str, object],
) -> None:
    total_commits = int(repository_summary["commits"].sum())
    total_prs = int(repository_summary["prs"].sum())
    total_commits_ia = int(repository_summary["commits_ia"].sum())
    total_prs_ia = int(repository_summary["prs_ia"].sum())
    rows = "\n".join(
        f"| {row.depot} | {int(row.commits):,} | {int(row.commits_ia):,} | {row.taux_commits_ia_pct:.2f} | {int(row.prs):,} | {int(row.prs_ia):,} | {row.taux_prs_ia_pct:.2f} |"
        for row in repository_summary.itertuples()
    )
    evidence_lines = "\n".join(
        f"| {'Commits' if row.canal == 'commits' else 'Pull requests'} | {EVIDENCE_LABELS[row.type_preuve]} | {int(row.detections):,} | {row.part_des_detections_pct:.2f} |"
        for row in evidence_global.itertuples()
    )
    bun_lines = "\n".join(
        f"| {row.annee_trimestre} | {int(row.prs_total):,} | {int(row.prs_ia):,} | {row.taux_prs_ia_pct:.2f} | {int(row.structurelle)} | {int(row.convention_branche)} | {int(row.auto_declaration)} |"
        for row in bun.itertuples()
    )
    aidev_lines = "\n".join(
        f"| {row.outil} | {int(row.n_reference):,} | {int(row.n_detecte):,} | {row.rappel_pct:.2f} | {row.couverture_donnees_commit * 100:.2f} |"
        for row in aidev_performance.itertuples()
    )
    (OUTPUT / "RESULTATS.md").write_text(f"""# Resultats

## 1. Perimetre

La synthese couvre huit depots GitHub du {START} au {END}. Le dernier trimestre, 2026Q3, est incomplet au 25 aout. Les commits sont dates par date auteur et les pull requests par `created_at`. Ces deux canaux restent separes.

Une attribution designe uniquement un signal explicite et observable dans les metadonnees Git ou GitHub : identite dediee, convention de branche ou auto-declaration. Elle ne mesure ni la part de code ecrite par IA, ni l'usage non declare d'un outil.

## 2. Resultats globaux par depot

Le corpus contient {total_commits:,} commits, dont {total_commits_ia:,} avec attribution explicite ({total_commits_ia / total_commits * 100:.2f} %), et {total_prs:,} pull requests, dont {total_prs_ia:,} avec attribution explicite ({total_prs_ia / total_prs * 100:.2f} %).

| Depot | Commits | Commits IA | Taux commits IA (%) | PR | PR IA | Taux PR IA (%) |
|---|---:|---:|---:|---:|---:|---:|
{rows}

Le graphique `attribution_par_depot.png` represente simultanement les taux des deux canaux pour chacun des huit depots.

## 3. Evolution temporelle commits / PR

Pour chaque depot et chaque trimestre, le taux correspond au nombre de contributions attribuees divise par le nombre total de contributions du meme canal. La courbe globale est ensuite la moyenne arithmetique des huit taux. Elle ne correspond donc pas au rapport entre les sommes globales, qui donnerait davantage de poids aux gros depots.

`evolution_trimestrielle_commits_prs.png` presente deux panneaux avec le meme axe temporel et la meme echelle verticale. Les valeurs correspondantes sont dans `evolution_globale_par_canal.csv`. 2026Q3 y est signale comme incomplet.

## 4. Repartition par type de preuve

Les detections sont reparties entre identites structurelles, conventions de branche et auto-declarations. Chaque contribution detectee appartient a une seule categorie, selon le premier signal retenu par le detecteur.

| Canal | Type de preuve | Detections | Part des detections (%) |
|---|---|---:|---:|
{evidence_lines}

`evolution_types_preuve.png` montre la contribution de chaque type au taux total, et non sa seule proportion parmi les detections. Les donnees detaillees figurent dans `types_preuve_trimestriels.csv` et les totaux dans `types_preuve_globaux.csv`.

## 5. Cas Bun

| Trimestre | PR totales | PR IA | Taux (%) | Structurelle | Convention de branche | Auto-declaration |
|---|---:|---:|---:|---:|---:|---:|
{bun_lines}

`bun_types_preuve_trimestriels.png` montre que l'evolution du taux depend a la fois du nombre de traces detectees, de leur nature et du volume total de PR. Une baisse du taux observe ne suffit pas a conclure a une baisse de l'usage reel de l'IA.

## 6. Validation AIDev

AIDev contient {int(aidev_report['n_reference']):,} PR positives deja associees a un agent. Le detecteur final en retrouve {int(aidev_report['n_detecte']):,}, soit un rappel global de {float(aidev_report['rappel_global']) * 100:.2f} %. La precision n'est pas calculable sur ce corpus seul, faute de PR negatives certifiees.

| Outil | Positifs AIDev | Detectes | Rappel (%) | Couverture commits (%) |
|---|---:|---:|---:|---:|
{aidev_lines}

Les six categories du tableau proviennent de la configuration `all_pull_request` du corpus AIDev. Elles ne constituent pas la liste exhaustive des outils reconnus par le detecteur. Selon le canal, celui-ci contient aussi des regles pour Aider, Replit, Codegen, Terragon ou Wildcard. La provenance locale disponible est enregistree dans `provenance_aidev.json`; aucun hash de revision n'a ete trouve dans les metadonnees locales.

## 7. Limites d'interpretation

Les resultats decrivent la visibilite des attributions explicites, pas l'usage reel de l'IA. L'absence de signal ne prouve pas l'absence d'utilisation. Les differences entre depots peuvent provenir des politiques de contribution, des conventions de branche, des outils ou des pratiques de declaration. La moyenne non ponderee donne le meme poids aux huit depots et doit etre lue comme une moyenne de projets, pas comme un taux global pondere par le nombre de contributions. Enfin, AIDev mesure le rappel sur des cas positifs mais ne permet pas d'estimer la precision du detecteur.
""", encoding="utf-8")


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    repository_summary, quarterly, channels = build_results()
    totals = {
        "commits": int(repository_summary["commits"].sum()),
        "commits_ia": int(repository_summary["commits_ia"].sum()),
        "prs": int(repository_summary["prs"].sum()),
        "prs_ia": int(repository_summary["prs_ia"].sum()),
    }
    assert totals == EXPECTED_TOTALS, f"Divergence des totaux: attendus={EXPECTED_TOTALS}, obtenus={totals}"
    repository_summary.to_csv(OUTPUT / "synthese_par_depot.csv", index=False)
    quarterly.to_csv(OUTPUT / "synthese_trimestrielle.csv", index=False)
    evolution = build_global_channel_evolution(quarterly)
    evolution.to_csv(OUTPUT / "evolution_globale_par_canal.csv", index=False)
    evidence_detail, evidence_global = build_evidence_type_summary(channels)
    evidence_detail.to_csv(OUTPUT / "types_preuve_trimestriels.csv", index=False)
    evidence_global.to_csv(OUTPUT / "types_preuve_globaux.csv", index=False)
    bun = build_bun_evidence_case(channels["prs"])
    bun.to_csv(OUTPUT / "bun_types_preuve_trimestriels.csv", index=False)
    bun_tool_detail = (
        channels["prs"].loc[
            channels["prs"]["depot"].eq("oven-sh/bun")
            & channels["prs"]["ai_attribue"]
            & channels["prs"]["annee_trimestre"].between("2025Q1", "2026Q3")
        ]
        .groupby(["annee_trimestre", "type_preuve", "outil"], as_index=False)
        .size()
    )
    plot_repository_attribution(repository_summary)
    plot_global_channel_evolution(evolution)
    plot_evidence_type_evolution(evidence_detail, quarterly)
    plot_bun_evidence_case(bun)
    aidev_performance, tool_composition, aidev_report = build_aidev_results()
    aidev_performance.to_csv(OUTPUT / "performance_aidev.csv", index=False)
    tool_composition.to_csv(OUTPUT / "composition_outils_aidev_vs_depots.csv", index=False)
    plot_aidev(aidev_performance, tool_composition)
    write_aidev_provenance(aidev_report)
    write_note(repository_summary, evolution, evidence_global, bun, aidev_performance, aidev_report)
    (OUTPUT / "manifest_resultats.json").write_text(json.dumps({"start": START, "end": END, "repositories": REPOSITORIES}, indent=2), encoding="utf-8")
    print("Totaux verifies:", totals)
    print("\nDetections par type de preuve:")
    print(evidence_global.to_string(index=False))
    print("\nBun 2025Q1 -> 2026Q3:")
    print(bun.to_string(index=False))
    print("\nDetail Bun par type de preuve et outil:")
    print(bun_tool_detail.to_string(index=False))
    print("\nPNG generes:")
    for name in (
        "attribution_par_depot.png", "taux_attribution_par_depot.png",
        "evolution_trimestrielle_commits_prs.png", "evolution_types_preuve.png",
        "bun_types_preuve_trimestriels.png", "performance_aidev_par_outil.png",
        "composition_outils_aidev_vs_depots.png",
    ):
        print(OUTPUT / name)
    print("\nCSV generes:")
    for name in (
        "synthese_par_depot.csv", "synthese_trimestrielle.csv",
        "evolution_globale_par_canal.csv", "types_preuve_trimestriels.csv",
        "types_preuve_globaux.csv", "bun_types_preuve_trimestriels.csv",
        "performance_aidev.csv", "composition_outils_aidev_vs_depots.csv",
    ):
        print(OUTPUT / name)


if __name__ == "__main__":
    main()