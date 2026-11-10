/**
 * 站点覆盖 themes/FixIt/assets/js/pages/link.ts（assets 同路径遮蔽主题资源）。
 *
 * 与主题版本的差异：**确认跳转前校验协议，只放行 http / https**。
 *
 * 主题原版把 `?target=` 的值直接赋给 `window.location.href`，没有做任何 scheme 检查：
 *     /link/?target=javascript:alert(document.domain)
 * 点「确认」就会在本站 origin 执行脚本（DOM XSS）。虽然本站是纯静态、没有登录态，
 * 但这个页面本身就是让用户「确认后跳转」的，攻击者可以拿它做钓鱼页。
 *
 * 校验失败时保持按钮禁用，并提示 Invalid target URL —— 与主题原本「缺 target」时的表现一致。
 *
 * 主题升级若改了同路径文件，需人工比对后同步；想恢复主题默认行为时删掉本文件即可。
 */
import { createCopyText } from '../utils'

const copyText = createCopyText()

/** 只接受绝对 http(s) 地址；解析失败或其它协议一律返回 null。 */
function safeTarget(raw: string): string | null {
  try {
    const url = new URL(raw)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

function initLinkGuard(): void {
  const params = new URLSearchParams(window.location.search)
  const raw = params.get('target')
  const $target = document.querySelector<HTMLElement>('.target')!
  const $copy = document.querySelector<HTMLButtonElement>('.copy-icon-btn')!
  const $confirm = document.querySelector<HTMLButtonElement>('.confirm-btn')!

  const target = raw ? safeTarget(raw) : null

  if (!target) {
    $target.textContent = 'Invalid target URL'
    return
  }

  $target.textContent = target
  $copy.disabled = false
  $confirm.disabled = false

  $copy.addEventListener('click', () => {
    copyText(target).then(() => {
      $copy.toggleAttribute('data-copied', true)
      window.setTimeout(() => {
        $copy.toggleAttribute('data-copied', false)
      }, 2000)
    }, () => {
      console.error('Clipboard write failed!', 'Your browser does not support clipboard API!')
    })
  })

  $confirm.addEventListener('click', () => {
    window.location.href = target
  })
}

document.addEventListener('DOMContentLoaded', initLinkGuard, false)
