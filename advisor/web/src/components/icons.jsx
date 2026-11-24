const base = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2,
  strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true };

export const BusIcon = (p) => (
  <svg {...base} {...p}><rect x="4" y="3" width="16" height="15" rx="3" /><path d="M4 11h16M8 21v-3M16 21v-3" /><circle cx="8" cy="14.5" r="0.8" fill="currentColor" /><circle cx="16" cy="14.5" r="0.8" fill="currentColor" /></svg>
);
export const MetroIcon = (p) => (
  <svg {...base} {...p}><rect x="5" y="2.5" width="14" height="15" rx="4" /><path d="M5 10h14M9 21l1.5-3.5M15 21l-1.5-3.5" /><circle cx="9" cy="13.5" r="0.8" fill="currentColor" /><circle cx="15" cy="13.5" r="0.8" fill="currentColor" /></svg>
);
export const TrainIcon = (p) => (
  <svg {...base} {...p}><path d="M6 3h12l1 10a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4z" /><path d="M5.5 9h13M8 21l2-4M16 21l-2-4M7 21h10" /></svg>
);
export const WalkIcon = (p) => (
  <svg {...base} {...p}><circle cx="13" cy="4" r="1.8" /><path d="M10 21l2-6-2-3 1-5 3 3 3 1M12 15l3 6M10 7l-3 3" /></svg>
);
export const SwapIcon = (p) => (
  <svg {...base} {...p}><path d="M7 4v16M3 8l4-4 4 4M17 20V4M13 16l4 4 4-4" /></svg>
);
export const LeafIcon = (p) => (
  <svg {...base} {...p}><path d="M5 19c0-9 6-14 15-14 0 9-5 15-14 15" /><path d="M5 19c3-4 6-6 9-7" /></svg>
);
export const ClockIcon = (p) => (
  <svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
);
export const RupeeIcon = (p) => (
  <svg {...base} {...p}><path d="M7 4h10M7 9h10M13 4c3 0 4 2 4 5s-2 5-5 5H8l7 7" /></svg>
);
export const ChangeIcon = (p) => (
  <svg {...base} {...p}><path d="M4 7h13l-3-3M20 17H7l3 3" /></svg>
);
export const PinIcon = (p) => (
  <svg {...base} {...p}><path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z" /><circle cx="12" cy="10" r="2.5" /></svg>
);
export const InfoIcon = (p) => (
  <svg {...base} {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.5" /></svg>
);
export const SparkIcon = (p) => (
  <svg {...base} {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M6 18l2.5-2.5M15.5 8.5L18 6" /></svg>
);

export function ModeIcon({ mode, ...rest }) {
  if (mode === 'bus') return <BusIcon {...rest} />;
  if (mode === 'metro') return <MetroIcon {...rest} />;
  if (mode === 'rail') return <TrainIcon {...rest} />;
  if (mode === 'cab') return <CabIcon {...rest} />;
  return <WalkIcon {...rest} />;
}
export const CrosshairIcon = (p) => (
  <svg {...base} {...p}><circle cx="12" cy="12" r="7" /><path d="M12 2v4M12 18v4M2 12h4M18 12h4" /><circle cx="12" cy="12" r="1.5" fill="currentColor" /></svg>
);
export const MapPickIcon = (p) => (
  <svg {...base} {...p}><path d="M9 4L3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5z" /><path d="M9 4v13M15 6.5v13" /></svg>
);
export const XIcon = (p) => (
  <svg {...base} {...p}><path d="M6 6l12 12M18 6L6 18" /></svg>
);
export const BackIcon = (p) => (
  <svg {...base} {...p}><path d="M15 6l-6 6 6 6" /></svg>
);
export const BrainIcon = (p) => (
  <svg {...base} {...p}><path d="M9 4a3 3 0 0 0-3 3v.5A3 3 0 0 0 4 10.5 3 3 0 0 0 5 13a3 3 0 0 0 1 4.5A3 3 0 0 0 9 20h0a2 2 0 0 0 3-1.7V5.7A2 2 0 0 0 9 4zM15 4a3 3 0 0 1 3 3v.5a3 3 0 0 1 2 3 3 3 0 0 1-1 2.5 3 3 0 0 1-1 4.5A3 3 0 0 1 15 20h0a2 2 0 0 1-3-1.7" /></svg>
);
export const ChevronDownIcon = (p) => (
  <svg {...base} {...p}><path d="M6 9l6 6 6-6" /></svg>
);
export const ChevronUpIcon = (p) => (
  <svg {...base} {...p}><path d="M6 15l6-6 6 6" /></svg>
);
export const CabIcon = (p) => (
  <svg {...base} {...p}><path d="M5 11l1.6-4.2A2 2 0 0 1 8.5 5.5h7a2 2 0 0 1 1.9 1.3L19 11" /><rect x="3" y="11" width="18" height="6" rx="2" /><path d="M6 17v2M18 17v2M9.5 3.5h5" /><circle cx="7" cy="14" r="0.9" fill="currentColor" /><circle cx="17" cy="14" r="0.9" fill="currentColor" /></svg>
);
