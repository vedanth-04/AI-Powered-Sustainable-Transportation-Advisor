"""Command-line pipeline to extract and save ground-truth travel-time labels."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from src.config import DEFAULT_RAW_DB, PROCESSED_DATA_DIR
from src.data.cleaner import CleaningAuditLog, clean_trajectory_data
from src.data.loader import load_corridor_observations
from src.features.label_generation import (
    LabelGenerationSummary,
    extract_segment_traversals,
)
from src.features.segment_config import (
    SEGMENT_MB_EASTBOUND,
    SEGMENT_MB_WESTBOUND,
    SEGMENT_ORR_EASTBOUND,
    SEGMENT_ORR_WESTBOUND,
    RoadSegment,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def generate_all_corridor_labels(
    raw_db_path: Path = DEFAULT_RAW_DB,
    output_dir: Path = PROCESSED_DATA_DIR,
) -> pd.DataFrame:
    """Run end-to-end trajectory cleaning and traversal extraction across corridors."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "traversals.csv"

    # Define segments to process
    target_segments = [
        SEGMENT_ORR_EASTBOUND,
        SEGMENT_ORR_WESTBOUND,
        SEGMENT_MB_EASTBOUND,
        SEGMENT_MB_WESTBOUND,
    ]

    all_traversals: list[pd.DataFrame] = []

    print("=" * 75)
    print("END-TO-END SEGMENT TRAVEL-TIME LABEL GENERATION PIPELINE")
    print(f"Source Database: {raw_db_path}")
    print(f"Target Output:   {out_file}")
    print("=" * 75)

    for seg in target_segments:
        print(f"\n>>> Processing Corridor: {seg.corridor_name} | Segment: {seg.segment_id} ({seg.direction})")
        print(f"    Envelope: Lat {seg.bounding_lat_range}, Lng {seg.bounding_lng_range}")
        print(f"    Primary Routes: {seg.primary_routes}")

        # 1. Load observations
        raw_df = load_corridor_observations(
            routes=seg.primary_routes,
            lat_range=seg.bounding_lat_range,
            lng_range=seg.bounding_lng_range,
            db_path=raw_db_path,
        )
        print(f"    Loaded raw observations: {len(raw_df):,}")

        # 2. Clean and segment trajectories
        cleaning_audit = CleaningAuditLog()
        clean_df = clean_trajectory_data(raw_df, log_audit=cleaning_audit)
        print(f"    Cleaning Summary: {cleaning_audit.clean_rows_retained:,} rows retained "
              f"({cleaning_audit.duplicate_rows_dropped:,} duplicates dropped, "
              f"{cleaning_audit.gps_jumps_rejected:,} jumps removed, "
              f"{cleaning_audit.subtrips_generated:,} subtrips generated across "
              f"{cleaning_audit.unique_vehicles:,} buses)")

        # 3. Extract traversals
        gen_summary = LabelGenerationSummary()
        traversals_df = extract_segment_traversals(clean_df, segment=seg, summary=gen_summary)
        print(f"    Extraction Summary: {gen_summary.valid_traversals_generated:,} valid traversals generated "
              f"(Entries: {gen_summary.entry_crossings_detected:,}, "
              f"Exits: {gen_summary.exit_crossings_detected:,}, "
              f"Rejected no exit: {gen_summary.rejected_no_exit:,}, "
              f"Rejected gap: {gen_summary.rejected_internal_gap:,}, "
              f"Rejected duration: {gen_summary.rejected_duration_bounds:,})")

        if not traversals_df.empty:
            mean_tt = traversals_df["travel_time_minutes"].mean()
            median_tt = traversals_df["travel_time_minutes"].median()
            std_tt = traversals_df["travel_time_minutes"].std()
            print(f"    Travel Time Stats: Mean = {mean_tt:.2f} min, Median = {median_tt:.2f} min, "
                  f"Std = {std_tt:.2f} min, Range = [{traversals_df['travel_time_minutes'].min():.2f}, "
                  f"{traversals_df['travel_time_minutes'].max():.2f}]")
            all_traversals.append(traversals_df)

    if not all_traversals:
        print("\n[WARNING] No traversals generated!")
        return pd.DataFrame()

    combined_df = pd.concat(all_traversals, ignore_index=True)
    combined_df = combined_df.sort_values("t_entry").reset_index(drop=True)
    combined_df.to_csv(out_file, index=False)

    print("\n" + "=" * 75)
    print("PIPELINE COMPLETE")
    print(f"Total Combined Valid Traversals: {len(combined_df):,}")
    print(f"Unique Buses Represented:        {combined_df['vehicle_id'].nunique():,}")
    print(f"Routes Represented:              {combined_df['route_id'].unique().tolist()}")
    print(f"Segments Represented:            {combined_df['segment_id'].unique().tolist()}")
    print(f"Saved dataset to:                {out_file}")
    print("=" * 75)

    return combined_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate segment travel-time ground-truth labels.")
    parser.add_argument("--db-path", type=str, default=str(DEFAULT_RAW_DB), help="Path to raw SQLite database.")
    parser.add_argument("--output-dir", type=str, default=str(PROCESSED_DATA_DIR), help="Output directory.")
    args = parser.parse_args()

    generate_all_corridor_labels(raw_db_path=Path(args.db_path), output_dir=Path(args.output_dir))
