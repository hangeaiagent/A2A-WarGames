<template>
  <div class="landing-page">
    <!-- Hero Section -->
    <section class="hero">
      <div class="container">
        <div class="hero-content">
          <div class="hero-badge">
            <span class="badge-icon">🤖</span>
            <span>{{ t('landing.badge') }}</span>
          </div>
          <h1 class="hero-title">
            {{ t('landing.heroTitle1') }}
            <span class="gradient-text">{{ t('landing.heroTitle2') }}</span>
          </h1>
          <p class="hero-subtitle">{{ t('landing.heroSubtitle') }}</p>
          <div class="hero-cta">
            <button class="btn btn-primary" @click="goToProjects">
              <span>{{ t('landing.launchSimulation') }}</span>
              <span class="btn-icon">→</span>
            </button>
            <button class="btn btn-accent" @click="tryDemo">
              <span>{{ t('landing.tryDemo') }}</span>
            </button>
            <a href="https://github.com/ArtemisAI/A2A-WarGames" target="_blank" class="btn btn-secondary">
              <svg class="github-icon" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
              </svg>
              <span>{{ t('landing.viewOnGitHub') }}</span>
            </a>
          </div>
        </div>
        <div class="hero-visual">
          <div class="floating-card card-1">
            <div class="card-icon">💬</div>
            <div class="card-text">{{ t('landing.autonomousAgents') }}</div>
          </div>
          <div class="floating-card card-2">
            <div class="card-icon">🎯</div>
            <div class="card-text">{{ t('landing.strategicConstraints') }}</div>
          </div>
          <div class="floating-card card-3">
            <div class="card-icon">🧠</div>
            <div class="card-text">{{ t('landing.cognitiveBiases') }}</div>
          </div>
          <div class="floating-card card-4">
            <div class="card-icon">⚖️</div>
            <div class="card-text">{{ t('landing.consensusAnalysis') }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- A2A Protocol Section -->
    <section class="protocol-section">
      <div class="container">
        <div class="section-header">
          <h2 class="section-title">{{ t('landing.a2aProtocol') }}</h2>
          <p class="section-subtitle">{{ t('landing.a2aProtocolDesc') }}</p>
        </div>
        <div class="protocol-content">
          <div class="protocol-diagram">
            <div class="diagram-node moderator">
              <div class="node-icon">👔</div>
              <div class="node-label">{{ t('landing.moderatorAgent') }}</div>
              <div class="node-desc">{{ t('landing.moderatorAgentDesc') }}</div>
            </div>
            <div class="diagram-arrow">↓</div>
            <div class="diagram-node selection">
              <div class="node-icon">🎲</div>
              <div class="node-label">{{ t('landing.speakerSelection') }}</div>
              <div class="node-desc">{{ t('landing.speakerSelectionDesc') }}</div>
            </div>
            <div class="diagram-arrow">↓</div>
            <div class="diagram-node agents">
              <div class="node-icon">👥</div>
              <div class="node-label">{{ t('landing.stakeholderAgents') }}</div>
              <div class="node-desc">{{ t('landing.stakeholderAgentsDesc') }}</div>
            </div>
            <div class="diagram-arrow">↓</div>
            <div class="diagram-node observer">
              <div class="node-icon">📊</div>
              <div class="node-label">{{ t('landing.observer') }}</div>
              <div class="node-desc">{{ t('landing.observerDesc') }}</div>
            </div>
            <div class="diagram-arrow">↓</div>
            <div class="diagram-node analytics">
              <div class="node-icon">📈</div>
              <div class="node-label">{{ t('landing.analytics') }}</div>
              <div class="node-desc">{{ t('landing.analyticsDesc') }}</div>
            </div>
          </div>
          <div class="protocol-features">
            <div class="feature-card">
              <div class="feature-icon">🎭</div>
              <h3>{{ t('landing.richPersonas') }}</h3>
              <p>{{ t('landing.richPersonasDesc') }}</p>
            </div>
            <div class="feature-card">
              <div class="feature-icon">🔄</div>
              <h3>{{ t('landing.structuredRounds') }}</h3>
              <p>{{ t('landing.structuredRoundsDesc') }}</p>
            </div>
            <div class="feature-card">
              <div class="feature-icon">📡</div>
              <h3>{{ t('landing.realtimeStreaming') }}</h3>
              <p>{{ t('landing.realtimeStreamingDesc') }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Features Section -->
    <section class="features-section">
      <div class="container">
        <div class="section-header">
          <h2 class="section-title">{{ t('landing.keyCapabilities') }}</h2>
          <p class="section-subtitle">{{ t('landing.keyCapabilitiesDesc') }}</p>
        </div>
        <div class="features-grid">
          <div class="feature-item">
            <div class="feature-item-icon">🎯</div>
            <h3>{{ t('landing.multiAgentOrchestration') }}</h3>
            <p>{{ t('landing.multiAgentOrchestrationDesc') }}</p>
          </div>
          <div class="feature-item">
            <div class="feature-item-icon">🧬</div>
            <h3>{{ t('landing.adkarModeling') }}</h3>
            <p>{{ t('landing.adkarModelingDesc') }}</p>
          </div>
          <div class="feature-item">
            <div class="feature-item-icon">💭</div>
            <h3>{{ t('landing.whisperChannels') }}</h3>
            <p>{{ t('landing.whisperChannelsDesc') }}</p>
          </div>
          <div class="feature-item">
            <div class="feature-item-icon">🧠</div>
            <h3>{{ t('landing.agentMemory') }}</h3>
            <p>{{ t('landing.agentMemoryDesc') }}</p>
          </div>
          <div class="feature-item">
            <div class="feature-item-icon">📊</div>
            <h3>{{ t('landing.liveAnalytics') }}</h3>
            <p>{{ t('landing.liveAnalyticsDesc') }}</p>
          </div>
          <div class="feature-item">
            <div class="feature-item-icon">🎨</div>
            <h3>{{ t('landing.dagVisualization') }}</h3>
            <p>{{ t('landing.dagVisualizationDesc') }}</p>
          </div>
          <div class="feature-item">
            <div class="feature-item-icon">🔐</div>
            <h3>{{ t('landing.multiTenantSecurity') }}</h3>
            <p>{{ t('landing.multiTenantSecurityDesc') }}</p>
          </div>
          <div class="feature-item">
            <div class="feature-item-icon">🌐</div>
            <h3>{{ t('landing.i18nSupport') }}</h3>
            <p>{{ t('landing.i18nSupportDesc') }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- Tech Stack Section -->
    <section class="tech-section">
      <div class="container">
        <div class="section-header">
          <h2 class="section-title">{{ t('landing.modernTechStack') }}</h2>
          <p class="section-subtitle">{{ t('landing.modernTechStackDesc') }}</p>
        </div>
        <div class="tech-grid">
          <div class="tech-category">
            <h3 class="tech-category-title">{{ t('landing.frontend') }}</h3>
            <div class="tech-items">
              <div class="tech-item">
                <span class="tech-icon">⚡</span>
                <div>
                  <div class="tech-name">Vue 3</div>
                  <div class="tech-desc">{{ t('landing.vue3Desc') }}</div>
                </div>
              </div>
              <div class="tech-item">
                <span class="tech-icon">🎨</span>
                <div>
                  <div class="tech-name">Tailwind CSS v4</div>
                  <div class="tech-desc">{{ t('landing.tailwindDesc') }}</div>
                </div>
              </div>
              <div class="tech-item">
                <span class="tech-icon">🏪</span>
                <div>
                  <div class="tech-name">Pinia</div>
                  <div class="tech-desc">{{ t('landing.piniaDesc') }}</div>
                </div>
              </div>
              <div class="tech-item">
                <span class="tech-icon">📊</span>
                <div>
                  <div class="tech-name">Chart.js + D3.js</div>
                  <div class="tech-desc">{{ t('landing.chartDesc') }}</div>
                </div>
              </div>
            </div>
          </div>
          <div class="tech-category">
            <h3 class="tech-category-title">{{ t('landing.backend') }}</h3>
            <div class="tech-items">
              <div class="tech-item">
                <span class="tech-icon">⚙️</span>
                <div>
                  <div class="tech-name">FastAPI</div>
                  <div class="tech-desc">{{ t('landing.fastapiDesc') }}</div>
                </div>
              </div>
              <div class="tech-item">
                <span class="tech-icon">🗄️</span>
                <div>
                  <div class="tech-name">PostgreSQL + Supabase</div>
                  <div class="tech-desc">{{ t('landing.postgresDesc') }}</div>
                </div>
              </div>
              <div class="tech-item">
                <span class="tech-icon">🔍</span>
                <div>
                  <div class="tech-name">pgvector</div>
                  <div class="tech-desc">{{ t('landing.pgvectorDesc') }}</div>
                </div>
              </div>
              <div class="tech-item">
                <span class="tech-icon">🤖</span>
                <div>
                  <div class="tech-name">OpenAI-compatible</div>
                  <div class="tech-desc">{{ t('landing.openaiCompatDesc') }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div class="llm-compat">
          <h3 class="llm-compat-title">{{ t('landing.llmCompatibility') }}</h3>
          <div class="llm-providers">
            <span class="llm-badge">OpenAI</span>
            <span class="llm-badge">Anthropic</span>
            <span class="llm-badge">Ollama</span>
            <span class="llm-badge">Groq</span>
            <span class="llm-badge">Together AI</span>
            <span class="llm-badge">LM Studio</span>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA Section -->
    <section class="cta-section">
      <div class="container">
        <div class="cta-content">
          <h2 class="cta-title">{{ t('landing.readyToExplore') }}</h2>
          <p class="cta-subtitle">{{ t('landing.readyToExploreDesc') }}</p>
          <div class="cta-buttons">
            <button class="btn btn-primary btn-lg" @click="goToProjects">
              <span>{{ t('landing.launchDemo') }}</span>
              <span class="btn-icon">→</span>
            </button>
            <a href="https://github.com/ArtemisAI/A2A-WarGames" target="_blank" class="btn btn-outline btn-lg">
              <span>{{ t('landing.readTheDocs') }}</span>
            </a>
          </div>
        </div>
      </div>
    </section>

    <!-- Footer -->
    <footer class="footer">
      <div class="container">
        <div class="footer-content">
          <div class="footer-info">
            <div class="footer-logo">{{ t('app.brandName') }}</div>
            <p class="footer-desc">{{ t('landing.footerDesc') }}</p>
          </div>
          <div class="footer-links">
            <a href="https://github.com/ArtemisAI/A2A-WarGames" target="_blank">GitHub</a>
            <a href="https://github.com/ArtemisAI/A2A-WarGames/issues" target="_blank">Issues</a>
            <a href="https://github.com/ArtemisAI" target="_blank">ArtemisAI</a>
          </div>
        </div>
        <div class="footer-bottom">
          <p>{{ t('landing.footerCopyright') }}</p>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import api from '../api/client'

const { t } = useI18n()
const router = useRouter()

const goToProjects = () => {
  router.push('/projects')
}

const tryDemo = async () => {
  try {
    await api.post('/api/projects/seed-demo')
  } catch { /* demos may already exist */ }
  router.push('/projects?tab=community')
}
</script>

<style scoped>
.landing-page {
  min-height: 100vh;
  background: var(--bg);
  color: var(--text);
}

.container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 var(--space-6);
}

/* Hero Section */
.hero {
  min-height: 90vh;
  display: flex;
  align-items: center;
  position: relative;
  overflow: hidden;
  padding: var(--space-12) 0;
}

.hero::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: radial-gradient(circle at 30% 20%, var(--accent-glow) 0%, transparent 50%),
              radial-gradient(circle at 70% 60%, rgba(124, 92, 191, 0.1) 0%, transparent 50%);
  pointer-events: none;
}

.hero-content {
  flex: 1;
  z-index: 1;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  font-size: 14px;
  margin-bottom: var(--space-6);
}

.badge-icon {
  font-size: 18px;
}

.hero-title {
  font-family: var(--font-display);
  font-size: clamp(2.5rem, 6vw, 4rem);
  font-weight: 700;
  line-height: 1.1;
  margin: 0 0 var(--space-6) 0;
}

.gradient-text {
  background: linear-gradient(135deg, var(--accent) 0%, #c084fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-subtitle {
  font-size: clamp(1rem, 2vw, 1.25rem);
  line-height: 1.6;
  color: var(--text-muted);
  max-width: 600px;
  margin-bottom: var(--space-8);
}

.hero-cta {
  display: flex;
  gap: var(--space-4);
  flex-wrap: wrap;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-6);
  border-radius: var(--radius);
  font-weight: 600;
  text-decoration: none;
  transition: all var(--transition-base);
  cursor: pointer;
  border: none;
  font-size: 16px;
}

.btn-primary {
  background: var(--accent);
  color: white;
}

.btn-primary:hover {
  background: #d63851;
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.btn-secondary {
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
}

.btn-secondary:hover {
  background: var(--surface-hover);
  border-color: var(--border-hover);
  transform: translateY(-2px);
}

.btn-accent {
  background: var(--surface);
  color: var(--accent);
  border: 1px solid var(--accent);
}
.btn-accent:hover {
  background: var(--accent);
  color: white;
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.btn-outline {
  background: transparent;
  color: var(--text);
  border: 1px solid var(--border);
}

.btn-outline:hover {
  background: var(--surface);
  border-color: var(--border-hover);
  transform: translateY(-2px);
}

.btn-lg {
  padding: var(--space-4) var(--space-8);
  font-size: 18px;
}

.btn-icon {
  font-size: 20px;
  transition: transform var(--transition-base);
}

.btn:hover .btn-icon {
  transform: translateX(4px);
}

.github-icon {
  width: 20px;
  height: 20px;
}

.hero-visual {
  flex: 1;
  position: relative;
  height: 400px;
  display: none;
}

@media (min-width: 768px) {
  .hero-visual {
    display: block;
  }
}

.floating-card {
  position: absolute;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4);
  box-shadow: var(--shadow-lg);
  animation: float 3s ease-in-out infinite;
}

.card-1 {
  top: 20%;
  left: 10%;
  animation-delay: 0s;
}

.card-2 {
  top: 15%;
  right: 15%;
  animation-delay: 0.5s;
}

.card-3 {
  bottom: 30%;
  left: 20%;
  animation-delay: 1s;
}

.card-4 {
  bottom: 20%;
  right: 10%;
  animation-delay: 1.5s;
}

@keyframes float {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-20px);
  }
}

.card-icon {
  font-size: 32px;
  margin-bottom: var(--space-2);
}

.card-text {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
}

/* Sections */
.protocol-section,
.features-section,
.tech-section {
  padding: var(--space-12) 0;
  border-top: 1px solid var(--border);
}

.section-header {
  text-align: center;
  margin-bottom: var(--space-10);
}

.section-title {
  font-family: var(--font-display);
  font-size: clamp(2rem, 4vw, 3rem);
  font-weight: 700;
  margin: 0 0 var(--space-4) 0;
}

.section-subtitle {
  font-size: clamp(1rem, 2vw, 1.125rem);
  color: var(--text-muted);
  max-width: 700px;
  margin: 0 auto;
}

/* Protocol Section */
.protocol-content {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-8);
}

