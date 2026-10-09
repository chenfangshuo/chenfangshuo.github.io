/**
 * 站点自定义脚本 — forsure.live
 * 由 FixIt 自动加载（assets/js/custom.js）
 *
 * 1) 首页随机一言：从 hitokoto 取一句随机句子，带打字机效果写入 .home-subtitle
 * 2) 雪花特效：动态注入旧站的 snow.js（经典脚本，非 ESM，见下方说明）
 */

const { fixit } = window

/**
 * 1. 首页随机一言（hitokoto）+ 打字机
 *    取不到（网络失败/被拦截）就保留 hugo.toml 里写死的 home.profile.subtitle。
 *    对应旧站 _config.fluid.yml 的 index.slogan.api。
 */
const initHitokoto = async () => {
  const el = document.querySelector('.home-subtitle')
  if (!el) return // 只在首页 profile 存在时执行

  const fallback = el.textContent.trim()
  // encode=text 直接返回纯文本，省去 JSON 解析
  const url = 'https://v1.hitokoto.cn/?encode=text'

  let text = fallback
  try {
    const res = await fetch(url, { headers: { Accept: 'text/plain' } })
    if (res.ok) {
      const t = (await res.text()).trim()
      if (t) text = `「${t}」`
    }
  } catch {
    // 静默回退到固定文案
  }

  // 简单打字机，逐字写入
  let i = 0
  el.textContent = ''
  const tick = () => {
    if (i <= text.length) {
      el.textContent = text.slice(0, i++)
      setTimeout(tick, 70)
    }
  }
  tick()
}

/**
 * 2. 雪花特效（原 blog/source/js/snow.js，DHTML Snowstorm）
 *    snowStorm 的 IIFE 依赖非严格模式下的全局 `this`，无法作为 ESM 模块引入，
 *    因此把它放在 static/js/ 下按经典脚本动态注入。
 *    该脚本自身带 excludeMobile，移动端不会启用。
 */
const initSnow = () => {
  const s = document.createElement('script')
  s.src = '/js/snow.js'
  s.async = true
  document.body.appendChild(s)
}

const init = () => {
  initHitokoto()
  initSnow()
  console.log('custom.js loaded', fixit && fixit.version)
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}
