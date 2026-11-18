<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const preview = ref(null)
const blocked = ref(null)
const msg = ref('')
const err = ref('')

const sameCodes = computed(() => {
  if (!preview.value || !blocked.value) return true
  const a = (preview.value.orphan_issues || []).map((o) => o.coupon_code).join(',')
  const b = (blocked.value.orphan_issues || []).map((o) => o.coupon_code).join(',')
  return a === b
})

async function load() {
  err.value = ''
  try { preview.value = await api.preview() } catch (e) { err.value = e.message }
}
async function seal() {
  msg.value = ''; err.value = ''; blocked.value = null
  try {
    const r = await api.seal({})
    msg.value = `已钉扎批次 #${r.batch_id} · ${r.fact_count} 笔 · 合计 ${r.total_amount} · 未核 ${r.orphan_issue_count} 笔`
    await load()
  } catch (e) {
    err.value = e.message
    // 409 闸口返回的未核清单与预览同源；落表渲染，而非前端临时过滤
    if (e.status === 409 && e.detail && Array.isArray(e.detail.orphan_issues)) {
      blocked.value = e.detail
      await load()
    }
  }
}
onMounted(load)
</script>
<template>
  <div class="panel" v-if="preview">
    <div class="grid">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ preview.business_day }}</div></div>
      <div class="stat"><div class="k">待钉笔数</div><div class="v ticket">{{ preview.open_count }}</div></div>
      <div class="stat"><div class="k">待钉合计</div><div class="v ticket">{{ preview.open_total }}</div></div>
      <div class="stat">
        <div class="k">未核发放（闸）</div>
        <div class="v" :class="{ ticket: preview.orphan_issue_count > 0 }">{{ preview.orphan_issue_count }}</div>
      </div>
      <div class="stat"><div class="k">已钉扎</div><div class="v">{{ preview.already_sealed ? '是' : '否' }}</div></div>
    </div>
    <p class="msg err" v-if="preview.orphan_issue_count > 0">
      存在 {{ preview.orphan_issue_count }} 笔仅发放未核销/作废的券码，钉扎将被拒绝；请先在「券事件」对其写 redeem 或 void。
    </p>
    <div class="row">
      <button
        type="button"
        @click="seal"
        :disabled="preview.already_sealed || preview.open_count === 0"
      >钉扎本日核销</button>
      <button type="button" class="ghost" @click="load">刷新预览</button>
    </div>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
    <p class="msg ok" v-if="blocked && sameCodes">
      闸口 409 返回 {{ blocked.orphan_issue_count }} 笔，与钉预览同源清单一致（同口径核对通过）。
    </p>
    <p class="msg err" v-if="blocked && !sameCodes">口径不一致：闸口清单与预览清单不符，禁止继续。</p>
  </div>

  <div class="panel" v-if="preview && preview.orphan_issues.length">
    <h3>未核发放清单（钉预览同源 · 后端扫描）</h3>
    <table>
      <thead><tr><th>事件ID</th><th>券码</th><th>活动</th><th>业务日</th><th>发放时刻</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="o in preview.orphan_issues" :key="o.event_id">
          <td>{{ o.event_id }}</td>
          <td>{{ o.coupon_code }}</td>
          <td>{{ o.campaign_code }}</td>
          <td>{{ o.business_day }}</td>
          <td>{{ o.occurred_at }}</td>
          <td><span class="tag bad">未核发放</span></td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="panel" v-if="blocked && blocked.orphan_issues && blocked.orphan_issues.length">
    <h3>钉扎闸拒绝清单（POST /redeem/seal → 409 原样返回）</h3>
    <table>
      <thead><tr><th>事件ID</th><th>券码</th><th>活动</th><th>业务日</th><th>发放时刻</th></tr></thead>
      <tbody>
        <tr v-for="o in blocked.orphan_issues" :key="o.event_id">
          <td>{{ o.event_id }}</td>
          <td>{{ o.coupon_code }}</td>
          <td>{{ o.campaign_code }}</td>
          <td>{{ o.business_day }}</td>
          <td>{{ o.occurred_at }}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="panel">
    <h3>待钉 open 核销事实</h3>
    <table>
      <thead><tr><th>事实ID</th><th>券码</th><th>活动</th><th>金额</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="f in (preview?.facts || [])" :key="f.id">
          <td>{{ f.id }}</td>
          <td>{{ f.coupon_code }}</td>
          <td>{{ f.campaign_code }}</td>
          <td>{{ f.amount }}</td>
          <td><span class="tag warn">{{ f.status }}</span></td>
        </tr>
        <tr v-if="preview && preview.facts.length === 0">
          <td colspan="5" class="muted">无 open 核销事实</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
