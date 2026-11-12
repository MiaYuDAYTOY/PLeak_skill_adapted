#!/usr/bin/env bash
set -euo pipefail
analysis_dir="$(cd "$(dirname "$0")" && pwd)"
stats_python="${STATS_PYTHON:-python3}"
token_python="${TOKEN_PYTHON:-/private/tmp/qwen-no-cleanup-20261103/bin/python}"
"$token_python" "$analysis_dir/audit_metrics.py" > "$analysis_dir/audit_execution.log"
"$stats_python" "$analysis_dir/analyze_overview.py" > "$analysis_dir/overview_execution.log"
"$token_python" "$analysis_dir/diagnostics/analyze_outputs.py" > "$analysis_dir/diagnostics/execution.log"
"$stats_python" "$analysis_dir/skills/analyze_skills.py" > "$analysis_dir/skills/execution.log"
"$stats_python" "$analysis_dir/loss/analyze_loss.py" > "$analysis_dir/loss/execution.log"
"$stats_python" "$analysis_dir/integrate_analysis.py" > "$analysis_dir/integration_execution.log"
"$stats_python" "$analysis_dir/build_report.py"
"$stats_python" "$analysis_dir/validate_delivery.py"
