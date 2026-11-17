"""CLI: python3 -m thermalite --sources S.csv --sinks K.csv --out out/"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import report
from .data import load_sinks, load_sources
from .matcher import assign, match_all, summarize


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="thermalite", description="Match data center waste heat to nearby heat users.")
    p.add_argument("--sources", default="data/example/sources.csv")
    p.add_argument("--sinks", default="data/example/sinks.csv")
    p.add_argument("--out", default="out")
    p.add_argument("--climate", action="store_true",
                   help="use real heating degree days per sink (ERA5-Land via Earth Engine)")
    p.add_argument("--ee-project", default="thermalite", help="Earth Engine Cloud project ID")
    args = p.parse_args(argv)

    sources, sinks = load_sources(args.sources), load_sinks(args.sinks)
    if args.climate:
        from .climate import apply_climate
        sinks = apply_climate(sinks, project=args.ee_project)
        print(f"Seasonality: ERA5-Land heating degree days for {len(sinks)} sinks\n")
    else:
        print("Seasonality: illustrative built-in curve (use --climate for real data)\n")
    matches = match_all(sources, sinks)
    chosen = assign(matches)
    text = report.summary_text(summarize(sources, chosen))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report.write_csv(matches, out / "matches.csv")
    report.write_map(sources, sinks, chosen, text, out / "map.html")

    print(text)
    print("\nViable pairings:")
    for m in chosen:
        print(f"  {m.source.name} -> {m.sink.name}: {m.route_km:.1f} km, "
              f"{m.heat_used_mwh:,.0f} MWh/yr, ~{m.homes_equivalent:,.0f} homes, net ${m.net_annual_usd:,.0f}/yr")
    rejected = [m for m in matches if not m.feasible]
    if rejected:
        print(f"\n{len(rejected)} pairs rejected; reasons are in {out / 'matches.csv'}")
    print(f"\nWrote {out / 'matches.csv'} and {out / 'map.html'}")


if __name__ == "__main__":
    main()
