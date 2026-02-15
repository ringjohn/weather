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
    Print two Rich tables (HDD and CDD) showing how forecasts have changed
    across recent model runs.
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

    run_headers = [f"{rd} {rh:02d}z" for rd, rh, _ in runs]

    for metric in ('HDD', 'CDD'):
        table = Table(title=f"{metric} Trend — {model.upper()}")
        table.add_column("Date", style="cyan")
        for hdr in run_headers:
            table.add_column(hdr, justify="right")

        for vdate in all_dates:
            row_vals = [vdate]
            for _, _, df in runs:
                match = df[df['valid_date'] == vdate]
                if len(match) > 0:
                    val = match.iloc[0][metric]
                    row_vals.append(f"{val:.1f}")
                else:
                    row_vals.append("-")
            table.add_row(*row_vals)

        console.print(table)
        console.print()


def plot_forecast_vs_normals(daily_df, normals_df=None, save_path="forecast.png", run_label=None):
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
    title = 'Forecast vs. 30-Year Normals'
    if run_label:
        title += f' — {run_label}'
    ax.set_title(title)
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


def print_model_comparison_table(model_runs, reference_runs=None):
    """
    Print HDD and CDD tables with dates as rows and models as columns.
    model_runs: list of (model_name, run_date, run_hour, DataFrame).
    Each DataFrame has columns: valid_date, HDD, CDD.
    """
    if not model_runs:
        console.print("[yellow]No model runs to compare.[/yellow]")
        return

    # Collect all valid_dates
    all_dates = set()
    for _, _, _, df in model_runs:
        all_dates.update(df['valid_date'].tolist())
    all_dates = sorted(all_dates)

    # Get normals for these dates
    normals_df = normals_for_dates(all_dates)
    normals_map = {}
    for _, row in normals_df.iterrows():
        normals_map[row['valid_date']] = (row['normal_HDD'], row['normal_CDD'])

    # Build column headers: "MODEL\nDD-MMM HHz"
    headers = []
    for model, rd, rh, _ in model_runs:
        headers.append(f"{model.upper()}\n{rd[5:]} {rh:02d}z")

    normal_metric_key = {'HDD': 'normal_HDD', 'CDD': 'normal_CDD'}

    for metric in ('HDD', 'CDD'):
        table = Table(title=f"{metric} Departure from Normal")
        table.add_column("Date", style="cyan", no_wrap=True)
        table.add_column("Normal", justify="right", style="dim")
        for hdr in headers:
            table.add_column(hdr, justify="right")

        norm_idx = 0 if metric == 'HDD' else 1
        # Track column sums for summary row
        col_sums = [0.0] * len(model_runs)
        col_counts = [0] * len(model_runs)

        for vdate in all_dates:
            short_date = pd.Timestamp(vdate).strftime('%b %d')
            norm_val = normals_map.get(vdate, (None, None))[norm_idx]
            norm_str = f"{norm_val:.1f}" if norm_val is not None else "-"
            row_vals = [short_date, norm_str]
            for i, (_, _, _, df) in enumerate(model_runs):
                match = df[df['valid_date'] == vdate]
                if len(match) > 0 and norm_val is not None:
                    dep = match.iloc[0][metric] - norm_val
                    col_sums[i] += dep
                    col_counts[i] += 1
                    row_vals.append(_format_departure(dep))
                else:
                    row_vals.append("-")
            table.add_row(*row_vals)

        # Summary row
        table.add_section()
        sum_row = ["Total", ""]
        for i in range(len(model_runs)):
            if col_counts[i] > 0:
                sum_row.append(_format_departure(col_sums[i]))
            else:
                sum_row.append("-")
        table.add_row(*sum_row, style="bold")

        console.print(table)
        console.print()

    # HDD change vs reference (e.g. Friday 12z)
    if reference_runs:
        # Build a lookup: model -> {vdate: HDD}
        ref_map = {}
        ref_label = None
        for model, rd, rh, df in reference_runs:
            ref_label = ref_label or f"{rd[5:]} {rh:02d}z"
            ref_map[model] = {}
            for _, row in df.iterrows():
                ref_map[model][row['valid_date']] = row['HDD']

        table = Table(title=f"HDD Change since {ref_label}")
        table.add_column("Date", style="cyan", no_wrap=True)
        for hdr in headers:
            table.add_column(hdr, justify="right")

        col_sums = [0.0] * len(model_runs)
        col_counts = [0] * len(model_runs)

        for vdate in all_dates:
            short_date = pd.Timestamp(vdate).strftime('%b %d')
            row_vals = [short_date]
            for i, (model, _, _, df) in enumerate(model_runs):
                match = df[df['valid_date'] == vdate]
                ref_hdd = ref_map.get(model, {}).get(vdate)
                if len(match) > 0 and ref_hdd is not None:
                    chg = match.iloc[0]['HDD'] - ref_hdd
                    col_sums[i] += chg
                    col_counts[i] += 1
                    row_vals.append(_format_departure(chg))
                else:
                    row_vals.append("-")
            table.add_row(*row_vals)

        table.add_section()
        sum_row = ["Total"]
        for i in range(len(model_runs)):
            if col_counts[i] > 0:
                sum_row.append(_format_departure(col_sums[i]))
            else:
                sum_row.append("-")
        table.add_row(*sum_row, style="bold")

        console.print(table)
        console.print()


