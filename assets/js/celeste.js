/*!
 * 关于页 Celeste 彩蛋 — https://fars.cc
 * Copyright (c) 2026 Chen Fangshuo
 * SPDX-License-Identifier: MIT · 完整许可文本见仓库根目录 LICENSE
 * （legal comment 形式，压缩后仍会留在 custom.min.<hash>.js 里）
 */

/**
 * 关于页 Celeste 彩蛋 — fars.cc
 *
 * 点击「Ta很懒，什么都没有留下？」后：
 *   1) 文字逐字翻转，翻到一半闪 Celeste 红；
 *   2) 雪被左风拉成横线（gust 通过 window.fixitSnow）；
 *   3) Madeline 在页脚线上按四幕循环：
 *        第 1 幕 逆风向右走（1440px 基准 3800ms，按舞台宽度等比缩放，下限 1200ms）
 *        第 2 幕 被强风吹回左（1440px 基准 2800ms，按舞台宽度等比缩放，下限 900ms）
 *        第 3 幕 右下 dash 冲回来 850ms/循环（左画外 -92px 起蹲冲入）
 *        第 4 幕 左下 dash 被吹回去 900ms/循环（右画外 stage-28 起蹲冲入）
 *
 * 只在关于页生效：找不到 .celeste-secret 就直接返回，其他页面零开销。
 * prefers-reduced-motion 下不拆字、不加 role、不绑定点击；运行中切到减少动效
 * 也会完整收尾（见 disable()）。
 *
 * ⚠️ 第 3/4 幕的 DASH3 / DASH4 仅保留运行时所需字段；完整 60fps 源帧及离线校准
 *    元数据归档在 D:\Software\Blog\lab\site\celeste-egg\index9.html。不要手改
 *    times/x/anchors/feetX —— 它们和 sheet 的帧号、像素特效的事件时刻共用同一个
 *    source PTS 时钟，改一个就会错位。
 * ⚠️ 不要给角色加 scaleX(-1)：四套 sprite 的朝向已经烘进图里。
 */

const SHEET_URLS = {
  1: '/images/celeste-act1.png?v=1',
  2: '/images/celeste-act2.png?v=1',
  3: '/images/celeste-act3.png?v=1',
  4: '/images/celeste-act4.png?v=1',
}

