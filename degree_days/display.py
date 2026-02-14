import pandas as pd
from rich.console import Console
from rich.table import Table

from .normals import normals_for_dates

console = Console()


def print_forecast_table(daily_df, normals_df=None):
    """
    Print a Rich table showing forecast HDD/CDD with normals comparison.
    daily_df: DataFrame with columns valid_date, HDD, CDD.
    normals_df: optional DataFrame with columns valid_date, normal_HDD, normal_CDD.
    """
    if normals_df is None:
        normals_df = normals_for_dates(daily_df['valid_date'].tolist())

    merged = daily_df.merge(normals_df, on='valid_date', how='left')

    table = Table(title="Degree Day Forecast vs. Normals (1991-2020)")
    table.add_column("Date", style="cyan")
    table.add_column("HDD", justify="right")
    table.add_column("Normal HDD", justify="right", style="dim")
    table.add_column("HDD Dep.", justify="right")
    table.add_column("CDD", justify="right")
    table.add_column("Normal CDD", justify="right", style="dim")
    table.add_column("CDD Dep.", justify="right")

    for _, row in merged.iterrows():
        hdd_dep = row['HDD'] - row.get('normal_HDD', 0)
        cdd_dep = row['CDD'] - row.get('normal_CDD', 0)

        hdd_dep_str = _format_departure(hdd_dep)
        cdd_dep_str = _format_departure(cdd_dep)

        table.add_row(
            row['valid_date'],
            f"{row['HDD']:.1f}",
            f"{row.get('normal_HDD', 0):.1f}",
            hdd_dep_str,
            f"{row['CDD']:.1f}",
            f"{row.get('normal_CDD', 0):.1f}",
            cdd_dep_str,
        )

    console.print(table)


def _format_departure(val):
    if val > 0.5:
        return f"[red]+{val:.1f}[/red]"
    elif val < -0.5:
        return f"[blue]{val:.1f}[/blue]"
    return f"{val:.1f}"


def print_trend_table(runs, model='gfs'):
    """
    Print a Rich table showing how forecasts have changed across recent model runs.
    runs: list of (run_date, run_hour, DataFrame) from ForecastCache.get_recent_runs().
    """
    if not runs:
        console.print("[yellow]No cached runs found.[/yellow]")
        return

    # Collect all valid_dates across runs
    all_dates = set()
    for _, _, df in runs:
        all_dates.update(df['valid_date'].tolist())
    all_dates = sorted(all_dates)

    table = Table(title=f"Forecast Trend — {model.upper()}")
    table.add_column("Date", style="cyan")
    for run_date, run_hour, _ in runs:
        table.add_column(f"{run_date} {run_hour:02d}z", justify="right")

    for vdate in all_dates:
        row_vals = [vdate]
        for _, _, df in runs:
            match = df[df['valid_date'] == vdate]
            if len(match) > 0:
                hdd = match.iloc[0]['HDD']
                cdd = match.iloc[0]['CDD']
                row_vals.append(f"H{hdd:.0f}/C{cdd:.0f}")
            else:
                row_vals.append("-")
        table.add_row(*row_vals)

    console.print(table)


def plot_forecast_vs_normals(daily_df, normals_df=None, save_path="forecast.png"):
    """Bar chart of forecast HDD/CDD with normal overlaid as lines."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    if normals_df is None:
        normals_df = normals_for_dates(daily_df['valid_date'].tolist())

    merged = daily_df.merge(normals_df, on='valid_date', how='left')
    dates = merged['valid_date']
    x = np.arange(len(dates))
    width = 0.35

    fig, ax = plt.subplots(figsize=(max(10, len(dates) * 0.6), 6))
    ax.bar(x - width / 2, merged['HDD'], width, label='Forecast HDD', color='steelblue')
    ax.bar(x + width / 2, merged['CDD'], width, label='Forecast CDD', color='coral')
    ax.plot(x, merged['normal_HDD'], 'b--', label='Normal HDD', linewidth=1.5)
    ax.plot(x, merged['normal_CDD'], 'r--', label='Normal CDD', linewidth=1.5)

    ax.set_xticks(x)
    ax.set_xticklabels(dates, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('Degree Days')
    ax.set_title('Forecast vs. 30-Year Normals')
    ax.legend()
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    console.print(f"Chart saved to [green]{save_path}[/green]")


def plot_trend(runs, target_date, save_path="trend.png"):
    """Line chart showing how a target date's forecast HDD/CDD changed across runs."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    labels = []
    hdds = []
    cdds = []
    for run_date, run_hour, df in reversed(runs):
        match = df[df['valid_date'] == target_date]
        if len(match) > 0:
            labels.append(f"{run_date}\n{run_hour:02d}z")
            hdds.append(match.iloc[0]['HDD'])
            cdds.append(match.iloc[0]['CDD'])

    if not labels:
        console.print(f"[yellow]No trend data found for {target_date}[/yellow]")
        return

    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 0.8), 5))
    x = range(len(labels))
    ax.plot(x, hdds, 'b-o', label='HDD')
    ax.plot(x, cdds, 'r-o', label='CDD')
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel('Degree Days')
    ax.set_title(f'Forecast Trend for {target_date}')
    ax.legend()
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    console.print(f"Trend chart saved to [green]{save_path}[/green]")
