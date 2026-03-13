// Gated behind feature_flags.notification_sounds
import { ref } from 'vue'

const enabled = ref(false)
let audioCtx = null

function getAudioContext() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)()
  }
  return audioCtx
}

function playTone(frequency, duration = 150, volume = 0.15) {
  if (!enabled.value) return
  try {
    const ctx = getAudioContext()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.frequency.value = frequency
    osc.type = 'sine'
    gain.gain.value = volume
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration / 1000)
    osc.start()
    osc.stop(ctx.currentTime + duration / 1000)
  } catch (e) {
    console.warn('Audio notification failed:', e)
  }
}

export function useNotificationSounds() {
  return {
    enabled,
    setEnabled(val) { enabled.value = val },
    onAgentMessage() { playTone(660, 120, 0.1) },        // subtle ping — E5
    onModeratorMessage() { playTone(440, 200, 0.12) },    // slightly lower — A4
    onSessionEnd() {                                        // two-note chime
      playTone(523, 200, 0.15)                              // C5
      setTimeout(() => playTone(659, 300, 0.15), 220)       // E5
    },
    onSessionPaused() { playTone(330, 250, 0.1) },         // low tone — E4
  }
}