const DASH3 = {"cellW":28,"scale":4,"direction":1,"duration":850.0,"dxGame":144.0,"times":[0.0,17.0,33.0,50.0,67.0,83.0,100.0,117.0,133.0,150.0,167.0,183.0,200.0,217.0,233.0,250.0,267.0,283.0,300.0,317.0,333.0,350.0,367.0,383.0,400.0,417.0,433.0,450.0,467.0,483.0,500.0,517.0,533.0,550.0,567.0,583.0,600.0,617.0,633.0,650.0,667.0,683.0,700.0,717.0,733.0,750.0,767.0,783.0,800.0,817.0,833.0,850.0],"x":[0.0,0.0,44.0,48.0,64.0,80.0,100.0,116.0,136.0,152.0,168.0,184.0,200.0,216.0,232.0,248.0,264.0,276.0,292.0,304.0,320.0,332.0,352.0,360.0,372.0,384.0,400.0,412.0,420.0,432.0,456.0,468.0,472.0,480.0,492.0,500.0,508.0,516.0,524.0,532.0,536.0,544.0,548.0,556.0,560.0,564.0,568.0,572.0,572.0,576.0,576.0,576.0],"anchors":[[15.679,6.0,0],[15.679,6.0,0],[14.075,11.0,1],[14.975,13.0,2],[15.775,13.5,3],[15.837,14.5,4],[15.811,14.5,4],[15.871,15.5,5],[15.649,16.0,6],[15.698,17.0,7],[15.606,18.0,8],[15.755,18.5,9],[16.1,19.5,10],[15.796,20.5,11],[15.807,20.5,11],[15.978,21.0,12],[15.978,21.0,12],[16.105,20.5,12],[16.077,19.5,11],[16.005,19.5,11],[16.105,18.5,10],[15.965,16.5,8],[14.105,15.5,7],[15.216,13.5,5],[15.215,12.5,4],[15.124,9.5,1],[13.987,8.0,1],[12.987,7.0,0],[14.987,7.0,0],[14.987,7.0,0],[12.785,6.0,0],[12.785,6.0,0],[14.785,6.0,0],[17.785,6.0,0],[14.785,6.0,0],[14.785,6.0,0],[14.785,6.0,0],[15.833,6.0,0],[15.711,6.0,0],[15.867,6.0,0],[15.674,6.0,0],[15.641,6.0,0],[15.641,6.0,0],[15.727,6.0,0],[15.842,6.0,0],[15.792,6.0,0],[15.679,6.0,0],[15.679,6.0,0],[15.595,6.0,0],[15.595,6.0,0],[15.679,6.0,0],[15.679,6.0,0]],"feetX":[16.182,16.182,12.643,13.5,14.5,14.3,14.3,13.7,13.7,15.5,15.5,15.929,15.5,15.5,15.5,13.0,13.0,17.808,17.808,17.808,17.808,17.808,15.808,17.75,17.75,17.75,10.5,9.5,11.5,11.5,12.667,12.667,14.667,17.667,14.667,14.667,14.667,15.667,16.182,16.182,16.182,16.182,16.182,16.182,16.182,16.182,16.182,16.182,16.182,16.182,16.182,16.182],"fx":{"dash":33.0,"apex":250.0,"landing":450.0}};
const DASH4 = {"cellW":28,"scale":4,"direction":-1,"duration":900.0,"dxGame":-197.0,"times":[0.0,17.0,34.0,50.0,67.0,84.0,100.0,117.0,134.0,150.0,167.0,184.0,200.0,217.0,234.0,250.0,267.0,284.0,300.0,317.0,334.0,350.0,367.0,384.0,400.0,417.0,434.0,450.0,467.0,484.0,500.0,517.0,534.0,550.0,567.0,584.0,600.0,617.0,634.0,650.0,667.0,684.0,700.0,717.0,734.0,750.0,767.0,784.0,800.0,817.0,834.0,850.0,867.0,884.0,900.0],"x":[0.0,0.0,-12.0,-40.0,-64.0,-84.0,-112.0,-136.0,-160.0,-188.0,-212.0,-236.0,-260.0,-284.0,-308.0,-332.0,-352.0,-376.0,-400.0,-420.0,-440.0,-464.0,-484.0,-500.0,-528.0,-548.0,-568.0,-592.0,-608.0,-620.0,-632.0,-648.0,-656.0,-664.0,-672.0,-684.0,-692.0,-700.0,-708.0,-716.0,-724.0,-732.0,-736.0,-744.0,-752.0,-756.0,-764.0,-768.0,-772.0,-776.0,-780.0,-780.0,-780.0,-784.0,-788.0],"anchors":[[15.48,6.0,0],[15.48,6.0,0],[13.656,11.5,1],[14.274,13.0,2],[13.904,13.5,3],[13.115,14.5,4],[13.3,14.5,4],[13.206,15.5,5],[13.211,16.0,6],[13.279,17.0,7],[13.342,18.0,8],[13.137,18.5,9],[12.861,19.5,10],[13.132,20.5,11],[13.092,20.5,11],[13.204,21.0,12],[13.111,21.0,12],[12.965,20.5,12],[13.035,20.5,12],[13.027,19.5,11],[13.054,18.5,10],[12.985,17.5,9],[12.935,16.5,8],[12.915,15.5,7],[13.708,13.5,5],[13.692,11.5,3],[13.773,9.5,1],[14.915,8.0,1],[15.915,7.0,0],[13.915,7.0,0],[13.915,7.0,0],[15.138,6.0,0],[14.138,6.0,0],[13.138,6.0,0],[10.138,6.0,0],[13.138,6.0,0],[13.138,6.0,0],[13.138,6.0,0],[13.139,6.0,0],[12.972,6.0,0],[13.135,6.0,0],[13.255,6.0,0],[12.864,6.0,0],[12.979,6.0,0],[13.718,6.0,0],[13.321,6.0,0],[14.187,6.0,0],[13.996,6.0,0],[13.795,6.0,0],[14.209,6.0,0],[14.209,6.0,0],[14.209,6.0,0],[13.96,6.0,0],[14.446,6.0,0],[15.48,6.0,0]],"feetX":[17.818,17.818,13.7,16.5,15.5,14.7,14.7,15.3,15.3,13.5,13.5,13.071,13.5,13.5,13.5,16.0,16.0,11.192,11.192,11.192,11.192,11.192,11.192,10.25,11.25,11.25,11.25,18.269,19.269,17.269,17.269,15.62,14.62,13.62,10.62,13.62,13.62,13.62,13.333,12.818,12.818,12.818,12.818,12.818,13.818,13.818,14.818,14.818,14.818,15.818,15.818,15.818,15.818,16.818,17.818],"fx":{"dash":34.0,"apex":250.0,"landing":467.0}};

