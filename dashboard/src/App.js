import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';

const API_BASE = 'http://localhost:8000';
const WS_URL = 'ws://localhost:8000/ws/agent-log';

const SEVERITY_CONFIG = {
  CRITICAL: { color: '#ff2b5e', bg: 'rgba(255,43,94,0.08)', label: 'CRITICAL', icon: '◉' },
  HIGH: { color: '#ff8c42', bg: 'rgba(255,140,66,0.08)', label: 'HIGH', icon: '◈' },
  MEDIUM: { color: '#ffd166', bg: 'rgba(255,209,102,0.08)', label: 'MEDIUM', icon: '◇' },
  LOW: { color: '#06d6a0', bg: 'rgba(6,214,160,0.08)', label: 'LOW', icon: '○' },
};

const ACTION_LABELS = {
  auto_refund: { label: 'Auto Refund', color: '#06d6a0', icon: '↩' },
  block_and_flag: { label: 'Blocked', color: '#ff2b5e', icon: '⊘' },
  block_refund: { label: 'Refund Blocked', color: '#ff2b5e', icon: '⊘' },
  fraud_alert: { label: 'Fraud Alert', color: '#ff2b5e', icon: '⚡' },
  flag_for_review: { label: 'Review', color: '#ffd166', icon: '◊' },
  escalate_to_support: { label: 'Escalated', color: '#ff8c42', icon: '↑' },
  cancel_duplicate: { label: 'Cancelled', color: '#06d6a0', icon: '✕' },
  hold_for_confirmation: { label: 'On Hold', color: '#ffd166', icon: '⏸' },
  flag_unusual_activity: { label: 'Flagged', color: '#ffd166', icon: '⚑' },
  flag_over_settlement: { label: 'Over-Settlement', color: '#ff8c42', icon: '△' },
  no_action: { label: 'No Action', color: '#555', icon: '—' },
};

const ANOMALY_TYPE_ICONS = {
  settlement_shortfall: '₹',
  settlement_excess: '₹',
  over_settlement: '₹',
  under_settlement: '₹',
  duplicate_transaction: '⊕',
  refund_not_processed: '↩',
  unmatched_refund: '↩',
  refund_mismatch: '↩',
  fraud_suspected: '⚡',
  suspicious_transaction: '⚡',
  unusual_activity: '⚡',
  chargeback_risk: '⚠',
  missing_transaction: '?',
  late_settlement: '⏱',
  currency_mismatch: '¤',
};

const EXECUTION_STATUS_CONFIG = {
  EXECUTED: { label: 'EXECUTED', color: '#06d6a0', bg: 'rgba(6,214,160,0.12)', icon: '✓' },
  SIMULATED: { label: 'SIMULATED', color: '#73b8ff', bg: 'rgba(115,184,255,0.12)', icon: '⟳' },
  FLAGGED_ONLY: { label: 'FLAGGED', color: '#ffd166', bg: 'rgba(255,209,102,0.12)', icon: '⚑' },
  'FLAGGED ONLY': { label: 'FLAGGED', color: '#ffd166', bg: 'rgba(255,209,102,0.12)', icon: '⚑' },
  FLAGGED: { label: 'FLAGGED', color: '#ffd166', bg: 'rgba(255,209,102,0.12)', icon: '⚑' },
  DISMISSED: { label: 'DISMISSED', color: '#555', bg: 'rgba(85,85,85,0.12)', icon: '—' },
};

