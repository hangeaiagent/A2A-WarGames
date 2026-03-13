<script setup>
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

const { t } = useI18n()

defineProps({
  open: Boolean,
  isAuthenticated: Boolean,
})
const emit = defineEmits(['close', 'sign-out', 'sign-in'])
</script>

<template>
  <Transition name="slide-down">
    <div v-if="open" class="mobile-menu" role="navigation" aria-label="Mobile navigation" @click="emit('close')">
      <RouterLink to="/projects">{{ t('nav.projects') }}</RouterLink>
      <RouterLink to="/sessions">{{ t('nav.sessions') }}</RouterLink>
      <RouterLink to="/settings">{{ t('nav.settings') }}</RouterLink>
      <div class="mobile-menu-divider"></div>
      <template v-if="isAuthenticated">
        <button @click="emit('sign-out')">{{ t('nav.signOut') }}</button>
      </template>
      <template v-else>
        <button @click="emit('sign-in')">{{ t('nav.signIn') }}</button>
      </template>
    </div>
  </Transition>
</template>

<style scoped>
.mobile-menu {
  display: none;
  flex-direction: column;
  padding: 8px 20px 16px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  box-shadow: var(--shadow-md);
}
.mobile-menu a,
.mobile-menu button {
  display: block;
  padding: 12px 0;
  color: var(--text-muted);
  text-decoration: none;
  background: none;
  border: none;
  font-size: 14px;
  cursor: pointer;
  text-align: left;
  transition: color var(--transition-fast);
}
.mobile-menu a:hover,
.mobile-menu button:hover { color: var(--text); }
.mobile-menu a.router-link-active { color: var(--accent); }
.mobile-menu-divider {
  height: 1px;
  background: var(--border);
  margin: 4px 0;
}

/* Slide-down transition */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: opacity 200ms ease, transform 200ms ease;
}
.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
.slide-down-enter-to,
.slide-down-leave-from {
  opacity: 1;
  transform: translateY(0);
}

@media (max-width: 768px) {
  .mobile-menu { display: flex; }
}
</style>
