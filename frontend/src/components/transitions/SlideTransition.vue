<script setup>
defineProps({
  direction: {
    type: String,
    default: 'left',
    validator: v => ['left', 'right', 'up', 'down'].includes(v),
  },
})
</script>

<template>
  <Transition :name="`slide-${direction}`" mode="out-in">
    <slot />
  </Transition>
</template>

<style>
/* Slide left: enter from right, exit to left */
.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 200ms ease;
}
.slide-left-enter-from { opacity: 0; transform: translateX(20px); }
.slide-left-leave-to   { opacity: 0; transform: translateX(-20px); }

/* Slide right: enter from left, exit to right */
.slide-right-enter-active,
.slide-right-leave-active {
  transition: all 200ms ease;
}
.slide-right-enter-from { opacity: 0; transform: translateX(-20px); }
.slide-right-leave-to   { opacity: 0; transform: translateX(20px); }

/* Slide up: enter from below, exit upward */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 200ms ease;
}
.slide-up-enter-from { opacity: 0; transform: translateY(20px); }
.slide-up-leave-to   { opacity: 0; transform: translateY(-20px); }

/* Slide down: enter from above, exit downward */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 200ms ease;
}
.slide-down-enter-from { opacity: 0; transform: translateY(-20px); }
.slide-down-leave-to   { opacity: 0; transform: translateY(20px); }
</style>