@media (min-width: 1024px) {
  .protocol-content {
    grid-template-columns: 1fr 1fr;
  }
}

.protocol-diagram {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.diagram-node {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-4);
  text-align: center;
}

.node-icon {
  font-size: 32px;
  margin-bottom: var(--space-2);
}

.node-label {
  font-weight: 600;
  margin-bottom: var(--space-1);
}

.node-desc {
  font-size: 14px;
  color: var(--text-muted);
}

.diagram-arrow {
  text-align: center;
  font-size: 24px;
  color: var(--text-muted);
}

.protocol-features {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.feature-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-6);
  transition: all var(--transition-base);
}

.feature-card:hover {
  border-color: var(--accent);
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

.feature-icon {
  font-size: 32px;
  margin-bottom: var(--space-3);
}

.feature-card h3 {
  margin: 0 0 var(--space-2) 0;
  font-size: 18px;
  font-weight: 600;
}

.feature-card p {
  margin: 0;
  color: var(--text-muted);
  line-height: 1.6;
}

/* Features Section */
.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--space-6);
}

.feature-item {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: var(--space-6);
  transition: all var(--transition-base);
}

.feature-item:hover {
  border-color: var(--accent);
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
}

.feature-item-icon {
  font-size: 40px;
  margin-bottom: var(--space-3);
}

