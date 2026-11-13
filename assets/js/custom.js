/*!
 * 站点自定义脚本 — https://fars.cc
 * Copyright (c) 2026 Chen Fangshuo
 * SPDX-License-Identifier: MIT · 完整许可文本见仓库根目录 LICENSE
 * （legal comment 形式，压缩后仍会留在 custom.min.<hash>.js 里）
 */

/**
 * 站点自定义脚本 — fars.cc
 * 由 FixIt 自动加载（assets/js/custom.js）
 *
 * 1) 首页随机一言：从 hitokoto 取一句随机句子，带打字机效果写入 .home-subtitle
 * 2) 雪花特效：同目录的 snow.js（Canvas 实现），由 js.Build 内联进同一份产物
 * 3) 正文懒加载图片骨架：加载完成后先加 is-loaded 淡出，淡出结束再加
 *    is-skeleton-done 停掉 shimmer（见同名函数里的注释）
 * 4) 首页 Hero 背景图骨架：用同 URL 的 Image 探针等背景图加载完成，
 *    给 .home-profile 加 is-hero-loaded，让 ::after 骨架淡出
 * 5) 首页卡片鼠标跟随光斑：两层预渲染的径向渐变跟着指针走，外层明显滞后
 * 6) 关于页 Celeste 彩蛋：点击那句「Ta很懒…」触发四幕动画（celeste.js）
 */

import { initSnow } from './snow.js'
import { initCelesteEgg } from './celeste.js'

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

  // 减少动效：直接整句写入，不逐字打字。
  // 打字机每 70ms 改一次 textContent，会连带样式/布局/绘制；一次短句实测 79.75ms
  // 主线程（逐字）vs 49.46ms（整句）。这句只在首页出现一次，但没必要让偏好它的用户看。
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    el.textContent = text
    return
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

/**
 * 3) 正文懒加载图片骨架
 *
 *    骨架是盖在图片上方的一层（custom.scss 第 10 节），加载期间挡住浏览器的
 *    渐进绘制；这里负责在图片 load / error 后分两步收掉它：
 *      is-loaded        只淡出，shimmer 继续跑（CSS 里刻意不在这里停动画）
 *      is-skeleton-done 淡出结束后（550ms）才加，停动画 + visibility: hidden
 *    合成一步会在淡出的半秒里把 shimmer 冻在当前帧，看起来就是"光条卡住"
 *    （2026-11-12 用户反馈）。
 *
 *    ⚠️ 不要改回“隐藏 img、再淡入 img”的写法：慢网下浏览器会先画出图片的
 *       部分内容，JS 还没把 img 压到 0 就会从骨架上面露出来（2026-10-31 实测）。
 *    ⚠️ 缓存命中（img.complete）直接标记 is-loaded，避免刷新时骨架多留一帧。
 *       complete 也包括“已经失败”（naturalWidth === 0）：失败图不会再触发 error，
 *       所以这里表示“无需继续等待”，让浏览器显示失败状态，而不是永久盖着骨架。
 */
const SKELETON_FADE_MS = 550 // 正文骨架 .45s、Hero 骨架 .5s，取更长的再加余量

const initImageSkeletons = () => {
  document.querySelectorAll('.image-skeleton').forEach((box) => {
    const img = box.querySelector('img')
    if (!img) return

    const done = () => {
      box.classList.add('is-loaded')
      setTimeout(() => box.classList.add('is-skeleton-done'), SKELETON_FADE_MS)
    }

    // complete 表示“已经不用等”（成功或失败都算）；失败图不会再触发 error，
    // 所以不能只认 naturalWidth > 0，否则骨架会永久保留。
    if (img.complete) {
      done()
      return
    }

    img.addEventListener('load', done, { once: true })
    img.addEventListener('error', done, { once: true })
  })
}

