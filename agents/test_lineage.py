"""
Test script for Lineage Analyzer (Task 13b-1).

Verifies:
- Correct downstream models and depths for all three staging models
- Dashboard mapping
- impact_tree_text renders correctly
- Nonexistent model returns empty list gracefully

Usage:
    python3 agents/test_lineage.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.lineage_analyzer import (
    build_dependency_graph,
    get_downstream_models,
    get_impact_summary,
    load_manifest,
)

PASS = "PASS"
FAIL = "FAIL"


def check(label: str, condition: bool) -> bool:
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}")
    return condition


def test_downstream_models():
    manifest = load_manifest()
    graph = build_dependency_graph(manifest)

    print("\n--- get_downstream_models ---")

    # stg_weather_sf
    models = get_downstream_models(graph, "stg_weather_sf", manifest)
    names = {m["name"] for m in models}
    check("stg_weather_sf: int_hourly_weather_transit present", "int_hourly_weather_transit" in names)
    check("stg_weather_sf: int_daily_weather_incidents present", "int_daily_weather_incidents" in names)
    check("stg_weather_sf: fact_weather_transit_hourly present", "fact_weather_transit_hourly" in names)
    check("stg_weather_sf: fact_daily_city_summary present", "fact_daily_city_summary" in names)
    check("stg_weather_sf: total 4 downstream", len(models) == 4)

    # Check depths
    depth_map = {m["name"]: m["depth"] for m in models}
    check("stg_weather_sf: int_hourly at depth 1", depth_map.get("int_hourly_weather_transit") == 1)
    check("stg_weather_sf: fact_weather_transit at depth 2", depth_map.get("fact_weather_transit_hourly") == 2)

    # stg_transit_sf
    models = get_downstream_models(graph, "stg_transit_sf", manifest)
    names = {m["name"] for m in models}
    check("stg_transit_sf: fact_transit_performance present", "fact_transit_performance" in names)
    check("stg_transit_sf: int_hourly_weather_transit present", "int_hourly_weather_transit" in names)
    check("stg_transit_sf: fact_weather_transit_hourly present", "fact_weather_transit_hourly" in names)
    check("stg_transit_sf: fact_daily_city_summary present", "fact_daily_city_summary" in names)
    check("stg_transit_sf: total 6 downstream", len(models) == 6)

    # fact_daily_city_summary appears only once (deduplication)
    count = sum(1 for m in models if m["name"] == "fact_daily_city_summary")
    check("stg_transit_sf: fact_daily_city_summary deduplicated (count=1)", count == 1)

    # stg_incidents_sf
    models = get_downstream_models(graph, "stg_incidents_sf", manifest)
    names = {m["name"] for m in models}
    check("stg_incidents_sf: fact_incident_trends present", "fact_incident_trends" in names)
    check("stg_incidents_sf: dim_neighborhood present", "dim_neighborhood" in names)
    check("stg_incidents_sf: int_daily_weather_incidents present", "int_daily_weather_incidents" in names)
    check("stg_incidents_sf: fact_daily_city_summary present", "fact_daily_city_summary" in names)
    check("stg_incidents_sf: total 4 downstream", len(models) == 4)

    # Edge case — nonexistent model
    result = get_downstream_models(graph, "nonexistent_model", manifest)
    check("nonexistent model: returns empty list", result == [])
    check("nonexistent model: no crash", True)


def test_impact_summary():
    print("\n--- get_impact_summary ---")

    summary = get_impact_summary("stg_weather_sf")
    check("source_model is stg_weather_sf", summary["source_model"] == "stg_weather_sf")
    check("total_affected is 4", summary["total_affected"] == 4)
    check("City Intelligence in affected_dashboards", "City Intelligence" in summary["affected_dashboards"])
    check("impact_tree_text contains BROKEN", "(BROKEN)" in summary["impact_tree_text"])
    check("impact_tree_text contains tree connectors", "├──" in summary["impact_tree_text"] or "└──" in summary["impact_tree_text"])
    check("impact_tree_text contains Affected dashboards line", "Affected dashboards" in summary["impact_tree_text"])

    summary = get_impact_summary("stg_transit_sf")
    check("stg_transit_sf total_affected is 6", summary["total_affected"] == 6)

    summary = get_impact_summary("stg_incidents_sf")
    check("stg_incidents_sf total_affected is 4", summary["total_affected"] == 4)

    # Nonexistent model
    summary = get_impact_summary("nonexistent_model")
    check("nonexistent model: total_affected is 0", summary["total_affected"] == 0)
    check("nonexistent model: downstream_models is []", summary["downstream_models"] == [])
    check("nonexistent model: no crash", True)


def print_trees():
    print("\n--- Impact trees ---")
    for source in ["stg_weather_sf", "stg_transit_sf", "stg_incidents_sf"]:
        summary = get_impact_summary(source)
        print(f"\n{summary['impact_tree_text']}")


def main():
    print("=" * 60)
    print("Lineage Analyzer — Test Suite")
    print("=" * 60)

    test_downstream_models()
    test_impact_summary()
    print_trees()

    print("\n" + "=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()
