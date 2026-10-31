/*!
 * 微信分享 —— forsure.live
 * Copyright (c) 2026 Chen Fangshuo
 * SPDX-License-Identifier: MIT · 完整许可文本见仓库根目录 LICENSE
 *
 * 由 layouts/_partials/share-wechat.html 在文章页通过 store/script.html 注册。
 * qrcodejs 在第一次点击时才从 data-qr-lib 指定的指纹地址加载。
 * 保持 ES2017 写法（不用 ?. / ??=），照顾微信 Android X5 内核。
 */

(function () {
  'use strict'

  var btn = document.querySelector('[data-share-wechat]')
  if (!btn) return

  var wrapper = btn.parentNode
  var modal = document.querySelector('.share-wechat-modal')
  if (!modal) return

  var qrBox = modal.querySelector('.share-wechat-qr')
  var tip = modal.querySelector('.share-wechat-tip')
  var closeBtn = modal.querySelector('.share-wechat-close')
  var shareUrl = btn.getAttribute('data-url') || window.location.href
  var libSrc = btn.getAttribute('data-qr-lib')
  var ua = navigator.userAgent
  var isWeChatMobile = /MicroMessenger/i.test(ua) && !/(WindowsWechat|MacWechat)/i.test(ua)
  var libPromise = null
  var rendered = false
  var lastFocus = null

  // 插进主题的分享行（X / 微博旁边）。找不到就留在正文末尾，不要静默消失。
  var row = document.querySelector('.post-info-share > span')
  if (row) {
    row.appendChild(btn)
    if (wrapper && wrapper !== btn) wrapper.hidden = true
  } else if (wrapper && wrapper !== btn) {
    wrapper.hidden = false
  }

  // 弹层移到 body：避免祖先元素的 transform / filter 让 position: fixed 失效。
  document.body.appendChild(modal)

  function loadLib() {
    if (window.QRCode) return Promise.resolve()
    if (libPromise) return libPromise
    libPromise = new Promise(function (resolve, reject) {
      if (!libSrc) {
        reject(new Error('missing qrcode source'))
        return
      }
      var script = document.createElement('script')
      script.src = libSrc
      script.async = true
      script.onload = resolve
      script.onerror = function () {
        reject(new Error('qrcode load failed'))
      }
      document.head.appendChild(script)
    })
    return libPromise
  }

  function show() {
    lastFocus = document.activeElement
    modal.hidden = false
    document.documentElement.classList.add('share-wechat-open')

    if (isWeChatMobile) {
      qrBox.hidden = true
      tip.textContent = '点击右上角 ··· 分享给朋友或朋友圈'
      closeBtn.focus()
      return
    }

    qrBox.hidden = false
    tip.textContent = '微信扫一扫，打开本页'
    if (rendered) {
      closeBtn.focus()
      return
    }

    loadLib().then(function () {
      if (!window.QRCode) throw new Error('QRCode missing')
      qrBox.innerHTML = ''
      // eslint-disable-next-line no-new
      new window.QRCode(qrBox, {
        text: shareUrl,
        width: 220,
        height: 220,
        colorDark: '#000000',
        colorLight: '#ffffff',
        correctLevel: window.QRCode.CorrectLevel.M
      })
      rendered = true
    }).catch(function () {
      qrBox.hidden = true
      tip.textContent = '二维码加载失败，请复制浏览器地址分享'
    }).then(function () {
      closeBtn.focus()
    })
  }

  function hide() {
    modal.hidden = true
    document.documentElement.classList.remove('share-wechat-open')
    if (lastFocus && lastFocus.focus) lastFocus.focus()
  }

  btn.addEventListener('click', function (event) {
    event.preventDefault()
    show()
  })
  closeBtn.addEventListener('click', hide)
  modal.addEventListener('click', function (event) {
    if (event.target === modal) hide()
  })
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && !modal.hidden) hide()
  })
})()