const initHeroSkeleton = () => {
  const hero = document.querySelector('.home.posts .home-profile')
  if (!hero) return

  // Hero 图是 .home-profile::before 的 background-image，CSS 没法监听背景图 load。
  // 从计算样式里把 URL 抠出来，用一张同 URL 的 Image 做探针（命中缓存时立即完成）。
  const bg = getComputedStyle(hero, '::before').backgroundImage
  const match = bg.match(/url\(["']?([^"')]*hero\.webp[^"')]*)["']?\)/)
  if (!match) return

  // 与正文图骨架同样的两步：先淡出，等 shimmer 跑完这 0.5s 再停（见第 10 节）
  const done = () => {
    hero.classList.add('is-hero-loaded')
    setTimeout(() => hero.classList.add('is-hero-done'), SKELETON_FADE_MS)
  }
  const probe = new Image()
  probe.onload = done
  probe.onerror = done
  probe.src = match[1]

  if (probe.complete && probe.naturalWidth > 0) done()
}

/**
 * 5. 首页卡片鼠标跟随光斑
 *
 *    往每张首页卡片里注入两层预渲染的径向渐变（样式见 custom.scss 第 4.1 节）：
 *    「主光」跟得比较紧，「拖尾」更大更淡、明显滞后。两级之间用不同的每帧
 *    插值比例，形成柔和的跟随延迟。
 *
 *    ⚠️ 每帧只改 transform，不要改 background-position / CSS 变量再让渐变重画 ——
 *       那会把整张卡片（含封面图）每帧重绘一遍，代价完全不一样。
 *    ⚠️ 指针停下后 rAF 会自己收尾退出，不常驻；离开卡片也只是让拖尾走完最后
 *       一小段，然后随 opacity 一起淡出。
 */
const initCardSpotlight = () => {
  const cards = document.querySelectorAll('.home.posts .summary')
  if (!cards.length) return
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
  // 精确指针（鼠标 / 触控板）才启用；纯触摸设备不绑定
  if (!window.matchMedia('(hover: hover) and (pointer: fine)').matches) return

  // ease = 每帧向指针插值的比例，越小拖得越久
  const LAYERS = [
    { className: 'card-glow card-glow--main', ease: 0.18 },
    { className: 'card-glow card-glow--trail', ease: 0.05 },
  ]

  // 每张卡片的"按最后一次指针坐标重算目标"函数；滚动 / 窗口缩放 /
  // 页面高度变化时统一调用
  const retargets = []

  // 运行中把系统动效关掉时立刻收光，不必等下一次 pointermove
  reduceMotion.addEventListener?.('change', (e) => {
    if (!e.matches) return
    for (const card of cards) card.classList.remove('is-spotlight')
  })

  for (const card of cards) {
    // 光斑只在封面图下方的卡片底色里：wrapper 的 top 对齐到封面底边，
    // overflow:hidden 把光裁掉 —— 图片（包括底部 mask 渐隐）一点都不会被染色。
    const mask = document.createElement('span')
    mask.className = 'card-glow-mask'
    mask.setAttribute('aria-hidden', 'true')

    const nodes = LAYERS.map(({ className }) => {
      const node = document.createElement('span')
      node.className = className
      node.setAttribute('aria-hidden', 'true')
      mask.appendChild(node)
      return node
    })
    card.appendChild(mask)

    const media = card.querySelector('.summary-media')

    const syncMask = () => {
      const cardRect = card.getBoundingClientRect()
      const mediaRect = media ? media.getBoundingClientRect() : null
      // card.clientTop = 顶部边框宽度；mask 的 top 相对 padding box
      const top = mediaRect
        ? Math.max(0, mediaRect.bottom - cardRect.top - (card.clientTop || 0))
        : 0
      mask.style.top = `${top.toFixed(2)}px`
    }

    syncMask()

    const points = LAYERS.map(() => ({ x: 0, y: 0 }))
    let targetX = 0
    let targetY = 0
    let clientX = 0
    let clientY = 0
    let fresh = false
    let hovering = false
    let frame = 0
    // 卡片进场是 transform 过渡：这段时间里即使指针不动，也要持续用最新 rect 校正
    let holdUntil = 0

    const step = () => {
      frame = 0
      // 减少动效下不再推进（元素本身由 CSS display:none 隐藏）；
      // 之后偏好恢复时，下一次 pointermove 会重新唤醒
      if (reduceMotion.matches) return

      // 卡片进场还在移动时，指针可能完全静止、没有 pointermove；
      // 这段 hold 里每帧都重取一次 rect，光斑才不会比卡片慢 12px。
      const holding = hovering && performance.now() < holdUntil
      if (holding) fresh = true

      // transform 不改布局，这里的 rect 读取命中布局缓存，不会强制重排
      const rect = mask.getBoundingClientRect()
      if (fresh) {
        targetX = clientX - rect.left
        targetY = clientY - rect.top
        fresh = false
      }

      let moving = false
      for (let i = 0; i < nodes.length; i++) {
        const point = points[i]
        const ease = LAYERS[i].ease
        point.x += (targetX - point.x) * ease
        point.y += (targetY - point.y) * ease
        if (Math.abs(targetX - point.x) > 0.3 || Math.abs(targetY - point.y) > 0.3) {
          moving = true
        }
        nodes[i].style.transform =
          `translate3d(${point.x.toFixed(1)}px, ${point.y.toFixed(1)}px, 0) translate(-50%, -50%)`
      }
      if (moving || holding) frame = requestAnimationFrame(step)
    }

    const wake = () => {
      if (!frame) frame = requestAnimationFrame(step)
    }

    card.addEventListener('pointerenter', (e) => {
      if (e.pointerType !== 'mouse' || reduceMotion.matches) return
      syncMask()
      // 如果正好在进场 transform 期间进入卡片，先续一段 hold（见 step）
      if (card.classList.contains('reveal-target') && getComputedStyle(card).transform !== 'none') {
        holdUntil = performance.now() + 700
      }
      const rect = mask.getBoundingClientRect()
      targetX = e.clientX - rect.left
      targetY = e.clientY - rect.top
      // 进入时直接落在指针处，避免从卡片左上角“飞”过来
      for (const point of points) {
        point.x = targetX
        point.y = targetY
      }
      clientX = e.clientX
      clientY = e.clientY
      fresh = false
      hovering = true
      card.classList.add('is-spotlight')
      wake()
    })

    card.addEventListener('pointermove', (e) => {
      if (e.pointerType !== 'mouse' || reduceMotion.matches) return
      clientX = e.clientX
      clientY = e.clientY
      fresh = true
      hovering = true
      card.classList.add('is-spotlight')
      wake()
    })

    // 只认鼠标的 leave：触屏/笔在卡片上抬起也会发 pointerleave，
    // 不能让它把仍悬停在卡片上的鼠标光斑关掉。
    card.addEventListener('pointerleave', (e) => {
      if (e.pointerType && e.pointerType !== 'mouse') return
      hovering = false
      card.classList.remove('is-spotlight')
      // 不立刻停帧：让拖尾层把最后一段路走完，再自然退出
      wake()
    })

    // 卡片进场（.reveal-target → .is-revealed）是 transform 过渡；
    // 指针已经停在卡片上时，靠这个事件把 step 的 hold 续上。
    card.addEventListener('transitionrun', (event) => {
      if (event.target !== card || event.propertyName !== 'transform' || !hovering) return
      holdUntil = performance.now() + 700
      fresh = true
      wake()
    })

    // 滚动 / 窗口缩放 / 页面高度变化时卡片会在指针下面移动，但不触发 pointermove。
    // 用最后一次指针坐标重算目标，光斑才能继续"钉"在指针上。
    retargets.push(() => {
      // 卡片宽度变化会改变封面高度 → mask 的顶边也要跟着重算
      syncMask()
      if (!hovering || reduceMotion.matches) return
      fresh = true
      wake()
    })
  }

  const retargetAll = () => {
    for (const retarget of retargets) retarget()
  }
  window.addEventListener('scroll', retargetAll, { passive: true })
  window.addEventListener('resize', retargetAll, { passive: true })
  // Hero 一言换行、字体/图片加载都可能改变页面高度，但不一定触发 resize。
  // 只观察文档整体尺寸，不逐张卡片观察。
  if (typeof ResizeObserver !== 'undefined') {
    new ResizeObserver(retargetAll).observe(document.documentElement)
  }
}

/**
 * 6. 卡片 / 图片滚动进场
 *
 *    只给"首屏之外"的目标加 .reveal-target，首屏元素从第一帧就是完全可见的。
 *    进入视口后加 .is-revealed 播一次，然后 unobserve，滚回去不会反复闪。
 *    文章节标题不做进场（2026-11-11 用户反馈）；标题的锚点微交互仍在。
 *    reduced-motion / 没有 IntersectionObserver 时直接不启动。
 */
const initScrollReveal = () => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  if (!('IntersectionObserver' in window)) return

  const targets = document.querySelectorAll([
    '.home.posts .summary',
    '.page.single .content img',
  ].join(','))
  if (!targets.length) return

  const viewport = window.innerHeight
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue
      entry.target.classList.add('is-revealed')
      observer.unobserve(entry.target)
    }
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.01 })

  for (const target of targets) {
    // 已经在首屏里的元素不加任何隐藏态，避免首帧半透明。
    // 这里用真实视口边界，别用 0.92 之类的提前量 —— 否则贴着底边、明明可见的
    // 图片/卡片也会被藏起来，还要等再滚一点才出现。
    if (target.getBoundingClientRect().top < viewport) continue
    target.classList.add('reveal-target')
    observer.observe(target)
  }
}

