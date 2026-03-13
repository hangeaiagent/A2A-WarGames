<script setup>
import { ref, provide, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useSettingsStore } from './stores/settings'
import { useTheme } from './composables/useTheme'
import NavBar from './components/layout/NavBar.vue'
import LoginModal from './components/auth/LoginModal.vue'
import AiAssistant from './components/AiAssistant.vue'

const { t, locale } = useI18n()
const auth = useAuthStore()
const settingsStore = useSettingsStore()
const showLogin = ref(false)
provide('showLogin', showLogin)
const { theme, toggleTheme } = useTheme()

function changeLocale(lang) {
  locale.value = lang
  localStorage.setItem('app-locale', lang)
}

onMounted(async () => {
  await settingsStore.fetchProfiles()
})
</script>

<template>
  <div class="app-shell">
    <NavBar
      :locale="locale"
      :theme="theme"
      :is-authenticated="auth.isAuthenticated"
      :is-guest="auth.isGuest"
      :display-name="auth.displayName"
      :avatar-url="auth.avatarUrl"
      @toggle-theme="toggleTheme"
      @change-locale="changeLocale"
      @sign-out="auth.signOut()"
      @sign-in="showLogin = true"
    />

    <div class="app-main-wrapper">
      <main class="main-content">
        <RouterView />
      </main>
      <footer class="app-footer">
        {{ t('app.copyright') }} &nbsp;·&nbsp;
        <a href="https://github.com/ArtemisAI" target="_blank" rel="noopener noreferrer" class="footer-link">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" style="vertical-align: -2px;">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
          </svg>
        </a>
        &nbsp;·&nbsp; {{ t('app.version') }}
      </footer>
    </div>
  </div>
  <LoginModal :open="showLogin" @close="showLogin = false" />
  <AiAssistant v-if="settingsStore.activeProfile?.feature_flags?.ai_assistant" />
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}
.app-main-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.main-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.app-footer {
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface);
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.footer-link {
  color: var(--text-muted);
  text-decoration: none;
  transition: color var(--transition-fast);
}
.footer-link:hover {
  color: var(--text);
}
</style>
