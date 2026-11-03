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
  var inerted = []

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

  // 只把弹层以外的 body 子节点设为 inert；弹层自己也是 body 的子节点，
  // 对 body/html 整体 inert 会把它一起禁用。
  function setBackgroundInert(on) {
    if (on) {
      inerted = []
      Array.prototype.forEach.call(document.body.children, function (el) {
        if (el === modal) return
        inerted.push({ el: el, inert: !!el.inert })
        el.inert = true
      })
      return
    }
    inerted.forEach(function (item) {
      item.el.inert = item.inert
    })
    inerted = []
  }

  function focusables() {
    return modal.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )
  }

  function trapTab(event) {
    var list = focusables()
    if (!list.length) return
    var first = list[0]
    var last = list[list.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  function show() {
    if (!modal.hidden) return
    // 顺序必须是：记录原焦点 → 取消 hidden → 再聚焦；隐藏元素拿不到焦点。
    lastFocus = document.activeElement
    modal.hidden = false
    document.documentElement.classList.add('share-wechat-open')
    setBackgroundInert(true)
    closeBtn.focus()

    if (isWeChatMobile) {
      qrBox.hidden = true
      tip.textContent = '点击右上角 ··· 分享给朋友或朋友圈'
      return
    }

    qrBox.hidden = false
    tip.textContent = '微信扫一扫，打开本页'
    if (rendered) return

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
      // 弹层可能已经被关掉；不要在关闭后把焦点抢回来
      if (!modal.hidden) closeBtn.focus()
    })
  }

  function hide() {
    if (modal.hidden) return
    modal.hidden = true
    document.documentElement.classList.remove('share-wechat-open')
    setBackgroundInert(false)
    if (lastFocus && lastFocus.focus) lastFocus.focus()
    lastFocus = null
  }

  btn.addEventListener('click', function (event) {
    event.preventDefault()
    show()
  })
  closeBtn.addEventListener('click', hide)
  modal.addEventListener('click', function (event) {
    if (event.target === modal) hide()
  })
  // 捕获阶段先处理：弹层打开时拦掉主题的 Ctrl/⌘+K，避免搜索弹层抢焦点。
  document.addEventListener('keydown', function (event) {
    if (modal.hidden) return
    if (event.key === 'Escape') {
      event.preventDefault()
      hide()
      return
    }
    if ((event.ctrlKey || event.metaKey) && (event.key === 'k' || event.key === 'K')) {
      event.preventDefault()
      event.stopImmediatePropagation()
      return
    }
    if (event.key === 'Tab') trapTab(event)
  }, true)
})()
