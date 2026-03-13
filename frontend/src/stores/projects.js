import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getProjects, getProject, createProject, updateProject, seedDemoProject,
  getStakeholders, createStakeholder, updateStakeholder, deleteStakeholder, getEdges,
} from '../api/client'

export const useProjectStore = defineStore('projects', () => {
  const projects = ref([])
  const currentProject = ref(null)
  const stakeholders = ref([])
  const edges = ref([])

  async function fetchProjects() {
    const r = await getProjects()
    projects.value = r.data
    return r.data
  }

  async function fetchProject(id) {
    const r = await getProject(id)
    currentProject.value = r.data
    return r.data
  }

  async function fetchStakeholders(projectId) {
    const r = await getStakeholders(projectId)
    stakeholders.value = r.data
    return r.data
  }

  async function fetchEdges(projectId) {
    const r = await getEdges(projectId)
    edges.value = r.data
    return r.data
  }

  async function saveProject(data) {
    if (data.id) return updateProject(data.id, data)
    return createProject(data)
  }

  async function saveStakeholder(projectId, data) {
    if (data.id) return updateStakeholder(projectId, data.id, data)
    return createStakeholder(projectId, data)
  }

  async function removeStakeholder(projectId, id) {
    return deleteStakeholder(projectId, id)
  }

  function setCurrentProject(project) {
    currentProject.value = project
  }

  async function loadDemo() {
    await seedDemoProject()
    return fetchProjects()
  }

  return {
    projects, currentProject, stakeholders, edges,
    fetchProjects, fetchProject, fetchStakeholders, fetchEdges,
    saveProject, saveStakeholder, removeStakeholder, setCurrentProject, loadDemo,
  }
})
