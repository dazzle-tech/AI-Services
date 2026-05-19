export function inferChartType(payload) {
  const explicit = payload && payload.visualization && payload.visualization.type;
  if (explicit) {
    return explicit;
  }

  const parsedIntent = payload && payload.parsed && payload.parsed.intent;
  const intent = String(parsedIntent || "").toLowerCase();
  if (intent.includes("trend")) {
    return "line_chart";
  }
  if (intent.includes("distribution")) {
    return "pie_chart";
  }
  if (intent.includes("top") || intent.includes("busiest")) {
    return "bar_chart";
  }
  return "kpi";
}

export function buildStatisticsViewModel(payload) {
  const safePayload = payload && typeof payload === "object" ? payload : {};
  const title = String(safePayload.title || "Statistics");
  const summary = String(safePayload.summary || "");
  const filters = safePayload.filters && typeof safePayload.filters === "object" ? safePayload.filters : {};
  const dateRange = filters.date_range ? String(filters.date_range) : null;

  const table = safePayload.table && typeof safePayload.table === "object" ? safePayload.table : {};
  const columns = Array.isArray(table.columns) ? table.columns.map((c) => String(c)) : [];
  const rows = Array.isArray(table.rows) ? table.rows : [];

  const chartData = safePayload.chart_data && typeof safePayload.chart_data === "object" ? safePayload.chart_data : {};
  const x = Array.isArray(chartData.x) ? chartData.x : [];
  const y = Array.isArray(chartData.y) ? chartData.y : [];

  const chartType = inferChartType(safePayload);

  return {
    title,
    summary,
    dateRange,
    columns,
    rows,
    chartType,
    x,
    y,
  };
}

