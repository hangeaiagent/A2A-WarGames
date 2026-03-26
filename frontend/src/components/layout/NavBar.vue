<script setup>
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { useI18n } from 'vue-i18n'
import UserDropdown from './UserDropdown.vue'
import MobileMenu from './MobileMenu.vue'

const { t } = useI18n()

const props = defineProps({
  locale: String,
  theme: String,
  isAuthenticated: Boolean,
  isGuest: Boolean,
  displayName: String,
  avatarUrl: String,
  email: String,
})
const emit = defineEmits(['toggle-theme', 'change-locale', 'sign-out', 'sign-in'])

const mobileMenuOpen = ref(false)
const dropdownOpen = ref(false)
</script>

<template>
  <!-- Top navigation bar -->
  <nav class="topbar" role="navigation" aria-label="Main navigation">
    <div class="topbar-left">
      <RouterLink to="/" class="topbar-brand">
        <span class="brand-icon">⚔</span>
        <span class="brand-name">{{ t('app.brandName') }}</span>
      </RouterLink>
      <ul class="nav-links">
        <li><RouterLink to="/projects">{{ t('nav.projects') }}</RouterLink></li>
        <li><RouterLink to="/sessions">{{ t('nav.sessions') }}</RouterLink></li>
        <li><RouterLink to="/settings">{{ t('nav.settings') }}<span v-if="isGuest" style="margin-left: 4px; font-size: 11px;">🔒</span></RouterLink></li>
      </ul>
    </div>
    <div class="topbar-right">
      <select class="topbar-select" :value="locale" @change="emit('change-locale', $event.target.value)">
        <option value="en">EN</option>
        <option value="fr">FR</option>
        <option value="es">ES</option>
        <option value="zh">中文</option>
      </select>

      <!-- Animated theme toggle -->
      <button
        class="topbar-theme-btn"
        @click="emit('toggle-theme')"
        :title="theme === 'dark' ? t('theme.light') : t('theme.dark')"
        :aria-label="theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'"
      >
        <svg class="theme-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <template v-if="theme === 'dark'">
            <!-- Sun icon -->
            <circle cx="12" cy="12" r="5"/>
            <line x1="12" y1="1" x2="12" y2="3"/>
            <line x1="12" y1="21" x2="12" y2="23"/>
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
            <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
            <line x1="1" y1="12" x2="3" y2="12"/>
            <line x1="21" y1="12" x2="23" y2="12"/>
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
            <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
          </template>
          <template v-else>
            <!-- Moon icon -->
            <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>
          </template>
        </svg>
      </button>

      <UserDropdown
        :is-authenticated="isAuthenticated"
        :display-name="displayName"
        :avatar-url="avatarUrl"
        :email="email"
        v-model:dropdown-open="dropdownOpen"
        @sign-out="emit('sign-out')"
        @sign-in="emit('sign-in')"
      />

      <!-- Hamburger for mobile -->
      <button
        class="hamburger"
        :class="{ 'hamburger--open': mobileMenuOpen }"
        @click="mobileMenuOpen = !mobileMenuOpen"
        aria-label="Toggle navigation menu"
        :aria-expanded="mobileMenuOpen"
      >
        <span></span><span></span><span></span>
      </button>
    </div>
  </nav>

  <!-- Mobile menu -->
  <MobileMenu
    :open="mobileMenuOpen"
    :is-authenticated="isAuthenticated"
    @close="mobileMenuOpen = false"
    @sign-out="emit('sign-out')"
    @sign-in="emit('sign-in')"
  />
</template>

<style scoped>
/* Top navigation bar */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 52px;
  padding: 0 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 50;
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 24px;
}
.topbar-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  text-decoration: none;
  color: inherit;
}
.topbar-brand .brand-icon { font-size: 20px; }
.topbar-brand .brand-name { font-size: 15px; font-weight: 700; color: var(--accent); }

.topbar .nav-links {
  list-style: none;
  display: flex;
  gap: 4px;
}
.topbar .nav-links li a {
  display: block;
  padding: 6px 14px;
  color: var(--text-muted);
  text-decoration: none;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 500;
  transition: color var(--transition-fast), background var(--transition-fast);
  position: relative;
}
.topbar .nav-links li a:hover { color: var(--text); background: var(--surface-hover); }
.topbar .nav-links li a.router-link-active {
  color: var(--accent);
  background: var(--accent-dim);
}
/* Active link underline accent */
.topbar .nav-links li a.router-link-active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 14px;
  right: 14px;
  height: 2px;
  background: var(--accent);
  border-radius: 1px;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.topbar-select {
  padding: 4px 6px;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
}

/* Animated theme toggle button */
.topbar-theme-btn {
  padding: 6px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  transition: color var(--transition-fast), background var(--transition-fast), transform var(--transition-fast);
}
.topbar-theme-btn:hover {
  color: var(--accent);
  background: var(--surface-hover);
  transform: rotate(15deg);
}
.theme-icon {
  transition: transform var(--transition-base);
}

/* Hamburger menu (mobile) */
.hamburger {
  display: none;
  flex-direction: column;
  gap: 4px;
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
}
.hamburger span {
  display: block;
  width: 18px;
  height: 2px;
  background: var(--text-muted);
  border-radius: 1px;
  transition: transform var(--transition-fast), opacity var(--transition-fast);
}
/* Animated hamburger → X */
.hamburger--open span:nth-child(1) { transform: translateY(6px) rotate(45deg); }
.hamburger--open span:nth-child(2) { opacity: 0; }
.hamburger--open span:nth-child(3) { transform: translateY(-6px) rotate(-45deg); }

@media (max-width: 768px) {
  .topbar .nav-links { display: none; }
  .topbar-select { display: none; }
  .hamburger { display: flex; }
}
</style>
