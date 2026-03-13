import { ref, watch } from 'vue'

const STORAGE_KEY = 'app-theme'

const saved = localStorage.getItem(STORAGE_KEY)
const theme = ref(saved || 'dark')

function applyTheme(value) {
  document.documentElement.setAttribute('data-theme', value)
}

// Apply on init
applyTheme(theme.value)

watch(theme, (val) => {
  localStorage.setItem(STORAGE_KEY, val)
  applyTheme(val)
})

export function useTheme() {
  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  function setTheme(value) {
    theme.value = value
  }

  return {
    theme,
    toggleTheme,
    setTheme,
  }
}
