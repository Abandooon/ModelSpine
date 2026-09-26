# Finite construction mechanism pilot

This is one deterministic engineering task, not a sample of independent tasks or an LLM experiment. No comparative advantage is established. The evaluator fixes these expectations before running any condition. Shared authorship and public fixtures do not establish blind independent truth.

## Fixed task and reference

The task is `structural-graph-task@1`, SHA-256 `38a5b1ed21cfbdb03c1019acef9e27cd396ceabf4a481c9fba9897b05b39b348`. Preserve a valid flat finite DAG, a path from node-a to node-c, and no path from node-c to node-a. Only the endpoints of edge-bc may change. Keep edge-ab = a→b. The evaluator reuses the already pinned [reference specification](../../tests/fixtures/task-acceptance/graph-reference.json) and test-owned [oracle](../../tests/support/task_oracle.py); it never derives a reference from a selected candidate or supplies it to production search.

The full endpoint table below is fixed analytically from that task. Endpoint values alone are not full candidate models. `no_change` is recognized in all conditions before construction and consumes one option. The current base already satisfies the task; this pilot measures finding an actual admissible edit, not repairing a broken base.

| source | destination | DAG/ordinary control | independent full task after assignment |
|---|---|---|---|
| a | a | exclude | violated (cycle) |
| a | b | allow | violated (a cannot reach c) |
| a | c | allow | satisfied |
| b | a | exclude | violated (cycle) |
| b | b | exclude | violated (cycle) |
| b | c | no_change | satisfied base; no new candidate |
| c | a | allow | violated (both fixed path goals) |
| c | b | allow | violated (a cannot reach c) |
| c | c | exclude | violated (cycle) |

## Conditions and denominator

`terminal-only` admits every changed endpoint pair. `dag-construction` uses A's DAG adapter. `ordinary-rule` independently builds an adjacency multilist with substituted endpoints and removes zero-indegree nodes (Kahn's algorithm); it never calls A's controller. All consume the same task, snapshot, endpoint sets/order, budget, builder, terminal checker and app/kernel save path. All have the same input information; only preconstruction use differs. Plans declare actual stages. Terminal validation always covers all fixed obligations.

For each condition, predeclare full-space budgets 1, 2, 3, 9; a singleton a→c; singleton a→a; singleton b→c. These are 21 paired engineering executions, not 21 independent observations. Budgets count control calls including exclusions/no-change. Expected full-space statuses are budget_exhausted, budget_exhausted, candidate_found, candidate_found. Singleton statuses are candidate_found, exhausted, exhausted. On budget 3, terminal-only constructs/checks 3 candidates, the other two 2; all consider 3 and save the same edit. `search_candidate_checks` counts only returned search evaluations. A study-side transparent wrapper counts every actual development checker invocation; total minus search checks gives final acceptance checker calls. Current successful run_task calls the checker in assess_task, kernel.decide, and kernel.apply (three calls). These costs are included, not inferred from one returned assessment.

Three explicit fault probes (unknown decision, error decision, raised controller exception) run with ordinary-rule and budget 3. They add 3 attempted executions to a separately identified engineering-fault stratum. They are not naturally observed failure frequencies. All planned, started, returned, failed, unknown and error executions remain in the 24-execution record. No retries, fallback, optional stopping or candidate-dependent changes to targets.

Each result preserves full app output, step decisions/reports and post-hoc reference outcomes for every constructed candidate and saved model. App callback exceptions are recorded as errors; if the app does not return a trace, counts and saved status are null, not fabricated zeros or an inferred rollback. A failed oracle remains a failed evaluation even if a model was saved. Reference failures do not drive search or cause retry.

Wall time uses perf_counter around condition assembly and the full run_construction call (including host preparation, study counter instrumentation, search and model saving; excluding input/fixture loading, evaluator and JSON output). Reference evaluation is timed separately. It is one noisy engineering timing, not a performance estimate. LLM calls are exactly zero; paid API cost is zero because no API runs. Human design/build/review seconds are null with an unmeasured reason. Compute monetary cost is null because it is not metered. Attempts/options/candidates are nested within the same task, never independent statistical samples.

## Running and evidence

From platform: `python -B studies/construction/run.py --output studies/construction/runs/<new-name>.json`. Output creation is exclusive; never overwrite earlier runs. The record contains UTC time, Python/platform versions, Git HEAD/dirty status, input and code SHA-256 values, expected evaluation reference and all planned trial IDs. Git HEAD alone is not the identity of an uncommitted working tree.

Meaningful counterexamples are in [the study tests](../../tests/test_construction_study.py): terminal rejection of leaked cycles; residual reachability; budgets 1/2/3; zero/one candidates; no-change; complete nine-option equivalence; preservation of the sole valid changed option; explicit unknown/error/exception accounting; and source-associated diagnostic repair witnesses. No production diagnostic classifier is introduced.