function formatPaise(paise) {
  if (!paise && paise !== 0) return '—';
  return `₹${(paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
}

function timeAgo(isoString) {
  if (!isoString) return '';
  const diff = Date.now() - new Date(isoString).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

// ─── AnimatedCounter ──────────────────────────────────
function AnimatedCounter({ value, color, duration = 1200 }) {
  const [display, setDisplay] = useState(0);
  const prevValue = useRef(0);

  useEffect(() => {
    const start = prevValue.current;
    const end = value;
    if (start === end) return;
    const startTime = Date.now();
    const animate = () => {
      const elapsed = Date.now() - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = Math.round(start + (end - start) * eased);
      setDisplay(current);
      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        prevValue.current = end;
      }
    };
    requestAnimationFrame(animate);
  }, [value, duration]);

  return <span style={{ color }}>{display}</span>;
}

// ─── SummaryBar ────────────────────────────────────────
function SummaryBar({ summary, scanning, resultsCount, totalExpected, statusFilter, onStatusFilter }) {
  const stats = [
    { key: 'total', label: 'ANOMALIES', value: summary.total_anomalies || 0, color: '#73b8ff' },
    { key: 'fixed', label: 'AUTO-FIXED', value: summary.auto_fixed || 0, color: '#06d6a0' },
    { key: 'flagged', label: 'FLAGGED', value: summary.flagged || 0, color: '#ff2b5e' },
    { key: 'review', label: 'NEEDS REVIEW', value: summary.pending_review || 0, color: '#ffd166' },
  ];

  return (
    <div className="summary-bar">
      {stats.map(s => (
        <div
          key={s.key}
          className={'summary-stat' + (s.value > 0 ? ' has-value' : '') + (statusFilter === s.key ? ' active-filter' : '')}
          onClick={() => onStatusFilter(statusFilter === s.key ? null : s.key)}
          title={`Click to ${statusFilter === s.key ? 'clear' : 'filter by ' + s.label}`}
        >
          <span className="stat-value">
            <AnimatedCounter value={s.value} color={s.color} />
          </span>
          <span className="stat-label">{s.label}</span>
        </div>
      ))}
      <div className="summary-text-wrap">
        {scanning ? (
          <div className="scanning-status">
            <span className="scanning-text">
              <span className="pulse-dot" />
              <span>Agent scanning transactions...</span>
            </span>
            {resultsCount > 0 && (
              <span className="scan-progress">
                Analyzing {resultsCount}/{totalExpected || '?'} anomalies...
              </span>
            )}
            <div className="scan-progress-bar">
              <div
                className="scan-progress-fill"
                style={{ width: totalExpected ? ((resultsCount / totalExpected) * 100) + '%' : '60%' }}
              />
            </div>
          </div>
        ) : summary.summary_text ? (
          <span className="summary-sentence">{summary.summary_text}</span>
        ) : (
          <span className="idle-text">Ready to scan</span>
        )}
      </div>
    </div>
  );
}

// ─── AnomalyCard ───────────────────────────────────────
function AnomalyCard({ result, index, resultIndex, onApprove, onDismiss }) {
  const [expanded, setExpanded] = useState(false);
  const [actionLoading, setActionLoading] = useState(null); // 'approve' | 'dismiss' | null
  const { anomaly, decision } = result;
  const sev = SEVERITY_CONFIG[anomaly.severity] || SEVERITY_CONFIG.MEDIUM;
  const action = ACTION_LABELS[decision.action] || ACTION_LABELS.no_action;
  const execRaw = result.execution?.status?.toUpperCase() || '';
  const execStatus = EXECUTION_STATUS_CONFIG[execRaw] || null;
  const typeIcon = ANOMALY_TYPE_ICONS[anomaly.type] || '●';
  const isDismissed = execRaw === 'DISMISSED';
  const isActioned = execRaw === 'EXECUTED' && result.execution?.method === 'merchant_approved';
  const isLLMReasoned = decision.confidence !== 0.8 || !decision.reasoning?.startsWith('Rule-based');
  const apiAttempted = result.execution?.method === 'pine_labs_api_attempted' || result.execution?.method === 'pine_labs_api';

  const handleApprove = async (e) => {
    e.stopPropagation();
    setActionLoading('approve');
    try {
      await onApprove(resultIndex);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDismiss = async (e) => {
    e.stopPropagation();
    setActionLoading('dismiss');
    try {
      await onDismiss(resultIndex);
    } finally {
      setActionLoading(null);
    }
  };

  const showButtons = !isDismissed && !isActioned &&
    (execStatus?.label === 'FLAGGED' || (!result.execution && decision.action !== 'auto_refund' && decision.action !== 'cancel_duplicate'));

  return (
    <div
      className={'anomaly-card' + (expanded ? ' expanded' : '') + (isDismissed ? ' dismissed' : '')}
      style={{ '--accent': sev.color, animationDelay: (index * 0.08) + 's' }}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="card-header">
        <div className="card-left">
          <span className="anomaly-type-icon">{typeIcon}</span>
          <span className="severity-badge" style={{ background: sev.bg, color: sev.color }}>
            {sev.icon} {sev.label}
          </span>
          <span className="anomaly-type">{anomaly.type.replace(/_/g, ' ')}</span>
        </div>
        <div className="card-right">
          {execStatus && (
            <span className="exec-status-badge" style={{ background: execStatus.bg, color: execStatus.color }}>
              {execStatus.icon === '✓' ? (
                <span className="checkmark-anim">{execStatus.icon}</span>
              ) : execStatus.icon}{' '}
              {execStatus.label}
            </span>
          )}
          <span className="action-badge" style={{ background: action.color + '18', color: action.color }}>
            {action.icon} {action.label}
          </span>
        </div>
      </div>

      <div className="card-body">
        <span className="order-id">{anomaly.order_id}</span>
        <span className="confidence">
          <span className="confidence-bar-wrap">
            <span
              className="confidence-bar-fill"
              style={{
                width: Math.round((decision.confidence || 0) * 100) + '%',
                background: (decision.confidence || 0) > 0.8 ? 'var(--accent-green)' : (decision.confidence || 0) > 0.5 ? 'var(--accent-yellow)' : 'var(--accent-red)'
              }}
            />
          </span>
          {Math.round((decision.confidence || 0) * 100)}%
        </span>
      </div>

      <div className="card-summary">{decision.merchant_summary}</div>

      {/* Reasoning preview — always visible */}
      {decision.reasoning && !expanded && (
        <div className="reasoning-preview">
          <span className={`reasoning-source ${isLLMReasoned ? 'llm' : 'rule'}`}>
            {isLLMReasoned ? 'Claude AI' : 'Rule Engine'}
          </span>
          <span className="reasoning-preview-text">
            {decision.reasoning.length > 120 ? decision.reasoning.slice(0, 120) + '...' : decision.reasoning}
          </span>
        </div>
      )}

      {expanded && (
        <div className="card-details">
          <div className="detail-section reasoning-section">
            <h4>
              Agent Reasoning
              <span className={`reasoning-source-badge ${isLLMReasoned ? 'llm' : 'rule'}`}>
                {isLLMReasoned ? 'Claude Sonnet' : 'Rule Engine'}
              </span>
            </h4>
            <div className="reasoning-bubble">
              <div className={`reasoning-avatar ${isLLMReasoned ? 'llm' : 'rule'}`}>
                {isLLMReasoned ? 'AI' : 'RE'}
              </div>
              <div className="reasoning-content">
                <p>{decision.reasoning}</p>
              </div>
            </div>
          </div>

          {/* Show Pine Labs API call status if attempted */}
          {apiAttempted && (
            <div className="detail-section api-call-section">
              <h4>Pine Labs API</h4>
              <div className="api-call-badge">
                <span className="api-dot live" />
                Real API call to Pine Labs sandbox
                {result.execution?.api_status_code && (
                  <span className="api-status-code">HTTP {result.execution.api_status_code}</span>
                )}
              </div>
              {result.execution?.note && (
                <p className="api-note">{result.execution.note}</p>
              )}
            </div>
          )}
          <div className="detail-section">
            <h4>Details</h4>
            <div className="detail-grid">
              {Object.entries(anomaly.details).map(([key, val]) => (
                <div key={key} className="detail-row">
                  <span className="detail-key">{key.replace(/_/g, ' ')}</span>
                  <span className="detail-val">
                    {typeof val === 'number' && (key.includes('amount') || key === 'shortfall' || key === 'excess')
                      ? formatPaise(val)
                      : Array.isArray(val) ? val.join(', ') : String(val)}
                  </span>
                </div>
              ))}
            </div>
          </div>
          {isActioned && (
            <div className="detail-section approve-section">
              <span className="action-done-badge approved">Approved</span>
            </div>
          )}
          {isDismissed && (
            <div className="detail-section approve-section">
              <span className="action-done-badge dismissed-label">Dismissed</span>
            </div>
          )}
          {showButtons && (
            <div className="detail-section approve-section">
              <button className="approve-btn" onClick={handleApprove} disabled={!!actionLoading}>
                {actionLoading === 'approve' ? (
                  <span className="btn-spinner" />
                ) : (
                  <span className="approve-icon">✓</span>
                )}
                {actionLoading === 'approve' ? ' Approving...' : ' Approve Action'}
              </button>
              <button className="dismiss-btn" onClick={handleDismiss} disabled={!!actionLoading}>
                {actionLoading === 'dismiss' ? 'Dismissing...' : 'Dismiss'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── AgentLog ──────────────────────────────────────────
function AgentLog({ logs, scanning }) {
  const logRef = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (logRef.current && autoScroll) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleScroll = () => {
    if (!logRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = logRef.current;
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40);
  };

  const typeStyles = {
    info: { color: '#8a8a8a', prefix: '>' },
    warning: { color: '#ffd166', prefix: '>' },
    processing: { color: '#73b8ff', prefix: '>' },
    decision: { color: '#06d6a0', prefix: '>' },
    summary: { color: '#06d6a0', prefix: '>' },
    error: { color: '#ff2b5e', prefix: '>' },
  };

  const typeLabels = {
    info: 'INFO',
    warning: 'WARN',
    processing: 'PROC',
    decision: 'DONE',
    summary: 'SUMM',
    error: 'ERR!',
  };

  return (
    <div className="agent-log" ref={logRef} onScroll={handleScroll}>
      <div className="log-header">
        <span className="log-title">
          <span className="terminal-icon">{'>_'}</span> AGENT LOG
        </span>
        <span className="log-count">{logs.length} entries</span>
      </div>
      <div className="log-entries">
        {logs.map((log, i) => {
          const style = typeStyles[log.type] || typeStyles.info;
          const label = typeLabels[log.type] || 'INFO';
          return (
            <div key={i} className={'log-entry log-type-' + (log.type || 'info')} style={{ animationDelay: (i * 0.02) + 's' }}>
              <span className="log-prefix" style={{ color: style.color }}>{style.prefix}</span>
              <span className={'log-type-label log-label-' + (log.type || 'info')}>{label}</span>
              <span className="log-time">{log.time ? new Date(log.time).toLocaleTimeString() : ''}</span>
              <span className="log-msg" style={{ color: style.color }}>{log.message}</span>
            </div>
          );
        })}
        {scanning && (
          <div className="log-entry log-cursor-line">
            <span className="log-prefix" style={{ color: '#73b8ff' }}>{'>'}</span>
            <span className="blinking-cursor">_</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── App ───────────────────────────────────────────────
function App() {
  const [results, setResults] = useState([]);
  const [summary, setSummary] = useState({});
  const [logs, setLogs] = useState([]);
  const [scanning, setScanning] = useState(false);
  const [connected, setConnected] = useState(false);
  const [filter, setFilter] = useState('ALL');
  const [theme, setTheme] = useState(() => localStorage.getItem('mm-theme') || 'dark');
  const [webhookNotif, setWebhookNotif] = useState(null);
  const [statusFilter, setStatusFilter] = useState(null); // 'total' | 'fixed' | 'flagged' | 'review' | null
  const wsRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('mm-theme', theme);
  }, [theme]);

  const connectWs = useCallback(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setTimeout(connectWs, 3000);
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === 'scan_started') {
        setScanning(true);
        setResults([]);
        setLogs([]);
        setSummary({});
      } else if (msg.type === 'log_entry') {
        setLogs(prev => [...prev, msg.data]);
      } else if (msg.type === 'anomaly_result') {
        setResults(prev => [...prev, msg.data]);
      } else if (msg.type === 'scan_complete') {
        setScanning(false);
        setResults(msg.data.results || []);
        setSummary(msg.data.summary || {});
        setLogs(msg.data.log_entries || []);
      } else if (msg.type === 'full_state') {
        setResults(msg.data.results || []);
        setSummary(msg.data.summary || {});
        setLogs(msg.data.log_entries || []);
      } else if (msg.type === 'webhook_received') {
        const { event_type, order_id } = msg.data;
        setWebhookNotif(`Webhook: ${event_type}${order_id ? ` on ${order_id}` : ''} triggered scan`);
        setTimeout(() => setWebhookNotif(null), 6000);
      } else if (msg.type === 'action_update') {
        const { index, result } = msg.data;
        setResults(prev => {
          const updated = [...prev];
          if (index >= 0 && index < updated.length) {
            updated[index] = result;
          }
          return updated;
        });
      }
    };
  }, []);

  useEffect(() => {
    connectWs();
    // Load existing data
    fetch(`${API_BASE}/api/anomalies`)
      .then(r => r.json())
      .then(data => {
        if (data.results?.length) {
          setResults(data.results);
          setSummary(data.summary || {});
          setLogs(data.log_entries || []);
        }
      })
      .catch(() => {});
    return () => wsRef.current?.close();
  }, [connectWs]);

  const triggerScan = async () => {
    setScanning(true);
    setResults([]);
    setLogs([]);
    setSummary({});
    try {
      await fetch(`${API_BASE}/api/scan`, { method: 'POST' });
    } catch (e) {
      setScanning(false);
    }
  };

  const handleApprove = async (resultIndex) => {
    try {
      const resp = await fetch(`${API_BASE}/api/actions/${resultIndex}/approve`, { method: 'POST' });
      const data = await resp.json();
      if (data.status === 'approved') {
        setResults(prev => {
          const updated = [...prev];
          if (updated[resultIndex]) {
            updated[resultIndex] = { ...updated[resultIndex], execution: data.execution };
          }
          return updated;
        });
      }
    } catch (e) {
      console.error('Approve failed:', e);
    }
  };

  const handleDismiss = async (resultIndex) => {
    try {
      const resp = await fetch(`${API_BASE}/api/actions/${resultIndex}/dismiss`, { method: 'POST' });
      const data = await resp.json();
      if (data.status === 'dismissed') {
        setResults(prev => {
          const updated = [...prev];
          if (updated[resultIndex]) {
            updated[resultIndex] = { ...updated[resultIndex], execution: { status: 'dismissed', reason: 'Merchant dismissed' } };
          }
          return updated;
        });
      }
    } catch (e) {
      console.error('Dismiss failed:', e);
    }
  };

  // Classify each result into a status category
  const classifyStatus = (r) => {
    const execStatus = r.execution?.status?.toUpperCase() || '';
    const action = r.decision?.action || '';
    // Auto-fixed: executed or simulated actions (auto_refund, cancel_duplicate)
    if (execStatus === 'EXECUTED' || execStatus === 'SIMULATED') {
      if (['auto_refund', 'cancel_duplicate'].includes(action)) return 'fixed';
    }
    // Flagged: critical blocks (block_and_flag, block_refund, fraud_alert)
    if (['block_and_flag', 'block_refund', 'fraud_alert'].includes(action)) return 'flagged';
    // Needs review: everything else that requires merchant attention
    if (['flag_for_review', 'hold_for_confirmation', 'flag_unusual_activity', 'flag_over_settlement', 'escalate_to_support'].includes(action)) return 'review';
    // Default
    return 'total';
  };

  const indexedResults = results.map((r, i) => ({ ...r, _resultIndex: i, _statusCategory: classifyStatus(r) }));

  const filteredResults = indexedResults.filter(r => {
    // Severity filter
    if (filter !== 'ALL' && r.anomaly.severity !== filter) return false;
    // Status filter (null = show all, 'total' = show all)
    if (statusFilter && statusFilter !== 'total' && r._statusCategory !== statusFilter) return false;
    return true;
  });

  const severityFilters = ['ALL', 'CRITICAL', 'HIGH', 'MEDIUM'];

  return (
    <div className="app">
      {/* Animated gradient background */}
      <div className="bg-gradient" />
      {/* Grain overlay */}
      <div className="grain" />

      {/* Webhook notification banner */}
      {webhookNotif && (
        <div className="webhook-banner">
          <span className="webhook-banner-icon">⚡</span>
          <span>{webhookNotif}</span>
          <button className="webhook-banner-close" onClick={() => setWebhookNotif(null)}>×</button>
        </div>
      )}

      {/* Header */}
      <header className="app-header">
        <div className="brand">
          <div className="brand-icon">
            <span className="brand-icon-inner">◈</span>
          </div>
          <div>
            <h1>MerchantMind</h1>
            <p className="tagline">Autonomous Reconciliation Agent</p>
          </div>
          <span className="partner-badge">Pine Labs × MerchantMind</span>
        </div>
        <div className="header-right">
          <span className="merchant-id">MID: 121478</span>
          <button
            className="theme-toggle"
            onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? '☀' : '☽'}
          </button>
          <div className={`connection-indicator ${connected ? 'connected' : ''}`}>
            <span className="conn-dot" />
            {connected ? 'LIVE' : 'OFFLINE'}
          </div>
          <button
            className={`scan-btn ${scanning ? 'scanning' : ''}`}
            onClick={triggerScan}
            disabled={scanning}
          >
            {scanning ? (
              <>
                <span className="scan-rings">
                  <span className="ring ring-1" />
                  <span className="ring ring-2" />
                  <span className="ring ring-3" />
                </span>
                Scanning...
              </>
            ) : (
              <>
                <span className="scan-icon">◉</span> Run Agent Scan
              </>
            )}
          </button>
        </div>
      </header>

      {/* Summary */}
      <SummaryBar
        summary={summary}
        scanning={scanning}
        resultsCount={results.length}
        totalExpected={summary.total_anomalies || 15}
        statusFilter={statusFilter}
        onStatusFilter={setStatusFilter}
      />

      {/* Main content */}
      <div className="main-content">
        <div className="anomalies-panel">
          <div className="panel-header">
            <h2>
              {statusFilter === 'fixed' ? 'Auto-Fixed Transactions' :
               statusFilter === 'flagged' ? 'Flagged Anomalies' :
               statusFilter === 'review' ? 'Needs Review' :
               'Detected Anomalies'}
              {filteredResults.length > 0 && (
                <span className="results-count">{filteredResults.length}</span>
              )}
              {statusFilter && (
                <button
                  className="clear-filter-btn"
                  onClick={() => setStatusFilter(null)}
                  title="Clear filter"
                >×</button>
              )}
            </h2>
            <div className="filters">
              {severityFilters.map(f => (
                <button
                  key={f}
                  className={`filter-btn ${filter === f ? 'active' : ''}`}
                  onClick={() => setFilter(f)}
                  style={f !== 'ALL' ? { '--filter-color': SEVERITY_CONFIG[f]?.color } : {}}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>
          <div className="anomaly-list">
            {filteredResults.length === 0 && !scanning && (
              <div className="empty-state">
                <span className="empty-icon">◇</span>
                <p>No anomalies detected yet. Run a scan to begin.</p>
              </div>
            )}
            {scanning && filteredResults.length === 0 && (
              <div className="empty-state scanning-state">
                <div className="radar-sweep">
                  <div className="radar-ring" />
                  <div className="radar-ring radar-ring-2" />
                  <div className="radar-line" />
                </div>
                <p>Agent is analyzing transactions...</p>
              </div>
            )}
            {filteredResults.map((r, i) => (
              <AnomalyCard
                key={`${r.anomaly.order_id}-${r.anomaly.type}`}
                result={r}
                index={i}
                resultIndex={r._resultIndex}
                onApprove={handleApprove}
                onDismiss={handleDismiss}
              />
            ))}
          </div>
        </div>

        <AgentLog logs={logs} scanning={scanning} />
      </div>

      {/* Footer */}
      <footer className="app-footer">
        <span>MerchantMind v1.0</span>
        <span className="footer-badge">
          Powered by <span className="footer-tech">Claude</span> + <span className="footer-tech">LangGraph</span> + <span className="footer-tech">Pine Labs MCP</span>
        </span>
        <span>Pine Labs Playground Hackathon 2025</span>
      </footer>
    </div>
  );
}

export default App;
