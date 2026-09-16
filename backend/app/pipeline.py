"""Orchestrates the full ingest -> resolve -> graph -> analytics pipeline,
end to end, timing each stage for the self-evaluation dashboard."""
import time
import json
from datetime import datetime, timezone

from app.config import PIPELINE_TIMINGS_PATH
from app.data_generation.generator import generate
from app.extraction.extractor import run_extraction
from app.resolution.resolver import run_resolution
from app.graph.exclusion import run_exclusion
from app.graph.builder import build_edges
from app.auth.rbac import seed_case_assignments
from app.db.schema import get_connection
from app.audit.chain import append_entry


def run_full_pipeline(reset_data: bool = True) -> dict:
    timings = {}
    run_started = time.time()

    t0 = time.time()
    gen_stats = generate(reset=reset_data)
    timings["data_generation"] = round(time.time() - t0, 4)

    t0 = time.time()
    extraction_stats = run_extraction()
    timings["entity_extraction"] = round(time.time() - t0, 4)

    t0 = time.time()
    resolution_stats = run_resolution()
    timings["entity_resolution"] = round(time.time() - t0, 4)

    t0 = time.time()
    exclusion_stats = run_exclusion()
    timings["role_utility_exclusion"] = round(time.time() - t0, 4)

    t0 = time.time()
    edge_stats = build_edges()
    timings["graph_construction"] = round(time.time() - t0, 4)

    seed_case_assignments()
    timings["total"] = round(time.time() - run_started, 4)

    conn = get_connection()
    append_entry(conn, actor="system", action="PIPELINE_RUN", reason="full ingest pipeline executed",
                 extra={"timings": timings})
    conn.close()

    result = {
        "timings_seconds": timings,
        "record_counts": {
            "fir_records": gen_stats["fir_records"],
            "cdr_records": gen_stats["cdr_records"],
            "transaction_records": gen_stats["transaction_records"],
            "mentions_extracted": extraction_stats["mentions_extracted"],
            "entities_created": resolution_stats["entities_created"],
            "review_clusters": resolution_stats["review_clusters"],
            "graph_edges": edge_stats["edges_created"],
        },
        "run_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_generation": gen_stats,
        "extraction": extraction_stats,
        "resolution": resolution_stats,
        "exclusion": exclusion_stats,
        "graph": edge_stats,
    }

    # Persisted separately from the audit chain (which can be legitimately
    # cleared/reset) so the self-evaluation dashboard always has the most
    # recent run's stage timings to show, computed from an actual run --
    # never hard-coded.
    with open(PIPELINE_TIMINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result


if __name__ == "__main__":
    print(json.dumps(run_full_pipeline(), indent=2))
