import base64
from html import escape
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import PowerNorm
from matplotlib.patches import FancyBboxPatch
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
    fig, ax = plt.subplots(figsize=(25, 13))
    fig.patch.set_facecolor("#f5f8fc")
    ax.set_xlim(-0.25, 5.88)
    ax.set_ylim(-0.8, 8.6)
    ax.axis("off")
    x_step, card_w, card_h = 1.16, 1.01, 0.66
    previous_ys = None
    for stage_index, (stage, ties) in enumerate(stages):
        x = stage_index * x_step
        count = len(ties)
        ys = np.linspace(7.5, 0.5, 8) if count == 8 else np.array([7.0, 5.0, 3.0, 1.0]) if count == 4 else np.array([6.0, 2.0]) if count == 2 else np.array([4.0])
        ax.text(x, 8.25, titles.get(stage, stage.replace("_", " ").title()), color="#526579", fontsize=13, fontweight="bold")
        if previous_ys is not None:
            for index, prev_y in enumerate(previous_ys):
                next_y = ys[index if len(previous_ys) == len(ys) else index // 2]
                mid = x - 0.075
                ax.plot([x - x_step + card_w, mid, mid, x], [prev_y, prev_y, next_y, next_y], color="#b8c8da", lw=1.3, zorder=1)
        for tie, y in zip(ties, ys):
            winner = tie["winner"]
            box = FancyBboxPatch((x, y - card_h / 2), card_w, card_h, boxstyle="round,pad=0.012,rounding_size=0.035",
                                 facecolor="white", edgecolor="#d8e3ef", linewidth=1, zorder=2)
            ax.add_patch(box)
            for team, offset in ((tie["team1"], 0.16), (tie["team2"], -0.015)):
                name = display_name(team, names)
                if len(name) > 27:
                    name = name[:26] + "…"
                ax.text(x + 0.045, y + offset, name, fontsize=10.6,
                        fontweight="bold" if team == winner else "normal", color="#0a664c" if team == winner else "#526579", zorder=3)
            pct = tie.get("advance_probability")
            detail = f"Winner advances: {pct:.2f}%" if pct is not None else "Observed winner"
            ax.text(x + 0.045, y - 0.23, detail, fontsize=8.1, color="#718297", zorder=3)
        previous_ys = ys
    favorite = result.summary["title_pct"].idxmax()
    favorite_pct = result.summary.loc[favorite, "title_pct"]
    champion = bracket["champion"]
    ax.text(4.64, 2.9, "PROJECTED BRACKET WINNER", color="#526579", fontsize=10, fontweight="bold")
    ax.text(4.64, 2.57, display_name(champion, names), color="#0a664c", fontsize=17, fontweight="bold")
    ax.text(0, -0.35, "Bold teams advance in this illustrative path. Matchup percentages condition on that pairing; title odds average all simulated paths.",
            fontsize=11, color="#526579")
    fig.suptitle("Champions League · projected knockout path", x=0.035, y=0.98, ha="left", fontsize=24,
                 fontweight="bold", color="#10263e")
    fig.text(0.035, 0.925, f"Overall title favorite: {display_name(favorite, names)} · {favorite_pct:.2f}% to win the tournament", fontsize=15, color="#0a664c")
    fig.text(0.035, 0.89, bracket.get("draw_label", "Illustrative permitted draw from projected league-phase ranks; the real draw is not yet known."), fontsize=11, color="#526579")
    fig.subplots_adjust(left=0.035, right=0.985, top=0.86, bottom=0.045)
    fig.savefig(path, dpi=160, facecolor=fig.get_facecolor())
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
<img src="{embedded('cl_bracket.png')}" alt="Projected playoff and knockout bracket through the final">
<h2>Qualification and title probabilities</h2><p>Entering the playoffs and reaching the round of 16 are separate events. Percentages describe all simulated paths; bracket matchup percentages condition on one pairing. Prior checks vary league-strength shrinkage (1, 4 and 16), including Monte Carlo noise; their range is a sensitivity check, not a confidence interval.</p>
<a href="cl_summary.csv">Download summary</a><div class="scroll">{table}</div>
<h2>Data coverage</h2><p>Counts and latest results show the evidence available at the forecast origin. Stale sources and sparse international links increase uncertainty.</p>
<div class="scroll">{coverage}</div><p class="note">{escape(result.metadata['uncertainty'])} Extra time uses one third of venue-correct 90-minute rates; shootouts are 50/50. Unmodeled disciplinary tiebreaks use a seeded random fallback. Relocated nominal home venues are treated as neutral where flagged.</p>
<details><summary>Provenance, rule versions and model diagnostics</summary><pre>{escape(json.dumps(result.metadata, indent=2, default=str))}</pre></details>
</main></body></html>'''
    (out_dir / "cl_forecast.html").write_text(content, encoding="utf-8")
