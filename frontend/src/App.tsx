import { useState, useEffect, useRef, useCallback } from 'react'

// ─── Types ────────────────────────────────────────────────────────────────────

interface Segment {
    id: number
    text: string
    keywords: string
    word_count: number
    estimated_duration: number
}

interface VideoOption {
    provider: string
    url: string
    thumbnail?: string
    score: number
    duration?: number
}

interface Voice {
    id: string
    name: string
}

interface VoicesResponse {
    elevenlabs: Voice[]
    deepgram: Voice[]
    free: Voice[]
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
    pixabay_key_preview: string
    elevenlabs_key_preview: string
    deepgram_key_preview: string
}

interface ParseResponse {
    segments: Segment[]
}

interface VideoOptionsResponse {
    options: VideoOption[]
}

// ─── Components ───────────────────────────────────────────────────────────────

function VideoReplacementModal({
    isOpen,
    segment,
    options,
    loading,
    selectedUrl,
    onPick,
    onClose,
}: {
    isOpen: boolean
    segment: Segment | null
    options: VideoOption[]
    loading: boolean
    selectedUrl?: string
    onPick: (url: string) => void
    onClose: () => void
}) {
    const [previewUrl, setPreviewUrl] = useState<string>('')

    useEffect(() => {
        if (options.length > 0 && !previewUrl) {
            setPreviewUrl(options[0].url)
        }
    }, [options, previewUrl])

    if (!isOpen || !segment) return null

    return (
        <div style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: 16,
        }}>
            <div style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border)',
                borderRadius: 12,
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: 16,
                maxWidth: 900,
                width: '100%',
                maxHeight: '90vh',
                overflow: 'hidden',
            }}>
                {/* Preview side */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 16 }}>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>Previsualización</div>
                    <div style={{
                        aspectRatio: '9/16',
                        background: '#000',
                        borderRadius: 8,
                        overflow: 'hidden',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                    }}>
                        {previewUrl ? (
                            <video
                                src={previewUrl}
                                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                                controls
                                autoPlay
                                loop
                            />
                        ) : (
                            <div style={{ opacity: 0.5 }}>Sin previsualización</div>
                        )}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                        {segment.text}
                    </div>
                </div>

                {/* Options side */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 16, borderLeft: '1px solid var(--border)', overflow: 'auto', maxHeight: '90vh' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>Videos disponibles</div>
                        <button
                            onClick={onClose}
                            style={{
                                background: 'none',
                                border: 'none',
                                color: 'var(--text-2)',
                                cursor: 'pointer',
                                fontSize: 18,
                            }}
                        >
                            ✕
                        </button>
                    </div>

                    {loading && (
                        <div style={{ fontSize: 12, textAlign: 'center', opacity: 0.7 }}>Cargando opciones...</div>
                    )}

                    {!loading && options.length === 0 && (
                        <div style={{ fontSize: 12, textAlign: 'center', opacity: 0.7 }}>No hay opciones de video</div>
                    )}

                    {!loading && (
                        <div style={{ display: 'grid', gap: 8 }}>
                            {options.map((opt) => (
                                <button
                                    key={opt.url}
                                    onClick={() => {
                                        setPreviewUrl(opt.url)
                                        onPick(opt.url)
                                    }}
                                    style={{
                                        background: previewUrl === opt.url ? 'var(--accent)' : 'rgba(255,255,255,0.05)',
                                        border: previewUrl === opt.url ? '2px solid var(--accent)' : '1px solid var(--border)',
                                        borderRadius: 8,
                                        padding: 8,
                                        cursor: 'pointer',
                                        display: 'flex',
                                        gap: 8,
                                        alignItems: 'center',
                                        transition: 'all 0.2s',
                                    }}
                                >
                                    {opt.thumbnail && (
                                        <img
                                            src={opt.thumbnail}
                                            alt="thumb"
                                            style={{ width: 60, height: 34, objectFit: 'cover', borderRadius: 4 }}
                                        />
                                    )}
                                    <div style={{ display: 'grid', gap: 2, textAlign: 'left', fontSize: 11 }}>
                                        <span style={{ opacity: 0.8 }}>{opt.provider}</span>
                                        <span style={{ opacity: 0.6 }}>{opt.duration || '?'}s</span>
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
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

function SetupWizard({ onComplete, existingConfig }: { onComplete: () => void, existingConfig?: Config }) {
    const [step, setStep] = useState(1)
    const [pexelsKey, setPexelsKey] = useState('')
    const [pixabayKey, setPixabayKey] = useState('')
    const [elevenlabsKey, setElevenlabsKey] = useState('')
    const [deepgramKey, setDeepgramKey] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [success, setSuccess] = useState(false)

    // Indicators for already-configured keys
    const hasPexels = !!existingConfig?.pexels_key_preview
    const hasPixabay = !!existingConfig?.pixabay_key_preview
    const hasElevenlabs = !!existingConfig?.elevenlabs_key_preview
    const hasDeepgram = !!existingConfig?.deepgram_key_preview

    const handleSave = async () => {
        setError(null)
        setLoading(true)
        try {
            await apiPost('/setup', {
                pexels_api_key: pexelsKey,
                pixabay_api_key: pixabayKey,
                elevenlabs_api_key: elevenlabsKey,
                deepgram_api_key: deepgramKey
            })
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
                                placeholder={hasPexels ? `Ya configurada: ${existingConfig?.pexels_key_preview || ''}` : "Pega tu Pexels API Key..."}
                                value={pexelsKey}
                                onChange={e => setPexelsKey(e.target.value)}
                                disabled={loading}
                                autoFocus
                            />
                        </div>

                        <div className="wizard-field" style={{ marginTop: '12px' }}>
                            <label className="wizard-label">
                                🎞️ Pixabay API Key (Opcional)
                            </label>
                            <p className="wizard-hint">
                                Regístrate gratis en{' '}
                                <a href="https://pixabay.com/api/docs/" target="_blank" rel="noreferrer" className="wizard-link">
                                    pixabay.com/api/docs
                                </a>{' '}
                                y copia tu API key aquí.
                            </p>
                            <input
                                id="pixabay-key-input"
                                type="text"
                                className="wizard-input"
                                placeholder={hasPixabay ? `Ya configurada: ${existingConfig?.pixabay_key_preview || ''}` : "Pega tu Pixabay API Key..."}
                                value={pixabayKey}
                                onChange={e => setPixabayKey(e.target.value)}
                                disabled={loading}
                            />
                        </div>

                        <div className="wizard-field" style={{ marginTop: '12px' }}>
                            <label className="wizard-label">
                                🎙️ ElevenLabs API Key
                            </label>
                            <p className="wizard-hint">
                                Regístrate gratis en{' '}
                                <a href="https://elevenlabs.io/" target="_blank" rel="noreferrer" className="wizard-link">
                                    elevenlabs.io
                                </a>{' '}
                                y copia tu API key aquí.
                            </p>
                            <input
                                id="elevenlabs-key-input"
                                type="text"
                                className="wizard-input"
                                placeholder={hasElevenlabs ? `Ya configurada: ${existingConfig?.elevenlabs_key_preview || ''}` : "Pega tu ElevenLabs API Key..."}
                                value={elevenlabsKey}
                                onChange={e => setElevenlabsKey(e.target.value)}
                                disabled={loading}
                            />
                        </div>

                        <div className="wizard-field" style={{ marginTop: '12px' }}>
                            <label className="wizard-label">
                                🎙️ Deepgram API Key (Opcional)
                            </label>
                            <p className="wizard-hint">
                                <a href="https://console.deepgram.com/" target="_blank" rel="noreferrer" className="wizard-link">
                                    console.deepgram.com
                                </a>
                            </p>
                            <input
                                id="deepgram-key-input"
                                type="text"
                                className="wizard-input"
                                placeholder={hasDeepgram ? `Ya configurada: ${existingConfig?.deepgram_key_preview || ''}` : "Pega tu Deepgram API Key..."}
                                value={deepgramKey}
                                onChange={e => setDeepgramKey(e.target.value)}
                                disabled={loading}
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
                            // Requerimos al menos una API de videos: Pexels o Pixabay
                            disabled={(!pexelsKey.trim() && !pixabayKey.trim() && !hasPexels && !hasPixabay) || loading || success}
                        >
                            {loading ? '⏳ Guardando...' : success ? '✅ ¡Listo!' : 'Guardar y continuar →'}
                        </button>
                    </div>
                )}

                <p className="wizard-footer">
                    VideoGen requiere al menos una API de videos (Pexels o Pixabay). ElevenLabs y Deepgram son opcionales para voces premium.
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

function SegmentCard({
    seg,
    index,
    videoOptions,
    selectedUrl,
    onThumbClick,
}: {
    seg: Segment
    index: number
    videoOptions: VideoOption[]
    selectedUrl?: string
    onThumbClick: () => void
}) {
    const thumbUrl = selectedUrl
        ? videoOptions.find(o => o.url === selectedUrl)?.thumbnail
        : videoOptions[0]?.thumbnail

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
                {videoOptions.length > 0 && (
                    <div
                        onClick={onThumbClick}
                        style={{
                            marginTop: 10,
                            cursor: 'pointer',
                            borderRadius: 8,
                            overflow: 'hidden',
                            aspectRatio: '16/9',
                            background: '#000',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            border: '2px solid var(--border)',
                            transition: 'all 0.2s',
                        }}
                        onMouseOver={(e) => {
                            (e.currentTarget as HTMLElement).style.borderColor = 'var(--accent)'
                        }}
                        onMouseOut={(e) => {
                            (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'
                        }}
                    >
                        {thumbUrl ? (
                            <img
                                src={thumbUrl}
                                alt="video-thumb"
                                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            />
                        ) : (
                            <div style={{ opacity: 0.5, fontSize: 12 }}>🎬 Click para cambiar</div>
                        )}
                    </div>
                )}
            </div>
        </div>
    )
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
    const [config, setConfig] = useState<Config | null>(null)
    const [showSetupWizard, setShowSetupWizard] = useState(false)
    const [checkingConfig, setCheckingConfig] = useState(true)
    const [script, setScript] = useState('')
    const [segments, setSegments] = useState<Segment[]>([])
    const [selectedVideos, setSelectedVideos] = useState<Record<number, string>>({})
    const [videoOptionsBySeg, setVideoOptionsBySeg] = useState<Record<number, VideoOption[]>>({})
    const [loadingVideosBySeg, setLoadingVideosBySeg] = useState<Record<number, boolean>>({})
    const [previewingSeg, setPreviewingSeg] = useState<Segment | null>(null)
    const [voices, setVoices] = useState<VoicesResponse>({ elevenlabs: [], deepgram: [], free: [] })
    const [selectedVoice, setSelectedVoice] = useState('ErXwobaYiN019PkySvjV')
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
            .then(c => {
                setConfig(c)
                setShowSetupWizard(!c.configured)
            })
            .catch(() => {
                setConfig({ configured: false, pexels_key_preview: '', pixabay_key_preview: '', elevenlabs_key_preview: '', deepgram_key_preview: '' })
                setShowSetupWizard(true)
            })
            .finally(() => setCheckingConfig(false))
    }, [])

    // Load voices on mount
    useEffect(() => {
        apiGet<VoicesResponse>('/voices')
            .then(d => {
                setVoices(d)
                // If they don't have ElevenLabs configured, try to pick a free voice to avoid 401 errors by default
                if (config && !config.elevenlabs_key_preview && d.free.length > 0) {
                    setSelectedVoice(d.free[0].id)
                }
            })
            .catch(() => { })
    }, [config])

    // Auto-preview segments as user types (debounced, canonical parse from backend) and load videos in parallel
    useEffect(() => {
        if (!script.trim()) {
            setSegments([])
            setSelectedVideos({})
            setVideoOptionsBySeg({})
            setPreviewingSeg(null)
            return
        }
        const timer = setTimeout(async () => {
            try {
                const parsed = await apiPost<ParseResponse>('/parse', { script })
                const newSegs = parsed.segments || []
                setSegments(newSegs)
                setSelectedVideos({})
                setPreviewingSeg(null)

                // Load videos for all segments in parallel
                setLoadingVideosBySeg(
                    newSegs.reduce((acc, s) => ({ ...acc, [s.id]: true }), {})
                )

                const videosBySegId: Record<number, VideoOption[]> = {}
                await Promise.all(
                    newSegs.map(seg =>
                        apiPost<VideoOptionsResponse>('/video-options', {
                            keywords: seg.keywords,
                            context_text: seg.text,
                            min_duration: Math.max(3, Math.round(seg.estimated_duration)),
                            limit: 8,
                            exclude_urls: Object.values(selectedVideos || {}),
                        })
                            .then(res => {
                                videosBySegId[seg.id] = res.options || []
                            })
                            .catch(() => {
                                videosBySegId[seg.id] = []
                            })
                    )
                )
                setVideoOptionsBySeg(videosBySegId)
                setLoadingVideosBySeg(
                    newSegs.reduce((acc, s) => ({ ...acc, [s.id]: false }), {})
                )
            } catch {
                // keep previous segments on transient parse errors
            }
        }, 450)
        return () => clearTimeout(timer)
    }, [script])

    const handleSegmentThumbClick = useCallback((seg: Segment) => {
        setPreviewingSeg(seg)
    }, [])

    const handlePickVideo = useCallback((segId: number, url: string) => {
        setSelectedVideos(prev => {
            if (!url) {
                const next = { ...prev }
                delete next[segId]
                return next
            }
            return { ...prev, [segId]: url }
        })
        setPreviewingSeg(null)
    }, [])

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
                selected_videos: Object.fromEntries(
                    Object.entries(selectedVideos).map(([k, v]) => [String(k), v])
                ),
            })
            setSegments(res.segments)
            setJobId(res.job_id)
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Error desconocido')
            setLoading(false)
        }
    }, [script, selectedVoice, rate, showSubtitles, selectedVideos])

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
            {config && showSetupWizard && (
                <SetupWizard 
                    onComplete={async () => {
                        // Reload config from backend after saving
                        try {
                            const newConfig = await apiGet<Config>('/config')
                            setConfig(newConfig)
                            setShowSetupWizard(!newConfig.configured)
                        } catch {
                            setShowSetupWizard(true)
                        }
                    }}
                    existingConfig={config}
                />
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
                            onClick={async () => {
                                try {
                                    const latest = await apiGet<Config>('/config')
                                    setConfig(latest)
                                } catch {
                                    // keep current config if refresh fails
                                }
                                setShowSetupWizard(true)
                            }}
                            title="Cambiar API keys"
                        >
                            ⚙️ Config
                        </button>
                    )}
                    <span className="badge">🎙 ElevenLabs HQ · 🎞 Pexels/Pixabay</span>
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
                            {Object.keys(selectedVideos).length > 0 && (
                                <div style={{ fontSize: 12, opacity: 0.8, marginBottom: 10 }}>
                                    🎯 Reemplazos manuales: {Object.keys(selectedVideos).length}
                                </div>
                            )}
                            <div className="segments-grid">
                                {segments.map((seg, i) => (
                                    <SegmentCard
                                        key={seg.id}
                                        seg={seg}
                                        index={i}
                                        videoOptions={videoOptionsBySeg[seg.id] || []}
                                        selectedUrl={selectedVideos[seg.id]}
                                        onThumbClick={() => handleSegmentThumbClick(seg)}
                                    />
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
                                    <optgroup label="Voces ElevenLabs (Premium ✦)">
                                        {voices.elevenlabs.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                                    </optgroup>
                                    <optgroup label="Voces Deepgram (Aura TTS ✦)">
                                        {voices.deepgram.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                                    </optgroup>
                                    <optgroup label="Voces Gratuitas (Microsoft / Google)">
                                        {voices.free.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                                    </optgroup>
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

            {/* Video Replacement Modal */}
            <VideoReplacementModal
                isOpen={previewingSeg !== null}
                segment={previewingSeg}
                options={previewingSeg ? videoOptionsBySeg[previewingSeg.id] || [] : []}
                loading={previewingSeg ? loadingVideosBySeg[previewingSeg.id] || false : false}
                selectedUrl={previewingSeg ? selectedVideos[previewingSeg.id] : undefined}
                onPick={(url) => {
                    if (previewingSeg) {
                        handlePickVideo(previewingSeg.id, url)
                    }
                }}
                onClose={() => setPreviewingSeg(null)}
            />
        </div>
    )
}
