<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const error = ref('')
const loading = ref(false)

onMounted(async () => {
  const code = route.query.code
  if (code) {
    loading.value = true
    error.value = ''
    try {
      await auth.loginWithAgentPitOAuth(code)
      router.replace('/projects')
    } catch (err) {
      error.value = err.message || t('login.agentPitLoginFailed')
    } finally {
      loading.value = false
    }
  }
})

async function signInAgentPit() {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetch('/api/auth/agentpit-oauth-config')
    if (!resp.ok) throw new Error(t('login.agentPitOAuthNotAvailable'))
    const { authorize_url, client_id, redirect_uri } = await resp.json()
    const url = new URL(authorize_url)
    url.searchParams.set('client_id', client_id)
    url.searchParams.set('redirect_uri', redirect_uri)
    url.searchParams.set('response_type', 'code')
    url.searchParams.set('scope', 'openid profile email')
    window.location.href = url.toString()
  } catch (err) {
    error.value = err.message || t('login.agentPitLoginFailed')
    loading.value = false
  }
}
</script>

<template>
  <div class="login-bg">
    <div class="login-card">
      <div class="login-logo">
        <span class="logo-mark">A2A</span>
        <span class="logo-sub">War Games</span>
      </div>

      <h1 class="login-title">{{ t('login.title') }}</h1>
      <p class="login-subtitle">{{ t('login.subtitle') }}</p>

      <p v-if="error" class="form-error">{{ error }}</p>

      <button class="btn-agentpit" @click="signInAgentPit" :disabled="loading">
        <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
          <polyline points="10 17 15 12 10 7"/>
          <line x1="15" y1="12" x2="3" y2="12"/>
        </svg>
        {{ loading ? t('login.signingIn') : t('login.continueWithAgentPit') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.login-bg {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  padding: 24px;
}

.login-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 48px 40px;
  width: 100%;
  max-width: 400px;
  display: flex;
  flex-direction: column;
}

.login-logo {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 32px;
}

.logo-mark {
  font-size: 22px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 1px;
}

.logo-sub {
  font-size: 14px;
  color: var(--text-muted);
  letter-spacing: 0.5px;
}

.login-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--text);
  margin: 0 0 4px 0;
}

.login-subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0 0 28px 0;
}

.form-error {
  font-size: 12px;
  color: var(--danger, #f85149);
  margin: 0 0 12px 0;
}

.btn-agentpit {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  padding: 12px 16px;
  background: #7c3aed;
  color: #fff;
  border: none;
  border-radius: var(--radius);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.btn-agentpit:hover:not(:disabled) {
  background: #6d28d9;
}

.btn-agentpit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}
</style>