/**
 * 7. 明暗切换圆形扩散
 *
 *    拦截 .theme-switch 的点击，只在本站保留 **明 / 暗两档**（不要 auto），
 *    调用 window.fixit.setThemeMode() 并放进 document.startViewTransition 里，
 *    再用 clip-path 把新主题从按钮位置圆形铺开。
 *
 *    ⚠️ 必须保留主题自己的 localStorage / theme-color 更新 —— 所以不复制逻辑，
 *       只调用它的公开 API；也不改 .theme-switch 的 DOM。
 *    ⚠️ 不支持 View Transition 或 reduced-motion 时仍然拦截（否则主题会切回 auto），
 *       只是不走圆形动画，直接 setThemeMode。
 */
const initThemeReveal = () => {
  if (!window.fixit?.setThemeMode) return

  // 老访客 localStorage 里可能还是主题的 auto；本站只留明/暗，
  // 进来就落到当前实际那一档（颜色不变，只把模式和图标收成两档）。
  if (window.fixit.themeMode === 'auto') {
    window.fixit.setThemeMode(window.fixit.isDark ? 'dark' : 'light')
  }

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
  // 一次只允许一个主题 VT。连点时第二次既可能读到旧模式，又可能把第一次的
  // finished 回调招来清掉第二次正在用的 vt-theme，干脆在动画期间忽略点击。
  let themeTransitionInFlight = false

  for (const button of document.querySelectorAll('.theme-switch')) {
    // capture：抢在 ThemeModule 的 click 监听之前
    button.addEventListener('click', (event) => {
      // 先阻止主题自己的 auto 循环：修饰键点击也不能让它跑回 auto
      event.preventDefault()
      event.stopImmediatePropagation()

      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      if (themeTransitionInFlight) return

      // 只留明/暗两档：auto 时按当前实际明暗决定往哪边切
      const next = window.fixit.isDark ? 'light' : 'dark'
      if (typeof document.startViewTransition !== 'function' || reduceMotion.matches) {
        window.fixit.setThemeMode(next)
        return
      }

      const rect = button.getBoundingClientRect()
      // 键盘触发（detail === 0）没有有意义的坐标，从按钮中心扩散
      const x = event.detail === 0 ? rect.left + rect.width / 2 : event.clientX
      const y = event.detail === 0 ? rect.top + rect.height / 2 : event.clientY
      const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y))
      const root = document.documentElement

      themeTransitionInFlight = true
      root.classList.add('vt-theme')

      let transition
      try {
        transition = document.startViewTransition(() => window.fixit.setThemeMode(next))
      } catch {
        themeTransitionInFlight = false
        root.classList.remove('vt-theme')
        window.fixit.setThemeMode(next)
        return
      }

      // transition.finished 可能在 clip-path 动画之前就 resolve（默认根动画被
      // html.vt-theme 关掉了）；守卫和 vt-theme 必须等真正的圆形动画结束再放。
      const clipFinished = transition.ready
        .then(() => root.animate(
          {
            clipPath: [
              `circle(0px at ${x}px ${y}px)`,
              `circle(${radius}px at ${x}px ${y}px)`,
            ],
          },
          {
            duration: 520,
            easing: 'cubic-bezier(.22, 1, .36, 1)',
            pseudoElement: '::view-transition-new(root)',
          },
        ).finished)
        .catch(() => {})

      Promise.all([transition.finished.catch(() => {}), clipFinished]).finally(() => {
        themeTransitionInFlight = false
        root.classList.remove('vt-theme')
      })
    }, true)
  }
}

