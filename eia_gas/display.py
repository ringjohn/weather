"""Rich tables and matplotlib charts for gas storage analysis."""

import pandas as pd
from rich.console import Console
from rich.table import Table

console = Console()


def print_regression_summary(coefficients):
    """Print current OLS regression coefficients."""
    table = Table(title="Gas Flow Regression (Rolling 3-Year OLS)")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Training period",
                  f"{coefficients['start_date']} to {coefficients['end_date']}")
    table.add_row("N observations", str(coefficients['n_obs']))
    table.add_row("Beta HDD", f"{coefficients['beta_hdd']:+.3f} Bcf/HDD")
    table.add_row("Beta CDD", f"{coefficients['beta_cdd']:+.3f} Bcf/CDD")
    table.add_row("Intercept", f"{coefficients['intercept']:+.2f} Bcf")
    table.add_row("R-squared", f"{coefficients['r_squared']:.4f}")

    console.print(table)
    console.print()


def print_gas_forecast_table(forecast_df, latest_storage):
    """Print weekly gas flow forecast."""
    table = Table(title=f"Gas Storage Forecast (from {latest_storage:.0f} Bcf)")
    table.add_column("Week End", style="cyan", no_wrap=True)
    table.add_column("Days", justify="right", style="dim")
    table.add_column("HDD", justify="right")
    table.add_column("CDD", justify="right")
    table.add_column("Flow (Bcf)", justify="right")
    table.add_column("Storage (Bcf)", justify="right")

    for _, row in forecast_df.iterrows():
        short_date = pd.Timestamp(row['week_end_date']).strftime('%b %d')
        flow = row['implied_flow_bcf']
        flow_style = "[red]" if flow < 0 else "[green]"
        flow_str = f"{flow_style}{flow:+.0f}[/{flow_style[1:]}"

        days_str = str(int(row['days_in_week']))
        if row['days_in_week'] < 7:
            days_str = f"[yellow]{days_str}*[/yellow]"

        table.add_row(
            short_date,
            days_str,
            f"{row['forecast_HDD']:.0f}",
            f"{row['forecast_CDD']:.0f}",
            flow_str,
            f"{row['forecast_storage_bcf']:.0f}",
        )

    console.print(table)
    console.print()


def print_storage_history(storage_df, n=10):
    """Print recent storage history."""
    table = Table(title=f"Recent EIA Storage Reports (last {n} weeks)")
    table.add_column("Week End", style="cyan")
    table.add_column("Storage (Bcf)", justify="right")
    table.add_column("Flow (Bcf)", justify="right")

    recent = storage_df.tail(n)
    for _, row in recent.iterrows():
        flow = row.get('implied_flow')
        if flow is not None and not pd.isna(flow):
            flow_style = "[red]" if flow < 0 else "[green]"
            flow_str = f"{flow_style}{flow:+.0f}[/{flow_style[1:]}"
        else:
            flow_str = "-"

        table.add_row(
            row['period'],
            f"{row['storage_bcf']:.0f}",
            flow_str,
        )

    console.print(table)
    console.print()


def plot_regression_fit(rolling_df, save_path="gas_regression.png"):
    """Plot rolling regression coefficients and R² over time."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    if rolling_df.empty:
        console.print("[yellow]No rolling regression data to plot.[/yellow]")
        return

    dates = pd.to_datetime(rolling_df['week_end_date'])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

    ax1.plot(dates, rolling_df['beta_hdd'], 'b-', label='Beta HDD', linewidth=1)
    ax1.plot(dates, rolling_df['beta_cdd'], 'r-', label='Beta CDD', linewidth=1)
    ax1.axhline(y=0, color='black', linewidth=0.5)
    ax1.set_ylabel('Coefficient (Bcf / weekly DD)')
    ax1.set_title('Rolling 3-Year Regression Coefficients')
    ax1.legend()

    ax2.plot(dates, rolling_df['r_squared'], 'g-', linewidth=1)
    ax2.set_ylabel('R-squared')
    ax2.set_xlabel('Date')
    ax2.set_title('Rolling 3-Year R-squared')
    ax2.set_ylim(0, 1)

    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    console.print(f"Regression chart saved to [green]{save_path}[/green]")


def plot_storage_forecast(actual_df, forecast_df, save_path="gas_forecast.png"):
    """Line chart: actual storage + forecast extension."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 6))

    # Actual storage (last 52 weeks)
    recent = actual_df.tail(52)
    actual_dates = pd.to_datetime(recent['period'])
    ax.plot(actual_dates, recent['storage_bcf'], 'b-', label='Actual', linewidth=1.5)

    # Forecast
    if not forecast_df.empty:
        fcst_dates = pd.to_datetime(forecast_df['week_end_date'])
        ax.plot(fcst_dates, forecast_df['forecast_storage_bcf'], 'r--',
                label='Forecast', linewidth=1.5)

    ax.set_ylabel('Storage (Bcf)')
    ax.set_title('Natural Gas Working Storage — Actual + Forecast')
    ax.legend()
    fig.tight_layout()
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    console.print(f"Storage forecast chart saved to [green]{save_path}[/green]")