def _compute_changes(current_df, compare_df):
    """Merge two forecast DataFrames and compute HDD/CDD changes."""
    merged = current_df.merge(
        compare_df, on='valid_date', how='inner', suffixes=('_cur', '_cmp')
    )
    merged['HDD_change'] = merged['HDD_cur'] - merged['HDD_cmp']
    merged['CDD_change'] = merged['CDD_cur'] - merged['CDD_cmp']
    return merged


def print_changes_table(current_df, compare_df, current_label, compare_label):
    """Rich table showing HDD/CDD changes between two forecast runs."""
    merged = _compute_changes(current_df, compare_df)
    if merged.empty:
        console.print("[yellow]No overlapping dates to compare.[/yellow]")
        return

    table = Table(title=f"Forecast Changes: {current_label} vs {compare_label}")
    table.add_column("Date", style="cyan")
    table.add_column("HDD Change", justify="right")
    table.add_column("CDD Change", justify="right")
    table.add_column("Net Effect", justify="right")

    for _, row in merged.iterrows():
        hdd_chg = row['HDD_change']
        cdd_chg = row['CDD_change']
        # Positive CDD change or negative HDD change = warmer
        net = cdd_chg - hdd_chg
        table.add_row(
            row['valid_date'],
            _format_departure(hdd_chg),
            _format_departure(cdd_chg),
            _format_departure(net),
        )

    console.print(table)


def plot_changes(current_df, compare_df, current_label, compare_label, save_path="changes.png"):
    """Bar chart showing HDD/CDD changes between two forecast runs."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    merged = _compute_changes(current_df, compare_df)
    if merged.empty:
        console.print("[yellow]No overlapping dates to chart.[/yellow]")
        return

    dates = merged['valid_date']
    x = np.arange(len(dates))
    width = 0.35

    fig, ax = plt.subplots(figsize=(max(10, len(dates) * 0.6), 6))
    ax.bar(x - width / 2, merged['HDD_change'], width, label='HDD Change', color='steelblue')
    ax.bar(x + width / 2, merged['CDD_change'], width, label='CDD Change', color='coral')
    ax.axhline(y=0, color='black', linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(dates, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel('Degree Day Change')
    ax.set_title(f'Forecast Changes: {current_label} vs {compare_label}')
    ax.legend()
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    console.print(f"Changes chart saved to [green]{save_path}[/green]")
