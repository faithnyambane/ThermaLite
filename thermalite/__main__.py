"""ThermaLite command line.

  python3 -m thermalite [match] [--sources S.csv --sinks K.csv --out out/ --climate]
  python3 -m thermalite sources --state NJ        # data centers from the IM3 atlas
  python3 -m thermalite sinks --state NJ          # heat users from OpenStreetMap
  python3 -m thermalite sensitivity [--sources ... --sinks ...]
  python3 -m thermalite greenhouses --state NJ [--bbox W,S,E,N]   # NAIP detector
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report
from .data import load_sinks, load_sources
from .matcher import assign, match_all, summarize


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--sources", default="data/example/sources.csv")
    p.add_argument("--sinks", default="data/example/sinks.csv")
    p.add_argument("--out", default="out")
    p.add_argument("--climate", action="store_true",
                   help="use real heating degree days per sink (ERA5-Land via Earth Engine)")
    p.add_argument("--ee-project", default="thermalite", help="Earth Engine Cloud project ID")


def _load(args):
    sources, sinks = load_sources(args.sources), load_sinks(args.sinks)
    if args.climate:
        from .climate import apply_climate
        sinks = apply_climate(sinks, project=args.ee_project)
        print(f"Seasonality: ERA5-Land heating degree days for {len(sinks)} sinks\n")
    else:
        print("Seasonality: illustrative built-in curve (use --climate for real data)\n")
    return sources, sinks


def cmd_match(args) -> None:
    sources, sinks = _load(args)
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


def cmd_sources(args) -> None:
    from .atlas import to_sources_csv
    out = Path(args.out or f"data/{args.state.lower()}/sources.csv")
    print(to_sources_csv([args.state], out), "->", out)


def cmd_sinks(args) -> None:
    from .osm import to_sinks_csv
    out = Path(args.out or f"data/{args.state.lower()}/sinks.csv")
    print(to_sinks_csv(args.state, out), "->", out)


def cmd_sensitivity(args) -> None:
    from . import sensitivity
    from .sensitivity_report import write_html
    sources, sinks = _load(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    prices = sensitivity.price_grid(sources, sinks)
    incentive = sensitivity.incentive_curve(sources, sinks)
    sensitivity.write(prices, out / "sensitivity_prices.csv")
    sensitivity.write(incentive, out / "sensitivity_incentive.csv")
    subtitle = f"{len(sources)} data centers and {len(sinks)} heat users from {args.sources} and {args.sinks}."
    write_html(prices, incentive, subtitle, out / "sensitivity.html")
    print("Incentive ($/MWh) -> viable pairs, MWh/yr reused")
    for r in incentive:
        print(f"  ${r['incentive_per_mwh']:>4}: {r['viable_pairs']:>4} pairs, {r['heat_reused_mwh']:>12,} MWh/yr")
    print(f"\nWrote {out / 'sensitivity.html'} and CSVs")


def cmd_greenhouses(args) -> None:
    from . import greenhouse
    osm_cache = Path(f"data/raw/osm_{args.state.lower()}_greenhouse.json")
    if not osm_cache.exists():
        raise SystemExit(f"{osm_cache} missing; run `python3 -m thermalite sinks --state {args.state}` first")
    if args.bbox:
        bbox = [float(x) for x in args.bbox.split(",")]
        out = Path(args.out or f"data/{args.state.lower()}/greenhouses_detected.csv")
        res = greenhouse.detect(bbox, osm_cache, out, project=args.ee_project)
        print(f"Wrote {out}")
    else:
        res = greenhouse.train(osm_cache, project=args.ee_project)
        res.pop("_clf"), res.pop("_gh")
    for k, v in res.items():
        print(f"  {k}: {v}")


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv.insert(0, "match")
    p = argparse.ArgumentParser(prog="thermalite", description="Match data center waste heat to nearby heat users.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("match", cmd_match), ("sensitivity", cmd_sensitivity)):
        sp = sub.add_parser(name)
        _common(sp)
        sp.set_defaults(fn=fn)
    for name, fn in (("sources", cmd_sources), ("sinks", cmd_sinks)):
        sp = sub.add_parser(name)
        sp.add_argument("--state", required=True, help="two-letter state code, e.g. NJ")
        sp.add_argument("--out", default=None)
        sp.set_defaults(fn=fn)
    sp = sub.add_parser("greenhouses", help="train/run the NAIP greenhouse detector (Earth Engine)")
    sp.add_argument("--state", required=True)
    sp.add_argument("--bbox", help="west,south,east,north to map candidates; omit to only train + validate")
    sp.add_argument("--out", default=None)
    sp.add_argument("--ee-project", default="thermalite")
    sp.set_defaults(fn=cmd_greenhouses)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