/**
 * 8. 代码块展开箭头：出视口暂停
 *
 *    FixIt 给折叠代码块底部加了一个 1.5s infinite 的上下浮动箭头，即使整块在视口外
 *    也一直在跑（实测 23.9ms Main/s + 8.9ms Style/s）。这里只切一个 class，
 *    动画本身、样式和观感都不动；减少动效时由 CSS 直接停掉，所以那种情况下不启动。
 *
 *    rootMargin 取正值：离开视口 200px 之后才暂停，避免贴着边缘时反复切换。
 */
const initCodeArrowAnimation = () => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  if (!('IntersectionObserver' in window)) return

  const arrows = document.querySelectorAll(
    '.single .highlight.code-block .code-expand-btn .fa-angles-down',
  )
  if (!arrows.length) return

  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      entry.target.classList.toggle('code-arrow-paused', !entry.isIntersecting)
    }
  }, { rootMargin: '200px 0px' })

  for (const arrow of arrows) observer.observe(arrow)
}

const init = () => {
  // ⚠️ 顺序有意为之：hitokoto 先启动。两者现在在同一份 bundle 里，而 initHitokoto 是
  //    async（在第一个 await 处就返回，后续不受影响），所以万一下面的 initSnow() 同步抛错，
  //    一言也不会被连累。别把两行对调。
  //    骨架是同步的，放在最前面，让未加载的图片尽早进入占位状态。
  initImageSkeletons()
  initHeroSkeleton()
  initCardSpotlight()
  initScrollReveal()
  initCodeArrowAnimation()
  initThemeReveal()
  initHitokoto()
  initSnow()
  // 雪花先建场：关于页点击时 fixitSnow 已就绪，gust 才能把雪吹起来。
  initCelesteEgg()
  console.log('custom.js loaded', fixit && fixit.version)
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init)
} else {
  init()
}
