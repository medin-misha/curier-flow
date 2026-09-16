<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { t } from '../content/i18n'
let observer: IntersectionObserver | undefined
onMounted(() => {
  observer = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) { entry.target.classList.add('in'); observer?.unobserve(entry.target) }
  }), { threshold: 0.08 })
  document.querySelectorAll('.reveal').forEach(element => observer?.observe(element))
})
onUnmounted(() => observer?.disconnect())
</script>
<template>
<section class="hero" id="top">
<div class="container hero-inner">
<div class="hero-copy">
<span class="eyebrow">Bolt Food</span>
<h1 class="h-display reveal">{{ t('landing.hero.title-line1') }} <br>
<span class="hl">{{ t('landing.hero.title-line2') }}</span>
</h1>
<p class="lead reveal" style="max-width: 520px;">{{ t('landing.hero.lead') }}</p>
<div class="hero-actions reveal">
<a href="/form" class="btn btn-primary btn-lg">{{ t('landing.cta.apply') }} <svg class="arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M5 12h14M13 5l7 7-7 7">
</path>
</svg>
</a>
<a href="#vehicles" class="btn btn-ghost btn-lg">{{ t('landing.hero.vehicle-link') }}</a>
</div>
<div class="hero-meta reveal">
<div>
<span class="dot">●</span> <b>4×</b>&nbsp;{{ t('landing.hero.meta.payouts') }}</div>
<div>
<span class="dot">●</span> <b>0&nbsp;Kč</b>&nbsp;{{ t('landing.hero.meta.deposit') }}</div>
<div>
<span class="dot">●</span> <b>5&nbsp;{{ t('landing.units.minutes-short') }}</b>&nbsp;{{ t('landing.hero.meta.application') }}</div>
</div>
</div>
<div class="hero-visual reveal">
<div class="hv-grid">
</div>
<div class="hv-blob">
</div>
<div class="hv-mark">
<span class="glyph-lg">
<svg fill="currentColor" aria-hidden="true" viewBox="0 19 78 31" style="width: 115px; height: auto;">
<path d="M36.917 35.4791L37.782 30.2397H49.535L48.67 35.4791H36.917Z">
</path>
<path d="M53.8181 29.4093H53.6709L53.6919 29.2729L53.8181 29.4093Z">
</path>
<path d="M70.7841 39.9395L70.7809 39.9679L70.7554 39.9395H70.7841Z">
</path>
<path d="M70.8437 40.0365H70.7673L70.7795 39.9668L70.8437 40.0365Z">
</path>
<path d="M54.5569 19.3517H38.8032L38.8092 19.3184H34.9646L29.438 24.5426L25.23 50.0002H33.7391L37.9381 24.5911H53.6919L54.5569 19.3517Z">
</path>
<path d="M60.9367 29.2728L61.7476 24.3637H69.2686L70.0976 19.3516H55.332L53.692 29.2728L53.8182 29.4091L63.6189 39.9394H63.5378L62.7028 44.9879H54.7072L55.5392 39.9394H48.2946L46.6306 50H69.1184L70.7794 39.9667L70.7554 39.9394L60.9367 29.2728Z">
</path>
<path d="M70.9145 19.3516L69.2505 29.4091H76.3389L77.9999 19.3516H70.9145Z">
</path>
<path d="M19.319 34.1184L9.15792 19.3184H5.07004L0 50.0002H8.6413L11.4316 33.0487L16.772 40.0881H20.3372L27.2245 33.0002L28.4709 25.4608L19.319 34.1184Z">
</path>
</svg>
</span>
<div class="hero-tag">
<span class="pulse">
</span> {{ t('landing.hero.open') }}</div>
</div>
<div class="hv-stats">
<div class="hv-stat">
<div class="num">2–3 <span class="unit">{{ t('landing.units.days') }}</span>
</div>
<div class="lbl">{{ t('landing.hero.stats.first-order') }}</div>
</div>
<div class="hv-stat">
<div class="num">4<span class="unit">{{ t('landing.units.per-month-times') }}</span>
</div>
<div class="lbl">{{ t('landing.hero.stats.weekly-payouts') }}</div>
</div>
<div class="hv-stat">
<div class="num">0 <span class="unit">Kč</span>
</div>
<div class="lbl">{{ t('landing.hero.stats.deposit') }}</div>
</div>
<div class="hv-stat">
<div class="num">24/7</div>
<div class="lbl">{{ t('landing.hero.stats.support') }}</div>
</div>
</div>
</div>
</div>
</section>
<section class="partners">
<div class="container partners-inner">
<span class="partners-label">{{ t('landing.partners.label') }}</span>
<div class="partners-list">
<span class="partner-logo partner-bolt">
<span class="pdot">
</span>Bolt Food</span>
</div>
</div>
</section>
<section class="section" id="features">
<div class="container">
<div class="section-head reveal">
<span class="eyebrow">{{ t('landing.features.eyebrow') }}</span>
<h2 class="h-section">{{ t('landing.features.title-prefix') }} <span class="accent">{{ t('landing.features.title-accent') }}</span>, {{ t('landing.features.title-suffix') }}</h2>
<p class="lead">{{ t('landing.features.lead') }}</p>
</div>
<div class="features">
<div class="feature reveal">
<div class="feature-icon">
<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
<path d="M3 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2">
</path>
<path d="M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7H7a2 2 0 0 0 0 4h14">
</path>
<circle cx="17" cy="14" r="1.2" fill="currentColor" stroke="none">
</circle>
</svg>
</div>
<span class="pill">{{ t('landing.features.pills.payouts') }}</span>
<h3>{{ t('why-us.item1.title') }}</h3>
<p>{{ t('why-us.item1.line1') }} {{ t('why-us.item1.line2') }} {{ t('why-us.item1.line3') }}</p>
</div>
<div class="feature reveal">
<div class="feature-icon">
<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z">
</path>
<path d="M14 3v6h6">
</path>
<path d="M9 15l2 2 4-4">
</path>
</svg>
</div>
<span class="pill">{{ t('landing.features.pills.paperwork') }}</span>
<h3>{{ t('why-us.item2.title') }}</h3>
<p>{{ t('why-us.item2.line1') }} {{ t('why-us.item2.line2') }}</p>
</div>
<div class="feature reveal">
<div class="feature-icon">
<svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
<path d="M13 2L4.5 14h6.5l-1 8L18.5 10H12z" fill="currentColor" stroke="none" opacity=".18">
</path>
<path d="M13 2L4.5 14h6.5l-1 8L18.5 10H12z">
</path>
</svg>
</div>
<span class="pill">{{ t('landing.features.pills.deposit') }}</span>
<h3>{{ t('why-us.item3.title') }}</h3>
<p>{{ t('why-us.item3.line1') }} {{ t('why-us.item3.line2') }}</p>
</div>
</div>
</div>
</section>
<section class="section section-tight" id="how">
<div class="container">
<div class="section-head reveal">
<span class="eyebrow">{{ t('footer.links.how') }}</span>
<h2 class="h-section">{{ t('landing.steps.title-prefix') }} <span class="accent">{{ t('landing.steps.title-accent') }}</span>
</h2>
<p class="lead">{{ t('landing.steps.lead') }}</p>
</div>
<div class="steps">
<div class="step reveal">
<span class="step-num">01</span>
<span class="step-tag">
<span class="sn">1</span>{{ t('landing.steps.step-label') }}</span>
<h3>{{ t('landing.steps.items.0.title') }}</h3>
<p>{{ t('landing.steps.items.0.text') }}</p>
</div>
<div class="step reveal">
<span class="step-num">02</span>
<span class="step-tag">
<span class="sn">2</span>{{ t('landing.steps.step-label') }}</span>
<h3>{{ t('how-to-start.steps.2') }}</h3>
<p>{{ t('landing.steps.items.1.text') }}</p>
</div>
<div class="step reveal">
<span class="step-num">03</span>
<span class="step-tag">
<span class="sn">3</span>{{ t('landing.steps.step-label') }}</span>
<h3>{{ t('landing.steps.items.2.title') }}</h3>
<p>{{ t('landing.steps.items.2.text') }}</p>
</div>
</div>
</div>
</section>
<section class="section" id="vehicles">
<div class="container">
<div class="section-head reveal">
<span class="eyebrow">{{ t('transport-section.title') }}</span>
<h2 class="h-section">{{ t('landing.vehicles.title-prefix') }} <span class="accent">{{ t('landing.vehicles.title-accent') }}</span>
</h2>
<p class="lead">{{ t('landing.vehicles.lead') }}</p>
</div>
<div class="vehicles">
<article class="vehicle reveal">
<div class="v-image">
<span class="v-no-deposit">{{ t('landing.vehicles.no-deposit') }}</span>
<div class="v-icon">
<svg viewBox="0 0 96 64">
<circle cx="22" cy="48" r="12">
</circle>
<circle cx="74" cy="48" r="12">
</circle>
<circle cx="22" cy="48" r="1.5" fill="currentColor">
</circle>
<circle cx="74" cy="48" r="1.5" fill="currentColor">
</circle>
<path d="M22 48 40 22h22l12 26">
</path>
<path d="M40 22h16">
</path>
<path d="M56 22l6-10h8" stroke-linecap="round">
</path>
<path d="M62 22v-4">
</path>
</svg>
</div>
</div>
<div class="v-body">
<h3>{{ t('transport.bike.title') }}</h3>
<p>{{ t('transport.bike.line1') }} {{ t('transport.bike.line2') }}</p>
<a href="/form" class="v-cta">{{ t('landing.cta.apply') }} <svg class="arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M5 12h14M13 5l7 7-7 7">
</path>
</svg>
</a>
</div>
</article>
<article class="vehicle reveal">
<div class="v-image">
<span class="v-badge">{{ t('landing.vehicles.ebike-price') }} <small>{{ t('landing.units.per-week') }}</small>
</span>
<span class="v-no-deposit">{{ t('landing.vehicles.no-deposit') }}</span>
<div class="v-icon">
<svg viewBox="0 0 96 64">
<circle cx="22" cy="48" r="12">
</circle>
<circle cx="74" cy="48" r="12">
</circle>
<circle cx="22" cy="48" r="1.5" fill="currentColor">
</circle>
<circle cx="74" cy="48" r="1.5" fill="currentColor">
</circle>
<path d="M22 48 40 22h22l12 26">
</path>
<path d="M40 22h16">
</path>
<path d="M56 22l6-10h8">
</path>
<path d="M44 38l6-8-4-2 6-8" fill="currentColor" stroke="currentColor" stroke-width="1.2">
</path>
</svg>
</div>
</div>
<div class="v-body">
<h3>{{ t('transport.ebike.title') }}</h3>
<p>{{ t('transport.ebike.line1') }} {{ t('transport.ebike.line2') }}</p>
<a href="/form" class="v-cta">{{ t('landing.cta.apply') }} <svg class="arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M5 12h14M13 5l7 7-7 7">
</path>
</svg>
</a>
</div>
</article>
<article class="vehicle reveal">
<div class="v-image">
<span class="v-no-deposit">{{ t('landing.vehicles.no-deposit') }}</span>
<div class="v-icon">
<svg viewBox="0 0 96 64">
<circle cx="20" cy="50" r="8">
</circle>
<circle cx="76" cy="50" r="8">
</circle>
<path d="M20 50h56">
</path>
<path d="M76 50 60 18h-8">
</path>
<path d="M60 18v-6h-8v6">
</path>
<path d="M52 12l6 6" stroke-linecap="round">
</path>
<path d="M28 50l8-12" stroke-linecap="round">
</path>
</svg>
</div>
</div>
<div class="v-body">
<h3>{{ t('transport.escooter.title') }}</h3>
<p>{{ t('transport.escooter.line1') }} {{ t('transport.escooter.line2') }}</p>
<a href="/form" class="v-cta">{{ t('landing.cta.apply') }} <svg class="arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M5 12h14M13 5l7 7-7 7">
</path>
</svg>
</a>
</div>
</article>
<article class="vehicle reveal">
<div class="v-image">
<span class="v-badge">{{ t('landing.vehicles.car-price') }} <small>{{ t('landing.units.per-week') }}</small>
</span>
<div class="v-icon">
<svg viewBox="0 0 96 64">
<path d="M10 44h76v-8l-8-4-6-12c-1.6-3-3.6-4-7-4H35c-3.4 0-5.4 1-7 4l-6 12-8 4z">
</path>
<path d="M22 36h52">
</path>
<circle cx="26" cy="50" r="6">
</circle>
<circle cx="70" cy="50" r="6">
</circle>
<path d="M5 44v6h5M86 44v6h5">
</path>
</svg>
</div>
</div>
<div class="v-body">
<h3>{{ t('transport.car.title') }}</h3>
<p>{{ t('transport.car.line1') }} {{ t('transport.car.line2') }}</p>
<a href="/form" class="v-cta">{{ t('landing.cta.apply') }} <svg class="arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M5 12h14M13 5l7 7-7 7">
</path>
</svg>
</a>
</div>
</article>
</div>
<div class="vehicles-note">
<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
<circle cx="12" cy="12" r="10">
</circle>
<path d="M12 16v-4M12 8h.01">
</path>
</svg>
<span>{{ t('transport-footnote') }}</span>
</div>
</div>
</section>
<section class="section" id="cta">
<div class="container">
<div class="cta-banner reveal">
<div class="cta-copy">
<span class="eyebrow">{{ t('landing.cta.eyebrow') }}</span>
<h2 class="h-section">{{ t('landing.cta.title') }}</h2>
<p class="lead">{{ t('landing.cta.lead') }}</p>
<ul class="cta-list">
<li>
<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
<path d="M20 6 9 17l-5-5">
</path>
</svg> {{ t('landing.cta.items.0') }}</li>
<li>
<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
<path d="M20 6 9 17l-5-5">
</path>
</svg> {{ t('landing.hero.stats.support') }}</li>
<li>
<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
<path d="M20 6 9 17l-5-5">
</path>
</svg> {{ t('landing.cta.items.2') }}</li>
</ul>
<div class="cta-actions">
<a href="/form" class="btn btn-primary btn-lg">{{ t('landing.cta.apply') }} <svg class="arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
<path d="M5 12h14M13 5l7 7-7 7">
</path>
</svg>
</a>
<a href="https://t.me/MFS_support" class="btn btn-ghost btn-lg" target="_blank" rel="noopener">{{ t('landing.cta.telegram') }}</a>
</div>
</div>
<div class="cta-side" aria-hidden="true">
<div class="cta-meta">
<div class="cta-metric">
<div class="v">~1 {{ t('landing.units.hour-short') }}</div>
<div class="k">{{ t('landing.cta.metrics.response') }}</div>
</div>
<div class="cta-metric">
<div class="v">5 {{ t('landing.units.minutes-short') }}</div>
<div class="k">{{ t('landing.cta.metrics.form') }}</div>
</div>
<div class="cta-metric">
<div class="v">{{ t('landing.steps.title-accent') }}</div>
<div class="k">{{ t('landing.cta.metrics.first-order') }}</div>
</div>
</div>
</div>
</div>
</div>
</section>
</template>
