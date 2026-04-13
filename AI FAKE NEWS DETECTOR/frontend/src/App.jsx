import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ShieldCheck, ShieldAlert, ShieldX, ShieldQuestion,
  Search, FileText, Link as LinkIcon, Loader2,
  ArrowRight, Clock, Info, ExternalLink, Zap,
  CheckCircle2, XCircle, AlertTriangle, Database, Globe,
} from 'lucide-react';
import { CircularProgressbar, buildStyles } from 'react-circular-progressbar';
import 'react-circular-progressbar/dist/styles.css';

import { checkUrlSafety, factCheckContent, getHistory } from './api';

// ─── Helpers ─────────────────────────────────────────────────────────────────

const VERDICT_CONFIG = {
  Real:       { color: 'teal',   icon: CheckCircle2,    label: 'Real / Verified',  gradient: 'from-teal-500/20 to-teal-900/10',  ring: 'ring-teal-500/40',   text: 'text-teal-400',   bar: '#14b8a6' },
  Fake:       { color: 'red',    icon: XCircle,         label: 'Fake / False',     gradient: 'from-red-500/20 to-red-900/10',    ring: 'ring-red-500/40',    text: 'text-red-400',    bar: '#ef4444' },
  Misleading: { color: 'amber',  icon: AlertTriangle,   label: 'Misleading',       gradient: 'from-amber-500/20 to-amber-900/10',ring: 'ring-amber-500/40',  text: 'text-amber-400',  bar: '#f59e0b' },
  Unknown:    { color: 'gray',   icon: ShieldQuestion,  label: 'Unknown',          gradient: 'from-gray-500/20 to-gray-900/10',  ring: 'ring-gray-500/40',   text: 'text-gray-400',   bar: '#6b7280' },
};

const SAFETY_CONFIG = {
  Safe:       { icon: ShieldCheck,    text: 'text-teal-400',   bg: 'bg-teal-500/10',   border: 'border-teal-500/30',  label: 'Safe'      },
  Suspicious: { icon: ShieldAlert,    text: 'text-amber-400',  bg: 'bg-amber-500/10',  border: 'border-amber-500/30', label: 'Suspicious'},
  Dangerous:  { icon: ShieldX,        text: 'text-red-400',    bg: 'bg-red-500/10',    border: 'border-red-500/30',   label: 'Dangerous' },
  Unknown:    { icon: ShieldQuestion, text: 'text-gray-400',   bg: 'bg-gray-500/10',   border: 'border-gray-500/30',  label: 'Unknown'   },
};

const fadeUp = { initial: { opacity: 0, y: 18 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -10 } };
const scaleFade = { initial: { opacity: 0, scale: 0.95 }, animate: { opacity: 1, scale: 1 }, exit: { opacity: 0, scale: 0.94 } };

// ─── Sub-components ───────────────────────────────────────────────────────────

function TabBar({ active, onChange }) {
  const tabs = [
    { id: 'safety', label: 'Safety Check', icon: ShieldCheck, desc: 'Scan a URL for threats' },
    { id: 'factcheck', label: 'Fact Check', icon: Zap, desc: 'Verify news with Hybrid RAG' },
  ];
  return (
    <div className="flex gap-2 p-1.5 bg-gray-950/80 rounded-2xl border border-gray-800/60 mb-8 backdrop-blur-sm">
      {tabs.map(t => {
        const Icon = t.icon;
        const isActive = active === t.id;
        return (
          <button
            key={t.id}
            id={`tab-${t.id}`}
            onClick={() => onChange(t.id)}
            className={`flex-1 flex flex-col items-center py-3 px-4 rounded-xl text-sm font-semibold transition-all duration-300 ${
              isActive
                ? t.id === 'safety'
                  ? 'bg-gradient-to-br from-teal-500 to-cyan-600 text-white shadow-lg shadow-teal-500/20'
                  : 'bg-gradient-to-br from-violet-500 to-purple-600 text-white shadow-lg shadow-violet-500/20'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/60'
            }`}
          >
            <Icon className="w-5 h-5 mb-1" />
            <span>{t.label}</span>
            {isActive && <span className="text-[10px] opacity-70 mt-0.5">{t.desc}</span>}
          </button>
        );
      })}
    </div>
  );
}

