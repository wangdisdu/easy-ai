<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    data: number[];
    labels?: string[];
    height?: number;
    color?: string;
  }>(),
  {
    labels: () => [],
    height: 180,
    color: "#3B82F6",
  }
);

const w = 600;

const max = computed(() => {
  const m = Math.max(...props.data, 0);
  return m > 0 ? m * 1.1 : 1;
});

const points = computed(() =>
  props.data
    .map((v, i) => {
      const x = (i / Math.max(1, props.data.length - 1)) * w;
      const y = props.height - (v / max.value) * (props.height - 20) - 10;
      return `${x},${y}`;
    })
    .join(" ")
);

const areaPoints = computed(() => `0,${props.height} ${points.value} ${w},${props.height}`);

const gridLines = computed(() =>
  [0.25, 0.5, 0.75].map((p) => props.height - p * (props.height - 20) - 10)
);

const gradId = computed(() => `area-grad-${props.color.replace("#", "")}`);
</script>

<template>
  <div class="chart-area" :style="{ height: `${height}px` }">
    <svg width="100%" :height="height" :viewBox="`0 0 ${w} ${height}`" preserveAspectRatio="none">
      <defs>
        <linearGradient :id="gradId" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" :stop-color="color" stop-opacity="0.25" />
          <stop offset="100%" :stop-color="color" stop-opacity="0.02" />
        </linearGradient>
      </defs>
      <line
        v-for="(y, i) in gridLines"
        :key="i"
        x1="0"
        :y1="y"
        :x2="w"
        :y2="y"
        stroke="rgba(148, 163, 184, 0.18)"
        stroke-width="1"
      />
      <polygon :points="areaPoints" :fill="`url(#${gradId})`" />
      <polyline
        :points="points"
        fill="none"
        :stroke="color"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
    <div v-if="labels.length" class="chart-area-labels">
      <span v-for="(l, i) in labels" :key="i">{{ l }}</span>
    </div>
  </div>
</template>

<style scoped>
.chart-area {
  width: 100%;
}
.chart-area-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  padding: 0 4px;
  font-size: 10px;
  color: #94a3b8;
}
</style>
