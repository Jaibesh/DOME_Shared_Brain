/**
 * StatusIcon.jsx — Reusable status indicator circles
 * 
 * Pure CSS circles (no icon library dependency for status dots).
 * States: ready (green), alert (red), waived (blue), neutral (grey outline)
 */

export default function StatusIcon({ status = 'neutral', size = 'md', className = '' }) {
  const sizeClass = size === 'sm' ? 'sm' : '';
  return (
    <span
      className={`status-dot ${status} ${sizeClass} ${className}`}
      role="img"
      aria-label={status}
    />
  );
}

/**
 * WaiverFraction — Colored text fraction (e.g., "1/2" in red, "2/2" in green)
 * The text itself IS the color indicator — no separate dot.
 */
export function WaiverFraction({ completed = 0, expected = 0 }) {
  const safeExpected = expected < completed ? completed : expected;
  const isComplete = safeExpected > 0 && completed >= safeExpected;
  const cls = isComplete ? 'complete' : 'incomplete';

  return (
    <span className={`waiver-fraction ${cls}`}>
      {completed}/{safeExpected}
    </span>
  );
}

/**
 * DepositBadge — Shows deposit status as a colored badge
 */
export function DepositBadge({ status = 'due' }) {
  const lower = (status || 'due').toLowerCase();

  if (lower === 'collected') {
    return <span className="badge badge-ready">PAID</span>;
  }
  if (lower === 'compensated') {
    return <span className="badge badge-blue">COMP</span>;
  }
  if (lower === 'due') {
    return <span className="badge badge-alert" style={{ fontSize: '0.85rem' }}>$</span>;
  }

  return <span className="badge badge-neutral">{(status || '').toUpperCase()}</span>;
}

/**
 * AABadge — Adventure Assure indicator (informational, shown in detail view)
 */
export function AABadge({ type = 'None' }) {
  if (type === 'None') return null;
  return (
    <span className="badge badge-blue" title={`Adventure Assure: ${type}`}>
      AA
    </span>
  );
}
