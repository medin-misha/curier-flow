<script setup lang="ts">
import { ui } from '../content/i18n'
defineProps<{ outcome: 'created' | 'existing' }>()
</script>
<template>
  <div class="success-page">
    <section class="success-container" aria-labelledby="success-title">
      <div class="check-big"><svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m5 12 4 4L19 6" /></svg></div>
      <h1 id="success-title" class="success-title">{{ ui(outcome === 'created' ? 'successTitle' : 'existingTitle') }}</h1>
      <div class="step-block"><p class="step-heading">{{ ui('successLead') }}</p></div>
      <div class="instructions"><p class="instructions-heading">{{ ui(outcome === 'created' ? 'successDescription' : 'existingDescription') }}</p></div>
      <a href="/" class="cta-button">{{ ui('home') }}</a>
      <a href="https://t.me/MFS_support" target="_blank" rel="noopener" class="support-link">Telegram: @MFS_support</a>
    </section>
  </div>
</template>
