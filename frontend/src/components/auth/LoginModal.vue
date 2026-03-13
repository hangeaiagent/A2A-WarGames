<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @click.self="$emit('close')">
      <div
        class="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="login-modal-title"
      >
        <!-- Post-signup email verification confirmation state -->
        <template v-if="emailVerificationSent">
          <h2 id="login-modal-title">{{ t('login.checkYourEmail') }}</h2>
          <p class="modal-sub">{{ t('login.verificationSentTo', { email }) }}</p>
          <p class="verify-hint">{{ t('login.verificationHint') }}</p>
          <button type="button" class="btn-primary" @click="emailVerificationSent = false; isSignUp = false">
            {{ t('login.backToSignIn') }}
          </button>
        </template>

        <template v-else>
          <h2 id="login-modal-title">{{ isSignUp ? t('login.signUpTitle') : t('login.title') }}</h2>
          <p class="modal-sub">{{ isSignUp ? t('login.createAccount') : t('login.signInToAccess') }}</p>

          <form @submit.prevent="handleEmail">
            <div class="field">
              <label for="login-email">{{ t('login.email') }}</label>
              <input id="login-email" v-model="email" type="email" required placeholder="you@example.com" />
            </div>
            <div class="field">
              <label for="login-password">{{ t('login.password') }}</label>
              <input id="login-password" v-model="password" type="password" required placeholder="••••••••" />
            </div>
            <div v-if="isSignUp" class="field">
              <label for="login-confirm-password">{{ t('login.confirmPassword') }}</label>
              <input id="login-confirm-password" v-model="confirmPassword" type="password" required placeholder="••••••••" />
            </div>
            <p v-if="error" class="error">{{ error }}</p>
            <button type="submit" :disabled="loading" class="btn-primary">
              {{ loading ? (isSignUp ? t('login.creatingAccount') : t('login.signingIn')) : (isSignUp ? t('login.signUp') : t('login.title')) }}
            </button>
          </form>

          <div class="divider">{{ t('login.or') }}</div>

          <button @click="handleGoogle" class="btn-google" :disabled="loading">
            <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
              <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
              <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853"/>
              <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
              <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
            </svg>
            {{ t('login.continueWithGoogle') }}
          </button>

          <button @click="handleGitHub" class="btn-github" :disabled="loading">
            <svg width="18" height="18" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="currentColor" aria-hidden="true" focusable="false">
              <path d="M12 0C5.37 0 0 5.373 0 12c0 5.303 3.438 9.8 8.205 11.387.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.929.43.372.823 1.102.823 2.222 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.573C20.565 21.795 24 17.298 24 12c0-6.627-5.373-12-12-12z"/>
            </svg>
            {{ t('login.continueWithGitHub') }}
          </button>

          <p class="toggle-mode">
            <template v-if="isSignUp">
              {{ t('login.haveAccount') }}
              <button type="button" class="link-btn" @click="isSignUp = false">{{ t('login.title') }}</button>
            </template>
            <template v-else>
              {{ t('login.noAccount') }}
              <button type="button" class="link-btn" @click="isSignUp = true">{{ t('login.signUp') }}</button>
            </template>
          </p>
        </template>

        <button class="btn-close" @click="$emit('close')">✕</button>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../../stores/auth'

const { t } = useI18n()

const props = defineProps({ open: Boolean })
const emit = defineEmits(['close'])

function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
}

watch(() => props.open, (val) => {
  if (val) {
    document.addEventListener('keydown', onKeydown)
  } else {
    document.removeEventListener('keydown', onKeydown)
  }
}, { immediate: true })

// Ensure the listener is removed if the component is destroyed while open
// (e.g., parent uses v-if and removes it before open goes false)
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})

const auth = useAuthStore()
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const error = ref('')
const loading = ref(false)
const isSignUp = ref(false)
const emailVerificationSent = ref(false)

