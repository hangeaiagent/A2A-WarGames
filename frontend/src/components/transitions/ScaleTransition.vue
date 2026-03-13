<template>
  <Transition name="scale" mode="out-in">
    <slot />
  </Transition>
</template>

<style>
.scale-enter-active {
  transition: all 150ms ease-out;
}
.scale-leave-active {
  transition: all 100ms ease-in;
}
.scale-enter-from {
  opacity: 0;
  transform: scale(0.95);
}
.scale-leave-to {
  opacity: 0;
  transform: scale(0.95);
}
</style>
