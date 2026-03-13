<script setup>
const props = defineProps({ modelValue: Object })
const emit = defineEmits(['update:modelValue'])

const dims = ['awareness', 'desire', 'knowledge', 'ability', 'reinforcement']

function update(dim, val) {
  emit('update:modelValue', { ...props.modelValue, [dim]: Number(val) })
}
</script>

<template>
  <div>
    <div v-for="dim in dims" :key="dim" class="adkar-row">
      <span class="adkar-label">{{ dim.charAt(0).toUpperCase() + dim.slice(1) }}</span>
      <input
        type="range" min="1" max="5" step="1"
        :value="modelValue[dim] || 3"
        @input="update(dim, $event.target.value)"
        style="flex: 1;"
      />
      <span style="font-size: 11px; color: var(--text-muted); width: 14px; text-align: right;">
        {{ modelValue[dim] || 3 }}
      </span>
    </div>
  </div>
</template>
