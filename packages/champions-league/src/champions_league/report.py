import base64
from html import escape
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import PowerNorm
import numpy as np


def display_name(team, names):
    return names.get(team, team.title())


def plot_standings(result, names, path):
    p = result.probabilities
    order = result.summary.sort_values("expected_position", kind="stable").index
    p = p.loc[order]
    fig, ax = plt.subplots(figsize=(23, 16.5))
    fig.patch.set_facecolor("white")
    image = ax.imshow(p.to_numpy(), cmap="YlGnBu", norm=PowerNorm(0.4, vmin=0, vmax=100), aspect="auto")
    ax.set_xticks(np.arange(36), np.arange(1, 37), fontsize=10)
    labels = [f"{display_name(team, names)}   {result.summary.loc[team, 'expected_points']:.1f} pts" for team in order]
    ax.set_yticks(np.arange(36), labels, fontsize=10)
    ax.xaxis.tick_top()
    ax.xaxis.set_label_position("top")
    ax.set_xlabel("Final league-phase position", fontsize=13, labelpad=14)
    for row in range(36):
        for col in range(36):
            value = p.iloc[row, col]
            ax.text(col, row, f"{value:.2f}", ha="center", va="center", fontsize=7.2,
                    color="white" if value > 18 else "#16324a")
    for boundary in (7.5, 23.5):
        ax.axvline(boundary, color="#e69126", linewidth=2)
    ax.set_xticks(np.arange(-0.5, 36, 1), minor=True)
    ax.set_yticks(np.arange(-0.5, 36, 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.5, alpha=0.6)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.tick_params(axis="both", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    season = result.metadata["season"]
    origin = result.metadata["as_of"][:16].replace("T", " ")
    fig.suptitle(f"Champions League {season}/{str(season + 1)[-2:]} · league-phase forecast", x=0.035, y=0.985,
                 ha="left", fontsize=23, fontweight="bold", color="#10263e")
    fig.text(0.035, 0.953, f"As of {origin} UTC · {result.metadata['n_sim']:,} simulations · cells show probability (%) · points are expected final points",
             fontsize=12, color="#526579")
    fig.text(0.035, 0.022, "1–8: direct to round of 16     9–24: knockout playoffs     25–36: eliminated     •     Conditional on fitted strengths; no odds by default.",
             fontsize=12, color="#526579")
    bar = fig.colorbar(image, ax=ax, orientation="horizontal", pad=0.035, fraction=0.025, aspect=70,
                       ticks=[0, 0.1, 0.5, 1, 2, 5, 10, 25, 50, 100])
    bar.ax.set_xticklabels(["0", "0.1", "0.5", "1", "2", "5", "10", "25", "50", "100%"])
    bar.outline.set_visible(False)
    fig.subplots_adjust(left=0.23, right=0.985, top=0.88, bottom=0.075)
    fig.savefig(path, dpi=160, facecolor="white")
    plt.close(fig)


def plot_bracket(result, names, path):
    bracket = result.bracket
    stages = bracket["stages"]
    stages = list(stages.items()) if isinstance(stages, dict) else [(s["stage"], s["ties"]) for s in stages]
    titles = {"PLAYOFFS": "Knockout playoffs", "PLAYOFF": "Knockout playoffs", "LAST_16": "Round of 16",
              "ROUND_OF_16": "Round of 16", "QUARTER_FINALS": "Quarter-finals",
              "SEMI_FINALS": "Semi-finals", "FINAL": "Final", "playoffs": "Knockout playoffs",
              "round16": "Round of 16", "quarterfinal": "Quarter-finals", "semifinal": "Semi-finals", "final": "Final"}
    fig, ax = plt.subplots(figsize=(16.54, 8.27))
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 6)
    ax.set_ylim(-0.2, 8.2)
    ax.axis("off")
    previous_ys = None
    for stage_index, (stage, ties) in enumerate(stages):
        x = stage_index
        if previous_ys is None:
            ys = np.linspace(7.5, 0.5, len(ties))
            rows = [(y + 0.14, y - 0.14) for y in ys]
        elif len(ties) == len(previous_ys):
            rows = [(y + 0.28, y) for y in previous_ys]
        else:
            rows = list(zip(previous_ys[::2], previous_ys[1::2]))
        ys = [np.mean(pair) for pair in rows]
        ax.text(x + 0.02, 8.05, titles.get(stage, stage.replace("_", " ").title()), fontsize=10)
        for tie, (top, bottom), y in zip(ties, rows, ys):
            for team, row in ((tie["team1"], top), (tie["team2"], bottom)):
                ax.text(x + 0.02, row + 0.035, display_name(team, names), fontsize=9,
                        fontweight="bold" if team == tie["winner"] else "normal", va="bottom")
                if tie.get("observed"):
                    chance = "W" if team == tie["winner"] else ""
                else:
                    pct = tie["advance_probability"]
                    chance = f"{pct if team == tie['winner'] else 100 - pct:.2f}%"
                ax.text(x + 0.94, row + 0.035, chance, fontsize=8, ha="right", va="bottom")
                ax.plot([x, x + 0.98], [row, row], color="black", lw=0.6)
            ax.plot([x + 0.98, x + 0.98], [top, bottom], color="black", lw=0.6)
            ax.plot([x + 0.98, x + 1], [y, y], color="black", lw=0.6)
        previous_ys = ys
    x = len(stages)
    ax.text(x + 0.02, 8.05, "Winner", fontsize=10)
    ax.text(x + 0.02, previous_ys[0] + 0.035, display_name(bracket["champion"], names),
            fontsize=9, fontweight="bold", va="bottom")
    ax.plot([x, x + 0.98], [previous_ys[0]] * 2, color="black", lw=0.6)
    season = result.metadata["season"]
    fig.text(0.035, 0.96, f"Champions League {season}/{str(season + 1)[-2:]} - Projected knockout draw", fontsize=13, fontweight="bold")
    origin = result.metadata["as_of"][:16].replace("T", " ")
    fig.text(0.975, 0.96, f"As of {origin} UTC", fontsize=9, ha="right")
    note = "Hypothetical pairings. Bold: projected winner. %: chance to advance in this pairing."
    if any(tie.get("observed") for _, ties in stages for tie in ties):
        note += " W: observed winner."
    fig.text(0.035, 0.035, note, fontsize=8)
    fig.subplots_adjust(left=0.035, right=0.975, top=0.9, bottom=0.08)
    path = Path(path)
    fig.savefig(path, dpi=160, facecolor="white")
    fig.savefig(path.with_suffix(".pdf"), facecolor="white", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def write_report(result, inputs, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    names = inputs.metadata.get("display_names", {})
    result.probabilities.rename(index=lambda t: display_name(t, names)).to_csv(out_dir / "cl_position_probs.csv", float_format="%.4f")
    shown = result.summary.sort_values("expected_position").rename(index=lambda t: display_name(t, names))
    shown.to_csv(out_dir / "cl_summary.csv", float_format="%.4f")
    (out_dir / "cl_forecast.json").write_text(json.dumps({
        "position_probabilities_pct": result.probabilities.to_dict(orient="index"),
        "summary": result.summary.to_dict(orient="index"), "bracket": result.bracket,
        "metadata": result.metadata,
    }, indent=2, default=str) + "\n")
    (out_dir / "cl_metadata.json").write_text(json.dumps(result.metadata, indent=2, default=str) + "\n")
    (out_dir / "cl_bracket.json").write_text(json.dumps(result.bracket, indent=2, default=str) + "\n")
    plot_standings(result, names, out_dir / "cl_position_probs.png")
    plot_bracket(result, names, out_dir / "cl_bracket.png")
    labels = {"expected_position": "Exp. position", "expected_points": "Exp. points", "top8_pct": "Top 8 %",
              "playoffs_pct": "Enter playoffs %", "eliminated_pct": "League elimination %", "round16_pct": "Reach R16 %",
              "quarterfinal_pct": "Reach QF %", "semifinal_pct": "Reach SF %", "final_pct": "Reach final %", "title_pct": "Win UCL %",
              "prior_title_min_pct": "Prior check min %", "prior_title_max_pct": "Prior check max %"}
    table = shown[[c for c in labels if c in shown]].rename(columns=labels).to_html(float_format=lambda v: f"{v:.2f}", border=0)
    coverage_columns = ["team", "league", "current_domestic_matches", "prior_domestic_matches", "european_matches",
                        "xg_matches", "latest_domestic_result", "stale_days", "domestic_missing"]
    coverage = inputs.coverage[coverage_columns].assign(team=lambda frame: frame.team.map(lambda t: display_name(t, names)))
    coverage = coverage.to_html(index=False, border=0, float_format=lambda v: f"{v:.2f}")
    favorite = result.summary["title_pct"].idxmax()
    pct = result.summary.loc[favorite, "title_pct"]
    def embedded(filename):
        return "data:image/png;base64," + base64.b64encode((out_dir / filename).read_bytes()).decode()
    content = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Champions League forecast</title><style>
body{{margin:0;background:#f5f8fc;color:#10263e;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1600px;margin:0 auto;padding:40px 24px}}h1{{font-size:36px;letter-spacing:-1px}}h2{{margin-top:40px}}p{{max-width:1100px;color:#526579}}.favorite{{color:#0a664c;font-size:23px;font-weight:650}}img{{display:block;width:100%;background:white}}.scroll{{overflow:auto;background:white;border:1px solid #d8e3ef;border-radius:8px}}table{{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}}td,th{{text-align:right;padding:9px 12px;border-bottom:1px solid #e5edf5}}td:first-child,th:first-child{{text-align:left}}thead{{background:#edf3fa}}a{{color:#126b9b}}details{{margin-top:24px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}.note{{font-size:14px}}
</style></head><body><main><h1>Champions League {result.metadata['season']}/{str(result.metadata['season'] + 1)[-2:]} forecast</h1>
<p>As of {escape(result.metadata['as_of'])} · {result.metadata['n_sim']:,} simulations · fixed calibration {escape(str(result.metadata['weight_calibration_version']))}</p>
<p class="favorite">Title favorite: {escape(display_name(favorite, names))} · {pct:.2f}%</p>
<h2>League-phase standings</h2><p>Expected final points and probability of each position. The top eight bypass playoffs; positions 9–24 enter playoffs.</p>
<a href="cl_position_probs.csv">Download position probabilities</a><img src="{embedded('cl_position_probs.png')}" alt="36-team league-phase position probability heatmap">
<h2>Projected knockout bracket</h2><p>{escape(result.bracket.get('draw_label', 'Illustrative draw; future pairings are unknown.'))}</p>
<a href="cl_bracket.pdf">Download bracket (PDF)</a>
<img src="{embedded('cl_bracket.png')}" alt="Projected playoff and knockout bracket through the final">
<h2>Qualification and title probabilities</h2><p>Entering the playoffs and reaching the round of 16 are separate events. Percentages describe all simulated paths; bracket matchup percentages condition on one pairing. Prior checks vary league-strength shrinkage (1, 4 and 16), including Monte Carlo noise; their range is a sensitivity check, not a confidence interval.</p>
<a href="cl_summary.csv">Download summary</a><div class="scroll">{table}</div>
<h2>Data coverage</h2><p>Counts and latest results show the evidence available at the forecast origin. Stale sources and sparse international links increase uncertainty.</p>
<div class="scroll">{coverage}</div><p class="note">{escape(result.metadata['uncertainty'])} Extra time uses one third of venue-correct 90-minute rates; shootouts are 50/50. Unmodeled disciplinary tiebreaks use a seeded random fallback. Relocated nominal home venues are treated as neutral where flagged.</p>
<details><summary>Provenance, rule versions and model diagnostics</summary><pre>{escape(json.dumps(result.metadata, indent=2, default=str))}</pre></details>
</main></body></html>'''
    (out_dir / "cl_forecast.html").write_text(content, encoding="utf-8")
