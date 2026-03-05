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

interface Config {
    configured: boolean
    pexels_key_preview: string
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

// ─── Setup Wizard ─────────────────────────────────────────────────────────────

function SetupWizard({ onComplete }: { onComplete: () => void }) {
    const [step, setStep] = useState(1)
    const [pexelsKey, setPexelsKey] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [success, setSuccess] = useState(false)

    const handleSave = async () => {
        setError(null)
        setLoading(true)
        try {
            await apiPost('/setup', { pexels_api_key: pexelsKey })
            setSuccess(true)
            setTimeout(onComplete, 1800)
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Error desconocido')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="wizard-overlay">
            <div className="wizard-card">
                {/* Logo */}
                <div className="wizard-logo">🎬</div>
                <h2 className="wizard-title">Bienvenido a VideoGen</h2>
                <p className="wizard-subtitle">
                    Configura tu cuenta en menos de un minuto para empezar a generar reels.
                </p>

                {/* Steps indicator */}
                <div className="wizard-steps">
                    {[1, 2].map(n => (
                        <div key={n} className={`wizard-step ${step >= n ? 'active' : ''} ${step > n ? 'done' : ''}`}>
                            <div className="wizard-step-dot">{step > n ? '✓' : n}</div>
                            <span>{n === 1 ? 'API Key' : 'Listo'}</span>
                        </div>
                    ))}
                </div>

                <div className="wizard-divider" />

                {step === 1 && (
                    <div className="wizard-body">
                        <div className="wizard-field">
                            <label className="wizard-label">
                                🔑 Pexels API Key
                            </label>
                            <p className="wizard-hint">
                                Regístrate gratis en{' '}
                                <a href="https://www.pexels.com/api/" target="_blank" rel="noreferrer" className="wizard-link">
                                    pexels.com/api
                                </a>{' '}
                                y copia tu API key aquí.
                            </p>
                            <input
                                id="pexels-key-input"
                                type="text"
                                className="wizard-input"
                                placeholder="Pega tu Pexels API Key..."
                                value={pexelsKey}
                                onChange={e => setPexelsKey(e.target.value)}
                                disabled={loading}
                                autoFocus
                            />
                        </div>

                        {error && <div className="wizard-error">❌ {error}</div>}

                        {success && (
                            <div className="wizard-success">✅ ¡Configuración guardada! Iniciando...</div>
                        )}

                        <button
                            id="btn-save-config"
                            className="wizard-btn"
                            onClick={handleSave}
                            disabled={!pexelsKey.trim() || loading || success}
                        >
                            {loading ? '⏳ Guardando...' : success ? '✅ ¡Listo!' : 'Guardar y continuar →'}
                        </button>
                    </div>
                )}

                <p className="wizard-footer">
                    edge-tts no requiere API key · Solo Pexels es necesaria
                </p>
            </div>
        </div>
    )
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
    const [config, setConfig] = useState<Config | null>(null)
    const [checkingConfig, setCheckingConfig] = useState(true)
    const [script, setScript] = useState('')
    const [segments, setSegments] = useState<Segment[]>([])
    const [voices, setVoices] = useState<Voice[]>([])
    const [selectedVoice, setSelectedVoice] = useState('es-MX-DaliaNeural')
    const [showSubtitles, setShowSubtitles] = useState(true)
    const [rate, setRate] = useState('+0%')
    const [jobId, setJobId] = useState<string | null>(null)
    const [job, setJob] = useState<Job | null>(null)
    const [loading, setLoading] = useState(false)
    const [playingPreview, setPlayingPreview] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const sseRef = useRef<EventSource | null>(null)

    // Check config on mount
    useEffect(() => {
        apiGet<Config>('/config')
            .then(c => setConfig(c))
            .catch(() => setConfig({ configured: false, pexels_key_preview: '' }))
            .finally(() => setCheckingConfig(false))
    }, [])

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

    const handlePreviewVoice = async () => {
        setPlayingPreview(true)
        setError(null)

        const previewText = segments.length > 0
            ? segments[0].text
            : "Hola, esta es una prueba de cómo suena mi voz para tu generador de videos."

        try {
            const res = await fetch('/api/preview-voice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: previewText,
                    voice: selectedVoice,
                    rate: rate
                })
            })

            if (!res.ok) {
                throw new Error("No se pudo generar el preview de la voz")
            }

            const blob = await res.blob()
            const url = URL.createObjectURL(blob)
            const audio = new Audio(url)

            audio.onended = () => {
                setPlayingPreview(false)
                URL.revokeObjectURL(url)
            }

            await audio.play()
        } catch (err: any) {
            setError(err.message || 'Error al escuchar la voz')
            setPlayingPreview(false)
        }
    }

    const wordCount = script.trim() ? script.trim().split(/\s+/).length : 0
    const estTotalDuration = segments.reduce((acc, s) => acc + s.estimated_duration, 0)
    const isDone = job?.status === 'done'
    const isRunning = loading || (job && job.status === 'queued') || job?.status === 'running'
    const rateLabel = rate === '+0%' ? 'Normal' : rate.startsWith('+') ? `Rápido` : `Lento`

    // Loading screen
    if (checkingConfig) {
        return (
            <div className="app" style={{ alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
                <div style={{ textAlign: 'center', color: 'var(--text-2)' }}>
                    <div className="spinner" />
                    <p style={{ marginTop: 16 }}>Iniciando VideoGen...</p>
                </div>
            </div>
        )
    }

    return (
        <div className="app">
            {/* Setup Wizard overlay if not configured */}
            {config && !config.configured && (
                <SetupWizard onComplete={() => setConfig({ configured: true, pexels_key_preview: '' })} />
            )}

            {/* ── Header ─────────────────────────────────────────────── */}
            <header className="header">
                <div className="logo-icon">🎬</div>
                <div>
                    <h1>VideoGen</h1>
                    <p>Generador de Reels con IA</p>
                </div>
                {/* Config status in header */}
                <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
                    {config?.configured && (
                        <button
                            className="badge"
                            style={{ cursor: 'pointer', border: '1px solid var(--border)' }}
                            onClick={() => setConfig(c => c ? { ...c, configured: false } : c)}
                            title="Cambiar API keys"
                        >
                            ⚙️ Config
                        </button>
                    )}
                    <span className="badge">🎙 edge-tts · 🎞 Pexels</span>
                </div>
            </header>

            {/* ── Main Grid ──────────────────────────────────────────── */}
            <main className="main">

                {/* Left column */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>

                    <div className="card">
                        <div className="card-title"><span>📝</span> Tu Guion</div>
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

                {/* Sidebar */}
                <aside className="sidebar">

                    <div className="card">
                        <div className="card-title"><span>⚙️</span> Configuración</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>

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
                                <button
                                    className="btn-secondary"
                                    onClick={handlePreviewVoice}
                                    disabled={playingPreview || !!isRunning}
                                    style={{ marginTop: '8px' }}
                                >
                                    {playingPreview ? '🔊 Reproduciendo...' : '▶️ Escuchar prueba'}
                                </button>
                            </div>

                            <div className="field">
                                <label>⚡ Velocidad — <span style={{ color: 'var(--accent-glow)' }}>{rateLabel}</span></label>
                                <input
                                    type="range" min={-30} max={30} step={5}
                                    value={parseInt(rate)}
                                    onChange={e => setRate(`${+e.target.value >= 0 ? '+' : ''}${e.target.value}%`)}
                                    disabled={!!isRunning}
                                    style={{ accentColor: 'var(--accent)' }}
                                />
                            </div>

                            <div className="field">
                                <div className="toggle-row">
                                    <label>💬 Subtítulos</label>
                                    <Toggle on={showSubtitles} onToggle={() => setShowSubtitles(p => !p)} />
                                </div>
                            </div>
                        </div>
                    </div>

                    <button
                        id="btn-generate"
                        className="btn-generate"
                        onClick={handleGenerate}
                        disabled={!script.trim() || !!isRunning || !config?.configured}
                    >
                        {isRunning
                            ? <><span className="status-dot running" />Generando...</>
                            : <>✨ Generar Reel</>}
                    </button>

                    {!config?.configured && (
                        <div className="error-box" style={{ textAlign: 'center' }}>
                            ⚙️ Configura tu API key primero
                        </div>
                    )}

                    {error && <div className="error-box">❌ {error}</div>}

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

                    {isDone && jobId && (
                        <div className="card">
                            <div className="card-title"><span className="status-dot done" />¡Video listo!</div>
                            <div className="video-container">
                                <video className="video-player" controls autoPlay src={`/api/download/${jobId}`} />
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
