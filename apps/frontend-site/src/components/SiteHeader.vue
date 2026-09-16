<script setup lang="ts">
import { t, ui, locale, languages, setLocale, theme, toggleTheme } from '../content/i18n'
</script>
<template>
<header class="header">
<div class="container header-inner">
<a href="/" class="brandmark" aria-label="MFS Fleet">
<span class="glyph">
<svg fill="currentColor" aria-hidden="true" viewBox="0 19 78 31" style="width: 70px; height: auto;">
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
<span class="brand-text"> Fleet <span class="sub">· {{ t('brand.country') }}</span>
</span>
</a>
<div class="header-actions">
<div class="lang-switcher" role="group" :aria-label="t('nav-bar.language')">
<button v-for="language in languages" :key="language" type="button" class="lang-btn" :class="{ active: locale === language }" :aria-pressed="locale === language" @click="setLocale(language)">{{ language.toUpperCase() }}</button>
</div>
<button type="button" class="theme-btn" :aria-label="ui(theme === 'dark' ? 'lightTheme' : 'darkTheme')" :aria-pressed="theme === 'dark'" @click="toggleTheme">
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
<path v-if="theme === 'light'" d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
<template v-else><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" /></template>
</svg>
</button>
<a href="/form" class="btn btn-primary btn-sm">{{ t('buttons.connect-button') }}</a>
</div>
</div>
</header>
</template>