function SafetyBadge({ status, size = 'sm' }) {
  const cfg = SAFETY_CONFIG[status] || SAFETY_CONFIG.Unknown;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border font-semibold ${cfg.text} ${cfg.bg} ${cfg.border} ${size === 'lg' ? 'text-base' : 'text-xs'}`}>
      <Icon className={size === 'lg' ? 'w-5 h-5' : 'w-3.5 h-3.5'} />
      {cfg.label}
    </span>
  );
}

function KeySignalPill({ signal }) {
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-1 text-xs rounded-full bg-gray-800/80 text-gray-300 border border-gray-700/60">
      <CheckCircle2 className="w-3 h-3 text-teal-400 flex-shrink-0" />
      {signal}
    </span>
  );
}

function SourceLink({ url, title }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer noopener"
      className="flex items-center gap-2 text-xs text-teal-400 hover:text-teal-300 hover:underline transition-colors truncate group"
    >
      <ExternalLink className="w-3.5 h-3.5 flex-shrink-0 group-hover:translate-x-0.5 transition-transform" />
      <span className="truncate">{title || url}</span>
    </a>
  );
}

function StepIndicator({ step, label, active, done }) {
  return (
    <div className={`flex items-center gap-2 text-xs transition-colors ${done ? 'text-teal-400' : active ? 'text-white' : 'text-gray-600'}`}>
      <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold border transition-all ${done ? 'bg-teal-500 border-teal-500' : active ? 'border-white/60 animate-pulse' : 'border-gray-700'}`}>
        {done ? '✓' : step}
      </span>
      {label}
    </div>
  );
}

// ─── Safety Check Panel ───────────────────────────────────────────────────────