const RED = '#e7624c'
const REF_WALK_DIST = 1440 + 140

export const initCelesteEgg = () => {
  const secret = document.querySelector('.celeste-secret')
  if (!secret) return

  const footer = document.querySelector('footer.footer') || document.querySelector('footer')
  if (!footer) return

  const mql = window.matchMedia('(prefers-reduced-motion: reduce)')
  const originalText = secret.textContent.trim()

  const sheetImgs = new Map()
  let chars = null
  let enabled = false
  let busy = false
  let phase = 0
  let run = 0
  let unlockTimer = 0

  // ------------------------------------------------------------------
  // 素材预加载
  //
  // CSS background-image 只有在元素真正渲染时才会去取。如果等到点击时才建节点，
  // 冷缓存下第一幕会先空白几十到几百毫秒。这里在初始化时就拉一遍，真正触发时
  // 再等当前幕 decode（最多 400ms），保证起跳帧不会错过。
  // ------------------------------------------------------------------

  const preloadAll = () => {
    for (const [n, url] of Object.entries(SHEET_URLS)) {
      const key = Number(n)
      if (sheetImgs.has(key)) continue
      const img = new Image()
      img.decoding = 'async'
      img.src = url
      // 主动开始解码；失败也不阻塞动画（最多就是不显示角色）。
      if (img.decode) img.decode().catch(() => {})
      sheetImgs.set(key, img)
    }
  }

  const whenDecoded = (img, capMs = 400) => {
    if (!img || !img.decode) return Promise.resolve()
    return new Promise((resolve) => {
      let done = false
      const finish = () => {
        if (done) return
        done = true
        clearTimeout(timer)
        resolve()
      }
      const timer = setTimeout(finish, capMs)
      Promise.resolve().then(() => img.decode()).then(finish, finish)
    })
  }

  // ------------------------------------------------------------------
  // 文字逐字翻转
  // ------------------------------------------------------------------

  const splitText = () => {
    if (chars) return chars
    secret.setAttribute('aria-label', originalText + '（点一下看看）')
    secret.textContent = ''
    chars = Array.from(originalText).map((ch) => {
      const span = document.createElement('span')
      span.className = 'ch'
      span.setAttribute('aria-hidden', 'true')
      span.textContent = ch
      secret.appendChild(span)
      return span
    })
    return chars
  }

  const spinText = (rapid = false) => {
    const list = splitText()
    const base = getComputedStyle(secret).color
    for (const el of list) {
      for (const a of el.getAnimations()) a.cancel()
    }
    for (let i = 0; i < list.length; i++) {
      list[i].animate([
        { transform: 'rotateY(0deg) translateY(0)', color: base },
        { transform: 'rotateY(180deg) translateY(-9px) scale(1.1)', color: RED, offset: .5 },
        { transform: 'rotateY(360deg) translateY(0)', color: base },
      ], {
        duration: rapid ? 640 : 860,
        delay: i * (rapid ? 12 : 26),
        easing: 'cubic-bezier(.36,.07,.19,.97)',
        // 不要用 "both"：结束帧的颜色是触发时的主题色，fill 会把它永久盖在
        // 字符上，之后切明暗文字就不变色了。none 会在结束后回到继承色。
        fill: 'none',
      })
    }
  }

  // ------------------------------------------------------------------
  // Madeline
  // ------------------------------------------------------------------

  const stageWidth = () => footer.clientWidth || document.documentElement.clientWidth || innerWidth

  const makeMadeline = (cls = '') => {
    const m = document.createElement('div')
    m.className = 'celeste-madeline' + (cls ? ' ' + cls : '')
    m.innerHTML = '<div class="celeste-madeline-flip"><div class="celeste-madeline-inner"></div></div>'
    footer.appendChild(m)
    return m
  }

  const wobble = (m, duration = 1400) => {
    m.querySelector('.celeste-madeline-inner').animate([
      { transform: 'translateY(0) rotate(0deg)' },
      { transform: 'translateY(0) rotate(2deg)', offset: .25 },
      { transform: 'translateY(0) rotate(0deg)', offset: .5 },
      { transform: 'translateY(0) rotate(3deg)', offset: .75 },
      { transform: 'translateY(0) rotate(1deg)' },
    ], {
      duration,
      iterations: Infinity,
      direction: 'alternate',
      easing: 'ease-in-out',
    })
  }

  const runWind = (id) => {
    const stage = stageWidth()
    const duration = Math.max(1200, Math.round(3800 * (stage + 140) / REF_WALK_DIST))
    const m = makeMadeline('')
    wobble(m)
    const a = m.animate([
      { transform: 'translate3d(-140px, 0, 0)' },
      { transform: 'translate3d(' + Math.round(stage * .56) + 'px, 0, 0)', offset: .58 },
      { transform: 'translate3d(' + stage + 'px, 0, 0)' },
    ], {
      duration,
      fill: 'both',
      easing: 'linear',
    })
    a.finished.then(() => {
      if (id === run) m.remove()
    }).catch(() => m.remove())
    return duration
  }

  const runBlown = (id) => {
    const stage = stageWidth()
    const duration = Math.max(900, Math.round(2800 * (stage + 140) / REF_WALK_DIST))
    const m = makeMadeline('is-act2')
    const a = m.animate([
      { transform: 'translate3d(' + stage + 'px, 0, 0)' },
      { transform: 'translate3d(-140px, 0, 0)' },
    ], {
      duration,
      fill: 'both',
      easing: 'linear',
    })
    a.finished.then(() => {
      if (id === run) m.remove()
    }).catch(() => m.remove())
    return duration
  }

  // Actual 60fps source poses and positions share one source-PTS clock with FX.
  const runDashLoop = (id, cfg) => {
    const stage = stageWidth()
    const cls = 'is-dash ' + (cfg.direction === 1 ? 'is-act3loop' : 'is-act4loop')
    const m = makeMadeline(cls)
    const inner = m.querySelector('.celeste-madeline-inner')
    const cell = cfg.cellW * cfg.scale
    const stride = cfg.dxGame * cfg.scale
    // frame 0 实体像素区间（4x）：act3 为 [24, 92]，act4 为 [28, 96]；统一从画外贴边起蹲冲入。
    const from = cfg.direction === 1 ? -92 : stage - 28
    const distance = cfg.direction === 1 ? stage - from : from + cell
    const cycles = Math.max(1, Math.ceil(distance / Math.abs(stride)))
    const duration = cycles * cfg.duration
    m.dataset.cycles = cycles
    m.dataset.stride = stride
    m.dataset.duration = duration

    const layer = document.createElement('canvas')
    layer.className = 'celeste-fx celeste-dash-fx'
    layer.width = stage
    layer.height = 220
    footer.appendChild(layer)
    const ink = layer.getContext('2d')
    const particles = []
    const rings = []
    const events = []
    let paletteTheme, colors

    const sample = (local) => {
      let frame = 0
      while (frame + 1 < cfg.times.length && cfg.times[frame + 1] <= local) frame++
      const anchor = cfg.anchors[frame]
      return { frame, anchor, x: cfg.x[frame] }
    }

    const point = (cycle, local) => {
      const p = sample(local)
      const left = Math.round(from + cycle * stride + p.x)
      return {
        x: left + p.anchor[0] * cfg.scale,
        y: layer.height - p.anchor[1] * cfg.scale,
        footX: left + cfg.feetX[p.frame] * cfg.scale,
        footY: layer.height - p.anchor[2] * cfg.scale,
      }
    }

    const square = (x, y, vx, vy, life, size, color, born) => {
      particles.push({ x, y, vx, vy, life, size, color, born })
    }

    for (let c = 0; c < cycles; c++) {
      for (let k = 0; k < 5; k++) {
        const local = cfg.fx.dash + k * 24
        events.push({ time: c * cfg.duration + local, fire(time) {
          const p = point(c, local)
          for (let j = 0; j < 3; j++) {
            square(p.x - cfg.direction * (8 + j * 6), p.y + (j - 1) * 4,
              -cfg.direction * (14 + j * 8), (j - 1) * 10,
              144 + j * 20, j === 1 ? 4 : 2, k % 2 ? 'cloud' : 'line', time)
          }
        }})
      }
      events.push({ time: c * cfg.duration + cfg.fx.apex, fire(time) {
        const p = point(c, cfg.fx.apex)
        rings.push({ x: p.x - cfg.direction * 20, y: p.y, born: time })
      }})
      events.push({ time: c * cfg.duration + cfg.fx.landing, fire(time) {
        const p = point(c, cfg.fx.landing)
        for (let j = 0; j < 8; j++) {
          const side = j % 2 ? 1 : -1
          square(p.footX + side * (2 + (j % 3) * 4), p.footY - 2,
            side * (26 + j * 4), -24 - (j % 4) * 12,
            180 + (j % 3) * 24, j % 3 ? 2 : 4, 'dust', time)
        }
      }})
    }
    events.sort((a, b) => a.time - b.time)

    const drawEffects = (time) => {
      if (!ink) return
      ink.clearRect(0, 0, layer.width, layer.height)
      // Avoid four live computed-style reads after every transform write.
      const theme = window.fixit?.isDark ? 'dark' : 'light'
      if (theme !== paletteTheme) {
        const style = getComputedStyle(footer)
        colors = Object.fromEntries(['line', 'cloud', 'dust', 'ring'].map(
          (key) => [key, style.getPropertyValue('--celeste-fx-' + key).trim()]))
        paletteTheme = theme
      }
      for (let j = particles.length - 1; j >= 0; j--) {
        const p = particles[j]
        const age = time - p.born
        if (age >= p.life) { particles.splice(j, 1); continue }
        const s = age / 1000
        const progress = age / p.life
        ink.globalAlpha = progress < .5 ? .9 : progress < .8 ? .6 : .25
        ink.fillStyle = colors[p.color]
        const gravity = p.color === 'dust' ? 220 : 0
        ink.fillRect(Math.round((p.x + p.vx * s) / 2) * 2,
          Math.min(layer.height - p.size, Math.round((p.y + p.vy * s + gravity * s * s) / 2) * 2), p.size, p.size)
      }
      for (let j = rings.length - 1; j >= 0; j--) {
        const p = rings[j]
        const age = time - p.born
        if (age >= 280) { rings.splice(j, 1); continue }
        const step = Math.floor(age / 70)
        ink.globalAlpha = 1 - step * .25
        ink.fillStyle = colors.ring
        for (let k = 0; k < 16; k++) {
          const a = k / 16 * Math.PI * 2
          ink.fillRect(Math.round((p.x + Math.cos(a) * (7 + step * 2)) / 2) * 2,
            Math.round((p.y + Math.sin(a) * (15 + step * 2)) / 2) * 2, 2, 2)
        }
      }
      ink.globalAlpha = 1
    }

    let eventIndex = 0, lastFrame = -1, lastCycle = -1
    const start = performance.now()
    const tick = (now) => {
      if (id !== run || !m.isConnected) { layer.remove(); return }
      try {
        const elapsed = now - start
        if (elapsed >= duration) { m.remove(); layer.remove(); return }
        const cycle = Math.floor(elapsed / cfg.duration)
        const p = sample(elapsed - cycle * cfg.duration)
        m.style.transform = 'translate3d(' + Math.round(from + cycle * stride + p.x) + 'px, 0, 0)'
        if (p.frame !== lastFrame) {
          inner.style.backgroundPosition = (-p.frame * cell) + 'px 0'
          m.dataset.frame = p.frame
          lastFrame = p.frame
        }
        if (cycle !== lastCycle) { m.dataset.cycle = cycle; lastCycle = cycle }
        while (eventIndex < events.length && events[eventIndex].time <= elapsed) {
          const event = events[eventIndex++]
          event.fire(event.time)
        }
        drawEffects(elapsed)
        requestAnimationFrame(tick)
      } catch {
        // 任何一帧抛错都不能留下"静止角色 + 半张特效 + 永久 busy"。
        layer.remove()
        if (id === run) abort()
      }
    }
    tick(start)
    return duration
  }

  // ------------------------------------------------------------------
  // 触发与锁
  // ------------------------------------------------------------------

  const gust = (strength, holdMs) => window.fixitSnow?.gust?.(strength, holdMs)

  const cleanup = () => {
    document.querySelectorAll('.celeste-madeline, .celeste-fx').forEach((n) => n.remove())
    try {
      secret.getAnimations({ subtree: true }).forEach((a) => a.cancel())
    } catch {
      // 极老浏览器没有 getAnimations：拆字已经被 textContent 恢复，不留动画也无妨。
    }
  }

  const lockUI = () => {
    busy = true
    document.body.classList.add('celeste-busy')
    secret.setAttribute('aria-busy', 'true')
  }

  const unlockUI = () => {
    busy = false
    document.body.classList.remove('celeste-busy')
    secret.removeAttribute('aria-busy')
    if (unlockTimer) {
      clearTimeout(unlockTimer)
      unlockTimer = 0
    }
  }

  // 统一收尾：让本次 run 失效、清掉节点/动画/定时器、解锁，并把文字恢复原文。
  // 正常结束不走这里（runWind/runBlown/runDashLoop 自己移除节点，unlockTimer 解锁）；
  // 它专门用于异常和 reduced-motion 中途切换。
  const abort = () => {
    run++
    if (unlockTimer) {
      clearTimeout(unlockTimer)
      unlockTimer = 0
    }
    try { cleanup() } catch {}
    unlockUI()
    try { secret.textContent = originalText } catch {}
    chars = null
  }

  const trigger = async (forcePhase) => {
    if (!enabled || busy) return
    if (Number.isInteger(forcePhase) && forcePhase >= 0 && forcePhase < 4) phase = forcePhase
    const thisPhase = phase
    phase = (phase + 1) % 4

    run++
    const id = run
    lockUI()

    try {
      cleanup()
      spinText(thisPhase !== 0)
      secret.dataset.phase = thisPhase

      // 冷缓存首点：等当前幕的 sheet decode，最多 400ms 就照常跑。
      await whenDecoded(sheetImgs.get(thisPhase + 1))
      if (id !== run) return

      let hold
      if (thisPhase === 0) {
        hold = runWind(id) + 150
        gust(-308, hold)
      } else if (thisPhase === 1) {
        hold = runBlown(id) + 150
        gust(-1100, hold)
      } else if (thisPhase === 2) {
        hold = runDashLoop(id, DASH3) + 150
        gust(-308, hold)
      } else {
        hold = runDashLoop(id, DASH4) + 150
        gust(-1100, hold)
      }

      unlockTimer = setTimeout(() => {
        if (id === run) unlockUI()
      }, hold + 300)
    } catch {
      // 已经进入锁：任何一步抛错都必须把本次 run 完整收掉，否则会永久 busy。
      if (id === run) abort()
    }
  }

  // ------------------------------------------------------------------
  // 可动效 / 减少动效 的开关
  // ------------------------------------------------------------------

  const enable = () => {
    if (enabled) return
    enabled = true
    preloadAll()
    footer.classList.add('celeste-stage')
    secret.classList.add('is-ready')
    secret.setAttribute('role', 'button')
    secret.setAttribute('tabindex', '0')
    secret.setAttribute('aria-label', originalText + '（点一下看看）')
  }

  const disable = () => {
    if (!enabled) return
    enabled = false
    abort()
    phase = 0
    secret.classList.remove('is-ready')
    secret.removeAttribute('role')
    secret.removeAttribute('tabindex')
    secret.removeAttribute('aria-label')
    secret.removeAttribute('aria-busy')
    delete secret.dataset.phase
  }

  const onMotionPreference = () => {
    if (mql.matches) disable()
    else enable()
  }

  mql.addEventListener?.('change', onMotionPreference)
  if (!mql.matches) enable()

  secret.addEventListener('click', () => {
    if (enabled) trigger()
  })

  secret.addEventListener('keydown', (e) => {
    if (!enabled) return
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault()
      trigger()
    }
  })
}
