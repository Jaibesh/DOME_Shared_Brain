/**
 * CountdownTimer.jsx — Live countdown to ride start time
 * 
 * Urgency levels:
 *   >2hr  → Polaris Blue, calm
 *   1-2hr → Blue with subtle pulse
 *   <1hr  → Epic Red with pulse
 *   <15m  → Red, large, "HURRY!"
 *   0     → "Your ride has started! 🏁"
 */

import { useState, useEffect } from 'react';

export default function CountdownTimer({ targetISO }) {
  const [remaining, setRemaining] = useState(null);

  useEffect(() => {
    if (!targetISO) return;

    const update = () => {
      const now = Date.now();
      const target = new Date(targetISO).getTime();
      const diff = target - now;
      setRemaining(diff);
    };

    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [targetISO]);

  if (remaining === null || !targetISO) {
    return (
      <div className="countdown-wrapper">
        <div className="countdown-time calm">--:--:--</div>
        <div className="countdown-label">Loading...</div>
      </div>
    );
  }

  // Ride has started
  if (remaining <= 0) {
    const hoursAgo = Math.abs(remaining) / 3600000;
    return (
      <div className="countdown-wrapper" style={{ borderColor: 'var(--status-ready)' }}>
        <div className="countdown-time" style={{ color: 'var(--status-ready)' }}>
          {hoursAgo > 12 ? '🏔️' : '🏁'}
        </div>
        <div className="countdown-label" style={{ color: 'var(--status-ready)', fontSize: '1rem' }}>
          {hoursAgo > 12
            ? 'Your adventure has begun! Enjoy the ride!'
            : 'Your ride has started!'}
        </div>
      </div>
    );
  }

  const hours = Math.floor(remaining / 3600000);
  const minutes = Math.floor((remaining % 3600000) / 60000);
  const seconds = Math.floor((remaining % 60000) / 1000);

  const pad = (n) => String(n).padStart(2, '0');
  const timeStr = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;

  // Determine urgency level
  const totalMinutes = remaining / 60000;
  let urgencyClass = 'calm';
  let label = 'Your ride starts in';
  let style = {};

  if (totalMinutes <= 15) {
    urgencyClass = 'urgent';
    label = "HURRY! Your ride departs soon!";
    style = { borderColor: 'var(--epic-red)', boxShadow: '0 0 20px rgba(232, 27, 27, 0.2)' };
  } else if (totalMinutes <= 60) {
    urgencyClass = 'urgent';
    label = 'Your ride starts soon';
    style = { borderColor: 'var(--epic-red)' };
  } else if (totalMinutes <= 120) {
    urgencyClass = 'calm';
    label = 'Your ride starts in';
    style = { borderColor: 'var(--polaris-blue)', animation: 'pulse-calm 3s ease-in-out infinite' };
  }

  return (
    <div className="countdown-wrapper" style={style}>
      <div className="countdown-label" style={{ marginBottom: 'var(--space-sm)' }}>
        ⏱️ {label}
      </div>
      <div className={`countdown-time ${urgencyClass}`}>
        {timeStr}
      </div>
    </div>
  );
}