function SafetyCheckPanel() {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!url.trim()) return;
    setLoading(true); setResult(null); setError('');
    try {
      const data = await checkUrlSafety(url.trim());
      setResult(data);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : (err.message || 'An error occurred.'));
    } finally { setLoading(false); }
  };

  const safetyCfg = result ? (SAFETY_CONFIG[result.status] || SAFETY_CONFIG.Unknown) : null;

  return (
    <div className="space-y-6">
      {/* Input */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-400 mb-2">Enter URL to scan</label>
          <div className="relative">
            <LinkIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              id="safety-url-input"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://suspicious-site.com"
              className="w-full bg-gray-950/60 border border-gray-700/80 rounded-xl pl-10 pr-4 py-3.5 text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-teal-500/50 focus:border-teal-500/50 transition-all"
              required
            />
          </div>
        </div>
        <button
          id="safety-submit-btn"
          type="submit"
          disabled={loading || !url.trim()}
          className={`w-full flex items-center justify-center gap-2.5 py-3.5 rounded-xl font-semibold text-sm transition-all duration-300 ${
            loading || !url.trim()
              ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
              : 'bg-gradient-to-r from-teal-500 to-cyan-500 text-white hover:from-teal-400 hover:to-cyan-400 shadow-lg shadow-teal-500/20 hover:shadow-teal-500/30'
          }`}
        >
          {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Scanning URL...</> : <><ShieldCheck className="w-4 h-4" /> Run Safety Scan</>}
        </button>
      </form>

      {/* Result */}
      <AnimatePresence mode="wait">
        {error && (
          <motion.div key="err" {...scaleFade} className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 flex items-start gap-3">
            <ShieldX className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <p className="text-red-300 text-sm">{error}</p>
          </motion.div>
        )}
        {result && !error && (
          <motion.div key="result" {...scaleFade} className={`rounded-2xl border p-6 space-y-4 bg-gradient-to-br ${safetyCfg.bg} ${safetyCfg.border}`}>
            {/* Status Hero */}
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">Safety Verdict</p>
                <SafetyBadge status={result.status} size="lg" />
              </div>
              {result.threat_type && (
                <span className="text-xs px-3 py-1 rounded-full bg-red-500/10 border border-red-500/30 text-red-300 font-mono">
                  {result.threat_type}
                </span>
              )}
            </div>

            {/* Detail */}
            <div className="flex items-start gap-2.5 bg-gray-900/50 rounded-xl p-4 border border-gray-700/40">
              <Info className="w-4 h-4 text-gray-400 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-gray-300 leading-relaxed">{result.detail}</p>
            </div>

            {/* URL chip */}
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <Globe className="w-3.5 h-3.5" />
              <span className="font-mono truncate">{result.url}</span>
            </div>
          </motion.div>
        )}
        {!result && !error && !loading && (
          <motion.div key="empty" {...scaleFade} className="flex flex-col items-center justify-center gap-3 py-10 text-center border-2 border-dashed border-gray-800 rounded-2xl opacity-50">
            <ShieldQuestion className="w-10 h-10 text-gray-600" />
            <p className="text-sm text-gray-500">Enter a URL above and run a safety scan</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* How it works */}
      <div className="bg-gray-900/30 rounded-xl p-4 border border-gray-800/50">
        <h4 className="text-xs font-semibold text-gray-400 uppercase mb-3">🔒 Detection Layers</h4>
        <ul className="space-y-1.5 text-xs text-gray-500">
          <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-teal-500" /> Google Safe Browsing API (Malware / Phishing)</li>
          <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-teal-500" /> Heuristic URL Pattern Analysis</li>
          <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-teal-500" /> Suspicious TLD Detection</li>
          <li className="flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-teal-500" /> Social Engineering Keyword Scan</li>
        </ul>
      </div>
    </div>
  );
}

// ─── Fact Check Panel ─────────────────────────────────────────────────────────

function FactCheckPanel({ onHistoryUpdate }) {
  const [mode, setMode] = useState('text');
  const [inputVal, setInputVal] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const STEPS = ['Vector DB Lookup', 'Live Web Search', 'LLM Synthesis'];

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputVal.trim()) return;
    setLoading(true); setResult(null); setError(''); setActiveStep(1);

    const stepDelay = (n) => new Promise((r) => setTimeout(() => { setActiveStep(n); r(); }, 900 * n));

    try {
      const promise = factCheckContent(
        mode === 'text' ? { text: inputVal } : { url: inputVal }
      );
      await stepDelay(2);
      const data = await promise;
      setActiveStep(3);
      await new Promise(r => setTimeout(r, 400));
      setResult(data);
      onHistoryUpdate?.();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : (err.message || 'Analysis failed.'));
    } finally {
      setLoading(false);
      setActiveStep(0);
    }
  };

  const vCfg = result ? (VERDICT_CONFIG[result.verdict] || VERDICT_CONFIG.Unknown) : null;
  const VIcon = vCfg?.icon;

  return (
    <div className="space-y-6">
      {/* Mode Toggle */}
      <div className="flex gap-2 p-1.5 bg-gray-950/60 rounded-xl border border-gray-800/60">
        {['text', 'url'].map(m => (
          <button
            key={m}
            id={`factcheck-mode-${m}`}
            onClick={() => { setMode(m); setInputVal(''); setResult(null); setError(''); }}
            className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-xs font-semibold transition-all duration-200 ${
              mode === m
                ? 'bg-gradient-to-br from-violet-500 to-purple-600 text-white shadow-md shadow-violet-500/20'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/60'
            }`}
          >
            {m === 'text' ? <FileText className="w-4 h-4" /> : <LinkIcon className="w-4 h-4" />}
            {m === 'text' ? 'Raw Text' : 'Article URL'}
          </button>
        ))}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-400 mb-2">
            {mode === 'text' ? 'Paste news text or claim' : 'Article URL to fact-check'}
          </label>
          {mode === 'text' ? (
            <textarea
              id="factcheck-text-input"
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              placeholder="Scientists confirm the Earth is flat according to a new study published in..."
              rows={5}
              className="w-full bg-gray-950/60 border border-gray-700/80 rounded-xl px-4 py-3.5 text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-violet-500/50 focus:border-violet-500/50 transition-all resize-none text-sm"
              required
            />
          ) : (
            <div className="relative">
              <LinkIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input
                id="factcheck-url-input"
                type="url"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                placeholder="https://news-article.com/story-to-verify"
                className="w-full bg-gray-950/60 border border-gray-700/80 rounded-xl pl-10 pr-4 py-3.5 text-white placeholder-gray-600 focus:outline-none focus:ring-2 focus:ring-violet-500/50 focus:border-violet-500/50 transition-all"
                required
              />
            </div>
          )}
        </div>

        {/* Pipeline steps (visible while loading) */}
        <AnimatePresence>
          {loading && (
            <motion.div
              initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}
              className="flex flex-col gap-2 px-4 py-3 bg-gray-900/60 rounded-xl border border-gray-700/50"
            >
              <p className="text-xs text-gray-500 mb-1 font-medium">Running Hybrid RAG Pipeline…</p>
              {STEPS.map((s, i) => (
                <StepIndicator key={s} step={i + 1} label={s} active={activeStep === i + 1} done={activeStep > i + 1} />
              ))}
            </motion.div>
          )}
        </AnimatePresence>

        <button
          id="factcheck-submit-btn"
          type="submit"
          disabled={loading || !inputVal.trim()}
          className={`w-full flex items-center justify-center gap-2.5 py-3.5 rounded-xl font-semibold text-sm transition-all duration-300 ${
            loading || !inputVal.trim()
              ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
              : 'bg-gradient-to-r from-violet-500 to-purple-600 text-white hover:from-violet-400 hover:to-purple-500 shadow-lg shadow-violet-500/20 hover:shadow-violet-500/30'
          }`}
        >
          {loading
            ? <><Loader2 className="w-4 h-4 animate-spin" /> Analysing…</>
            : <><Zap className="w-4 h-4" /> Run Fact Check <ArrowRight className="w-4 h-4" /></>}
        </button>
      </form>

      {/* Error */}
      <AnimatePresence mode="wait">
        {error && (
          <motion.div key="err" {...scaleFade} className="p-4 rounded-xl bg-red-500/10 border border-red-500/30 flex items-start gap-3">
            <ShieldX className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <p className="text-red-300 text-sm">{error}</p>
          </motion.div>
        )}

        {/* Result Card */}
        {result && !error && (
          <motion.div key="result" {...scaleFade} className={`rounded-2xl border p-6 space-y-5 bg-gradient-to-br ${vCfg.gradient} ${vCfg.ring} ring-1`}>
            {/* Top Row: gauge + verdict */}
            <div className="flex items-center gap-6">
              <div className="w-24 h-24 flex-shrink-0">
                <CircularProgressbar
                  value={result.confidence}
                  text={`${Math.round(result.confidence)}%`}
                  strokeWidth={9}
                  styles={buildStyles({
                    pathColor: vCfg.bar,
                    textColor: '#fff',
                    trailColor: 'rgba(255,255,255,0.07)',
                    pathTransitionDuration: 1.2,
                    textSize: '22px',
                  })}
                />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] text-gray-400 uppercase tracking-widest mb-1.5">AI Verdict</p>
                <div className={`flex items-center gap-2 text-2xl font-bold ${vCfg.text} mb-2`}>
                  {VIcon && <VIcon className="w-6 h-6 flex-shrink-0" />}
                  <span>{vCfg.label}</span>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  <SafetyBadge status={result.safety_status || 'Safe'} />
                  {result.vector_hits > 0 && (
                    <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-400">
                      <Database className="w-3 h-3" />{result.vector_hits} DB match{result.vector_hits > 1 ? 'es' : ''}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Explanation */}
            <div className="bg-gray-900/60 rounded-xl p-4 border border-gray-700/40">
              <p className="text-xs text-gray-400 uppercase tracking-wider mb-2 font-semibold">Analysis</p>
              <p className="text-sm text-gray-200 leading-relaxed">{result.explanation}</p>
            </div>

            {/* Key Signals */}
            {result.key_signals?.length > 0 && (
              <div>
                <p className="text-xs text-gray-400 uppercase tracking-wider mb-2 font-semibold">Key Signals</p>
                <div className="flex flex-wrap gap-2">
                  {result.key_signals.map((s, i) => <KeySignalPill key={i} signal={s} />)}
                </div>
              </div>
            )}

            {/* Sources */}
            {result.sources?.length > 0 && (
              <div>
                <p className="text-xs text-gray-400 uppercase tracking-wider mb-2 font-semibold flex items-center gap-1.5">
                  <Globe className="w-3.5 h-3.5" /> Live Sources Retrieved
                </p>
                <div className="space-y-2">
                  {result.sources.map((src, i) => <SourceLink key={i} url={src} />)}
                </div>
              </div>
            )}

            {/* Note */}
            {result.note && (
              <div className="flex items-start gap-2.5 bg-amber-500/5 border border-amber-500/20 rounded-xl px-4 py-3">
                <Info className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                <p className="text-amber-300/80 text-xs leading-relaxed">{result.note}</p>
              </div>
            )}
          </motion.div>
        )}

        {/* Empty State */}
        {!result && !error && !loading && (
          <motion.div key="empty" {...scaleFade} className="flex flex-col items-center justify-center gap-3 py-10 text-center border-2 border-dashed border-gray-800 rounded-2xl opacity-50">
            <Zap className="w-10 h-10 text-gray-600" />
            <p className="text-sm text-gray-500">Enter text or a URL above to run the Hybrid RAG pipeline</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ─── History Section ──────────────────────────────────────────────────────────

function HistorySection({ refresh }) {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchHistory = useCallback(async () => {
    try { const d = await getHistory(8); setHistory(d); }
    catch (e) { console.error('History fetch error:', e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchHistory(); }, [refresh, fetchHistory]);

  return (
    <motion.section {...fadeUp} transition={{ delay: 0.3 }} className="mt-12">
      <div className="flex items-center gap-2.5 mb-5">
        <Clock className="w-5 h-5 text-gray-400" />
        <h3 className="text-lg font-semibold text-gray-200">Recent Analyses</h3>
        <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded-full">{history.length}</span>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-10 gap-2 text-gray-600">
          <Loader2 className="w-4 h-4 animate-spin" /><span className="text-sm">Loading history…</span>
        </div>
      ) : history.length === 0 ? (
        <div className="text-center py-10 text-gray-600 border-2 border-dashed border-gray-800 rounded-2xl text-sm">
          No analyses yet. Run a check above to get started.
        </div>
      ) : (
        <div className="space-y-3">
          {history.map((item) => {
            const vCfg = VERDICT_CONFIG[item.prediction_result] || VERDICT_CONFIG.Unknown;
            const safeCfg = SAFETY_CONFIG[item.safety_status] || SAFETY_CONFIG.Unknown;
            return (
              <motion.div
                key={item.id}
                layout
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                className="flex items-center gap-4 p-4 bg-gray-900/40 border border-gray-800/60 rounded-2xl hover:border-gray-700/80 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500 bg-gray-800 px-2 py-0.5 rounded-full">
                      {item.input_type}
                    </span>
                    <span className="text-[11px] text-gray-600">
                      {new Date(item.timestamp).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-sm text-gray-300 truncate font-medium">{item.user_input}</p>
                </div>
                <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
                  <span className={`text-xs font-bold px-2.5 py-1 rounded-lg flex items-center gap-1.5 ${vCfg.text} bg-gray-800/80 border border-gray-700/60`}>
                    {item.prediction_result} · {Number(item.confidence_score).toFixed(0)}%
                  </span>
                  <SafetyBadge status={item.safety_status} />
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </motion.section>
  );
}

// ─── Root App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [activeTab, setActiveTab] = useState('safety');
  const [historyRefresh, setHistoryRefresh] = useState(0);

  const triggerHistoryRefresh = () => setHistoryRefresh(n => n + 1);

  return (
    <div className="min-h-screen text-gray-100 font-sans relative overflow-x-hidden">
      {/* Ambient orbs */}
      <div className="fixed top-[-15%] left-[-10%] w-[50%] h-[50%] bg-teal-600/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="fixed bottom-[-10%] right-[-10%] w-[45%] h-[45%] bg-violet-600/10 rounded-full blur-[140px] pointer-events-none" />
      <div className="fixed top-[40%] left-[50%] w-[30%] h-[30%] bg-cyan-500/5 rounded-full blur-[120px] pointer-events-none" />

      <main className="relative z-10 container mx-auto px-4 py-12 max-w-3xl">

        {/* Header */}
        <motion.header {...fadeUp} className="text-center mb-10">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-gray-800/70 border border-gray-700/60 text-xs text-gray-400 font-medium mb-6 backdrop-blur-sm">
            <Zap className="w-3.5 h-3.5 text-teal-400" />
            Hybrid RAG · Safe Browsing · Gemini LLM
          </div>
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight mb-3 leading-tight">
            AI Fake News &{' '}
            <span className="bg-gradient-to-r from-teal-400 via-cyan-400 to-violet-400 bg-clip-text text-transparent">
              Web Safety
            </span>
            <br />Detector
          </h1>
          <p className="text-gray-400 max-w-xl mx-auto text-sm leading-relaxed">
            Two-in-one security platform. Check URLs for phishing & malware, or verify news content with our Hybrid RAG pipeline powered by live web search and vector memory.
          </p>
        </motion.header>

        {/* Main Card */}
        <motion.div
          {...fadeUp}
          transition={{ delay: 0.1 }}
          className="bg-gray-900/50 backdrop-blur-xl border border-gray-800/60 rounded-3xl p-6 md:p-8 shadow-2xl"
        >
          <TabBar active={activeTab} onChange={setActiveTab} />

          <AnimatePresence mode="wait">
            {activeTab === 'safety' && (
              <motion.div key="safety" {...scaleFade} transition={{ duration: 0.2 }}>
                <SafetyCheckPanel />
              </motion.div>
            )}
            {activeTab === 'factcheck' && (
              <motion.div key="factcheck" {...scaleFade} transition={{ duration: 0.2 }}>
                <FactCheckPanel onHistoryUpdate={triggerHistoryRefresh} />
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>

        {/* History */}
        <HistorySection refresh={historyRefresh} />

        {/* Footer */}
        <motion.footer {...fadeUp} transition={{ delay: 0.5 }} className="text-center mt-12 text-xs text-gray-600">
          <p>AI Fake News & Web Safety Detector · Hybrid RAG v2.0</p>
          <p className="mt-1">Vector DB · Tavily Live Search · Google Safe Browsing · Gemini LLM</p>
        </motion.footer>
      </main>
    </div>
  );
}
