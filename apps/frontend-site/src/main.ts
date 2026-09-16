import { createApp } from 'vue'
import App from './App.vue'
import { initPreferences } from './content/i18n'
import './styles/mfs-fonts.css'
import './styles/mfs-design.css'
import './styles/application.css'

initPreferences()
createApp(App).mount('#app')
