<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/auth'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submitEmail() {
  if (!email.value.trim() || !password.value) return
  loading.value = true
  error.value = ''
  try {
    await auth.signInWithEmail(email.value.trim(), password.value)
    router.push('/projects')
  } catch (err) {
    error.value = err.message || t('login.signInFailed')
  } finally {
    loading.value = false
  }
}

async function signInGitHub() {
  loading.value = true
  error.value = ''
  try {
    await auth.signInWithGitHub()
  } catch (err) {
    error.value = err.message || t('login.oauthFailed')
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

      <div class="oauth-buttons">
        <button class="btn-oauth btn-github" @click="signInGitHub" :disabled="loading">
          <svg class="oauth-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
          </svg>
          {{ t('login.continueWithGitHub') }}
        </button>
      </div>

      <div class="divider"><span>{{ t('login.orSignInWithEmail') }}</span></div>

      <form class="email-form" @submit.prevent="submitEmail">
        <label class="form-label" for="login-email">{{ t('login.email') }}</label>
        <input
          id="login-email"
          class="form-input"
          type="email"
          placeholder="you@example.com"
          v-model="email"
          :disabled="loading"
          required
        />
        <label class="form-label" for="login-password" style="margin-top: 10px;">{{ t('login.password') }}</label>
        <input
          id="login-password"
          class="form-input"
          type="password"
          placeholder="••••••••"
          v-model="password"
          :disabled="loading"
          required
        />
        <p v-if="error" class="form-error">{{ error }}</p>
        <button
          type="submit"
          class="btn btn-primary submit-btn"
          :disabled="loading || !email.trim() || !password"
        >
          {{ loading ? t('login.signingIn') : t('login.title') }}
        </button>
      </form>
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
  gap: 0;
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

.oauth-buttons {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 20px;
}

.btn-oauth {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-radius: var(--radius);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid var(--border);
  transition: background 0.15s, border-color 0.15s;
  width: 100%;
}

.btn-github {
  background: #161b22;
  color: #e6edf3;
  border-color: #30363d;
}

.btn-github:hover:not(:disabled) {
  background: #1c2128;
  border-color: #58a6ff;
}

.oauth-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

.divider {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-muted);
  font-size: 12px;
  margin: 4px 0 20px;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

.email-form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--surface-alt, var(--surface));
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 14px;
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: var(--accent);
}

.form-error {
  font-size: 12px;
  color: var(--danger, #f85149);
  margin: 4px 0 0;
}

.submit-btn {
  margin-top: 12px;
  width: 100%;
  justify-content: center;
}
</style>
