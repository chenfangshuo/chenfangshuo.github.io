/**
 * 站点自定义脚本 — forsure.live
 * 由 FixIt 自动加载（assets/js/custom.js）
 *
 * 1) 首页随机一言：从 hitokoto 取一句随机句子，带打字机效果写入 .home-subtitle
 * 2) 雪花特效：同目录的 snow.js（Canvas 实现），由 js.Build 内联进同一份产物
 */

import { initSnow } from './snow.js'

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
 * 2. 雪花特效见 ./snow.js（原 blog/source/js/snow.js，DHTML Snowstorm 1.44，
 *    已整份换成 Canvas 实现）。放在 assets/ 而不是 static/ 是有意的：
 *    static/ 不走 Hugo 资源管线、产物不带 hash，改一次要等 Cloudflare 4 小时过期
 *    或手动 purge；import 进来就随 custom.min.<hash>.js 一起指纹化，改完立刻生效。
 */

const init = () => {
  // ⚠️ 顺序有意为之：hitokoto 先启动。两者现在在同一份 bundle 里，而 initHitokoto 是
  //    async（在第一个 await 处就返回，后续不受影响），所以万一下面的 initSnow() 同步抛错，
  //    一言也不会被连累。别把两行对调。
  initHitokoto()
  initSnow()
  console.log('custom.js loaded', fixit && fixit.version)
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}
