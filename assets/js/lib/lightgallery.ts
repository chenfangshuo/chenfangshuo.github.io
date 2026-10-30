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
 *
 * 主题升级若改了同路径文件，需人工比对后同步；想恢复主题默认行为时删掉本文件即可。
 */
let lg: { destroy: (removeSubModules?: boolean) => void } | undefined

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
    licenseKey: 'none',
    mobileSettings: { controls: false, showCloseIcon: false, download: true },
  })
}

document.addEventListener('DOMContentLoaded', initLightGallery, false)
