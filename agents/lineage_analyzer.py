"""
Lineage Analyzer — Task 13b-1

Parses dbt's manifest.json, builds the dependency graph, and returns the full
downstream impact tree for any model. Used by the repair engine in 13b-4.

No LLM calls, no BigQuery writes — pure Python + file I/O.

Standalone usage:
    python3 agents/test_lineage.py
Import usage:
    from agents.lineage_analyzer import get_impact_summary
"""

import json
import logging
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)

# Project root — two levels up from agents/
_PROJECT_ROOT = Path(__file__).parent.parent

# Which warehouse tables feed which dashboards.
# Agent Monitor reads from agents.* tables (not dbt models) — not listed here.
DASHBOARD_MAP = {
    "fact_weather_transit_hourly": ["City Intelligence"],
    "fact_daily_city_summary":     ["City Intelligence"],
    "fact_transit_performance":    ["City Intelligence"],
    "fact_incident_trends":        ["City Intelligence"],
    "dim_date":                    ["City Intelligence"],
    "dim_route":                   ["City Intelligence"],
    "dim_stop":                    ["City Intelligence"],
    "dim_neighborhood":            ["City Intelligence"],
}


# =============================================================================
# Manifest loading
# =============================================================================

def load_manifest(manifest_path: str = None) -> dict:
    """
    Load and return the parsed dbt manifest.json.

    Args:
        manifest_path: Optional override. Defaults to dbt/target/manifest.json
                       resolved from the project root.

    Returns:
        Parsed manifest dict.

    Raises:
        FileNotFoundError: If manifest doesn't exist, with instructions to
                           generate it via `dbt ls` or `dbt run`.
    """
    if manifest_path:
        path = Path(manifest_path)
    else:
        path = _PROJECT_ROOT / "dbt" / "target" / "manifest.json"

    if not path.exists():
        raise FileNotFoundError(
            f"dbt manifest not found at {path}.\n"
            "Generate it by running one of:\n"
            "  dbt ls        (fastest — no BigQuery queries)\n"
            "  dbt run       (full build)\n"
            "inside the dbt/ directory or Airflow container."
        )

    with open(path) as f:
        return json.load(f)


# =============================================================================
# Graph construction
# =============================================================================

def build_dependency_graph(manifest: dict) -> dict:
    """
    Build upstream and downstream dependency graphs from the manifest.

    Filters to resource_type == "model" only. Sources, tests, and snapshots
    are excluded.

    Args:
        manifest: Parsed manifest dict from load_manifest().

    Returns:
        {
          "upstream":   {unique_id: [list of unique_ids it depends on]},
          "downstream": {unique_id: [list of unique_ids that depend on it]}
        }
        Both dicts contain every model node as a key, even nodes with no
        dependencies (empty list value).
    """
    nodes = {
        uid: node
        for uid, node in manifest["nodes"].items()
        if node["resource_type"] == "model"
    }

    upstream = {}
    downstream = {}

    # Initialise every model with empty lists so lookups never KeyError
    for uid in nodes:
        upstream[uid] = []
        downstream[uid] = []

    # Populate upstream from depends_on.nodes, and invert to build downstream.
    # depends_on may reference source nodes (not models) — only include edges
    # where both ends are models.
    for uid, node in nodes.items():
        for dep_uid in node["depends_on"]["nodes"]:
            if dep_uid in nodes:
                upstream[uid].append(dep_uid)
                downstream[dep_uid].append(uid)

    return {"upstream": upstream, "downstream": downstream}


# =============================================================================
# Downstream traversal
# =============================================================================

def get_downstream_models(graph: dict, model_name: str, manifest: dict) -> list[dict]:
    """
    Return all models downstream of model_name, ordered by depth.

    Uses BFS so nodes are visited level by level. A node's depth is set on
    first visit (shallowest path) and never updated.

    Args:
        graph:       Built by build_dependency_graph().
        model_name:  Short name e.g. "stg_weather_sf" (not the full unique_id).
        manifest:    Parsed manifest — needed to resolve name → unique_id
                     and to read file_path / materialization metadata.

    Returns:
        List of dicts, sorted by depth ascending (direct dependents first).
        Empty list if model_name not found in manifest.
    """
    project_name = manifest["metadata"]["project_name"]
    uid = f"model.{project_name}.{model_name}"

    if uid not in graph["downstream"]:
        logger.warning("Model '%s' not found in dependency graph", model_name)
        return []

    visited = set()
    queue = deque()
    results = []

    # Seed the queue with direct dependents at depth 1
    for child_uid in graph["downstream"][uid]:
        if child_uid not in visited:
            visited.add(child_uid)
            queue.append((child_uid, 1))

    while queue:
        current_uid, depth = queue.popleft()
        node = manifest["nodes"][current_uid]

        results.append({
            "unique_id":    current_uid,
            "name":         node["name"],
            "file_path":    node["original_file_path"],
            "materialized": node["config"]["materialized"],
            "schema":       node["config"]["schema"],
            "depth":        depth,
        })

        # Enqueue children not yet visited
        for child_uid in graph["downstream"].get(current_uid, []):
            if child_uid not in visited:
                visited.add(child_uid)
                queue.append((child_uid, depth + 1))

    return sorted(results, key=lambda x: x["depth"])


