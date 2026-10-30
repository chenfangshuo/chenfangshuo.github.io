/**
 * 站点覆盖 themes/FixIt/assets/js/lib/lightgallery.ts（assets 同路径遮蔽主题资源）。
 *
 * 与主题版本的差异：
 * 1) 不加载 lgThumbnail：主题把 data-thumbnail 指向原图，缩略图插件初始化时
 *    会给每张图建 <img src=原图>，整篇文章的大图在进页面时就被全部拉一遍
 *    （double-pulse 那篇正文图合计 ≈1.99MB），正文的 loading="lazy" 被彻底废掉。
 * 2) 手机端也显示下载按钮：核心默认 mobileSettings.download = false。
 *    mobileSettings 是整对象替换，三项必须写全，否则 controls/showCloseIcon
 *    会退回桌面默认值。
 * 3) 滚轮缩放：lightGallery 2.x 的 zoom 插件本身不监听 wheel，滚轮会穿透去滚
 *    背后的页面（遮罩挡住看不见，只看到右侧滚动条在动）。这里在灯箱打开时自己
 *    接管 wheel，阻止默认滚动并调用主题自带的缩放按钮。
 *
 * 主题升级若改了同路径文件，需人工比对后同步；想恢复主题默认行为时删掉本文件即可。
 */
let lg: { destroy: (removeSubModules?: boolean) => void } | undefined

/** 一次滚轮事件的累计阈值：鼠标一格 ±100 立即触发，触控板小 delta 先累计 */
const WHEEL_STEP_THRESHOLD = 30

let wheelBound = false
let wheelAccum = 0
let wheelResetTimer: ReturnType<typeof setTimeout> | undefined

function onWheel(event: WheelEvent) {
  // 灯箱没开：完全不干预，页面照常滚动
  if (!document.documentElement.classList.contains('lg-on') || !event.deltaY)
    return
  // Ctrl/⌘ + 滚轮是浏览器缩放，不抢
  if (event.ctrlKey || event.metaKey)
    return

  // 必须阻止默认行为：否则滚轮会继续滚背景页面。document 上的 wheel
  // 监听在 Chrome 里默认是 passive 的，所以下面绑定时要显式 passive: false。
  event.preventDefault()
  event.stopPropagation()

  // 触控板一次滑动会发很多小 delta：累计到阈值再缩放，避免一下放大好几倍
  wheelAccum += event.deltaY
  clearTimeout(wheelResetTimer)
  wheelResetTimer = setTimeout(() => { wheelAccum = 0 }, 250)
  if (Math.abs(wheelAccum) < WHEEL_STEP_THRESHOLD)
    return

  // 直接点主题渲染出来的缩放按钮，复用插件自己的 beginZoom/zoomImage 逻辑
  // （包括 imageReset 等边界处理），不复制内部实现。
  const button = document.querySelector<HTMLButtonElement>(
    wheelAccum < 0 ? '.lg-zoom-in' : '.lg-zoom-out',
  )
  button?.click()
  wheelAccum = 0
}

function initLightGallery() {
  if (!window.config.lightgallery || !window.lightGallery)
    return

  lg?.destroy(true)
  const contentEl = document.getElementById('content')
  if (!contentEl)
    return

  lg = window.lightGallery(contentEl, {
    plugins: [window.lgZoom],
    selector: '.lightgallery',
    speed: 400,
    hideBarsDelay: 2000,
    allowMediaOverlap: true,
    actualSize: false,
    showZoomInOutIcons: true,
    // 缩放步长从默认的 1（一次翻倍）改成 0.3，滚轮/按钮都是一次 30%
    scale: 0.3,
    licenseKey: 'none',
    mobileSettings: { controls: false, showCloseIcon: false, download: true },
  })

  if (!wheelBound) {
    document.addEventListener('wheel', onWheel, { capture: true, passive: false })
    wheelBound = true
  }
}

document.addEventListener('DOMContentLoaded', initLightGallery, false)
