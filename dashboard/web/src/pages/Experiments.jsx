import { Card, Empty, Legend, Stat, Status, Table } from '../components/ui.jsx';
import { GroupedBars } from '../components/charts.jsx';
import { humanize, num, SEGMENT_SHORT } from '../lib/format.js';

const SHORT_MODEL = { 'Historical-Median Baseline': 'Median baseline', 'Random Forest Regressor': 'Random forest', 'Gradient Boosting Regressor': 'Gradient boosting' };

export default function Experiments({ state }) {
  const ex = state.experiments;
  if (!ex) return <div className="page"><Empty title="Phase 2 quality report not found" /></div>;
  const models = [...new Set(ex.metrics.map((m) => m.model))];
  const splits = [...new Set(ex.metrics.map((m) => m.split))];
  const colors = { [splits[0]]: 'var(--s1)', [splits[1]]: 'var(--s2)' };
  const bars = ex.metrics.map((m) => ({ category: m.model, group: m.split, value: m.mae,
    extra: [{ label: 'RMSE', value: num(m.rmse) }, { label: 'R²', value: num(m.r2, 3) }] }));
  const passed = ex.checks.filter((c) => c.passed).length;

  return (
    <div className="page">
      <div className="stat-row">
        <Stat label="Selected model" value="Gradient boosting" sub={`run ${ex.run_id.slice(0, 8)}`} />
        <Stat label="Train / validation / test" value={`${ex.split_counts.train} / ${ex.split_counts.validation} / ${ex.split_counts.test}`} sub="split by date, no leakage" />
        <Stat label="Quality checks" value={`${passed}/${ex.checks.length}`} sub="all required to register" />
        <Stat label="Validation MAE" value={`${num(ex.metrics.find((m) => m.model === ex.candidate)?.mae)} min`} sub="the approved error level" />
      </div>

      <div className="grid-2 wide-left">
        <Card title="Model comparison" subtitle="MAE in minutes · lower is better · selection on validation only">
          <Legend items={splits.map((s) => ({ label: s, color: colors[s] }))} />
          <GroupedBars data={bars} categories={models} groups={splits} colors={colors} yLabel="MAE (min)" categoryLabel={(m) => SHORT_MODEL[m] || m} />
        </Card>
        <Card title="Quality gate that approved v1" subtitle="Phase 2 · every check must pass">
          <ul className="checklist">
            {ex.checks.map((check) => (
              <li key={check.name}>
                <Status status={check.passed ? 'PASS' : 'FAIL'} compact />
                <span>{humanize(check.name)}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card title="Metrics table">
        <Table rows={ex.metrics} columns={[
          { key: 'model', label: 'Model', render: (r) => SHORT_MODEL[r.model] || r.model },
          { key: 'split', label: 'Split' },
          { key: 'mae', label: 'MAE', align: 'right', render: (r) => num(r.mae) },
          { key: 'rmse', label: 'RMSE', align: 'right', render: (r) => num(r.rmse) },
          { key: 'mape', label: 'MAPE %', align: 'right', render: (r) => num(r.mape, 1) },
          { key: 'r2', label: 'R²', align: 'right', render: (r) => num(r.r2, 3) },
        ]} />
      </Card>

      {ex.test_by_segment.length > 0 && (
        <Card title="Held-out error by segment" subtitle="8 July test day">
          <Table dense rows={ex.test_by_segment} columns={[
            { key: 'model', label: 'Model', render: (r) => SHORT_MODEL[r.model] || r.model },
            { key: 'segment_id', label: 'Segment', render: (r) => SEGMENT_SHORT[r.segment_id] || r.segment_id },
            { key: 'sample_count', label: 'Trips', align: 'right' },
            { key: 'mae_minutes', label: 'MAE', align: 'right', render: (r) => num(r.mae_minutes) },
            { key: 'rmse_minutes', label: 'RMSE', align: 'right', render: (r) => num(r.rmse_minutes) },
          ]} />
        </Card>
      )}
    </div>
  );
}
