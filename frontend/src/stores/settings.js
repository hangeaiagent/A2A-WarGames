import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getSettingsProfiles, createSettingsProfile, updateSettingsProfile, activateProfile,
  getProviderPresets,
} from '../api/client'

export const useSettingsStore = defineStore('settings', () => {
  const profiles = ref([])
  const activeProfile = ref(null)
  const providers = ref([])
  const selectedProvider = ref('')

  async function fetchProfiles() {
    const r = await getSettingsProfiles()
    profiles.value = r.data
    activeProfile.value = r.data.find(p => p.is_active) || r.data[0] || null
    return r.data
  }

  async function saveProfile(data) {
    if (data.id) return updateSettingsProfile(data.profile_name, data)
    return createSettingsProfile(data)
  }

  async function setActiveProfile(name) {
    await activateProfile(name)
    await fetchProfiles()
  }

  async function fetchProviders() {
    try {
      const r = await getProviderPresets()
      providers.value = r.data || []
    } catch {
      providers.value = []
    }
  }

  function getProviderById(id) {
    return providers.value.find(p => p.id === id) || null
  }

  return {
    profiles, activeProfile, providers, selectedProvider,
    fetchProfiles, saveProfile, setActiveProfile, fetchProviders, getProviderById,
  }
})
