import { Card, Empty, Legend, Stat, Table } from '../components/ui.jsx';
import { BoxPlot, GroupedBars } from '../components/charts.jsx';
import { SEGMENT_ORDER, SEGMENT_SHORT, segmentColor, shortHash } from '../lib/format.js';

export default function DataPage({ state }) {
  const data = state.dataset;
  if (!data || !data.available) {
    return <div className="page"><Empty title="Processed traversals not found on this machine" command="dvc pull  (or the Phase 2 data preparation)" /></div>;
  }
  const days = [...new Set(data.per_day.map((r) => r.day))];
  const segments = SEGMENT_ORDER.filter((s) => data.per_day.some((r) => r.segment === s));
  const colors = Object.fromEntries(segments.map((s) => [s, segmentColor(s)]));
  const bars = data.per_day.map((r) => ({ category: r.day, group: r.segment, value: r.count }));
  const boxes = SEGMENT_ORDER.map((s) => data.boxes.find((b) => b.segment === s)).filter(Boolean);

  return (
    <div className="page">
      <div className="stat-row">
        <Stat label="Labelled traversals" value={data.rows} sub="gate-to-gate trips" />
        <Stat label="Service days" value={data.days} sub="July 2019, IST" />
        <Stat label="Road segments" value={data.segments} sub="ORR + Mehrauli–Badarpur" />
        <Stat label="Bus routes" value={data.routes} sub="one primary route per segment" />
      </div>

      <div className="grid-2">
        <Card title="Traversals per day and segment" subtitle="Train 1–3 Jul · validation 5 Jul · test 8 Jul">
          <Legend items={segments.map((s) => ({ label: SEGMENT_SHORT[s], color: colors[s] }))} />
          <GroupedBars data={bars} categories={days} groups={segments} colors={colors} yLabel="Traversals" format={(v) => String(v)}
            categoryLabel={(d) => d.slice(5).replace('-', ' / ')} />
        </Card>
        <Card title="Riding time by segment" subtitle="The label the model learns · box = middle 50%, line = median">
          <BoxPlot boxes={boxes} colorOf={segmentColor} labelOf={(b) => SEGMENT_SHORT[b.segment]} />
        </Card>
      </div>

      <div className="callout">
        Labels are not in the GPS feed. Each one is the time between a bus crossing the entry and exit gate lines of a
        verified road segment, after removing duplicate pings and implausible jumps.
      </div>

      <div className="grid-2">
        <Card title="Source archive days" subtitle="july_19_corrected.zip · Zenodo DOI 10.5281/zenodo.21738157">
          <Table dense rows={data.sources} columns={[
            { key: 'day', label: 'Day' },
            { key: 'sha', label: 'SQLite sha256', render: (r) => <code>{shortHash(r.database_sha256, 14)}</code> },
            { key: 'traversals_retained', label: 'Kept', align: 'right' },
          ]} />
        </Card>
        <Card title="DVC pipeline" subtitle="Reproducible one-day sample">
          <Table dense rows={data.dvc_stages} columns={[
            { key: 'stage', label: 'Stage' },
            { key: 'command', label: 'Command', render: (r) => <code>{r.command}</code> },
            { key: 'locked', label: 'Locked', render: (r) => (r.locked ? 'yes' : 'no') },
          ]} />
        </Card>
      </div>
    </div>
  );
}
