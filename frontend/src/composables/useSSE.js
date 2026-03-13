import { ref, onUnmounted } from 'vue'

export function useSSE(url) {
  const source = ref(null)
  const isConnected = ref(false)

  function connect(handlers) {
    source.value = new EventSource(url)
    isConnected.value = true

    for (const [event, handler] of Object.entries(handlers)) {
      source.value.addEventListener(event, (e) => handler(JSON.parse(e.data)))
    }

    source.value.onerror = () => {
      isConnected.value = false
      source.value?.close()
    }
  }

  function disconnect() {
    source.value?.close()
    isConnected.value = false
  }

  onUnmounted(disconnect)
  return { connect, disconnect, isConnected }
}
