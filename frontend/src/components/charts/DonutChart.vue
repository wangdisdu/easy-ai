<script setup lang="ts">
import { computed } from "vue";

interface Segment {
  value: number;
  color: string;
}

const props = withDefaults(
  defineProps<{
    segments: Segment[];
    size?: number;
  }>(),
  { size: 120 }
);

const radius = 36;
const circumference = 2 * Math.PI * radius;

const total = computed(() => props.segments.reduce((a, s) => a + s.value, 0));

const computedSegments = computed(() => {
  if (!total.value) return [];
  let cumulative = 0;
  return props.segments.map((seg) => {
    const pct = seg.value / total.value;
    const offset = cumulative * circumference;
    cumulative += pct;
    return {
      color: seg.color,
      dashArray: `${pct * circumference} ${circumference}`,
      dashOffset: -offset,
    };
  });
});
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 100 100">
    <circle cx="50" cy="50" :r="radius" fill="none" stroke="rgba(148,163,184,0.15)" stroke-width="8" />
    <circle
      v-for="(seg, i) in computedSegments"
      :key="i"
      cx="50"
      cy="50"
      :r="radius"
      fill="none"
      :stroke="seg.color"
      stroke-width="8"
      :stroke-dasharray="seg.dashArray"
      :stroke-dashoffset="seg.dashOffset"
      transform="rotate(-90 50 50)"
      stroke-linecap="round"
    />
    <text x="50" y="48" text-anchor="middle" fill="#1e293b" font-size="13" font-weight="600">
      {{ total.toLocaleString() }}
    </text>
    <text x="50" y="62" text-anchor="middle" fill="#94a3b8" font-size="7">总计</text>
  </svg>
</template>
