<template>
  <div class="trace-chart">
    <svg v-if="hasData" :viewBox="`0 0 ${W} ${H}`" preserveAspectRatio="none" class="trace-svg">
      <!-- 阈值线 -->
      <line
        :x1="0"
        :x2="W"
        :y1="thresholdY"
        :y2="thresholdY"
        class="trace-threshold"
      />
      <!-- 触发时刻竖线 -->
      <line
        v-if="triggeredX !== null"
        :x1="triggeredX"
        :x2="triggeredX"
        :y1="0"
        :y2="H"
        class="trace-trigger"
      />
      <!-- 指标折线(逐段,跳过 null) -->
      <polyline
        v-for="(seg, i) in segments"
        :key="i"
        :points="seg"
        class="trace-line"
      />
    </svg>
    <div v-else class="trace-empty">该指标暂不支持溯源曲线(聚合表未覆盖)</div>

    <div v-if="hasData" class="trace-legend">
      <span class="lg"><span class="lg-line lg-metric" />指标值</span>
      <span class="lg"><span class="lg-line lg-thr" />阈值 {{ threshold }}</span>
      <span class="lg"><span class="lg-line lg-trig" />触发时刻</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { AlertTracePoint } from "@/api/types";

const props = defineProps<{
  points: AlertTracePoint[];
  threshold: number;
  triggeredAt: number;
}>();

const W = 600;
const H = 160;
const PAD = 12;

const hasData = computed(() => props.points.some((p) => p.value !== null));

const values = computed(() =>
  props.points.map((p) => p.value).filter((v): v is number => v !== null),
);

const yMax = computed(() => {
  const m = Math.max(...values.value, props.threshold, 0);
  return m > 0 ? m * 1.15 : 1;
});

function xAt(i: number): number {
  const n = props.points.length;
  return n <= 1 ? 0 : (i / (n - 1)) * W;
}

function yAt(v: number): number {
  return H - PAD - (v / yMax.value) * (H - 2 * PAD);
}

const thresholdY = computed(() => yAt(props.threshold));

const triggeredX = computed<number | null>(() => {
  const pts = props.points;
  if (pts.length < 2) return null;
  const first = pts[0].ts;
  const last = pts[pts.length - 1].ts;
  if (last <= first) return null;
  const ratio = (props.triggeredAt - first) / (last - first);
  if (ratio < 0 || ratio > 1) return null;
  return ratio * W;
});

// 把连续的非空点切成多段 polyline,null 处断开
const segments = computed<string[]>(() => {
  const segs: string[] = [];
  let cur: string[] = [];
  props.points.forEach((p, i) => {
    if (p.value === null) {
      if (cur.length) segs.push(cur.join(" "));
      cur = [];
    } else {
      cur.push(`${xAt(i)},${yAt(p.value)}`);
    }
  });
  if (cur.length) segs.push(cur.join(" "));
  return segs.filter((s) => s.includes(" ") || segs.length === 1);
});
</script>

<style scoped>
.trace-chart { width: 100%; }
.trace-svg { width: 100%; height: 160px; display: block; }
.trace-line { fill: none; stroke: var(--color-accent); stroke-width: 2; vector-effect: non-scaling-stroke; }
.trace-threshold { stroke: var(--color-error); stroke-width: 1; stroke-dasharray: 5 4; vector-effect: non-scaling-stroke; }
.trace-trigger { stroke: var(--color-warning); stroke-width: 1; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
.trace-empty { padding: 48px 0; text-align: center; font-size: 13px; color: var(--color-text-quaternary); }

.trace-legend { display: flex; gap: 16px; margin-top: 8px; }
.lg { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--color-text-tertiary); }
.lg-line { width: 16px; height: 0; border-top-width: 2px; border-top-style: solid; }
.lg-metric { border-top-color: var(--color-accent); }
.lg-thr { border-top-color: var(--color-error); border-top-style: dashed; }
.lg-trig { border-top-color: var(--color-warning); border-top-style: dashed; }
</style>
