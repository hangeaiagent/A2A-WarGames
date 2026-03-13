<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const props = defineProps({ status: String })

const label = computed(() =>
  props.status
    ? t(`status.${props.status}`, props.status)
    : '—'
)
</script>

<template>
  <span
    :class="['status', props.status ? `status-${props.status}` : 'status-unknown']"
    :title="label"
  >{{ label }}</span>
</template>
