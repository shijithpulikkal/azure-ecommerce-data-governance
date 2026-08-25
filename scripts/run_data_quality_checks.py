"""
run_data_quality_checks.py — Runs data quality validation checks against
the curated e-commerce dataset using Great Expectations 1.21.0.

pip install great_expectations==1.21.0 pandas

Notes on the GX 1.x API (a rewrite from the older 0.x style):
  - Datasources/Assets are created via context.data_sources.add_pandas(...)
  - Expectations are objects: gx.expectations.ExpectColumnValuesToNotBeNull(...)
  - Validation runs through a ValidationDefinition + Checkpoint, not a bare Validator
  - Data Docs are refreshed automatically via an UpdateDataDocsAction on the Checkpoint
"""

import pandas as pd
import great_expectations as gx
from great_expectations.checkpoint import UpdateDataDocsAction

# ---- Config ------------------------------------------------------------------
DATA_PATH = "curated_sales_sample.csv"  # adjust to your actual curated data path

VALID_BRAZIL_STATES = [
    "SP", "RJ", "MG", "RS", "PR", "BA", "SC", "PE", "CE", "GO",
    "DF", "ES", "PA", "AM", "MT", "MS", "MA", "PB", "PI", "RN",
    "AL", "SE", "RO", "TO", "AC", "AP", "RR",
]


def main() -> None:
    # ---- 1. Load data ---------------------------------------------------------
    df = pd.read_csv(DATA_PATH)
    print(f"Loaded {len(df)} rows, {len(df.columns)} columns from {DATA_PATH}")

    # ---- 2. Get / create a FILE-BACKED context ----------------------------------
    # gx.get_context() with no args creates an in-memory ("Ephemeral") context by
    # default in GX 1.x — nothing gets written to disk, so Data Docs never appear
    # as an actual HTML file. Passing mode="file" persists everything (including
    # the Data Docs site) under a local "gx/" folder in project_root_dir.
    context = gx.get_context(mode="file", project_root_dir=".")

    # ---- 3. Register a Pandas data source + dataframe asset + batch definition --
    data_source = context.data_sources.add_pandas(name="ecommerce_datasource")
    data_asset = data_source.add_dataframe_asset(name="curated_sales_asset")
    batch_definition = data_asset.add_batch_definition_whole_dataframe(
        "full_dataset_batch"
    )

    # ---- 4. Build the Expectation Suite -----------------------------------------
    suite = context.suites.add(gx.ExpectationSuite(name="ecommerce_quality_suite"))

    # No nulls in key business columns
    for col in ["order_id", "customer_id", "price"]:
        if col in df.columns:
            suite.add_expectation(
                gx.expectations.ExpectColumnValuesToNotBeNull(column=col)
            )

    # Uniqueness of the fact table's grain key, if present
    if "order_item_key" in df.columns:
        suite.add_expectation(
            gx.expectations.ExpectColumnValuesToBeUnique(column="order_item_key")
        )

    # price should be positive and within a sane range
    if "price" in df.columns:
        suite.add_expectation(
            gx.expectations.ExpectColumnValuesToBeBetween(
                column="price", min_value=0, max_value=10000
            )
        )

    # quantity should be a small positive integer
    if "quantity" in df.columns:
        suite.add_expectation(
            gx.expectations.ExpectColumnValuesToBeBetween(
                column="quantity", min_value=1, max_value=50
            )
        )

    # customer_state should be a known Brazilian state code
    if "customer_state" in df.columns:
        suite.add_expectation(
            gx.expectations.ExpectColumnValuesToBeInSet(
                column="customer_state", value_set=VALID_BRAZIL_STATES
            )
        )

    print(f"Built expectation suite with {len(suite.expectations)} expectations")

    # ---- 5. Create a Validation Definition (links the suite to the batch) ------
    validation_definition = context.validation_definitions.add(
        gx.ValidationDefinition(
            name="ecommerce_validation",
            data=batch_definition,
            suite=suite,
        )
    )

    # ---- 6. Create a Checkpoint that also refreshes Data Docs -------------------
    checkpoint = context.checkpoints.add(
        gx.Checkpoint(
            name="ecommerce_checkpoint",
            validation_definitions=[validation_definition],
            actions=[UpdateDataDocsAction(name="update_data_docs")],
        )
    )

    # ---- 7. Run validation --------------------------------------------------------
    results = checkpoint.run(batch_parameters={"dataframe": df})

    print(f"\nValidation success: {results.success}")

    # ---- 8. Print a quick per-expectation summary --------------------------------
    # Convert to a plain dict via to_json_dict() so we don't depend on the exact
    # object structure, which has shifted between GX 1.x minor versions.
    for run_result in results.run_results.values():
        result_dict = (
            run_result.to_json_dict() if hasattr(run_result, "to_json_dict") else run_result
        )
        for expectation_result in result_dict.get("results", []):
            exp_config = expectation_result.get("expectation_config", {})
            exp_type = exp_config.get("type", "unknown_expectation")
            column = exp_config.get("kwargs", {}).get("column", "-")
            passed = expectation_result.get("success", False)
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {status} | {exp_type} | column={column}")

    print(
        "\nData Docs updated — open gx/uncommitted/data_docs/"
        "local_site/index.html to view the full report."
    )


if __name__ == "__main__":
    main()
