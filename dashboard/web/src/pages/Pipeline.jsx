import { useState } from 'react';
import { Badge, Card, CodeLine, Icon, Status } from '../components/ui.jsx';

const PHASE = { data: 1, version: 1, labels: 1, train: 2, gate: 2, registry: 2, package: 2, deploy: 2, monitor: 3, retrain: 3, rollback: 3 };

export default function Pipeline({ state }) {
  const stages = state.pipeline;
  const [selected, setSelected] = useState(stages.find((s) => s.key === 'monitor')?.key || stages[0].key);
  const active = stages.find((s) => s.key === selected);
  const lanes = [1, 2, 3].map((phase) => ({ phase, stages: stages.filter((s) => PHASE[s.key] === phase) }));
  const laneTitle = { 1: 'Data foundation', 2: 'Build, approve & ship', 3: 'Operate & improve (Phase 3)' };

  return (
    <div className="page">
      <div className="lanes">
        {lanes.map((lane) => (
          <div key={lane.phase} className={`lane lane-${lane.phase}`}>
            <div className="lane-head">
              <Badge tone={lane.phase === 3 ? 'accent' : 'neutral'}>Phase {lane.phase === 1 ? '1–2' : lane.phase}</Badge>
              <strong>{laneTitle[lane.phase]}</strong>
            </div>
            <div className="lane-flow">
              {lane.stages.map((stage, index) => (
                <div key={stage.key} className="flow-item">
                  <button type="button" className={`stage-card status-${stage.status} ${selected === stage.key ? 'selected' : ''}`} onClick={() => setSelected(stage.key)}>
                    <div className="stage-top">
                      <span className="stage-num">{stage.stage.split('.')[0]}</span>
                      <Status status={stage.status} compact />
                    </div>
                    <strong>{stage.stage.replace(/^\d+\.\s*/, '')}</strong>
                    <span className="stage-detail">{stage.detail}</span>
                    <span className="chips">{stage.tools.map((tool) => <span key={tool} className="chip">{tool}</span>)}</span>
                  </button>
                  {index < lane.stages.length - 1 && <span className="flow-arrow"><Icon name="arrow" size={16} /></span>}
                </div>
              ))}
            </div>
          </div>
        ))}
        <div className="loop-note">
          <Icon name="refresh" size={16} />
          <span>The loop closes: new labelled days feed the next replay, alarms open retraining candidates, and the gate decides what serves.</span>
        </div>
      </div>

      {active && (
        <Card title={active.stage} subtitle={active.detail} action={<Status status={active.status} />}>
          <div className="grid-2 tight">
            <div>
              <p className="label">Evidence</p>
              <CodeLine text={active.evidence} />
            </div>
            <div>
              <p className="label">Tools</p>
              <span className="chips">{active.tools.map((tool) => <span key={tool} className="chip chip-lg">{tool}</span>)}</span>
            </div>
          </div>
        </Card>
      )}

      <Card title="Reproduce Phase 3" subtitle="From the repository root, in .venv-dev">
        <div className="stack">
          <CodeLine text="python -m scripts.run_phase3 --write-evidence" />
          <CodeLine text="python -m dashboard.server" />
        </div>
      </Card>
    </div>
  );
}
