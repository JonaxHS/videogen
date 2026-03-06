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
    telegram_bot_token_preview: string
}

interface PreferencesPayload {
    voice: string
    rate: string
    pitch: string
    show_subtitles: boolean
    subtitle_style: string
}

interface CacheSettings {
    max_cache_size_mb: number
    max_file_age_days: number
    max_file_age_hours: number
    cleanup_interval_seconds: number
}

interface ParseResponse {
    segments: Segment[]
}

interface VideoOptionsResponse {
    options: VideoOption[]
}

interface ScriptGenerationResponse {
    script: string
    model: string
    duration_seconds: number
}

const PREF_KEYS = {
    selectedVoice: 'videogen:selectedVoice',
    rate: 'videogen:rate',
    showSubtitles: 'videogen:showSubtitles',
    subtitleStyle: 'videogen:subtitleStyle',
}

function getStoredString(key: string, fallback: string): string {
    try {
        const value = localStorage.getItem(key)
        return value ?? fallback
    } catch {
        return fallback
    }
}

function getStoredBool(key: string, fallback: boolean): boolean {
    try {
        const value = localStorage.getItem(key)
        if (value === 'true') return true
        if (value === 'false') return false
        return fallback
    } catch {
        return fallback
    }
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
    const [searchQuery, setSearchQuery] = useState<string>('')
    const [searchResults, setSearchResults] = useState<VideoOption[]>([])
    const [defaultGlobalOptions, setDefaultGlobalOptions] = useState<VideoOption[]>([])
    const [selectedProviders, setSelectedProviders] = useState<string[]>(['pexels', 'pixabay', 'nasa', 'esa'])
    const [searchPage, setSearchPage] = useState(1)
    const [searchLoading, setSearchLoading] = useState(false)
    const searchTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

    const toggleProvider = (provider: string) => {
        setSelectedProviders(prev => {
            if (prev.includes(provider)) {
                if (prev.length <= 1) return prev
                return prev.filter(p => p !== provider)
            }
            return [...prev, provider]
        })
    }

    // Reset preview URL when segment changes
    useEffect(() => {
        if (isOpen && segment) {
            setPreviewUrl('')
            setSearchQuery('')
            setSearchResults([])
            setSearchPage(1)
        }
    }, [segment?.id, isOpen, selectedUrl])

    useEffect(() => {
        if (!isOpen) return
        if (!previewUrl) {
            const initial = selectedUrl || options[0]?.url || ''
            if (initial) {
                setPreviewUrl(initial)
            }
        }
    }, [options, previewUrl, isOpen, selectedUrl])

    useEffect(() => {
        if (!isOpen || !segment) return

        let cancelled = false

        const loadGlobalOptions = async () => {
            setSearchLoading(true)
            try {
                const res = await apiPost<VideoOptionsResponse>('/video-options', {
                    keywords: segment.keywords || segment.text,
                    context_text: '',
                    min_duration: segment ? Math.max(3, Math.round(segment.estimated_duration)) : 3,
                    limit: 30,
                    global_search: true,
                    prefer_nasa: true,
                    page: 1,
                    exclude_urls: [],
                    include_providers: selectedProviders,
                })
                if (!cancelled) {
                    setDefaultGlobalOptions(res.options || [])
                    if (!previewUrl && res.options && res.options.length > 0) {
                        setPreviewUrl(res.options[0].url)
                    }
                }
            } catch {
                if (!cancelled) {
                    setDefaultGlobalOptions([])
                }
            } finally {
                if (!cancelled) {
                    setSearchLoading(false)
                }
            }
        }

        loadGlobalOptions()
        return () => {
            cancelled = true
        }
    }, [isOpen, segment, selectedProviders])

    // Debounced search handler
    const handleSearchInput = (query: string) => {
        setSearchQuery(query)
        setSearchPage(1)
        
        if (searchTimeoutRef.current) {
            clearTimeout(searchTimeoutRef.current)
        }

        if (!query.trim()) {
            setSearchResults([])
            return
        }

        setSearchLoading(true)
        searchTimeoutRef.current = setTimeout(async () => {
            try {
                const res = await apiPost<VideoOptionsResponse>('/video-options', {
                    keywords: query,
                    context_text: '',
                    min_duration: segment ? Math.max(3, Math.round(segment.estimated_duration)) : 3,
                    limit: 30,
                    global_search: true,
                    prefer_nasa: true,
                    page: 1,
                    exclude_urls: [],
                    include_providers: selectedProviders,
                })
                setSearchResults(res.options || [])
            } catch {
                // Keep previous results on transient failures
            } finally {
                setSearchLoading(false)
            }
        }, 500) // 500ms debounce
    }

    const runSearch = async (append: boolean) => {
        const query = searchQuery.trim()
        if (!query) return

        const nextPage = append ? searchPage + 1 : 1
        setSearchLoading(true)
        try {
            const res = await apiPost<VideoOptionsResponse>('/video-options', {
                keywords: query,
                context_text: '',
                min_duration: segment ? Math.max(3, Math.round(segment.estimated_duration)) : 3,
                limit: 30,
                global_search: true,
                prefer_nasa: true,
                page: nextPage,
                exclude_urls: [],
                include_providers: selectedProviders,
            })
            const incoming = res.options || []
            if (append) {
                setSearchResults(prev => {
                    const existing = new Set(prev.map(o => o.url))
                    const merged = [...prev]
                    for (const item of incoming) {
                        if (!existing.has(item.url)) {
                            merged.push(item)
                        }
                    }
                    return merged
                })
            } else {
                setSearchResults(incoming)
            }
            setSearchPage(nextPage)
        } catch {
            // Keep current results on transient failures
        } finally {
            setSearchLoading(false)
        }
    }

    const displayOptions = searchQuery.trim()
        ? searchResults
        : (defaultGlobalOptions.length > 0 ? defaultGlobalOptions : options)

    const selectedPreviewOption = displayOptions.find(o => o.url === previewUrl)

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
                    <button
                        onClick={() => {
                            if (!previewUrl) return
                            onPick(previewUrl)
                        }}
                        disabled={!previewUrl}
                        style={{
                            marginTop: 'auto',
                            background: 'linear-gradient(135deg, var(--accent), var(--accent-2))',
                            border: 'none',
                            borderRadius: 8,
                            color: 'white',
                            fontWeight: 700,
                            padding: '10px 12px',
                            cursor: previewUrl ? 'pointer' : 'not-allowed',
                            opacity: previewUrl ? 1 : 0.5,
                        }}
                    >
                        ✅ Usar este video
                    </button>
                </div>

                {/* Options side */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 16, borderLeft: '1px solid var(--border)', overflow: 'hidden' }}>
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

                    {/* Search Input */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {[
                            { id: 'pexels', label: 'Pexels' },
                            { id: 'pixabay', label: 'Pixabay' },
                            { id: 'nasa', label: 'NASA' },
                            { id: 'esa', label: 'ESA' },
                        ].map(provider => {
                            const active = selectedProviders.includes(provider.id)
                            return (
                                <button
                                    key={provider.id}
                                    onClick={() => toggleProvider(provider.id)}
                                    style={{
                                        background: active ? 'rgba(59,130,246,0.2)' : 'rgba(255,255,255,0.06)',
                                        border: `1px solid ${active ? '#3b82f6' : 'var(--border)'}`,
                                        color: 'var(--text)',
                                        borderRadius: 999,
                                        padding: '6px 10px',
                                        fontSize: 12,
                                        cursor: 'pointer',
                                    }}
                                >
                                    {active ? '✅' : '◻️'} {provider.label}
                                </button>
                            )
                        })}
                    </div>

                    <input
                        type="text"
                        placeholder="🔍 Buscar globalmente (Pexels + Pixabay)..."
                        value={searchQuery}
                        onChange={(e) => handleSearchInput(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                                e.preventDefault()
                                runSearch(false)
                            }
                        }}
                        style={{
                            background: 'rgba(255,255,255,0.05)',
                            border: '1px solid var(--border)',
                            borderRadius: 6,
                            padding: '8px 12px',
                            color: 'var(--text)',
                            fontSize: 13,
                            outline: 'none',
                            transition: 'all 0.2s',
                        }}
                    />

                    <div style={{ display: 'flex', gap: 8 }}>
                        <button
                            onClick={() => runSearch(false)}
                            disabled={!searchQuery.trim() || searchLoading}
                            style={{
                                flex: 1,
                                background: 'rgba(124,58,237,0.18)',
                                border: '1px solid var(--border)',
                                borderRadius: 6,
                                color: 'var(--text)',
                                padding: '8px 10px',
                                cursor: !searchQuery.trim() || searchLoading ? 'not-allowed' : 'pointer',
                                opacity: !searchQuery.trim() || searchLoading ? 0.6 : 1,
                            }}
                        >
                            🔎 Buscar
                        </button>
                        <button
                            onClick={() => runSearch(true)}
                            disabled={!searchQuery.trim() || searchLoading}
                            style={{
                                flex: 1,
                                background: 'rgba(255,255,255,0.08)',
                                border: '1px solid var(--border)',
                                borderRadius: 6,
                                color: 'var(--text)',
                                padding: '8px 10px',
                                cursor: !searchQuery.trim() || searchLoading ? 'not-allowed' : 'pointer',
                                opacity: !searchQuery.trim() || searchLoading ? 0.6 : 1,
                            }}
                        >
                            ➕ Buscar más
                        </button>
                    </div>

                    <button
                        onClick={() => {
                            if (!previewUrl) return
                            onPick(previewUrl)
                        }}
                        disabled={!previewUrl}
                        style={{
                            marginTop: 6,
                            background: 'linear-gradient(135deg, var(--accent), var(--accent-2))',
                            border: 'none',
                            borderRadius: 8,
                            color: 'white',
                            fontWeight: 700,
                            padding: '10px 12px',
                            cursor: previewUrl ? 'pointer' : 'not-allowed',
                            opacity: previewUrl ? 1 : 0.5,
                        }}
                    >
                        ✅ Seleccionar video
                    </button>

                    {(loading || searchLoading) && (
                        <div style={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: 12,
                            padding: 24,
                            minHeight: 200
                        }}>
                            <div className="spinner" style={{
                                width: 40,
                                height: 40,
                                border: '3px solid rgba(255,255,255,0.1)',
                                borderTop: '3px solid var(--accent)',
                                borderRadius: '50%',
                            }} />
                            <div style={{ fontSize: 14, fontWeight: 500 }}>🎬 Buscando videos...</div>
                            <div style={{ fontSize: 12, opacity: 0.6 }}>Esto puede tomar unos segundos</div>
                        </div>
                    )}

                    {!loading && !searchLoading && previewUrl && (
                        <div style={{ fontSize: 12, opacity: 0.75, padding: '8px 0' }}>
                            Vista previa: {selectedPreviewOption?.provider || 'video seleccionado'} · {selectedPreviewOption?.duration || '?'}s
                        </div>
                    )}

                    {!loading && !searchLoading && displayOptions.length === 0 && (
                        <div style={{ fontSize: 13, textAlign: 'center', opacity: 0.7, padding: 24 }}>
                            {searchQuery.trim() ? '❌ No se encontraron videos' : '⚠️ No hay opciones de video'}
                        </div>
                    )}

                    {!loading && !searchLoading && displayOptions.length > 0 && (
                        <div style={{ display: 'grid', gap: 8, overflow: 'auto', maxHeight: 'calc(90vh - 200px)' }}>
                            {displayOptions.map((opt) => (
                                <button
                                    key={opt.url}
                                    onClick={() => {
                                        setPreviewUrl(opt.url)
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
                                    {opt.thumbnail && opt.thumbnail.trim() && opt.thumbnail.startsWith('http') && (
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
    const [telegramBotToken, setTelegramBotToken] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [success, setSuccess] = useState(false)

    // Indicators for already-configured keys
    const hasPexels = !!existingConfig?.pexels_key_preview
    const hasPixabay = !!existingConfig?.pixabay_key_preview
    const hasElevenlabs = !!existingConfig?.elevenlabs_key_preview
    const hasDeepgram = !!existingConfig?.deepgram_key_preview
    const hasTelegramBot = !!existingConfig?.telegram_bot_token_preview

    const handleSave = async () => {
        setError(null)
        setLoading(true)
        try {
            await apiPost('/setup', {
                pexels_api_key: pexelsKey,
                pixabay_api_key: pixabayKey,
                elevenlabs_api_key: elevenlabsKey,
                deepgram_api_key: deepgramKey,
                telegram_bot_token: telegramBotToken,
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

                        <div className="wizard-field" style={{ marginTop: '12px' }}>
                            <label className="wizard-label">
                                🤖 Telegram Bot Token (Opcional)
                            </label>
                            <p className="wizard-hint">
                                Créalo con{' '}
                                <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" className="wizard-link">
                                    @BotFather
                                </a>{' '}
                                y pega el token aquí para activar generación desde Telegram.
                            </p>
                            <input
                                id="telegram-bot-token-input"
                                type="text"
                                className="wizard-input"
                                placeholder={hasTelegramBot ? `Ya configurado: ${existingConfig?.telegram_bot_token_preview || ''}` : "Pega tu Telegram Bot Token..."}
                                value={telegramBotToken}
                                onChange={e => setTelegramBotToken(e.target.value)}
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
            {videoOptions.length > 0 && (
                <div
                    onClick={onThumbClick}
                    className="segment-thumb"
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
                        <div style={{ opacity: 0.5, fontSize: 10 }}>🎬</div>
                    )}
                </div>
            )}
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

// ─── Config Panel ─────────────────────────────────────────────────────────────

function ConfigPanel({
    onClose,
    existingConfig,
    onReload,
}: {
    onClose: () => void
    existingConfig?: Config
    onReload: () => void
}) {
    const [pexelsKey, setPexelsKey] = useState('')
    const [pixabayKey, setPixabayKey] = useState('')
    const [elevenlabsKey, setElevenlabsKey] = useState('')
    const [deepgramKey, setDeepgramKey] = useState('')
    const [telegramBotToken, setTelegramBotToken] = useState('')
    const [loading, setLoading] = useState(false)
    const [cleanupLoading, setCleanupLoading] = useState(false)
    const [cleanupMessage, setCleanupMessage] = useState<string | null>(null)
    const [cacheSettingsLoading, setCacheSettingsLoading] = useState(false)
    const [cacheSettingsMessage, setCacheSettingsMessage] = useState<string | null>(null)
    const [maxCacheSizeMb, setMaxCacheSizeMb] = useState(800)
    const [maxFileAgeDays, setMaxFileAgeDays] = useState(1)
    const [maxFileAgeHours, setMaxFileAgeHours] = useState(12)
    const [cleanupIntervalSeconds, setCleanupIntervalSeconds] = useState(30)
    const [error, setError] = useState<string | null>(null)
    const [success, setSuccess] = useState(false)

    const hasPexels = !!existingConfig?.pexels_key_preview
    const hasPixabay = !!existingConfig?.pixabay_key_preview
    const hasElevenlabs = !!existingConfig?.elevenlabs_key_preview
    const hasDeepgram = !!existingConfig?.deepgram_key_preview
    const hasTelegramBot = !!existingConfig?.telegram_bot_token_preview

    useEffect(() => {
        let cancelled = false
        apiGet<CacheSettings>('/cache-settings')
            .then(settings => {
                if (cancelled) return
                setMaxCacheSizeMb(settings.max_cache_size_mb || 800)
                setMaxFileAgeDays(settings.max_file_age_days || 0)
                setMaxFileAgeHours(settings.max_file_age_hours || 0)
                setCleanupIntervalSeconds(settings.cleanup_interval_seconds || 30)
            })
            .catch(() => {
                // Keep defaults if endpoint is temporarily unavailable
            })
        return () => {
            cancelled = true
        }
    }, [])

    const handleSave = async () => {
        setError(null)
        setLoading(true)
        try {
            await apiPost('/setup', {
                pexels_api_key: pexelsKey,
                pixabay_api_key: pixabayKey,
                elevenlabs_api_key: elevenlabsKey,
                deepgram_api_key: deepgramKey,
                telegram_bot_token: telegramBotToken,
            })
            setSuccess(true)
            setTimeout(() => {
                onReload()
                onClose()
            }, 1200)
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Error desconocido')
        } finally {
            setLoading(false)
        }
    }

    const handleCleanup = async () => {
        setCleanupLoading(true)
        setCleanupMessage(null)
        try {
            const res = await apiPost<any>('/cleanup', {})
            setCleanupMessage(`✅ ${res.message}\nLiberados: ${res.freed}`)
            setTimeout(() => setCleanupMessage(null), 5000)
        } catch (e: unknown) {
            setCleanupMessage(`❌ Error: ${e instanceof Error ? e.message : 'Error desconocido'}`)
        } finally {
            setCleanupLoading(false)
        }
    }

    const handleSaveCacheSettings = async () => {
        setCacheSettingsLoading(true)
        setCacheSettingsMessage(null)
        try {
            const res = await apiPost<any>('/cache-settings', {
                max_cache_size_mb: maxCacheSizeMb,
                max_file_age_days: maxFileAgeDays,
                max_file_age_hours: maxFileAgeHours,
                cleanup_interval_seconds: cleanupIntervalSeconds,
            })
            setCacheSettingsMessage(`✅ ${res.message}`)
            setTimeout(() => setCacheSettingsMessage(null), 4000)
        } catch (e: unknown) {
            setCacheSettingsMessage(`❌ Error: ${e instanceof Error ? e.message : 'Error desconocido'}`)
        } finally {
            setCacheSettingsLoading(false)
        }
    }

    return (
        <div className="config-panel-overlay">
            <div className="config-panel">
                <div className="config-panel-header">
                    <h2>⚙️ Configuración</h2>
                    <button
                        className="btn-close"
                        onClick={onClose}
                        aria-label="Cerrar"
                    >
                        ✕
                    </button>
                </div>

                <div className="config-panel-body">
                    <div className="config-section">
                        <h3>Proveedores de Video</h3>
                        <div className="config-field">
                            <label>🔑 Pexels API Key {hasPexels && '✓'}</label>
                            <p className="config-hint">
                                Regístrate gratis en <a href="https://www.pexels.com/api/" target="_blank" rel="noreferrer">pexels.com/api</a>
                            </p>
                            <input
                                type="text"
                                placeholder={hasPexels ? `Ya configurada: ${existingConfig?.pexels_key_preview || ''}` : "Pega tu Pexels API Key..."}
                                value={pexelsKey}
                                onChange={e => setPexelsKey(e.target.value)}
                                disabled={loading}
                            />
                        </div>

                        <div className="config-field">
                            <label>🎞️ Pixabay API Key {hasPixabay && '✓'}</label>
                            <p className="config-hint">
                                Regístrate gratis en <a href="https://pixabay.com/api/docs/" target="_blank" rel="noreferrer">pixabay.com/api/docs</a>
                            </p>
                            <input
                                type="text"
                                placeholder={hasPixabay ? `Ya configurada: ${existingConfig?.pixabay_key_preview || ''}` : "Pega tu Pixabay API Key..."}
                                value={pixabayKey}
                                onChange={e => setPixabayKey(e.target.value)}
                                disabled={loading}
                            />
                        </div>
                    </div>

                    <div className="config-section">
                        <h3>Proveedores de Voz</h3>
                        <div className="config-field">
                            <label>🎙️ ElevenLabs API Key {hasElevenlabs && '✓'}</label>
                            <p className="config-hint">
                                Regístrate en <a href="https://elevenlabs.io/" target="_blank" rel="noreferrer">elevenlabs.io</a> para voces premium
                            </p>
                            <input
                                type="text"
                                placeholder={hasElevenlabs ? `Ya configurada: ${existingConfig?.elevenlabs_key_preview || ''}` : "Pega tu ElevenLabs API Key..."}
                                value={elevenlabsKey}
                                onChange={e => setElevenlabsKey(e.target.value)}
                                disabled={loading}
                            />
                        </div>

                        <div className="config-field">
                            <label>🎤 Deepgram API Key {hasDeepgram && '✓'}</label>
                            <p className="config-hint">
                                Accede a <a href="https://console.deepgram.com/" target="_blank" rel="noreferrer">console.deepgram.com</a> (opcional)
                            </p>
                            <input
                                type="text"
                                placeholder={hasDeepgram ? `Ya configurada: ${existingConfig?.deepgram_key_preview || ''}` : "Pega tu Deepgram API Key..."}
                                value={deepgramKey}
                                onChange={e => setDeepgramKey(e.target.value)}
                                disabled={loading}
                            />
                        </div>
                    </div>

                    <div className="config-section">
                        <h3>Integraciones</h3>
                        <div className="config-field">
                            <label>🤖 Telegram Bot Token {hasTelegramBot && '✓'}</label>
                            <p className="config-hint">
                                Créalo con <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a> para enviar videos por Telegram
                            </p>
                            <input
                                type="text"
                                placeholder={hasTelegramBot ? `Ya configurado: ${existingConfig?.telegram_bot_token_preview || ''}` : "Pega tu Telegram Bot Token..."}
                                value={telegramBotToken}
                                onChange={e => setTelegramBotToken(e.target.value)}
                                disabled={loading}
                            />
                        </div>
                    </div>

                    <div className="config-section">
                        <h3>🧹 Mantenimiento</h3>
                        <div className="config-field">
                            <label>Limpieza Automática de Cache</label>
                            <p className="config-hint">
                                Ajusta cuánto cache conservar, cada cuánto revisar y cuándo expirar archivos.
                            </p>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                                <div>
                                    <label style={{ display: 'block', marginBottom: 6, fontSize: 12, opacity: 0.8 }}>Máx. cache (MB)</label>
                                    <input
                                        type="number"
                                        min={200}
                                        value={maxCacheSizeMb}
                                        onChange={e => setMaxCacheSizeMb(Number(e.target.value || 0))}
                                        disabled={cacheSettingsLoading}
                                    />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: 6, fontSize: 12, opacity: 0.8 }}>Intervalo revisión (s)</label>
                                    <input
                                        type="number"
                                        min={10}
                                        value={cleanupIntervalSeconds}
                                        onChange={e => setCleanupIntervalSeconds(Number(e.target.value || 0))}
                                        disabled={cacheSettingsLoading}
                                    />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: 6, fontSize: 12, opacity: 0.8 }}>Expirar por horas</label>
                                    <input
                                        type="number"
                                        min={0}
                                        value={maxFileAgeHours}
                                        onChange={e => setMaxFileAgeHours(Number(e.target.value || 0))}
                                        disabled={cacheSettingsLoading}
                                    />
                                </div>
                                <div>
                                    <label style={{ display: 'block', marginBottom: 6, fontSize: 12, opacity: 0.8 }}>Expirar por días (fallback)</label>
                                    <input
                                        type="number"
                                        min={0}
                                        value={maxFileAgeDays}
                                        onChange={e => setMaxFileAgeDays(Number(e.target.value || 0))}
                                        disabled={cacheSettingsLoading}
                                    />
                                </div>
                            </div>

                            <button
                                onClick={handleSaveCacheSettings}
                                disabled={cacheSettingsLoading}
                                style={{
                                    width: '100%',
                                    marginTop: 10,
                                    background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
                                    border: 'none',
                                    borderRadius: 6,
                                    color: 'white',
                                    padding: '10px 12px',
                                    cursor: cacheSettingsLoading ? 'not-allowed' : 'pointer',
                                    opacity: cacheSettingsLoading ? 0.7 : 1,
                                    fontWeight: 500,
                                }}
                            >
                                {cacheSettingsLoading ? '⏳ Guardando limpieza automática...' : '💾 Guardar limpieza automática'}
                            </button>

                            {cacheSettingsMessage && (
                                <div style={{
                                    marginTop: 12,
                                    padding: 10,
                                    borderRadius: 6,
                                    background: cacheSettingsMessage.startsWith('✅') ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                    border: `1px solid ${cacheSettingsMessage.startsWith('✅') ? '#22c55e' : '#ef4444'}`,
                                    fontSize: 13,
                                    color: 'var(--text)',
                                    whiteSpace: 'pre-wrap',
                                }}>
                                    {cacheSettingsMessage}
                                </div>
                            )}
                        </div>

                        <div className="config-field">
                            <label>Limpiar Cache de Videos</label>
                            <p className="config-hint">
                                Elimina archivos de cache antiguos para liberar espacio en disco
                            </p>
                            <button
                                onClick={handleCleanup}
                                disabled={cleanupLoading}
                                style={{
                                    width: '100%',
                                    background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                                    border: 'none',
                                    borderRadius: 6,
                                    color: 'white',
                                    padding: '10px 12px',
                                    cursor: cleanupLoading ? 'not-allowed' : 'pointer',
                                    opacity: cleanupLoading ? 0.7 : 1,
                                    fontWeight: 500,
                                }}
                            >
                                {cleanupLoading ? '⏳ Limpiando...' : '🧹 Limpiar Cache'}
                            </button>
                            {cleanupMessage && (
                                <div style={{
                                    marginTop: 12,
                                    padding: 10,
                                    borderRadius: 6,
                                    background: cleanupMessage.startsWith('✅') ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                    border: `1px solid ${cleanupMessage.startsWith('✅') ? '#22c55e' : '#ef4444'}`,
                                    fontSize: 13,
                                    color: 'var(--text)',
                                    whiteSpace: 'pre-wrap',
                                }}>
                                    {cleanupMessage}
                                </div>
                            )}
                        </div>
                    </div>

                    {error && <div className="config-error">❌ {error}</div>}
                    {success && <div className="config-success">✅ ¡Configuración guardada!</div>}
                </div>

                <div className="config-panel-footer">
                    <button className="btn-secondary" onClick={onClose} disabled={loading || success}>
                        Cancelar
                    </button>
                    <button
                        className="btn-generate"
                        onClick={handleSave}
                        disabled={!pexelsKey.trim() && !pixabayKey.trim() && !hasPexels && !hasPixabay || loading || success}
                    >
                        {loading ? '⏳ Guardando...' : success ? '✅ ¡Listo!' : '💾 Guardar cambios'}
                    </button>
                </div>
            </div>
        </div>
    )
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
    const [config, setConfig] = useState<Config | null>(null)
    const [showSetupWizard, setShowSetupWizard] = useState(false)
    const [showConfigPanel, setShowConfigPanel] = useState(false)
    const [checkingConfig, setCheckingConfig] = useState(true)
    const [script, setScript] = useState('')
    const [scriptTopic, setScriptTopic] = useState('')
    const [scriptTone, setScriptTone] = useState('educativo viral')
    const [scriptDurationSeconds, setScriptDurationSeconds] = useState(60)
    const [scriptGeneratorLoading, setScriptGeneratorLoading] = useState(false)
    const [segments, setSegments] = useState<Segment[]>([])
    const [selectedVideos, setSelectedVideos] = useState<Record<number, string>>({})
    const [videoOptionsBySeg, setVideoOptionsBySeg] = useState<Record<number, VideoOption[]>>({})
    const [loadingVideosBySeg, setLoadingVideosBySeg] = useState<Record<number, boolean>>({})
    const [previewingSeg, setPreviewingSeg] = useState<Segment | null>(null)
    const [voices, setVoices] = useState<VoicesResponse>({ elevenlabs: [], deepgram: [], free: [] })
    const [selectedVoice, setSelectedVoice] = useState(() => getStoredString(PREF_KEYS.selectedVoice, 'ErXwobaYiN019PkySvjV'))
    const [showSubtitles, setShowSubtitles] = useState(() => getStoredBool(PREF_KEYS.showSubtitles, true))
    const [subtitleStyle, setSubtitleStyle] = useState(() => getStoredString(PREF_KEYS.subtitleStyle, 'classic'))
    const [rate, setRate] = useState(() => getStoredString(PREF_KEYS.rate, '+0%'))
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
                setConfig({ configured: false, pexels_key_preview: '', pixabay_key_preview: '', elevenlabs_key_preview: '', deepgram_key_preview: '', telegram_bot_token_preview: '' })
                setShowSetupWizard(true)
            })
            .finally(() => setCheckingConfig(false))
    }, [])

    // Load voices on mount
    useEffect(() => {
        apiGet<VoicesResponse>('/voices')
            .then(d => {
                setVoices(d)
                const availableVoiceIds = new Set([
                    ...d.elevenlabs.map(v => v.id),
                    ...d.deepgram.map(v => v.id),
                    ...d.free.map(v => v.id),
                ])

                setSelectedVoice(prev => {
                    if (availableVoiceIds.has(prev)) {
                        return prev
                    }
                    if (config && !config.elevenlabs_key_preview && d.free.length > 0) {
                        return d.free[0].id
                    }
                    return d.elevenlabs[0]?.id || d.deepgram[0]?.id || d.free[0]?.id || prev
                })
            })
            .catch(() => { })
    }, [config])

    useEffect(() => {
        try {
            localStorage.setItem(PREF_KEYS.selectedVoice, selectedVoice)
        } catch { }
    }, [selectedVoice])

    useEffect(() => {
        try {
            localStorage.setItem(PREF_KEYS.rate, rate)
        } catch { }
    }, [rate])

    useEffect(() => {
        try {
            localStorage.setItem(PREF_KEYS.showSubtitles, String(showSubtitles))
        } catch { }
    }, [showSubtitles])

    useEffect(() => {
        try {
            localStorage.setItem(PREF_KEYS.subtitleStyle, subtitleStyle)
        } catch { }
    }, [subtitleStyle])

    // Sync current UI defaults to backend so Telegram bot uses the same settings
    useEffect(() => {
        if (checkingConfig) return

        const timer = setTimeout(() => {
            const payload: PreferencesPayload = {
                voice: selectedVoice,
                rate,
                pitch: '+0Hz',
                show_subtitles: showSubtitles,
                subtitle_style: subtitleStyle,
            }
            apiPost('/preferences', payload).catch(() => {
                // Silent fail: this sync is best-effort
            })
        }, 450)

        return () => clearTimeout(timer)
    }, [checkingConfig, selectedVoice, rate, showSubtitles, subtitleStyle])

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
                // Preserve selected videos for segments that still exist
                setSelectedVideos(prev => {
                    const preserved: Record<number, string> = {}
                    for (const seg of newSegs) {
                        if (prev[seg.id]) {
                            preserved[seg.id] = prev[seg.id]
                        }
                    }
                    return preserved
                })
                setPreviewingSeg(null)

                // Load videos segment by segment to avoid repeating the same top clip
                setLoadingVideosBySeg(
                    newSegs.reduce((acc, s) => ({ ...acc, [s.id]: true }), {})
                )

                const videosBySegId: Record<number, VideoOption[]> = {}
                const usedPreviewUrls = new Set<string>(Object.values(selectedVideos || {}))

                for (const seg of newSegs) {
                    try {
                        const res = await apiPost<VideoOptionsResponse>('/video-options', {
                            keywords: seg.keywords,
                            context_text: seg.text,
                            min_duration: Math.max(3, Math.round(seg.estimated_duration)),
                            limit: 12,
                            global_search: true,
                            prefer_nasa: true,
                            exclude_urls: Array.from(usedPreviewUrls),
                        })

                        const options = res.options || []
                        videosBySegId[seg.id] = options

                        const topUrl = options[0]?.url
                        if (topUrl) {
                            usedPreviewUrls.add(topUrl)
                        }
                    } catch {
                        videosBySegId[seg.id] = []
                    } finally {
                        setLoadingVideosBySeg(prev => ({ ...prev, [seg.id]: false }))
                    }
                }

                // Auto-select the first video option for each segment if not already selected
                setSelectedVideos(prev => {
                    const updated = { ...prev }
                    for (const seg of newSegs) {
                        if (!updated[seg.id] && videosBySegId[seg.id]?.length > 0) {
                            updated[seg.id] = videosBySegId[seg.id][0].url
                        }
                    }
                    return updated
                })

                setVideoOptionsBySeg(videosBySegId)
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
                subtitle_style: subtitleStyle,
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
    }, [script, selectedVoice, rate, showSubtitles, subtitleStyle, selectedVideos])

    const handlePreviewNoVoice = useCallback(async () => {
        if (!script.trim()) return
        setError(null)
        setJob(null)
        setLoading(true)

        try {
            const res = await apiPost<{ job_id: string; segments: Segment[] }>('/generate-preview', {
                script,
                show_subtitles: showSubtitles,
                subtitle_style: subtitleStyle,
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
    }, [script, showSubtitles, subtitleStyle, selectedVideos])

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

    const handleGenerateScriptWithAI = useCallback(async () => {
        if (!scriptTopic.trim()) {
            setError('Escribe un tema para generar el guion con IA')
            return
        }

        setError(null)
        setScriptGeneratorLoading(true)
        try {
            const res = await apiPost<ScriptGenerationResponse>('/generate-script', {
                topic: scriptTopic,
                tone: scriptTone,
                duration_seconds: scriptDurationSeconds,
                language: 'es',
            })
            setScript(res.script || '')
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'No se pudo generar el guion con IA')
        } finally {
            setScriptGeneratorLoading(false)
        }
    }, [scriptTopic, scriptTone, scriptDurationSeconds])

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
            {/* Config Panel overlay */}
            {showConfigPanel && (
                <ConfigPanel
                    onClose={() => setShowConfigPanel(false)}
                    existingConfig={config || undefined}
                    onReload={async () => {
                        try {
                            const newConfig = await apiGet<Config>('/config')
                            setConfig(newConfig)
                        } catch {
                            // keep current config
                        }
                    }}
                />
            )}

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
                            onClick={() => setShowConfigPanel(true)}
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
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: '1fr 160px 130px',
                            gap: 10,
                            marginBottom: 10,
                        }}>
                            <input
                                type="text"
                                placeholder="Tema del guion (ej: viajar al futuro con relatividad)"
                                value={scriptTopic}
                                onChange={e => setScriptTopic(e.target.value)}
                                disabled={!!isRunning || scriptGeneratorLoading}
                                style={{ width: '100%' }}
                            />
                            <input
                                type="text"
                                placeholder="Tono"
                                value={scriptTone}
                                onChange={e => setScriptTone(e.target.value)}
                                disabled={!!isRunning || scriptGeneratorLoading}
                                style={{ width: '100%' }}
                            />
                            <input
                                type="number"
                                min={15}
                                max={180}
                                step={5}
                                value={scriptDurationSeconds}
                                onChange={e => setScriptDurationSeconds(Number(e.target.value || 60))}
                                disabled={!!isRunning || scriptGeneratorLoading}
                                style={{ width: '100%' }}
                            />
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 10 }}>
                            <button
                                className="btn-secondary"
                                onClick={handleGenerateScriptWithAI}
                                disabled={!!isRunning || scriptGeneratorLoading || !scriptTopic.trim()}
                            >
                                {scriptGeneratorLoading ? '🤖 Generando con Qwen...' : '🤖 Generar guion con Qwen'}
                            </button>
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

                            {showSubtitles && (
                                <div className="field">
                                    <label htmlFor="subtitle-style">🎨 Estilo de subtítulos</label>
                                    <select
                                        id="subtitle-style"
                                        value={subtitleStyle}
                                        onChange={e => setSubtitleStyle(e.target.value)}
                                        disabled={!!isRunning}
                                        style={{
                                            background: 'var(--bg-input)',
                                            border: '1px solid var(--border)',
                                            borderRadius: 6,
                                            padding: '8px 12px',
                                            color: 'var(--text)',
                                            fontSize: 13,
                                            cursor: 'pointer',
                                            outline: 'none',
                                        }}
                                    >
                                        <option value="classic">📝 Clásico (Blanco/Negro)</option>
                                        <option value="luminous">✨ Luminoso (Con sombra)</option>
                                        <option value="cinema">🎬 Cine (Grande y nítido)</option>
                                        <option value="yellow-subtitle">💛 Amarillo (Tradicional)</option>
                                        <option value="minimal">🔍 Minimalista (Pequeño/Arriba)</option>
                                        <option value="neon">💫 Neón (Cyan brillante)</option>
                                        <option value="karaoke">🎤 Karaoke (Progresivo)</option>
                                    </select>
                                </div>
                            )}
                        </div>
                    </div>

                    <div style={{ display: 'grid', gap: 10 }}>
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
                        <button
                            id="btn-preview-video"
                            className="btn-secondary"
                            onClick={handlePreviewNoVoice}
                            disabled={!script.trim() || !!isRunning || !config?.configured}
                        >
                            👀 Previsualizar video (sin voz)
                        </button>
                    </div>

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
