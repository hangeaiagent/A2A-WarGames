import { ref } from 'vue'
import { useSettingsStore } from '../stores/settings'
import { useAuthStore } from '../stores/auth'
import { API_BASE } from '../api/client'

const _cache = new Map() // cacheKey → blob URL (module-level, shared across calls)

export function useTTS() {
  const isPlaying = ref(false)
  const currentAudio = ref(null)
  const settings = useSettingsStore()
  const auth = useAuthStore()

  function isEnabled() {
    return settings.activeProfile?.tts_enabled ?? false
  }

  async function speak(text, { voice, model, speed } = {}) {
    if (!isEnabled() || !text) return
    if (isPlaying.value) stop()

    const cacheKey = `${text}::${voice}::${model}::${speed}`
    let url = _cache.get(cacheKey)

    if (!url) {
      const form = new FormData()
      form.append('input', text)
      if (voice) form.append('voice', voice)
      if (model) form.append('model', model)
      const effectiveSpeed = speed ?? settings.activeProfile?.tts_speed ?? 1.0
      form.append('speed', String(effectiveSpeed))

      const apiBase = API_BASE
      const headers = {}
      if (auth.token) headers['Authorization'] = `Bearer ${auth.token}`

      const res = await fetch(`${apiBase}/api/audio/speech`, { method: 'POST', body: form, headers })
      if (!res.ok) throw new Error(`TTS failed: ${res.status}`)
      const blob = await res.blob()
      url = URL.createObjectURL(blob)
      _cache.set(cacheKey, url)
    }

    const audio = new Audio(url)
    currentAudio.value = audio
    isPlaying.value = true
    audio.onended = () => { isPlaying.value = false; currentAudio.value = null }
    audio.onerror = () => { isPlaying.value = false; currentAudio.value = null }
    audio.play()
  }

  function stop() {
    if (currentAudio.value) {
      currentAudio.value.pause()
      currentAudio.value.currentTime = 0
      currentAudio.value = null
    }
    isPlaying.value = false
  }

  return { speak, stop, isPlaying, isEnabled }
}
