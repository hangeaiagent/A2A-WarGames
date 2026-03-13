import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getSessions, getSession, createSession, deleteSession,
  runSession, stopSession, injectMessage, getAnalytics,
  createSessionStream, pauseSession, resumeSession, recoverSession, continueSession,
} from '../api/client'
import { useNotificationSounds } from '../composables/useNotificationSounds'

export const useSessionStore = defineStore('sessions', () => {
  const sessions = ref([])
  const currentSession = ref(null)
  const turns = ref([])
  const observerData = ref({})
  const analyticsRounds = ref([])
  const syntheses = ref([])
  const agentOverrides = ref({})
  const status = ref('idle')
  const eventSource = ref(null)
  const analyticsData = ref(null)

  // Real-time status notifications (phase updates from engine)
  const statusMessage = ref(null)  // { phase, message, speaker, speaker_name, round }

  // #92: current round tracking (round_start / round_end SSE events)
  const currentRound = ref(null)    // number | null — null means no active round

  // CR-011: private thread state
  const privateThreads = ref([])   // array of thread objects for WhisperPanel

  // Legacy refs — kept for backwards compatibility, no longer used by streaming flow
  const thinkingByAgent = ref({})  // { [speaker]: string }
  const contentByAgent = ref({})   // { [speaker]: string }

  // CR-012: streaming message state keyed by speaker slug
  // This is the single source of truth for in-progress streaming tokens.
  // Both content_token and thinking_token events write here.
  // On turn_end/turn, content is flushed into `turns` and the entry is cleared.
  const streamingMessages = ref({})  // { [speaker]: { content: '', thinking: '' } }

  function appendStreamToken(speaker, delta) {
    if (!streamingMessages.value[speaker]) {
      streamingMessages.value[speaker] = { content: '', thinking: '' }
    }
    streamingMessages.value[speaker].content += delta ?? ''
  }

  function appendThinkingToken(speaker, delta) {
    if (!streamingMessages.value[speaker]) {
      streamingMessages.value[speaker] = { content: '', thinking: '' }
    }
    streamingMessages.value[speaker].thinking += delta ?? ''
  }

  function clearStreamingMessage(speaker) {
    delete streamingMessages.value[speaker]
  }

  async function fetchSessions(projectId) {
    const r = await getSessions(projectId)
    sessions.value = r.data
    return r.data
  }

  async function fetchSession(id) {
    const r = await getSession(id)
    currentSession.value = r.data
    status.value = r.data.status
    return r.data
  }

  async function createNewSession(data) {
    const r = await createSession(data)
    await fetchSessions(data.project_id)
    return r.data
  }

  async function removeSession(id) {
    await deleteSession(id)
  }

  // --- Extracted SSE connection setup ---
  // Registers all event listeners on a new EventSource for the given sessionId.
  // Called by startSession (after runSession) and recoverCurrentSession.
  async function connectToStream(sessionId) {
    const sounds = useNotificationSounds()
    const es = await createSessionStream(sessionId)  // #130: async ticket flow
    eventSource.value = es

    // --- Streaming thinking tokens (unified into streamingMessages) ---
    es.addEventListener('thinking_token', (e) => {
      try {
        const data = JSON.parse(e.data)
        appendThinkingToken(data.speaker, data.delta)
      } catch (err) {
        console.warn('[SSE] thinking_token parse error:', err, e.data?.slice?.(0, 200))
      }
    })

    // --- CR-012: Streaming content tokens ---
    es.addEventListener('content_token', (e) => {
      try {
        const data = JSON.parse(e.data)
        appendStreamToken(data.speaker, data.delta)
      } catch (err) {
        console.warn('[SSE] content_token parse error:', err, e.data?.slice?.(0, 200))
      }
    })

    // --- #218: clear streaming buffer when LLM retries mid-stream ---
    es.addEventListener('stream_reset', (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.speaker) clearStreamingMessage(data.speaker)
      } catch {}
    })

    // --- #92: round lifecycle tracking ---
    es.addEventListener('round_start', (e) => {
      try {
        const data = JSON.parse(e.data)
        currentRound.value = data.round ?? null
      } catch {}
    })

    es.addEventListener('round_end', (e) => {
      try {
        const data = JSON.parse(e.data)
        // Keep currentRound set to the completed round number so UI can
        // show "Round N complete" — reset to null on next round_start
        currentRound.value = data.round ?? currentRound.value
      } catch {}
    })

    // --- CR-012: keepalive ---
    es.addEventListener('ping', () => {})

    // --- Real-time status notifications ---
    es.addEventListener('status', (e) => {
      try {
        const data = JSON.parse(e.data)
        statusMessage.value = data
      } catch (err) {
        console.warn('[SSE] status parse error:', err)
      }
    })

    // Shared handler for turn_end / turn events
    function handleTurnEvent(e, eventName) {
      let data
      try {
        data = JSON.parse(e.data)
      } catch (err) {
        console.error(`[SSE] ${eventName} JSON parse failed:`, err, e.data?.slice?.(0, 300))
        return
      }

      const speaker = data.speaker ?? data.speaker_slug

      // Read streamed content BEFORE clearing
      const streamed = streamingMessages.value[speaker]
      const streamedContent = streamed?.content || ''
      const streamedThinking = streamed?.thinking || ''

      // Use the longest available content: streamed accumulation vs backend payload
      // This guards against proxy truncation or missed content_token events
      const finalContent = (streamedContent.length >= (data.content || '').length)
        ? streamedContent
        : (data.content || '')

      if (!finalContent && data.content) {
        console.warn(`[SSE] ${eventName}: empty finalContent for ${speaker}, backend had ${data.content?.length} chars`)
      }

      const turnWithThinking = {
        ...data,
        content: finalContent || data.content || '[Response not received]',
        thinking: streamedThinking,
      }

      // Debug: log content resolution
      if (import.meta.env.DEV) {
        console.debug(`[SSE] ${eventName}: speaker=${speaker} streamed=${streamedContent.length}ch backend=${(data.content||'').length}ch final=${turnWithThinking.content.length}ch`)
      }

      turns.value.push(turnWithThinking)

      // Clear streaming buffers AFTER reading
      if (speaker) {
        clearStreamingMessage(speaker)
      }

      statusMessage.value = null

      if (speaker === 'moderator') {
        sounds.onModeratorMessage()
      } else {
        sounds.onAgentMessage()
      }
    }

    // --- turn_end: flush accumulated buffers into a complete turn object ---
    es.addEventListener('turn_end', (e) => handleTurnEvent(e, 'turn_end'))

    // --- turn: legacy event (backend may emit this instead of turn_end) ---
    es.addEventListener('turn', (e) => handleTurnEvent(e, 'turn'))

    es.addEventListener('observer', (e) => {
      const data = JSON.parse(e.data)
      observerData.value = { ...observerData.value, [data.speaker]: data }
    })

    es.addEventListener('analytics', (e) => {
      const data = JSON.parse(e.data)
      analyticsRounds.value.push(data)
    })

    es.addEventListener('synthesis', (e) => {
      const data = JSON.parse(e.data)
      syntheses.value.push(data)
    })

    // CR-011: Whisper opportunity events (agent gets chance to open a private thread)
    es.addEventListener('whisper_opportunity_start', (e) => {
      try {
        const data = JSON.parse(e.data)
        // Track that an agent is evaluating a whisper opportunity (UI can show pending state)
        if (!privateThreads.value.find(t => t.thread_id === data.thread_id)) {
          privateThreads.value.push({
            thread_id: data.thread_id,
            initiator: data.initiator,
            initiator_name: data.initiator_name,
            target: data.target,
            target_name: data.target_name,
            round: data.round,
            status: 'pending',
            messages: [],
          })
        }
      } catch (err) {
        console.warn('[SSE] whisper_opportunity_start parse error:', err)
      }
    })

    es.addEventListener('whisper_opportunity_end', (e) => {
      try {
        const data = JSON.parse(e.data)
        // Remove pending thread if the opportunity was not taken
        const idx = privateThreads.value.findIndex(
          t => t.thread_id === data.thread_id && t.status === 'pending'
        )
        if (idx !== -1) {
          privateThreads.value.splice(idx, 1)
        }
      } catch (err) {
        console.warn('[SSE] whisper_opportunity_end parse error:', err)
      }
    })

    // CR-011: Whisper channel events
    es.addEventListener('whisper_thread_open', (e) => {
      const data = JSON.parse(e.data)
      // If a pending thread exists for this id, upgrade it to open
      const existing = privateThreads.value.find(t => t.thread_id === data.thread_id)
      if (existing) {
        existing.status = 'open'
      } else {
        privateThreads.value.push({
          thread_id: data.thread_id,
          initiator: data.initiator,
          initiator_name: data.initiator_name,
          target: data.target,
          target_name: data.target_name,
          round: data.round,
          status: 'open',
          messages: [],
        })
      }
    })

    es.addEventListener('whisper_turn_end', (e) => {
      const data = JSON.parse(e.data)
      const thread = privateThreads.value.find(t => t.thread_id === data.thread_id)
      if (thread) {
        thread.messages.push({
          speaker: data.speaker,
          speaker_name: data.speaker_name,
          content: data.content,
          round: data.round,
        })
      }
    })

    es.addEventListener('whisper_thread_close', (e) => {
      const data = JSON.parse(e.data)
      const thread = privateThreads.value.find(t => t.thread_id === data.thread_id)
      if (thread) {
        thread.status = data.outcome === 'declined' ? 'declined' : 'closed'
      }
    })

    es.addEventListener('session_paused', () => {
      sounds.onSessionPaused()
      status.value = 'paused'
    })

    es.addEventListener('session_resumed', () => {
      status.value = 'running'
    })

    es.addEventListener('done', () => {
      sounds.onSessionEnd()
      statusMessage.value = null
      status.value = 'complete'
      // #146: defer close by one tick so buffered observer/analytics events
      // that arrive in the same TCP window are processed before the connection drops
      setTimeout(() => { es.close(); eventSource.value = null }, 0)
    })

    es.addEventListener('complete', () => {
      sounds.onSessionEnd()
      statusMessage.value = null
      status.value = 'complete'
      // #146: defer close by one tick so any buffered preceding SSE events
      // (observer, analytics) are consumed before the EventSource is torn down
      setTimeout(() => { es.close(); eventSource.value = null }, 0)
    })

    es.addEventListener('error', (e) => {
      if (e.data) {
        try {
          const data = JSON.parse(e.data)
          console.error('Session error:', data.message)
        } catch {}
      }
      status.value = 'error'
      es.close()
      eventSource.value = null
    })

    es.onerror = () => {
      // Don't promote to 'complete' — backend may still be running after a network drop
      if (status.value === 'running') {
        status.value = 'disconnected'
      }
      es.close()
      eventSource.value = null
    }
  }

  async function startSession(sessionId, config) {
    await runSession(sessionId, config)
    status.value = 'running'
    await connectToStream(sessionId)
  }

  async function stopCurrentSession(sessionId) {
    try {
      await stopSession(sessionId)
    } catch {}
    eventSource.value?.close()
    eventSource.value = null
    // Use 'stopped' to match the DB status — do not conflate with 'complete'
    status.value = 'stopped'
  }

  async function pauseCurrentSession(sessionId) {
    await pauseSession(sessionId)
    status.value = 'paused'
  }

  async function resumeCurrentSession(sessionId) {
    await resumeSession(sessionId)
    status.value = 'running'
  }

  async function recoverCurrentSession(sessionId, additionalRounds = 5) {
    await recoverSession(sessionId, additionalRounds)  // #197: POST /recover first so backend rebuilds engine
    status.value = 'running'
    await connectToStream(sessionId)
  }

  // #203: Allow continuing stopped/complete sessions — POST /continue then reconnect stream
  async function continueCurrentSession(sessionId, additionalRounds = 5) {
    await continueSession(sessionId, { additional_rounds: additionalRounds })
    status.value = 'running'
    await connectToStream(sessionId)
  }

  async function sendInjectMessage(sessionId, content, asModerator = false) {
    await injectMessage(sessionId, content, asModerator)
  }

  function muteAgent(slug) {
    if (!agentOverrides.value[slug]) agentOverrides.value[slug] = {}
    agentOverrides.value[slug].is_silenced = !agentOverrides.value[slug].is_silenced
  }

  function updateAgentOverride(slug, overrides) {
    agentOverrides.value[slug] = { ...agentOverrides.value[slug], ...overrides }
  }

  async function fetchAnalytics(sessionId) {
    const r = await getAnalytics(sessionId)
    analyticsData.value = r.data
    return r.data
  }

  function resetSession() {
    turns.value = []
    observerData.value = {}
    analyticsRounds.value = []
    syntheses.value = []
    agentOverrides.value = {}
    thinkingByAgent.value = {}
    contentByAgent.value = {}
    streamingMessages.value = {}
    privateThreads.value = []
    statusMessage.value = null
    currentRound.value = null
    status.value = 'idle'
    eventSource.value?.close()
    eventSource.value = null
    analyticsData.value = null
  }

  return {
    sessions, currentSession, turns, observerData, analyticsRounds, syntheses,
    agentOverrides, status, eventSource, analyticsData, statusMessage, currentRound,
    thinkingByAgent, contentByAgent, streamingMessages, privateThreads,
    appendStreamToken, appendThinkingToken, clearStreamingMessage,
    fetchSessions, fetchSession, createNewSession, removeSession,
    startSession, stopCurrentSession, sendInjectMessage,
    pauseCurrentSession, resumeCurrentSession, recoverCurrentSession, continueCurrentSession,
    connectToStream,
    muteAgent, updateAgentOverride, fetchAnalytics, resetSession,
  }
})
