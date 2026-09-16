<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import SiteHeader from './components/SiteHeader.vue'
import SiteFooter from './components/SiteFooter.vue'
import LandingPage from './components/LandingPage.vue'
import ApplicationForm from './components/ApplicationForm.vue'
import SuccessPage from './components/SuccessPage.vue'

const route = ref('')
const outcome = ref<'created' | 'existing'>()
function currentRoute() {
  const path = location.pathname
  route.value = path === '/form' || path === '/apply' ? 'form' : path.startsWith('/success') && outcome.value ? 'success' : 'home'
  if (path.startsWith('/success') && !outcome.value) { history.replaceState(null, '', '/form'); route.value = 'form' }
}
async function scroll() {
  await nextTick()
  if (location.hash) {
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)))
    target?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  } else window.scrollTo({ top: 0, behavior: 'instant' })
}
function navigate(path: string) { history.pushState(null, '', path); currentRoute(); void scroll() }
function popstate() { currentRoute(); void scroll() }
function click(event: MouseEvent) {
  if (event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return
  const target = (event.target as Element).closest<HTMLAnchorElement>('a[href]')
  if (!target || target.target || target.hasAttribute('download')) return
  const url = new URL(target.href)
  if (url.origin !== location.origin) return
  event.preventDefault()
  navigate(url.pathname + url.search + url.hash)
}
function submitted(value: 'created' | 'existing') { outcome.value = value; navigate('/success/bolt') }
onMounted(() => {
  // Старые ссылки OpenDesign остаются рабочими.
  if (location.hash.startsWith('#/')) history.replaceState(null, '', location.hash.slice(1))
  currentRoute()
  void scroll()
  window.addEventListener('popstate', popstate)
})
onUnmounted(() => window.removeEventListener('popstate', popstate))
</script>
<template>
  <div class="app-shell" @click="click">
    <SiteHeader />
    <main class="app-main">
      <ApplicationForm v-if="route === 'form'" @submitted="submitted" />
      <SuccessPage v-else-if="route === 'success' && outcome" :outcome="outcome" />
      <LandingPage v-else />
    </main>
    <SiteFooter />
  </div>
</template>
