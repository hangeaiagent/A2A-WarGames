<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @click.self="$emit('close')">
      <div
        class="modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="login-modal-title"
      >
        <h2 id="login-modal-title">{{ t('login.title') }}</h2>
        <p class="modal-sub">{{ t('login.signInToAccess') }}</p>

        <p v-if="error" class="error">{{ error }}</p>

        <button @click="handleAgentPit" class="btn-agentpit" :disabled="loading">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
            <polyline points="10 17 15 12 10 7"/>
            <line x1="15" y1="12" x2="3" y2="12"/>
          </svg>
          {{ loading ? t('login.signingIn') : t('login.continueWithAgentPit') }}
        </button>

        <button class="btn-close" @click="$emit('close')">&#x2715;</button>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'

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

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})

const error = ref('')
const loading = ref(false)

async function handleAgentPit() {
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
  } catch (e) {
    error.value = e.message || t('login.agentPitLoginFailed')
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
.error { color: var(--danger, #f85149); font-size: 0.8rem; margin-bottom: 0.5rem; }
.btn-agentpit { width: 100%; padding: 0.7rem; background: #7c3aed;
  color: #fff; border: none; border-radius: 6px; font-size: 0.95rem; cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 8px; }
.btn-agentpit:hover:not(:disabled) { background: #6d28d9; }
.btn-agentpit:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-close { position: absolute; top: 1rem; right: 1rem; background: none; border: none;
  color: var(--text-muted, #aaa); cursor: pointer; font-size: 1.1rem; }
</style>