.feature-item h3 {
  margin: 0 0 var(--space-2) 0;
  font-size: 18px;
  font-weight: 600;
}

.feature-item p {
  margin: 0;
  color: var(--text-muted);
  line-height: 1.6;
  font-size: 14px;
}

/* Tech Section */
.tech-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--space-8);
  margin-bottom: var(--space-10);
}

@media (min-width: 768px) {
  .tech-grid {
    grid-template-columns: 1fr 1fr;
  }
}

.tech-category {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
}

.tech-category-title {
  margin: 0 0 var(--space-4) 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--accent);
}

.tech-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.tech-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.tech-icon {
  font-size: 24px;
}

.tech-name {
  font-weight: 600;
  margin-bottom: 2px;
}

.tech-desc {
  font-size: 14px;
  color: var(--text-muted);
}

.llm-compat {
  text-align: center;
}

.llm-compat-title {
  margin: 0 0 var(--space-4) 0;
  font-size: 20px;
  font-weight: 600;
}

.llm-providers {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  justify-content: center;
}

.llm-badge {
  padding: var(--space-2) var(--space-4);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  font-size: 14px;
  font-weight: 600;
}

/* CTA Section */
.cta-section {
  padding: var(--space-12) 0;
  background: var(--surface);
  border-top: 1px solid var(--border);
}

