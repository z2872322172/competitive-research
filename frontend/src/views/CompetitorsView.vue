<script setup lang="ts">
import { computed } from 'vue'
import { Search } from 'lucide-vue-next'
import { useTasksStore } from '@/stores/tasks'

const tasksStore = useTasksStore()

const competitorProfiles = computed(() => tasksStore.competitorProfiles)

const competitorRows = computed(() => {
  return competitorProfiles.value.map(profile => ({
    name: profile.name,
    category: profile.category || '未分类',
    reports: profile.report_count || 0,
    verified: profile.verified_claim_count || 0,
    conflicts: profile.risky_claim_count || 0,
    update: profile.updated_at ? new Date(profile.updated_at).toLocaleDateString() : '未知',
  }))
})
</script>

<template>
  <section class="content-page">
    <header class="page-topbar">
      <div>
        <span class="eyebrow">Competitor library</span>
        <h1>竞品库</h1>
      </div>
      <button class="secondary-button" type="button"><Search :size="17" /> 搜索</button>
    </header>
    <div class="competitor-grid">
      <article v-for="row in competitorRows" :key="row.name" class="competitor-card">
        <div>
          <h2>{{ row.name }}</h2>
          <span>{{ row.category }}</span>
        </div>
        <dl>
          <dt>报告</dt>
          <dd>{{ row.reports }}</dd>
          <dt>已验证 Claim</dt>
          <dd>{{ row.verified }}</dd>
          <dt>冲突</dt>
          <dd>{{ row.conflicts }}</dd>
        </dl>
        <p>{{ row.update }}</p>
      </article>
    </div>
  </section>
</template>

<style scoped>
.competitor-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.competitor-card {
  min-height: 250px;
  padding: 18px;
  border: 1px solid #dfe6e2;
  border-radius: 8px;
  background: #fff;
}

.competitor-card h2 {
  margin: 0;
  color: #26342d;
  font-size: 20px;
}

.competitor-card > div span {
  display: block;
  margin-top: 6px;
  color: #6f7b75;
  font-size: 12px;
}

.competitor-card dl {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 9px;
  margin-top: 22px;
  font-size: 12px;
}

.competitor-card dt {
  color: #77837d;
}

.competitor-card dd {
  margin: 0;
  color: #26342d;
  font-weight: 720;
  overflow-wrap: anywhere;
}

.competitor-card p {
  margin: 20px 0 0;
  padding-top: 14px;
  border-top: 1px solid #e5ebe7;
  color: #526059;
  font-size: 13px;
  line-height: 1.55;
}

@media (max-width: 1180px) {
  .competitor-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 820px) {
  .competitor-grid {
    grid-template-columns: 1fr;
  }
}
</style>
