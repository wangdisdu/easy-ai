<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    data: number[];
    color?: string;
    height?: number;
    width?: number;
  }>(),
  {
    color: "#3B82F6",
    height: 24,
    width: 60,
  }
);

const gradientId = computed(() => `spark-grad-${props.color.replace("#", "")}`);

const points = computed(() => {
  if (!props.data.length) return "";
  const max = Math.max(...props.data);
  const min = Math.min(...props.data);
  const range = max - min || 1;
  return props.data
    .map((v, i) => {
      const x = (i / Math.max(1, props.data.length - 1)) * props.width;
      const y = props.height - ((v - min) / range) * (props.height - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");
});

const areaPoints = computed(
  () => `0,${props.height} ${points.value} ${props.width},${props.height}`
);
</script>

<template>
  <svg :width="width" :height="height" style="overflow: visible">
    <defs>
      <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" :stop-color="color" stop-opacity="0.3" />
        <stop offset="100%" :stop-color="color" stop-opacity="0" />
      </linearGradient>
    </defs>
    <polygon :points="areaPoints" :fill="`url(#${gradientId})`" />
    <polyline
      :points="points"
      fill="none"
      :stroke="color"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
  </svg>
</template>
