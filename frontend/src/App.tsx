import { useState, useEffect, useRef, useCallback } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Segment {
    id: number
    text: string
    keywords: string
    word_count: number
    estimated_duration: number
}

interface Voice {
    id: string
    name: string
}

interface Job {
    status: 'queued' | 'running' | 'done' | 'error'
    progress: number
    message: string
    error?: string
    output_path?: string
}

// ─── API Helpers ──────────────────────────────────────────────────────────────

const API = '/api'

async function apiPost<T>(path: string, body: object): Promise<T> {
    const res = await fetch(API + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    })
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || 'Request failed')
    }
    return res.json()
}

async function apiGet<T>(path: string): Promise<T> {
    const res = await fetch(API + path)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.json()
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function Toggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
    return (
        <div className={`toggle ${on ? 'on' : ''}`} onClick={onToggle} role="switch" aria-checked={on}>
            <div className="toggle-knob" />
        </div>
    )
}

function SegmentCard({ seg, index }: { seg: Segment; index: number }) {
    return (
        <div className="segment-card">
            <div className="segment-num">{index + 1}</div>
            <div className="segment-info">
                <p className="segment-text">{seg.text}</p>
                <div className="segment-tags">
                    {seg.keywords.split(' ').map((kw) => (
                        <span key={kw} className="tag tag-kw">#{kw}</span>
                    ))}
                    <span className="tag tag-dur">⏱ ~{seg.estimated_duration.toFixed(1)}s</span>
                </div>
            </div>
        </div>
    )
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
    const [script, setScript] = useState('')
    const [segments, setSegments] = useState<Segment[]>([])
    const [voices, setVoices] = useState<Voice[]>([])
    const [selectedVoice, setSelectedVoice] = useState('es-MX-DaliaNeural')
    const [showSubtitles, setShowSubtitles] = useState(true)
    const [rate, setRate] = useState('+0%')
    const [jobId, setJobId] = useState<string | null>(null)
    const [job, setJob] = useState<Job | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const sseRef = useRef<EventSource | null>(null)

    // Load voices on mount
    useEffect(() => {
        apiGet<{ voices: Voice[] }>('/voices')
            .then(d => setVoices(d.voices))
            .catch(() => { })
    }, [])

    // Auto-preview segments as user types (debounced)
    useEffect(() => {
        if (!script.trim()) { setSegments([]); return }
        const timer = setTimeout(() => {
            // Simple client-side preview (split by double newline)
            const raw = script.split(/\n{2,}/).map((t, i) => ({
                id: i,
                text: t.trim(),
                keywords: t.trim().split(/\s+/).slice(0, 3).join(' '),
                word_count: t.trim().split(/\s+/).length,
                estimated_duration: Math.max(3, (t.trim().split(/\s+/).length / 2.5)),
            })).filter(s => s.text)
            setSegments(raw)
        }, 400)
        return () => clearTimeout(timer)
    }, [script])

    // SSE connection when job starts
    useEffect(() => {
        if (!jobId) return
        sseRef.current?.close()

        const sse = new EventSource(`/api/stream/${jobId}`)
        sseRef.current = sse

        sse.onmessage = (e) => {
            const data: Job = JSON.parse(e.data)
            setJob(data)
            if (data.status === 'done' || data.status === 'error') {
                sse.close()
                setLoading(false)
            }
        }
        sse.onerror = () => { sse.close(); setLoading(false) }

        return () => sse.close()
    }, [jobId])

    const handleGenerate = useCallback(async () => {
        if (!script.trim()) return
        setError(null)
        setJob(null)
        setLoading(true)

        try {
            const res = await apiPost<{ job_id: string; segments: Segment[] }>('/generate', {
                script,
                voice: selectedVoice,
                rate,
                show_subtitles: showSubtitles,
            })
            setSegments(res.segments)
            setJobId(res.job_id)
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Error desconocido')
            setLoading(false)
        }
    }, [script, selectedVoice, rate, showSubtitles])

    const wordCount = script.trim() ? script.trim().split(/\s+/).length : 0
    const estTotalDuration = segments.reduce((acc, s) => acc + s.estimated_duration, 0)
    const isDone = job?.status === 'done'
    const isRunning = loading || (job && job.status === 'queued') || job?.status === 'running'

    const rateLabel = rate === '+0%' ? 'Normal' : rate.startsWith('+') ? `+${rate.replace('+', '').replace('%', '')}% Rápido` : `${rate.replace('%', '')}% Lento`

    return (
        <div className="app">
            {/* ── Header ─────────────────────────────────────────────── */}
            <header className="header">
                <div className="logo-icon">🎬</div>
                <div>
                    <h1>VideoGen</h1>
                    <p>Generador de Reels con IA</p>
                </div>
                <span className="badge">🎙 edge-tts · 🎞 Pexels</span>
            </header>

            {/* ── Main Grid ──────────────────────────────────────────── */}
            <main className="main">

                {/* Left column: Script input + segments */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>

                    {/* Script input */}
                    <div className="card">
                        <div className="card-title">
                            <span>📝</span> Tu Guion
                        </div>
                        <textarea
                            id="script-input"
                            className="script-area"
                            placeholder={`Pega aquí tu guion...\n\nSepara cada segmento con una línea en blanco.\n\nEjemplo:\n¿Sabías que el cerebro humano puede almacenar el equivalente a 2.5 millones de gigabytes?\n\nEsa cantidad de información equivale a toda la música publicada en los últimos 200 años.`}
                            value={script}
                            onChange={e => setScript(e.target.value)}
                            disabled={!!isRunning}
                        />
                        <div className="script-meta">
                            <span>{wordCount} palabras · {segments.length} segmento{segments.length !== 1 ? 's' : ''}</span>
                            {segments.length > 0 && (
                                <span>Duración estimada: ~{Math.round(estTotalDuration)}s</span>
                            )}
                        </div>
                    </div>

                    {/* Segments preview */}
                    {segments.length > 0 && (
                        <div className="card">
                            <div className="card-title">
                                <span>🎞</span> Segmentos detectados ({segments.length})
                            </div>
                            <div className="segments-grid">
                                {segments.map((seg, i) => (
                                    <SegmentCard key={seg.id} seg={seg} index={i} />
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Right sidebar */}
                <aside className="sidebar">

                    {/* Settings */}
                    <div className="card">
                        <div className="card-title"><span>⚙️</span> Configuración</div>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>

                            {/* Voice selector */}
                            <div className="field">
                                <label htmlFor="voice-select">🎙 Voz</label>
                                <select
                                    id="voice-select"
                                    value={selectedVoice}
                                    onChange={e => setSelectedVoice(e.target.value)}
                                    disabled={!!isRunning}
                                >
                                    {voices.length > 0
                                        ? voices.map(v => <option key={v.id} value={v.id}>{v.name}</option>)
                                        : <option value="es-MX-DaliaNeural">Dalia (Mujer · México)</option>}
                                </select>
                            </div>

                            {/* Speed */}
                            <div className="field">
                                <label>⚡ Velocidad — <span style={{ color: 'var(--accent-glow)' }}>{rateLabel}</span></label>
                                <input
                                    type="range"
                                    min={-30}
                                    max={30}
                                    step={5}
                                    value={parseInt(rate)}
                                    onChange={e => setRate(`${+e.target.value >= 0 ? '+' : ''}${e.target.value}%`)}
                                    disabled={!!isRunning}
                                    style={{ accentColor: 'var(--accent)' }}
                                />
                            </div>

                            {/* Subtitles toggle */}
                            <div className="field">
                                <div className="toggle-row">
                                    <label>💬 Subtítulos</label>
                                    <Toggle on={showSubtitles} onToggle={() => setShowSubtitles(p => !p)} />
                                </div>
                            </div>

                        </div>
                    </div>

                    {/* Generate button */}
                    <button
                        id="btn-generate"
                        className="btn-generate"
                        onClick={handleGenerate}
                        disabled={!script.trim() || !!isRunning}
                    >
                        {isRunning
                            ? <><span className="status-dot running" />Generando...</>
                            : <>✨ Generar Reel</>}
                    </button>

                    {/* Error */}
                    {error && <div className="error-box">❌ {error}</div>}

                    {/* Progress */}
                    {job && job.status !== 'done' && (
                        <div className="card">
                            <div className="card-title">
                                <span className={`status-dot ${job.status}`} />
                                {job.status === 'error' ? 'Error' : 'Progreso'}
                            </div>
                            {job.status === 'error'
                                ? <div className="error-box">{job.error}</div>
                                : (
                                    <div className="progress-box">
                                        <div className="progress-header">
                                            <span className="progress-msg">{job.message}</span>
                                            <span className="progress-pct">{job.progress}%</span>
                                        </div>
                                        <div className="progress-track">
                                            <div className="progress-fill" style={{ width: `${job.progress}%` }} />
                                        </div>
                                    </div>
                                )}
                        </div>
                    )}

                    {/* Video result */}
                    {isDone && jobId && (
                        <div className="card">
                            <div className="card-title"><span className="status-dot done" />¡Video listo!</div>
                            <div className="video-container">
                                <video
                                    className="video-player"
                                    controls
                                    autoPlay
                                    src={`/api/download/${jobId}`}
                                />
                            </div>
                            <a
                                className="btn-download"
                                href={`/api/download/${jobId}`}
                                download={`reel_${jobId.slice(0, 8)}.mp4`}
                            >
                                ⬇️ Descargar MP4
                            </a>
                        </div>
                    )}

                </aside>
            </main>
        </div>
    )
}