# =============================================================================
# Impact summary + tree rendering
# =============================================================================

def _render_tree(model_name: str, downstream_models: list[dict], graph: dict, manifest: dict) -> str:
    """
    Render a human-readable dependency tree for display.

    Uses the downstream graph to reconstruct parent-child relationships so
    ├── vs └── connectors are placed correctly.

    Args:
        model_name:        Short name of the broken source model.
        downstream_models: List from get_downstream_models().
        graph:             Built by build_dependency_graph().
        manifest:          Parsed manifest — for unique_id resolution.

    Returns:
        Multi-line string with tree connectors.
    """
    if not downstream_models:
        return f"{model_name} (BROKEN)\n  (no downstream models affected)"

    project_name = manifest["metadata"]["project_name"]
    root_uid = f"model.{project_name}.{model_name}"

    # Build a set of all affected unique_ids for quick membership checks
    affected_uids = {m["unique_id"] for m in downstream_models}

    # Build parent → children mapping restricted to affected nodes
    children_of = {}
    for m in downstream_models:
        uid = m["unique_id"]
        affected_children = [
            c for c in graph["downstream"].get(uid, [])
            if c in affected_uids
        ]
        children_of[uid] = affected_children

    # Direct children of the root
    root_children = [
        c for c in graph["downstream"].get(root_uid, [])
        if c in affected_uids
    ]
    children_of[root_uid] = root_children

    # Build name lookup
    name_of = {m["unique_id"]: m["name"] for m in downstream_models}
    mat_of  = {m["unique_id"]: m["materialized"] for m in downstream_models}

    lines = [f"{model_name} (BROKEN)"]

    def _render_children(parent_uid: str, prefix: str) -> None:
        kids = children_of.get(parent_uid, [])
        for i, child_uid in enumerate(kids):
            is_last = (i == len(kids) - 1)
            connector = "└── " if is_last else "├── "
            child_name = name_of[child_uid]
            child_mat  = mat_of[child_uid]
            lines.append(f"{prefix}{connector}{child_name} [{child_mat}]")
            # Continuation prefix: blank under last child, │ under others
            extension = "    " if is_last else "│   "
            _render_children(child_uid, prefix + extension)

    _render_children(root_uid, " ")
    return "\n".join(lines)


def get_impact_summary(model_name: str, manifest_path: str = None) -> dict:
    """
    Main entry point for impact analysis. Called by the repair engine.

    Loads the manifest, builds the graph, finds all downstream models,
    maps them to affected dashboards, and renders a readable impact tree.

    Args:
        model_name:    Short model name e.g. "stg_weather_sf".
        manifest_path: Optional override for manifest location.

    Returns:
        {
          "source_model":       str,
          "downstream_models":  list[dict],   # from get_downstream_models
          "total_affected":     int,
          "affected_dashboards": list[str],
          "impact_tree_text":   str           # human-readable tree
        }
    """
    manifest = load_manifest(manifest_path)
    graph    = build_dependency_graph(manifest)
    downstream = get_downstream_models(graph, model_name, manifest)

    # Collect affected dashboards — deduplicated, preserving first-seen order
    seen_dashboards = []
    for m in downstream:
        for dashboard in DASHBOARD_MAP.get(m["name"], []):
            if dashboard not in seen_dashboards:
                seen_dashboards.append(dashboard)

    tree_text = _render_tree(model_name, downstream, graph, manifest)

    # Append dashboard line to tree text
    if seen_dashboards:
        tree_text += f"\n Affected dashboards: {', '.join(seen_dashboards)}"

    return {
        "source_model":        model_name,
        "downstream_models":   downstream,
        "total_affected":      len(downstream),
        "affected_dashboards": seen_dashboards,
        "impact_tree_text":    tree_text,
    }
