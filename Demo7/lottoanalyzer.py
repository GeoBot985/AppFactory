"""
lottoanalyzer.py

Purpose:
    Analyze historical lottery draw data within stable game-rule eras and test
    whether observed draws behave consistently with a simple random model.

Expected input files in the same folder as this script:
    - lootohist.csv
    - powerballhist.csv

Run:
    python lottoanalyzer.py
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
LOTTO_FILE = SCRIPT_DIR / "lootohist.csv"
POWERBALL_FILE = SCRIPT_DIR / "powerballhist.csv"
OUTPUT_DIR = SCRIPT_DIR / "output"

SIMULATION_RUNS = 3000
RNG_SEED = 42


@dataclass
class ParsedDraw:
    row_index: int
    draw_date: pd.Timestamp
    main_numbers: list[int]
    bonus_number: int
    raw_results: str
    raw_numbers: list[int]

    @property
    def year(self) -> int:
        return int(self.draw_date.year)


@dataclass
class DatasetContext:
    name: str
    file_path: Path
    draws_raw: pd.DataFrame
    parsed_draws: list[ParsedDraw]
    expected_main_count: int
    expected_total_count: int
    bonus_label: str
    data_quality_rows: list[dict[str, object]]
    format_counter: Counter


@dataclass
class AnalysisDataset:
    name: str
    output_prefix: str
    main_draws: list[list[int]]
    bonus_draws: list[int]
    draw_dates: list[pd.Timestamp]
    all_numbers_counter: Counter
    pool_size_main: int
    numbers_per_main_draw: int
    bonus_pool_size: Optional[int]
    has_bonus: bool


@dataclass
class EraDefinition:
    dataset_name: str
    era_label: str
    output_prefix: str
    start_year: int
    end_year: int
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    main_pool_size: int
    bonus_pool_size: int
    numbers_per_main_draw: int
    draw_count: int
    rows: list[ParsedDraw]


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def safe_print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def parse_result_numbers(value: object) -> list[int]:
    if pd.isna(value):
        return []
    return [int(n) for n in re.findall(r"\d+", str(value).strip())]


def clean_draw_date(value: object) -> pd.Timestamp:
    if pd.isna(value):
        return pd.NaT
    text = re.sub(r"\s+", " ", str(value).replace("\n", " ").strip())
    return pd.to_datetime(text, errors="coerce")


def choose_n_over_k(n: int, k: int) -> int:
    return math.comb(n, k)


def chi_square_statistic(observed: list[int], expected: list[float]) -> float:
    stat = 0.0
    for o, e in zip(observed, expected):
        if e > 0:
            stat += ((o - e) ** 2) / e
    return stat


def approx_chi_square_zscore(chi2_value: float, degrees_of_freedom: int) -> float:
    if degrees_of_freedom <= 0:
        return 0.0
    return (chi2_value - degrees_of_freedom) / math.sqrt(2 * degrees_of_freedom)


def mean_std(values: Iterable[float]) -> tuple[float, float]:
    arr = np.array(list(values), dtype=float)
    if len(arr) == 0:
        return 0.0, 0.0
    return float(np.mean(arr)), float(np.std(arr))


def summarize_against_simulation(observed: float, sim_values: list[float]) -> dict[str, float]:
    arr = np.array(sim_values, dtype=float)
    mean_val = float(np.mean(arr))
    std_val = float(np.std(arr))
    z = 0.0 if std_val == 0 else (observed - mean_val) / std_val
    less_equal = float(np.mean(arr <= observed))
    greater_equal = float(np.mean(arr >= observed))
    two_sided_tail = min(less_equal, greater_equal) * 2.0
    return {
        "observed": float(observed),
        "sim_mean": mean_val,
        "sim_std": std_val,
        "z_score": z,
        "approx_two_sided_tail": min(two_sided_tail, 1.0),
    }


def format_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def infer_pool_size(counter: Counter) -> int:
    return max(counter.keys()) if counter else 0


def itertools_combinations(values: list[int], r: int):
    if r != 2:
        raise NotImplementedError("This helper currently supports r=2 only.")
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            yield tuple(sorted((values[i], values[j])))


def read_history_csv(file_path: Path) -> pd.DataFrame:
    df = pd.read_csv(file_path)
    if "Results" not in df.columns and len(df.columns) == 1 and ";" in str(df.columns[0]):
        df = pd.read_csv(file_path, sep=";")
    return df


def write_metric_report(path: Path, rows: list[dict[str, object]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return df


def parse_game_row(
    row_index: int,
    row: pd.Series,
    expected_main_count: int,
) -> tuple[Optional[ParsedDraw], list[str], str]:
    issues: list[str] = []
    numbers = parse_result_numbers(row.get("Results"))
    format_label = f"{len(numbers)}_numbers"
    expected_total = expected_main_count + 1

    draw_date = clean_draw_date(row.get("Draw Date"))
    if pd.isna(draw_date):
        issues.append("invalid_draw_date")

    if len(numbers) != expected_total:
        issues.append("unexpected_result_length")

    main_numbers = sorted(numbers[:expected_main_count]) if len(numbers) >= expected_main_count else []
    bonus_number = numbers[expected_main_count] if len(numbers) > expected_main_count else None

    if len(main_numbers) != expected_main_count:
        issues.append("missing_main_numbers")
    elif len(set(main_numbers)) != expected_main_count:
        issues.append("duplicate_main_numbers")
    elif any(n <= 0 for n in main_numbers):
        issues.append("non_positive_main_numbers")

    if bonus_number is None:
        issues.append("missing_bonus_number")
    elif bonus_number <= 0:
        issues.append("non_positive_bonus_number")

    if issues:
        return None, issues, format_label

    return (
        ParsedDraw(
            row_index=row_index,
            draw_date=draw_date,
            main_numbers=main_numbers,
            bonus_number=int(bonus_number),
            raw_results=str(row.get("Results", "")),
            raw_numbers=numbers,
        ),
        [],
        format_label,
    )


def parse_lotto_row(row_index: int, row: pd.Series) -> tuple[Optional[ParsedDraw], list[str], str]:
    return parse_game_row(row_index, row, expected_main_count=6)


def parse_powerball_row(row_index: int, row: pd.Series) -> tuple[Optional[ParsedDraw], list[str], str]:
    return parse_game_row(row_index, row, expected_main_count=5)


def load_dataset(
    name: str,
    file_path: Path,
    parser: Callable[[int, pd.Series], tuple[Optional[ParsedDraw], list[str], str]],
    expected_main_count: int,
    bonus_label: str,
) -> DatasetContext:
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    df = read_history_csv(file_path)
    required_columns = {"Draw Date", "Results"}
    missing = required_columns.difference(df.columns)
    if missing:
        raise ValueError(f"{file_path.name} is missing required columns: {sorted(missing)}")

    parsed_draws: list[ParsedDraw] = []
    skipped_rows: list[dict[str, object]] = []
    format_counter: Counter = Counter()
    malformed_row_count = 0
    rows_skipped = 0
    unexpected_result_length_rows = 0
    inconsistent_rows = 0

    for row_index, row in df.iterrows():
        parsed, issues, format_label = parser(row_index, row)
        format_counter[format_label] += 1

        if parsed is not None:
            parsed_draws.append(parsed)
            continue

        malformed_row_count += 1
        rows_skipped += 1
        if "unexpected_result_length" in issues:
            unexpected_result_length_rows += 1
        if any(issue != "unexpected_result_length" for issue in issues):
            inconsistent_rows += 1

        skipped_rows.append(
            {
                "row_index": int(row_index),
                "draw_date_raw": row.get("Draw Date"),
                "results_raw": row.get("Results"),
                "issues": ", ".join(issues),
                "format_label": format_label,
            }
        )

    data_quality_rows: list[dict[str, object]] = [
        {"section": "summary", "metric": "rows_in_file", "value": len(df)},
        {"section": "summary", "metric": "valid_draws", "value": len(parsed_draws)},
        {"section": "summary", "metric": "malformed_row_count", "value": malformed_row_count},
        {"section": "summary", "metric": "rows_skipped", "value": rows_skipped},
        {"section": "summary", "metric": "unexpected_result_length_rows", "value": unexpected_result_length_rows},
        {"section": "summary", "metric": "parsed_main_bonus_inconsistency_rows", "value": inconsistent_rows},
        {"section": "summary", "metric": "distinct_row_formats_found", "value": len(format_counter)},
    ]
    data_quality_rows.extend(
        {"section": "format", "metric": format_label, "value": count}
        for format_label, count in sorted(format_counter.items())
    )
    data_quality_rows.extend(
        {
            "section": "skipped_row",
            "metric": row["issues"],
            "value": row["row_index"],
            "draw_date_raw": row["draw_date_raw"],
            "results_raw": row["results_raw"],
            "format_label": row["format_label"],
        }
        for row in skipped_rows
    )

    return DatasetContext(
        name=name,
        file_path=file_path,
        draws_raw=df,
        parsed_draws=sorted(parsed_draws, key=lambda draw: draw.draw_date),
        expected_main_count=expected_main_count,
        expected_total_count=expected_main_count + 1,
        bonus_label=bonus_label,
        data_quality_rows=data_quality_rows,
        format_counter=format_counter,
    )


def write_data_quality_report(context: DatasetContext) -> pd.DataFrame:
    safe_print_header(f"{context.name} - DATA QUALITY")

    summary_map = {
        row["metric"]: row["value"]
        for row in context.data_quality_rows
        if row["section"] == "summary"
    }
    for key in [
        "rows_in_file",
        "valid_draws",
        "malformed_row_count",
        "rows_skipped",
        "unexpected_result_length_rows",
        "parsed_main_bonus_inconsistency_rows",
        "distinct_row_formats_found",
    ]:
        print(f"{key}: {summary_map.get(key, 0)}")

    print("row_formats:")
    for format_label, count in sorted(context.format_counter.items()):
        print(f"  {format_label}: {count}")

    return write_metric_report(OUTPUT_DIR / f"{context.name.lower()}_data_quality.csv", context.data_quality_rows)


def build_analysis_dataset(name: str, output_prefix: str, rows: list[ParsedDraw], has_bonus: bool = True) -> AnalysisDataset:
    main_draws = [row.main_numbers for row in rows]
    bonus_draws = [row.bonus_number for row in rows if row.bonus_number is not None]
    all_main_numbers = [number for draw in main_draws for number in draw]
    main_counter = Counter(all_main_numbers)
    bonus_counter = Counter(bonus_draws)

    return AnalysisDataset(
        name=name,
        output_prefix=output_prefix,
        main_draws=main_draws,
        bonus_draws=bonus_draws,
        draw_dates=[row.draw_date for row in rows],
        all_numbers_counter=main_counter,
        pool_size_main=infer_pool_size(main_counter),
        numbers_per_main_draw=len(main_draws[0]) if main_draws else 0,
        bonus_pool_size=infer_pool_size(bonus_counter) if bonus_counter else None,
        has_bonus=has_bonus,
    )


def dataset_overview(dataset: AnalysisDataset) -> dict[str, object]:
    total_draws = len(dataset.main_draws)
    unique_main_numbers = len(dataset.all_numbers_counter)
    overview = {
        "dataset": dataset.name,
        "valid_draws": total_draws,
        "main_numbers_per_draw": dataset.numbers_per_main_draw,
        "main_number_pool_size_inferred": dataset.pool_size_main,
        "has_bonus": dataset.has_bonus,
        "bonus_pool_size_inferred": dataset.bonus_pool_size,
        "start_date": dataset.draw_dates[0].date().isoformat() if dataset.draw_dates else None,
        "end_date": dataset.draw_dates[-1].date().isoformat() if dataset.draw_dates else None,
    }

    safe_print_header(f"{dataset.name} - OVERVIEW")
    for key, value in overview.items():
        print(f"{key}: {value}")
    print(f"unique_main_numbers_seen: {unique_main_numbers}")
    return overview


def frequency_analysis(dataset: AnalysisDataset) -> dict[str, object]:
    safe_print_header(f"{dataset.name} - FREQUENCY ANALYSIS")

    counter = dataset.all_numbers_counter
    pool_size = dataset.pool_size_main
    total_draws = len(dataset.main_draws)
    picks_per_draw = dataset.numbers_per_main_draw

    observed = [counter.get(i, 0) for i in range(1, pool_size + 1)]
    expected_freq = (total_draws * picks_per_draw) / pool_size if pool_size else 0.0
    expected = [expected_freq] * pool_size

    chi2 = chi_square_statistic(observed, expected)
    z_approx = approx_chi_square_zscore(chi2, pool_size - 1)
    min_freq = min(observed) if observed else 0
    max_freq = max(observed) if observed else 0
    avg_freq = float(np.mean(observed)) if observed else 0.0
    std_freq = float(np.std(observed)) if observed else 0.0
    top_10 = counter.most_common(10)
    bottom_10 = sorted(((i, counter.get(i, 0)) for i in range(1, pool_size + 1)), key=lambda x: (x[1], x[0]))[:10]

    print(f"pool_size: {pool_size}")
    print(f"total_draws: {total_draws}")
    print(f"picks_per_draw: {picks_per_draw}")
    print(f"expected_frequency_per_number: {expected_freq:.2f}")
    print(f"min_frequency: {min_freq}")
    print(f"max_frequency: {max_freq}")
    print(f"mean_frequency: {avg_freq:.2f}")
    print(f"std_frequency: {std_freq:.2f}")
    print(f"chi_square_statistic: {chi2:.2f}")
    print(f"chi_square_z_approx: {z_approx:.2f}")
    print(f"top_10_numbers: {top_10}")
    print(f"bottom_10_numbers: {bottom_10}")

    pd.DataFrame(
        {
            "number": list(range(1, pool_size + 1)),
            "observed_freq": observed,
            "expected_freq": expected,
            "diff": [o - expected_freq for o in observed],
        }
    ).to_csv(OUTPUT_DIR / f"{dataset.output_prefix}_frequency_table.csv", index=False)

    return {
        "pool_size": pool_size,
        "total_draws": total_draws,
        "picks_per_draw": picks_per_draw,
        "expected_frequency_per_number": expected_freq,
        "chi_square_statistic": chi2,
        "chi_square_z_approx": z_approx,
        "min_frequency": min_freq,
        "max_frequency": max_freq,
        "mean_frequency": avg_freq,
        "std_frequency": std_freq,
        "top_10_numbers": top_10,
        "bottom_10_numbers": bottom_10,
    }


def repeat_overlap_analysis(dataset: AnalysisDataset) -> dict[str, object]:
    safe_print_header(f"{dataset.name} - CONSECUTIVE DRAW OVERLAP ANALYSIS")

    overlaps: list[int] = []
    for i in range(1, len(dataset.main_draws)):
        prev_draw = set(dataset.main_draws[i - 1])
        curr_draw = set(dataset.main_draws[i])
        overlaps.append(len(prev_draw & curr_draw))

    overlap_counter = Counter(overlaps)
    mean_overlap, std_overlap = mean_std(overlaps)

    print(f"pairs_of_consecutive_draws: {len(overlaps)}")
    print(f"average_overlap: {mean_overlap:.4f}")
    print(f"std_overlap: {std_overlap:.4f}")
    print(f"overlap_distribution: {dict(sorted(overlap_counter.items()))}")

    pd.DataFrame(
        {"overlap_size": list(overlap_counter.keys()), "count": list(overlap_counter.values())}
    ).sort_values("overlap_size").to_csv(
        OUTPUT_DIR / f"{dataset.output_prefix}_overlap_distribution.csv",
        index=False,
    )

    return {
        "num_pairs": len(overlaps),
        "average_overlap": mean_overlap,
        "std_overlap": std_overlap,
        "distribution": dict(sorted(overlap_counter.items())),
        "raw_overlaps": overlaps,
    }


def gap_analysis(dataset: AnalysisDataset) -> dict[str, object]:
    safe_print_header(f"{dataset.name} - GAP ANALYSIS")

    indices_by_number: dict[int, list[int]] = defaultdict(list)
    for draw_idx, draw in enumerate(dataset.main_draws):
        for number in draw:
            indices_by_number[number].append(draw_idx)

    all_gaps: list[int] = []
    gap_summary_rows: list[dict[str, float]] = []

    for number in range(1, dataset.pool_size_main + 1):
        indices = indices_by_number.get(number, [])
        if len(indices) < 2:
            continue

        gaps = [indices[i] - indices[i - 1] for i in range(1, len(indices))]
        all_gaps.extend(gaps)
        gap_summary_rows.append(
            {
                "number": number,
                "appearances": len(indices),
                "avg_gap": float(np.mean(gaps)),
                "std_gap": float(np.std(gaps)),
                "min_gap": int(min(gaps)),
                "max_gap": int(max(gaps)),
            }
        )

    overall_avg_gap, overall_std_gap = mean_std(all_gaps)
    print(f"numbers_with_gap_history: {len(gap_summary_rows)}")
    print(f"overall_average_gap: {overall_avg_gap:.4f}")
    print(f"overall_gap_std: {overall_std_gap:.4f}")
    if all_gaps:
        print(f"min_gap_seen: {min(all_gaps)}")
        print(f"max_gap_seen: {max(all_gaps)}")

    pd.DataFrame(gap_summary_rows).sort_values("number").to_csv(
        OUTPUT_DIR / f"{dataset.output_prefix}_gap_summary.csv",
        index=False,
    )
    pd.DataFrame({"gap": all_gaps}).to_csv(
        OUTPUT_DIR / f"{dataset.output_prefix}_all_gaps.csv",
        index=False,
    )

    return {
        "overall_average_gap": overall_avg_gap,
        "overall_gap_std": overall_std_gap,
        "all_gaps": all_gaps,
    }


def sequence_analysis(dataset: AnalysisDataset) -> dict[str, object]:
    safe_print_header(f"{dataset.name} - CONSECUTIVE NUMBER SEQUENCE ANALYSIS")

    sequence_counts = {2: 0, 3: 0, 4: 0, 5: 0}
    draws_with_sequence = {2: 0, 3: 0, 4: 0, 5: 0}
    perfect_full_draw_sequences = 0
    detailed_rows: list[dict[str, object]] = []

    for draw_idx, draw in enumerate(dataset.main_draws):
        draw_set = set(draw)
        min_num = min(draw)
        max_num = max(draw)

        for seq_len in sequence_counts.keys():
            found_in_this_draw = set()
            for start in range(min_num, max_num - seq_len + 2):
                seq = tuple(range(start, start + seq_len))
                if all(n in draw_set for n in seq):
                    found_in_this_draw.add(seq)

            if found_in_this_draw:
                sequence_counts[seq_len] += len(found_in_this_draw)
                draws_with_sequence[seq_len] += 1
                for seq in sorted(found_in_this_draw):
                    detailed_rows.append(
                        {
                            "draw_index": draw_idx,
                            "sequence_length": seq_len,
                            "sequence": ",".join(map(str, seq)),
                            "draw_numbers": ",".join(map(str, draw)),
                        }
                    )

        if all(draw[i] + 1 == draw[i + 1] for i in range(len(draw) - 1)):
            perfect_full_draw_sequences += 1

    total_draws = len(dataset.main_draws)
    print(f"total_draws: {total_draws}")
    print(f"perfect_full_draw_sequences: {perfect_full_draw_sequences}")
    for seq_len in sequence_counts.keys():
        draw_pct = draws_with_sequence[seq_len] / total_draws if total_draws else 0.0
        print(
            f"sequence_length_{seq_len}: "
            f"total_sequences_found={sequence_counts[seq_len]}, "
            f"draws_with_sequence={draws_with_sequence[seq_len]} "
            f"({format_percent(draw_pct)})"
        )

    pd.DataFrame(
        [
            {
                "sequence_length": seq_len,
                "total_sequences_found": sequence_counts[seq_len],
                "draws_with_sequence": draws_with_sequence[seq_len],
                "draw_percentage": draws_with_sequence[seq_len] / total_draws if total_draws else 0.0,
            }
            for seq_len in sequence_counts.keys()
        ]
    ).to_csv(OUTPUT_DIR / f"{dataset.output_prefix}_sequence_summary.csv", index=False)
    pd.DataFrame(detailed_rows).to_csv(OUTPUT_DIR / f"{dataset.output_prefix}_sequence_details.csv", index=False)

    return {
        "perfect_full_draw_sequences": perfect_full_draw_sequences,
        "sequence_counts": sequence_counts,
        "draws_with_sequence": draws_with_sequence,
    }


def pair_frequency_analysis(dataset: AnalysisDataset, top_n: int = 25) -> dict[str, object]:
    safe_print_header(f"{dataset.name} - PAIR CO-OCCURRENCE ANALYSIS")

    pair_counter: Counter = Counter()
    for draw in dataset.main_draws:
        for pair in itertools_combinations(draw, 2):
            pair_counter[pair] += 1

    total_draws = len(dataset.main_draws)
    pool_size = dataset.pool_size_main
    picks_per_draw = dataset.numbers_per_main_draw
    total_possible_pairs = choose_n_over_k(pool_size, 2)
    pairs_per_draw = choose_n_over_k(picks_per_draw, 2)
    expected_per_pair = (total_draws * pairs_per_draw) / total_possible_pairs if total_possible_pairs else 0.0

    top_pairs = pair_counter.most_common(top_n)
    min_pair_count = min(pair_counter.values()) if pair_counter else 0
    max_pair_count = max(pair_counter.values()) if pair_counter else 0
    mean_pair_count = float(np.mean(list(pair_counter.values()))) if pair_counter else 0.0
    std_pair_count = float(np.std(list(pair_counter.values()))) if pair_counter else 0.0

    print(f"distinct_pairs_seen: {len(pair_counter)}")
    print(f"expected_average_pair_frequency: {expected_per_pair:.4f}")
    print(f"min_pair_count: {min_pair_count}")
    print(f"max_pair_count: {max_pair_count}")
    print(f"mean_pair_count: {mean_pair_count:.4f}")
    print(f"std_pair_count: {std_pair_count:.4f}")
    print(f"top_{top_n}_pairs: {top_pairs}")

    pd.DataFrame([{"pair": f"{a}-{b}", "count": c} for (a, b), c in top_pairs]).to_csv(
        OUTPUT_DIR / f"{dataset.output_prefix}_top_pairs.csv",
        index=False,
    )

    return {
        "distinct_pairs_seen": len(pair_counter),
        "expected_average_pair_frequency": expected_per_pair,
        "min_pair_count": min_pair_count,
        "max_pair_count": max_pair_count,
        "mean_pair_count": mean_pair_count,
        "std_pair_count": std_pair_count,
        "top_pairs": top_pairs,
    }


def bonus_ball_analysis(dataset: AnalysisDataset, bonus_label: str) -> dict[str, object] | None:
    if not dataset.has_bonus or not dataset.bonus_draws:
        return None

    safe_print_header(f"{dataset.name} - {bonus_label.upper()} FREQUENCY ANALYSIS")

    counter = Counter(dataset.bonus_draws)
    pool_size = dataset.bonus_pool_size or infer_pool_size(counter)
    total_draws = len(dataset.bonus_draws)
    observed = [counter.get(i, 0) for i in range(1, pool_size + 1)]
    expected_freq = total_draws / pool_size if pool_size else 0.0
    expected = [expected_freq] * pool_size

    chi2 = chi_square_statistic(observed, expected)
    z_approx = approx_chi_square_zscore(chi2, pool_size - 1)

    print(f"{bonus_label.lower()}_pool_size: {pool_size}")
    print(f"{bonus_label.lower()}_draws: {total_draws}")
    print(f"expected_frequency_per_{bonus_label.lower()}_number: {expected_freq:.2f}")
    print(f"chi_square_statistic: {chi2:.2f}")
    print(f"chi_square_z_approx: {z_approx:.2f}")
    print(f"top_{bonus_label.lower()}_numbers: {counter.most_common(10)}")

    pd.DataFrame(
        {
            "number": list(range(1, pool_size + 1)),
            "observed_freq": observed,
            "expected_freq": expected,
            "diff": [o - expected_freq for o in observed],
        }
    ).to_csv(OUTPUT_DIR / f"{dataset.output_prefix}_bonus_frequency_table.csv", index=False)

    return {
        "bonus_pool_size": pool_size,
        "bonus_draws": total_draws,
        "expected_frequency_per_bonus_number": expected_freq,
        "chi_square_statistic": chi2,
        "chi_square_z_approx": z_approx,
        "top_bonus_numbers": counter.most_common(10),
    }


def build_year_diagnostics(context: DatasetContext) -> pd.DataFrame:
    safe_print_header(f"{context.name} - YEAR ANALYSIS")

    rows: list[dict[str, object]] = []
    by_year: dict[int, list[ParsedDraw]] = defaultdict(list)
    for draw in context.parsed_draws:
        by_year[draw.year].append(draw)

    for year in sorted(by_year):
        draws = by_year[year]
        main_draws = [draw.main_numbers for draw in draws]
        bonus_draws = [draw.bonus_number for draw in draws]
        flat_main = [number for draw in main_draws for number in draw]
        counter = Counter(flat_main)
        pool_size = max(flat_main)
        numbers_per_draw = len(main_draws[0])
        bonus_pool_size = max(bonus_draws)
        observed = [counter.get(i, 0) for i in range(1, pool_size + 1)]
        expected_freq = len(flat_main) / pool_size if pool_size else 0.0
        chi2 = chi_square_statistic(observed, [expected_freq] * pool_size)
        z_approx = approx_chi_square_zscore(chi2, pool_size - 1)

        row = {
            "year": year,
            "draw_count": len(draws),
            "start_date": min(draw.draw_date for draw in draws).date().isoformat(),
            "end_date": max(draw.draw_date for draw in draws).date().isoformat(),
            "main_pool_size": pool_size,
            "main_numbers_per_draw": numbers_per_draw,
            "bonus_pool_size": bonus_pool_size,
            "chi_square_statistic": chi2,
            "chi_square_z_approx": z_approx,
            "top_5_main_numbers": ", ".join(f"{n}:{c}" for n, c in counter.most_common(5)),
        }
        rows.append(row)

        print(
            f"{year}: draws={row['draw_count']}, "
            f"main_pool={row['main_pool_size']}, "
            f"main_numbers_per_draw={row['main_numbers_per_draw']}, "
            f"bonus_pool={row['bonus_pool_size']}, "
            f"chi2={row['chi_square_statistic']:.2f}, "
            f"z~={row['chi_square_z_approx']:.2f}"
        )

    year_df = pd.DataFrame(rows).sort_values("year")
    year_df.to_csv(OUTPUT_DIR / f"{context.name.lower()}_year_analysis.csv", index=False)
    return year_df


def build_era_definition(context: DatasetContext, year_group: list[dict[str, object]]) -> EraDefinition:
    start_year = int(year_group[0]["year"])
    end_year = int(year_group[-1]["year"])
    era_rows = [draw for draw in context.parsed_draws if start_year <= draw.year <= end_year]
    main_pool_size = max(number for draw in era_rows for number in draw.main_numbers)
    bonus_pool_size = max(draw.bonus_number for draw in era_rows)
    numbers_per_main_draw = len(era_rows[0].main_numbers)

    return EraDefinition(
        dataset_name=context.name,
        era_label=f"ERA {main_pool_size}",
        output_prefix=f"{context.name.lower()}_era_{main_pool_size}",
        start_year=start_year,
        end_year=end_year,
        start_date=min(draw.draw_date for draw in era_rows),
        end_date=max(draw.draw_date for draw in era_rows),
        main_pool_size=main_pool_size,
        bonus_pool_size=bonus_pool_size,
        numbers_per_main_draw=numbers_per_main_draw,
        draw_count=len(era_rows),
        rows=era_rows,
    )


def detect_eras(context: DatasetContext, year_df: pd.DataFrame) -> list[EraDefinition]:
    safe_print_header(f"{context.name} - ERA SUMMARY")

    if year_df.empty:
        return []

    def same_structure(a: dict[str, object], b: dict[str, object]) -> bool:
        return (
            a["main_numbers_per_draw"] == b["main_numbers_per_draw"]
            and a["main_pool_size"] == b["main_pool_size"]
        )

    eras: list[EraDefinition] = []
    year_rows = year_df.sort_values("year").to_dict("records")
    current_group = [year_rows[0]]

    for row in year_rows[1:]:
        prev = current_group[-1]
        if int(row["year"]) == int(prev["year"]) + 1 and same_structure(prev, row):
            current_group.append(row)
        else:
            eras.append(build_era_definition(context, current_group))
            current_group = [row]
    eras.append(build_era_definition(context, current_group))

    summary_rows = []
    for era in eras:
        span = f"{era.start_year}-{era.end_year}" if era.start_year != era.end_year else str(era.start_year)
        print(
            f"{era.era_label}: years={span}, "
            f"dates={era.start_date.date().isoformat()} to {era.end_date.date().isoformat()}, "
            f"draws={era.draw_count}, "
            f"main_pool={era.main_pool_size}, "
            f"main_numbers_per_draw={era.numbers_per_main_draw}, "
            f"bonus_pool={era.bonus_pool_size}"
        )
        summary_rows.append(
            {
                "era_label": era.era_label,
                "output_prefix": era.output_prefix,
                "start_year": era.start_year,
                "end_year": era.end_year,
                "start_date": era.start_date.date().isoformat(),
                "end_date": era.end_date.date().isoformat(),
                "draw_count": era.draw_count,
                "main_pool_size": era.main_pool_size,
                "main_numbers_per_draw": era.numbers_per_main_draw,
                "bonus_pool_size": era.bonus_pool_size,
            }
        )

    pd.DataFrame(summary_rows).to_csv(OUTPUT_DIR / f"{context.name.lower()}_era_summary.csv", index=False)
    return eras


def simulate_draws(
    rng: np.random.Generator,
    num_draws: int,
    pool_size: int,
    picks_per_draw: int,
) -> list[list[int]]:
    draws = []
    for _ in range(num_draws):
        draw = sorted(rng.choice(np.arange(1, pool_size + 1), size=picks_per_draw, replace=False).tolist())
        draws.append(draw)
    return draws


def compute_overlap_metric(draws: list[list[int]]) -> float:
    overlaps = []
    for i in range(1, len(draws)):
        overlaps.append(len(set(draws[i - 1]) & set(draws[i])))
    return float(np.mean(overlaps)) if overlaps else 0.0


def compute_sequence_draw_rate(draws: list[list[int]], sequence_length: int) -> float:
    if not draws:
        return 0.0

    draws_with_sequence = 0
    for draw in draws:
        draw_set = set(draw)
        found = False
        for start in range(min(draw), max(draw) - sequence_length + 2):
            seq = range(start, start + sequence_length)
            if all(n in draw_set for n in seq):
                found = True
                break
        if found:
            draws_with_sequence += 1
    return draws_with_sequence / len(draws)


def compute_frequency_chi2(draws: list[list[int]], pool_size: int, picks_per_draw: int) -> float:
    counter = Counter(num for draw in draws for num in draw)
    observed = [counter.get(i, 0) for i in range(1, pool_size + 1)]
    expected_freq = (len(draws) * picks_per_draw) / pool_size
    return chi_square_statistic(observed, [expected_freq] * pool_size)


def simulation_baseline_analysis(dataset: AnalysisDataset, runs: int = SIMULATION_RUNS) -> dict[str, object]:
    safe_print_header(f"{dataset.name} - MONTE CARLO BASELINE")

    rng = np.random.default_rng(RNG_SEED)
    num_draws = len(dataset.main_draws)
    pool_size = dataset.pool_size_main
    picks_per_draw = dataset.numbers_per_main_draw

    observed_overlap = compute_overlap_metric(dataset.main_draws)
    observed_seq2_rate = compute_sequence_draw_rate(dataset.main_draws, 2)
    observed_seq3_rate = compute_sequence_draw_rate(dataset.main_draws, 3)
    observed_chi2 = compute_frequency_chi2(dataset.main_draws, pool_size, picks_per_draw)

    sim_overlap_values = []
    sim_seq2_values = []
    sim_seq3_values = []
    sim_chi2_values = []

    for _ in range(runs):
        sim_draws = simulate_draws(rng, num_draws, pool_size, picks_per_draw)
        sim_overlap_values.append(compute_overlap_metric(sim_draws))
        sim_seq2_values.append(compute_sequence_draw_rate(sim_draws, 2))
        sim_seq3_values.append(compute_sequence_draw_rate(sim_draws, 3))
        sim_chi2_values.append(compute_frequency_chi2(sim_draws, pool_size, picks_per_draw))

    overlap_summary = summarize_against_simulation(observed_overlap, sim_overlap_values)
    seq2_summary = summarize_against_simulation(observed_seq2_rate, sim_seq2_values)
    seq3_summary = summarize_against_simulation(observed_seq3_rate, sim_seq3_values)
    chi2_summary = summarize_against_simulation(observed_chi2, sim_chi2_values)

    print("Observed vs Monte Carlo")
    print(
        f"average_overlap: observed={overlap_summary['observed']:.4f}, "
        f"sim_mean={overlap_summary['sim_mean']:.4f}, "
        f"z={overlap_summary['z_score']:.2f}, "
        f"tail~={overlap_summary['approx_two_sided_tail']:.4f}"
    )
    print(
        f"draw_rate_with_2_sequences: observed={seq2_summary['observed']:.4f}, "
        f"sim_mean={seq2_summary['sim_mean']:.4f}, "
        f"z={seq2_summary['z_score']:.2f}, "
        f"tail~={seq2_summary['approx_two_sided_tail']:.4f}"
    )
    print(
        f"draw_rate_with_3_sequences: observed={seq3_summary['observed']:.4f}, "
        f"sim_mean={seq3_summary['sim_mean']:.4f}, "
        f"z={seq3_summary['z_score']:.2f}, "
        f"tail~={seq3_summary['approx_two_sided_tail']:.4f}"
    )
    print(
        f"frequency_chi2: observed={chi2_summary['observed']:.4f}, "
        f"sim_mean={chi2_summary['sim_mean']:.4f}, "
        f"z={chi2_summary['z_score']:.2f}, "
        f"tail~={chi2_summary['approx_two_sided_tail']:.4f}"
    )

    pd.DataFrame(
        [
            {"metric": "average_overlap", **overlap_summary},
            {"metric": "draw_rate_with_2_sequences", **seq2_summary},
            {"metric": "draw_rate_with_3_sequences", **seq3_summary},
            {"metric": "frequency_chi2", **chi2_summary},
        ]
    ).to_csv(OUTPUT_DIR / f"{dataset.output_prefix}_simulation_summary.csv", index=False)

    return {
        "average_overlap": overlap_summary,
        "draw_rate_with_2_sequences": seq2_summary,
        "draw_rate_with_3_sequences": seq3_summary,
        "frequency_chi2": chi2_summary,
    }


def interpret_randomness(dataset_name: str, output_prefix: str, sim_summary: dict[str, object]) -> pd.DataFrame:
    safe_print_header(f"{dataset_name} - RANDOMNESS INTERPRETATION")

    rows = []
    for metric_name, metric_summary in sim_summary.items():
        z = metric_summary["z_score"]
        tail = metric_summary["approx_two_sided_tail"]

        if abs(z) < 2.0 and tail > 0.05:
            verdict = "Looks consistent with random baseline"
        elif abs(z) < 3.0 and tail > 0.01:
            verdict = "Mild deviation; probably noise unless repeated elsewhere"
        else:
            verdict = "Potential deviation worth investigating"

        rows.append(
            {
                "metric": metric_name,
                "observed": metric_summary["observed"],
                "sim_mean": metric_summary["sim_mean"],
                "sim_std": metric_summary["sim_std"],
                "z_score": z,
                "approx_two_sided_tail": tail,
                "verdict": verdict,
            }
        )

    result_df = pd.DataFrame(rows)
    print(result_df.to_string(index=False))
    result_df.to_csv(OUTPUT_DIR / f"{output_prefix}_interpretation.csv", index=False)
    return result_df


def analyze_era(era: EraDefinition, bonus_label: str) -> None:
    dataset = build_analysis_dataset(
        name=f"{era.dataset_name} - {era.era_label}",
        output_prefix=era.output_prefix,
        rows=era.rows,
    )
    dataset_overview(dataset)
    frequency_analysis(dataset)
    repeat_overlap_analysis(dataset)
    gap_analysis(dataset)
    sequence_analysis(dataset)
    pair_frequency_analysis(dataset)
    bonus_ball_analysis(dataset, bonus_label=bonus_label)
    sim_summary = simulation_baseline_analysis(dataset)
    interpret_randomness(dataset.name, dataset.output_prefix, sim_summary)


def analyze_dataset(
    name: str,
    file_path: Path,
    parser: Callable[[int, pd.Series], tuple[Optional[ParsedDraw], list[str], str]],
    expected_main_count: int,
    bonus_label: str,
) -> None:
    context = load_dataset(
        name=name,
        file_path=file_path,
        parser=parser,
        expected_main_count=expected_main_count,
        bonus_label=bonus_label,
    )

    write_data_quality_report(context)
    full_dataset = build_analysis_dataset(
        name=f"{context.name} - WHOLE HISTORY OVERVIEW",
        output_prefix=f"{context.name.lower()}_whole_history",
        rows=context.parsed_draws,
    )
    dataset_overview(full_dataset)
    year_df = build_year_diagnostics(context)
    eras = detect_eras(context, year_df)
    for era in eras:
        analyze_era(era, bonus_label=context.bonus_label)


def main() -> None:
    ensure_output_dir()

    print("Lottery Analyzer")
    print(f"Working folder: {SCRIPT_DIR}")
    print(f"Output folder:  {OUTPUT_DIR}")

    analyze_dataset(
        name="Lotto",
        file_path=LOTTO_FILE,
        parser=parse_lotto_row,
        expected_main_count=6,
        bonus_label="Bonus",
    )
    analyze_dataset(
        name="PowerBall",
        file_path=POWERBALL_FILE,
        parser=parse_powerball_row,
        expected_main_count=5,
        bonus_label="PowerBall",
    )

    print("\nDone.")
    print(f"CSV outputs written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
