import assert from "node:assert/strict";
import { buildStatisticsViewModel, inferChartType } from "./statistics_result.js";

function run() {
  assert.equal(
    inferChartType({ visualization: { type: "bar_chart" } }),
    "bar_chart"
  );

  const vm = buildStatisticsViewModel({
    title: "Top 5 Diagnoses Last Month",
    summary: "Hypertension was the most common diagnosis with 124 cases.",
    visualization: { type: "bar_chart" },
    table: { columns: ["Diagnosis", "Count"], rows: [["Hypertension", 124]] },
    chart_data: { x: ["Hypertension"], y: [124] },
    filters: { date_range: "last_month" },
  });

  assert.equal(vm.title, "Top 5 Diagnoses Last Month");
  assert.equal(vm.chartType, "bar_chart");
  assert.equal(vm.dateRange, "last_month");
  assert.deepEqual(vm.columns, ["Diagnosis", "Count"]);
  assert.deepEqual(vm.x, ["Hypertension"]);
  assert.deepEqual(vm.y, [124]);

  assert.equal(inferChartType({ parsed: { intent: "diagnosis_trend" } }), "line_chart");
  assert.equal(
    inferChartType({ parsed: { intent: "diagnosis_distribution" } }),
    "pie_chart"
  );
  assert.equal(inferChartType({ parsed: { intent: "top_diagnoses" } }), "bar_chart");
}

run();
console.log("OK - statistics_result view model tests passed");

