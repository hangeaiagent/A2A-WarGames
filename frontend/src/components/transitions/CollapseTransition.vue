<script setup>
function onEnter(el) {
  el.style.maxHeight = '0'
  el.style.opacity = '0'
  el.style.overflow = 'hidden'
  // Force reflow
  void el.offsetHeight
  el.style.transition = 'max-height 300ms ease, opacity 300ms ease'
  el.style.maxHeight = el.scrollHeight + 'px'
  el.style.opacity = '1'
}

function onAfterEnter(el) {
  el.style.maxHeight = ''
  el.style.overflow = ''
  el.style.transition = ''
}

function onLeave(el) {
  el.style.maxHeight = el.scrollHeight + 'px'
  el.style.overflow = 'hidden'
  // Force reflow
  void el.offsetHeight
  el.style.transition = 'max-height 300ms ease, opacity 300ms ease'
  el.style.maxHeight = '0'
  el.style.opacity = '0'
}

function onAfterLeave(el) {
  el.style.maxHeight = ''
  el.style.overflow = ''
  el.style.opacity = ''
  el.style.transition = ''
}
</script>

<template>
  <Transition
    @enter="onEnter"
    @after-enter="onAfterEnter"
    @leave="onLeave"
    @after-leave="onAfterLeave"
  >
    <slot />
  </Transition>
</template>