async function handleEmail() {
  error.value = ''
  if (isSignUp.value) {
    if (password.value !== confirmPassword.value) {
      error.value = t('login.passwordMismatch')
      return
    }
  }
  loading.value = true
  try {
    if (isSignUp.value) {
      const result = await auth.signUpWithEmail(email.value, password.value)
      // Supabase signUp returns session=null when email confirmation is required.
      // Show a "check your email" state rather than leaving the modal in limbo.
      if (!result.session) {
        emailVerificationSent.value = true
      }
      // If session is non-null, email confirmation is disabled and the user is
      // already logged in — onAuthStateChange will handle closing the modal.
    } else {
      await auth.signInWithEmail(email.value, password.value)
    }
  } catch (e) {
    error.value = e.message || (isSignUp.value ? t('login.signUpFailed') : t('login.signInFailed'))
  } finally {
    loading.value = false
  }
}

async function handleGoogle() {
  loading.value = true
  try {
    await auth.signInWithGoogle()
  } catch (e) {
    // Detect Supabase "provider not enabled" error and show actionable message
    const msg = e.message || ''
    if (msg.toLowerCase().includes('provider is not enabled') || msg.toLowerCase().includes('unsupported provider')) {
      error.value = t('login.oauthProviderNotEnabled')
    } else {
      error.value = msg || t('login.oauthFailed')
    }
    loading.value = false
  }
}

async function handleGitHub() {
  loading.value = true
  try {
    await auth.signInWithGitHub()
  } catch (e) {
    // Detect Supabase "provider not enabled" error and show actionable message
    const msg = e.message || ''
    if (msg.toLowerCase().includes('provider is not enabled') || msg.toLowerCase().includes('unsupported provider')) {
      error.value = t('login.oauthProviderNotEnabled')
    } else {
      error.value = msg || t('login.oauthFailed')
    }
    loading.value = false
  }
}
</script>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.modal-card {
  position: relative; background: var(--surface); border-radius: 12px;
  padding: 2rem; width: 360px; box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}
h2 { margin: 0 0 0.25rem; font-size: 1.4rem; }
.modal-sub { color: var(--text-muted, #aaa); font-size: 0.85rem; margin-bottom: 1.5rem; }
.field { margin-bottom: 1rem; }
.field label { display: block; font-size: 0.8rem; color: var(--text-muted, #aaa); margin-bottom: 0.3rem; }
.field input { width: 100%; padding: 0.5rem 0.75rem; background: var(--surface-alt, #2a2a3a);
  border: 1px solid var(--border, #333); border-radius: 6px; color: inherit; font-size: 0.95rem; box-sizing: border-box; }
.field input:focus { outline: none; border-color: var(--accent, #7c3aed); }
.error { color: var(--danger); font-size: 0.8rem; margin-bottom: 0.5rem; }
.verify-hint { font-size: 0.8rem; color: var(--text-muted, #aaa); margin: 1rem 0 1.5rem; line-height: 1.5; }
.btn-primary { width: 100%; padding: 0.6rem; background: var(--accent, #7c3aed);
  color: white; border: none; border-radius: 6px; font-size: 0.95rem; cursor: pointer; }
.btn-primary:hover:not(:disabled) { opacity: 0.9; }
.btn-google { width: 100%; padding: 0.6rem; background: var(--surface-alt, #2a2a3a);
  color: inherit; border: 1px solid var(--border, #333); border-radius: 6px; font-size: 0.9rem; cursor: pointer; margin-bottom: 0.5rem;
  display: flex; align-items: center; justify-content: center; gap: 8px; }
.btn-google:hover:not(:disabled) { border-color: var(--text-muted, #aaa); }
.btn-github { width: 100%; padding: 0.6rem; background: var(--surface-alt, #2a2a3a);
  color: inherit; border: 1px solid var(--border, #333); border-radius: 6px; font-size: 0.9rem; cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 8px; }
.btn-github:hover:not(:disabled) { border-color: var(--text-muted, #aaa); }
.divider { text-align: center; color: var(--text-muted, #aaa); font-size: 0.75rem; margin: 1rem 0; }
.toggle-mode { text-align: center; font-size: 0.8rem; color: var(--text-muted, #aaa); margin-top: 1rem; }
.link-btn { background: none; border: none; color: var(--accent, #7c3aed); cursor: pointer; font: inherit; font-size: inherit; padding: 0; text-decoration: none; }
.link-btn:hover { text-decoration: underline; }
.btn-close { position: absolute; top: 1rem; right: 1rem; background: none; border: none;
  color: var(--text-muted, #aaa); cursor: pointer; font-size: 1.1rem; }
</style>
