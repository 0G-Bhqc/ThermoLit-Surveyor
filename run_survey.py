import argparse
import json
from prototype_multihop_deepresearch import run_agent

def main():
    parser = argparse.ArgumentParser(description="ThermoLit-Surveyor Literature Survey Agent")
    parser.add_argument("--query", type=str, default="Bi2Te3 thermoelectric figure of merit zT Seebeck conductivity",
                        help="Initial literature search query")
    parser.add_argument("--output_report", type=str, default="deepresearch_multihop_report.md",
                        help="Path to save markdown survey report")
    parser.add_argument("--output_json", type=str, default="deepresearch_all_records.json",
                        help="Path to save extracted json records and evidence chain")
    args = parser.parse_args()

    print(f"[ThermoLit-Surveyor] Initiating literature survey for query: '{args.query}'...")
    state = run_agent(args.query)

    print(f"\n[ThermoLit-Surveyor] Pipeline finished in {state['metrics']['total_pipeline_duration']:.2f} seconds!")
    print(f"[ThermoLit-Surveyor] Total papers analyzed across 2 Passes: {state['metrics']['total_papers_analyzed']}")

    # Save report
    with open(args.output_report, "w", encoding="utf-8") as f:
        f.write(state['deep_gap_report'])
    print(f"[Output] Markdown report saved to: {args.output_report}")

    # Save json records
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump({
            "all_records": state['all_records'],
            "followup_queries": state['followup_queries'],
            "metrics": state['metrics']
        }, f, ensure_ascii=False, indent=2)
    print(f"[Output] Structured JSON saved to: {args.output_json}")

if __name__ == "__main__":
    main()