.cta-content {
  text-align: center;
}

.cta-title {
  font-family: var(--font-display);
  font-size: clamp(2rem, 4vw, 3rem);
  font-weight: 700;
  margin: 0 0 var(--space-4) 0;
}

.cta-subtitle {
  font-size: clamp(1rem, 2vw, 1.25rem);
  color: var(--text-muted);
  max-width: 700px;
  margin: 0 auto var(--space-8) auto;
}

.cta-buttons {
  display: flex;
  gap: var(--space-4);
  justify-content: center;
  flex-wrap: wrap;
}

/* Footer */
.footer {
  background: var(--surface-alt);
  border-top: 1px solid var(--border);
  padding: var(--space-8) 0 var(--space-6) 0;
}

.footer-content {
  display: flex;
  justify-content: space-between;
  align-items: start;
  margin-bottom: var(--space-6);
  flex-wrap: wrap;
  gap: var(--space-6);
}

.footer-logo {
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 700;
  margin-bottom: var(--space-2);
}

.footer-desc {
  color: var(--text-muted);
  margin: 0;
  font-size: 14px;
}

.footer-links {
  display: flex;
  gap: var(--space-6);
}

.footer-links a {
  color: var(--text-muted);
  text-decoration: none;
  transition: color var(--transition-base);
}

.footer-links a:hover {
  color: var(--accent);
}

.footer-bottom {
  text-align: center;
  padding-top: var(--space-6);
  border-top: 1px solid var(--border);
}

.footer-bottom p {
  margin: 0;
  color: var(--text-muted);
  font-size: 14px;
}
</style>
