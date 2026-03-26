<script setup>
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const router = useRouter()

const props = defineProps({
  isAuthenticated: Boolean,
  displayName: String,
  avatarUrl: String,
  email: String,
})
const emit = defineEmits(['sign-out', 'sign-in'])

const userDropdownOpen = defineModel('dropdownOpen', { type: Boolean, default: false })

function handleKeydown(e) {
  if (e.key === 'Escape') userDropdownOpen.value = false
}

function goToTokenUsage() {
  userDropdownOpen.value = false
  router.push('/token-usage')
}

function goToGameHistory() {
  userDropdownOpen.value = false
  router.push('/game-history')
}
</script>

<template>
  <div class="user-dropdown-wrapper">
    <template v-if="isAuthenticated">
      <button
        class="user-dropdown-trigger"
        @click.stop="userDropdownOpen = !userDropdownOpen"
        @keydown="handleKeydown"
        :aria-expanded="userDropdownOpen"
        aria-haspopup="menu"
        aria-label="User menu"
      >
        <img v-if="avatarUrl" :src="avatarUrl" class="user-avatar" alt="" />
        <span v-else class="user-avatar-placeholder">{{ (displayName || '?')[0].toUpperCase() }}</span>
        <span class="user-name">{{ displayName }}</span>
        <svg class="dropdown-caret" :class="{ 'caret-open': userDropdownOpen }" width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
          <path d="M2 3.5L5 6.5L8 3.5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <Transition name="dropdown">
        <div v-if="userDropdownOpen" class="dropdown-menu" role="menu" @click.stop>
          <div class="dropdown-user-info">
            <div class="dropdown-user-name">{{ displayName }}</div>
            <div v-if="email" class="dropdown-user-email">{{ email }}</div>
          </div>
          <div class="dropdown-divider"></div>
          <button role="menuitem" @click="goToTokenUsage">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
            {{ t('userMenu.tokenUsage') }}
          </button>
          <button role="menuitem" @click="goToGameHistory">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            {{ t('userMenu.gameHistory') }}
          </button>
          <div class="dropdown-divider"></div>
          <button
            role="menuitem"
            @click="emit('sign-out'); userDropdownOpen = false"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
            {{ t('nav.signOut') }}
          </button>
        </div>
      </Transition>
      <div v-if="userDropdownOpen" class="dropdown-backdrop" @click="userDropdownOpen = false"></div>
    </template>
    <template v-else>
      <button class="btn-signin" @click="emit('sign-in')">{{ t('nav.signIn') }}</button>
    </template>
  </div>
</template>

<style scoped>
.user-dropdown-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}
.user-dropdown-trigger {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius);
  transition: background var(--transition-fast);
  background: none;
  border: none;
  color: inherit;
  font: inherit;
}
.user-dropdown-trigger:hover { background: var(--surface-hover); }

.user-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  object-fit: cover;
}
.user-avatar-placeholder {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #7c3aed;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.user-name {
  font-size: 13px;
  color: var(--text-muted);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dropdown-caret {
  color: var(--text-muted);
  transition: transform var(--transition-fast);
}
.caret-open {
  transform: rotate(180deg);
}
.dropdown-menu {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  min-width: 180px;
  z-index: 65;
  overflow: hidden;
}
.dropdown-user-info {
  padding: 10px 14px;
}
.dropdown-user-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.dropdown-user-email {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dropdown-divider {
  height: 1px;
  background: var(--border);
}
.dropdown-menu button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 14px;
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
  text-align: left;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.dropdown-menu button:hover {
  background: var(--surface-hover);
  color: var(--text);
}
.dropdown-backdrop {
  position: fixed;
  inset: 0;
  z-index: 55;
}
.btn-signin {
  padding: 5px 14px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: opacity var(--transition-fast);
}
.btn-signin:hover { opacity: 0.9; }

.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.97);
}
.dropdown-enter-to,
.dropdown-leave-from {
  opacity: 1;
  transform: translateY(0) scale(1);
}

@media (max-width: 768px) {
  .user-name,
  .dropdown-caret { display: none; }
}
</style>
