<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Bot, ChevronDown, Sparkles, Upload } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useTasksStore } from '@/stores/tasks'

const router = useRouter()
const authStore = useAuthStore()
const tasksStore = useTasksStore()

const prompt = ref('')

const canStart = computed(() => prompt.value.trim().length >= 8)
const isLoading = computed(() => tasksStore.isLoading)

const examples = [
  {
    title: '分析 Notion / 飞书 / Obsidian',
    desc: '对比知识管理工具的产品定位与定价策略',
    prompt: '分析 Notion / 飞书 / Obsidian 在知识管理市场的竞争格局',
    icon: Sparkles,
  },
  {
    title: '研究 AI 编程助手市场',
    desc: '了解 Cursor / Copilot / Trae 的竞争态势',
    prompt: '研究 AI 编程助手市场，对比 Cursor、GitHub Copilot、Trae 的产品特性与定价',
    icon: Bot,
  },
  {
    title: '分析企业协作工具',
    desc: '对比 Slack / Teams / 飞书的差异化定位',
    prompt: '分析企业协作工具市场，对比 Slack、Microsoft Teams、飞书的产品策略',
    icon: Sparkles,
  },
]

function chooseExample(examplePrompt: string) {
  prompt.value = examplePrompt
}

function createDraftResearchTask() {
  if (!canStart.value || isLoading.value) return
  if (!authStore.authUser) {
    authStore.requireLogin('请先登录后再发起研究任务。')
    return
  }
  tasksStore.draftPrompt = prompt.value.trim()
  router.push('/confirm')
}
</script>

<template>
  <section class="workspace-page home-page">
    <header class="home-topline">
      <button class="feature-pill" type="button">
        <Sparkles :size="15" />
        新功能上线
      </button>
    </header>

    <section class="home-hero" aria-label="竞品分析入口">
      <div class="home-heading">
        <h1>下午好，林研究员</h1>
        <p>你的 AI 竞品分析 Agent —— 48 位专家协作，无证据不立论</p>
      </div>

      <div class="chat-composer">
        <textarea
          v-model="prompt"
          aria-label="研究需求"
          placeholder="想分析哪个市场、公司或竞争策略？例如：分析 Notion / 飞书 / Obsidian 的产品与定价竞争格局"
        />
        <div class="chat-toolbar">
          <span>48 位专家 · 真实网页 · 无证据不立论</span>
          <div>
            <button class="model-button" type="button">
              <Bot :size="15" />
              切换模型
              <ChevronDown :size="14" />
            </button>
            <button class="icon-button subtle" type="button" title="上传资料"><Upload :size="17" /></button>
            <button class="send-button" type="button" :disabled="!canStart || isLoading" title="创建研究计划" @click="createDraftResearchTask">
              <ArrowRight :size="19" />
            </button>
          </div>
        </div>
      </div>

      <div class="prompt-label">试试这些示例</div>
      <div class="home-example-grid">
        <button v-for="example in examples" :key="example.title" class="home-example-card" type="button" @click="chooseExample(example.prompt)">
          <span class="example-icon"><component :is="example.icon" :size="20" /></span>
          <strong>{{ example.title }}</strong>
          <small>{{ example.desc }}</small>
        </button>
      </div>
    </section>
  </section>
</template>

<style scoped>
.workspace-page {
  min-height: 100vh;
  padding: 26px clamp(22px, 3.8vw, 48px) 48px;
}

.home-page {
  position: relative;
  overflow: hidden;
  min-height: 100vh;
  padding: 20px clamp(20px, 4vw, 54px) 46px;
  background:
    linear-gradient(105deg, rgba(255, 255, 255, 0.96) 0%, rgba(246, 250, 247, 0.96) 52%, rgba(250, 238, 202, 0.66) 100%),
    #f7faf8;
}

.home-topline {
  display: flex;
  justify-content: flex-start;
  max-width: 980px;
  margin: 0 auto;
}

.feature-pill,
.model-button,
.send-button {
  border: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.feature-pill {
  min-height: 34px;
  padding: 0 13px;
  gap: 7px;
  border: 1px solid #dfe7e2;
  border-radius: 999px;
  color: #4f6157;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 8px 20px rgba(55, 84, 70, 0.06);
  font-size: 12px;
}

.home-hero {
  width: min(100%, 920px);
  margin: 6px auto 0;
  display: grid;
  justify-items: center;
}

.home-heading {
  margin-top: 8px;
  text-align: center;
}

.home-heading h1 {
  margin: 0;
  color: #24302a;
  font-family: Georgia, "Times New Roman", "Microsoft YaHei", serif;
  font-size: clamp(36px, 5vw, 54px);
  font-weight: 520;
  line-height: 1.15;
  letter-spacing: 0;
}

.home-heading p {
  margin: 16px 0 0;
  color: #5f6d66;
  font-size: 16px;
  line-height: 1.6;
}

.chat-composer {
  width: min(100%, 760px);
  min-height: 158px;
  margin-top: 30px;
  padding: 16px;
  border: 2px solid #7fa08f;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 16px 42px rgba(47, 86, 66, 0.14);
}

.chat-composer textarea {
  width: 100%;
  min-height: 86px;
  padding: 0;
  border: 0;
  outline: 0;
  resize: none;
  color: #26342d;
  background: transparent;
  font-size: 15px;
  line-height: 1.7;
}

.chat-composer textarea::placeholder {
  color: #9aa6a0;
}

.chat-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
}

.chat-toolbar > span {
  color: #9aa49e;
  font-size: 11px;
}

.chat-toolbar > div {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.model-button {
  min-height: 34px;
  padding: 0 12px;
  gap: 6px;
  border-radius: 999px;
  color: #446154;
  background: #e8f1ec;
  font-size: 12px;
}

.icon-button.subtle {
  width: 34px;
  min-height: 34px;
  color: #6a7a72;
  background: transparent;
}

.send-button {
  width: 38px;
  height: 38px;
  border-radius: 999px;
  color: #fff;
  background: #9eb0a7;
}

.send-button:hover:not(:disabled) {
  background: #6f9181;
}

.prompt-label {
  margin-top: 30px;
  color: #8b9691;
  font-size: 13px;
}

.home-example-grid {
  width: min(100%, 760px);
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-top: 16px;
}

.home-example-card {
  min-height: 134px;
  padding: 16px;
  border: 1px solid #e4e9e6;
  border-radius: 12px;
  color: #2d3a33;
  background: rgba(255, 255, 255, 0.72);
  text-align: left;
  box-shadow: 0 10px 26px rgba(54, 70, 61, 0.05);
}

.home-example-card:hover {
  border-color: #cbd8d1;
  background: rgba(255, 255, 255, 0.92);
  transform: translateY(-1px);
}

.home-example-card .example-icon {
  width: 34px;
  height: 34px;
  color: #5e826f;
  background: #e6f0ea;
}

.example-icon {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border-radius: 8px;
  color: #335f79;
  background: #e8f0f5;
}

.home-example-card strong,
.home-example-card small {
  display: block;
}

.home-example-card strong {
  margin-top: 16px;
  font-size: 13px;
  line-height: 1.35;
}

.home-example-card small {
  margin-top: 7px;
  color: #737f79;
  font-size: 11px;
  line-height: 1.55;
}

@media (max-width: 1180px) {
  .home-example-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 820px) {
  .home-page {
    padding: 18px 18px 36px;
  }

  .home-heading h1 {
    font-size: 34px;
  }

  .home-example-grid {
    grid-template-columns: 1fr;
  }

  .chat-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
