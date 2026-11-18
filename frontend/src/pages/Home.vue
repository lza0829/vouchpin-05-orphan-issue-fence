<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const d = ref(null)
const err = ref('')
async function load() {
  err.value = ''
  try { d.value = await api.dashboard() } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="grid" v-if="d">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ d.business_day }}</div></div>
      <div class="stat"><div class="k">今日事件</div><div class="v">{{ d.event_count }}</div></div>
      <div class="stat"><div class="k">核销事实</div><div class="v ticket">{{ d.fact_count }}</div></div>
      <div class="stat"><div class="k">待钉 open</div><div class="v">{{ d.open_fact_count }}</div></div>
      <div class="stat"><div class="k">今日核销额</div><div class="v ticket">{{ d.redeem_total_today }}</div></div>
      <div class="stat">
        <div class="k">未核发放（闸）</div>
        <div class="v" :class="{ ticket: d.orphan_issue_count > 0 }">{{ d.orphan_issue_count }}</div>
      </div>
      <div class="stat"><div class="k">日已钉扎</div><div class="v">{{ d.day_sealed ? '是' : '否' }}</div></div>
    </div>
    <p class="msg err" v-if="d && d.orphan_issue_count > 0">
      有 {{ d.orphan_issue_count }} 笔仅发放未核销/作废，钉扎闸将拒绝本日钉扎。
      <router-link class="inline-link" to="/redeem">打开同源未核清单 →</router-link>
    </p>
    <p class="msg" v-else-if="!err">未核发发放与钉扎闸同源扫描；钉扎后禁止再写入该日核销。</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
</template>
