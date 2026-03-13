import { ref } from 'vue'
import { useSettingsStore } from '../stores/settings'
import { useAuthStore } from '../stores/auth'
import { API_BASE } from '../api/client'

export function useSTT() {
  const isRecording = ref(false)
  const transcript = ref('')
  const settings = useSettingsStore()
  const auth = useAuthStore()
  let mediaRecorder = null
  let chunks = []

  function isEnabled() {
    return settings.activeProfile?.stt_enabled ?? false
  }

  async function startRecording() {
    if (!isEnabled()) return
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    chunks = []
    const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm'
      : MediaRecorder.isTypeSupported('audio/mp4') ? 'audio/mp4'
      : ''
    mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {})
    const effectiveMime = mediaRecorder.mimeType || 'audio/webm'
    mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop())
      const blob = new Blob(chunks, { type: effectiveMime })
      const form = new FormData()
      form.append('file', blob, `recording.${effectiveMime.split('/')[1].split(';')[0]}`)
      const lang = settings.activeProfile?.stt_language
      if (lang && lang !== 'auto') form.append('language', lang)

      const apiBase = API_BASE
      const headers = {}
      if (auth.token) headers['Authorization'] = `Bearer ${auth.token}`

      try {
        const res = await fetch(`${apiBase}/api/audio/transcriptions`, { method: 'POST', body: form, headers })
        const data = await res.json()
        transcript.value = data.text || ''
      } catch {
        transcript.value = ''
      }
    }
    mediaRecorder.start()
    isRecording.value = true
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop()
    }
    isRecording.value = false
  }

  function toggleRecording() {
    isRecording.value ? stopRecording() : startRecording()
  }

  return { isRecording, transcript, isEnabled, startRecording, stopRecording, toggleRecording }
}
