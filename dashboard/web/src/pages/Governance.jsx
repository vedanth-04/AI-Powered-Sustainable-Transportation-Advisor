import { useEffect, useState } from 'react';
import { getText } from '../api.js';
import { Card, Icon, Segmented, Status } from '../components/ui.jsx';
import { markdownToHtml } from '../lib/markdown.js';

const SUTRAS = [
  ['Trust', 'Hash-pinned artifacts, reproducible pipeline, honest "historical replay" labels'],
  ['People First', 'Advisory output only; the traveller decides; no rider data'],
  ['Innovation over Restraint', 'Proportionate controls instead of approval layers the risk does not need'],
  ['Fairness & Equity', 'Per-segment monitoring and a no-segment-regression gate'],
  ['Accountability', 'Named roles, actor on every change, tamper-evident audit log'],
  ['Understandable by Design', 'Model card, plain-language gate checks, version diffs'],
  ['Safety, Resilience & Sustainability', 'Drift detection, quarantine, rollback drill, scope limits'],
];
const DOC_LABEL = { governance: 'Governance policy', model_card: 'Model card', presentation: 'Phase 3 presentation', guide: 'Run guide' };

export default function Governance({ state }) {
  const { controls, docs } = state.governance;
  const [doc, setDoc] = useState(docs[0] || null);
  const [html, setHtml] = useState('');
  const areas = [...new Set(controls.map((c) => c.area))];
  const passed = controls.filter((c) => c.passed).length;

  useEffect(() => {
    if (!doc) return undefined;
    let cancelled = false;
    getText(`/api/doc/${doc}`).then((text) => !cancelled && setHtml(markdownToHtml(text))).catch((exc) => !cancelled && setHtml(`<p>${exc.message}</p>`));
    return () => { cancelled = true; };
  }, [doc]);

  return (
    <div className="page">
      <section className="gov-hero">
        <div className="gov-score">
          <span className="big">{passed}/{controls.length}</span>
          <span className="muted">controls with live evidence</span>
        </div>
        <div className="gov-risk">
          <div><span className="label">Decision type</span><strong>Advisory</strong><span className="muted small">a person picks the journey</span></div>
          <div><span className="label">Personal data</span><strong>None</strong><span className="muted small">bus GPS only, no rider records</span></div>
          <div><span className="label">Cost of an error</span><strong>Minutes</strong><span className="muted small">not safety, money or rights</span></div>
          <div><span className="label">Therefore</span><strong>Proportionate</strong><span className="muted small">traceability, fairness, fast recovery</span></div>
        </div>
      </section>

      <div className="control-areas">
        {areas.map((area) => (
          <Card key={area} title={area}>
            <ul className="control-list">
              {controls.filter((c) => c.area === area).map((c) => (
                <li key={c.control}>
                  <Status status={c.passed ? 'PASS' : 'MISSING'} compact />
                  <div><strong>{c.control}</strong><span className="muted small">{c.evidence}</span></div>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>

      <Card title="Mapped to MeitY's India AI Governance Guidelines (Nov 2025)" subtitle="The seven sutras and how this project applies each">
        <div className="sutra-grid">
          {SUTRAS.map(([name, text], i) => (
            <div key={name} className="sutra">
              <span className="sutra-num">{i + 1}</span>
              <strong>{name}</strong>
              <p className="muted small">{text}</p>
            </div>
          ))}
        </div>
      </Card>

      {doc && (
        <Card title="Documents" action={<Segmented size="sm" value={doc} onChange={setDoc} options={docs.map((d) => ({ value: d, label: DOC_LABEL[d] || d }))} />}>
          {/* Rendered from the repository's own Markdown; the renderer escapes all HTML first. */}
          <article className="markdown" dangerouslySetInnerHTML={{ __html: html }} />
        </Card>
      )}
      {!doc && <p className="muted"><Icon name="info" size={14} /> Governance documents not found in docs/.</p>}
    </div>
  );
}
