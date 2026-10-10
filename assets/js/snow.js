/**
 * 雪花特效 — forsure.live（Canvas 实现，替换 DHTML Snowstorm 1.44）
 *
 * 由同目录的 custom.js `import { initSnow } from './snow.js'` 引入。Hugo 的
 * js.Build（esbuild）会把它内联进同一份 custom.min.<hash>.js —— 那份是带指纹、带 SRI、
 * 被不缓存的 HTML 引用的，所以改完立刻生效。
 * 换成 static/ 就做不到这点（static/ 不走资源管线、不带 hash，改一次要等 Cloudflare
 * 4 小时过期或手动 purge，见 hugo.toml 里的相关说明）。
 *
 * -----------------------------------------------------------------------------
 * 三层坐标系（读懂这个才能改这个文件）
 *
 *   1. 文档坐标 y ∈ [0, docH]   —— 粒子活在这里。所以雪花是**锚定在页面上**的：
 *      滚动时它跟着文章一起走，而不是钉在屏幕上（钉在屏幕上会像一层贴膜）。
 *   2. 屏幕坐标 sy = y - scrollY —— 只用于判定"在不在视野里"和"有没有落到屏幕底边"。
 *   3. "地面" = 屏幕底边，也就是文档坐标里的 scrollY + H。
 *
 *   为什么地面是屏幕底边而不是文档底部：这样才能"雪落在你眼前"。
 *   为什么粒子要铺满整个文档而不只是一屏：否则往下滚会滚进一片没有雪的区域。
 *   这两件事同时成立的关键在下面"落地与重生"那一段，先读完再动。
 * -----------------------------------------------------------------------------
 * 为什么当初整份重写 —— 旧 static/js/snow.js 的三处硬伤（行号按旧文件）：
 *   1) 方向会整体反号。move()（旧 426 行）算的是**乘法** vX = s.vX * windOffset，而 s.vX
 *      的符号来自 vRndX = plusMinus(...)，那是在 randomizeWind()（旧 246 行）里只跑一次
 *      的**全局唯一**正负号，所有雪花共用。抛到负号时全场基准漂移向左，此时鼠标在右半边
 *      （windOffset > 0）就得到 vX < 0 —— 鼠标在右、雪往左，看起来就是反的。
 *      这里改成**加法** vX = drift + mouseWind，风向不可能再整体反号。
 *   2) 速度随刷新率变。旧速度是"每帧像素"，animationInterval = 24（旧 22 行）只喂给
 *      timeoutShim（旧 85-87 行），后者仅在没有 requestAnimationFrame 时兜底 —— 现代
 *      浏览器一律走 rAF，所以那个值等于没生效，144Hz 屏比 60Hz 快 2.4 倍。
 *      这里一律 px/s × dt，与刷新率无关。
 *   3) 每帧强制布局。旧 setXY()（旧 150-185 行）走百分比分支，每帧给每片雪花写
 *      style.right / style.bottom —— 百分比定位不参与合成，触发样式重算与布局（实测
 *      每秒 120 次布局 + 120 次样式重算）。这里只往 canvas 上画，两者都是 0。
 *
 * 顺带一提：旧版其实**并没有**锚定在页面上 —— 它的 bottom 百分比是相对初始包含块算的，
 * 所以雪只存在于文档最顶上那一屏里。实测滚到 1200px 时视野内的雪花从 58 片掉到 15 片，
 * 剩下的基本是 position:fixed 粘在视口底边的那批。所以"滚动后雪就没了"才是它的实际行为。
 *
 * ⚠️ 别把 SPEED 改回"每帧像素"，也别把 mouseWind 改回乘法 —— 那等于把 1)、2) 重新挖开。
 */

// -----------------------------------------------------------------------------
// 可调参数（速度一律 px/s，与刷新率无关）
// -----------------------------------------------------------------------------
const PAGE_ANCHORED = true   // ★开关：true = 雪花锚定在页面上（滚动时跟着文章走）
                             //   false = 钉在屏幕上（旧行为）。改完要重新构建。

const SPEED = 60             // 近景下落速度：1000px 视口约 17s 穿屏（旧版约 110px/s）
const MOUSE_WIND = 0.3       // 鼠标风上限 = 0.3 × SPEED = 18 px/s（旧系数 0.6 太猛）
const BASE_DRIFT = 4         // 每片自带的水平漂移 ±4 px/s，让居中区域也不是笔直下落
// 密度。注意它是**按面积**算的，所以屏幕越大雪越多：1440×900 一屏约 108 片，
// 而 4K（3840×2160）一屏约 488 片 —— 面积是 6.4 倍。觉得还是多就继续调大这个数
// （17000 → 24000 约再少三成），整篇文档与每屏都按同一密度，改一个数就够。
const AREA_PER_FLAKE = 17000 // 约每 17000 平方像素一片（按**整篇文档**的面积算）
const MAX_FLAKES = 3000      // 上限，防止 4K + 长文章时画爆（4K × 8432px 文章实测 1905 片）
const MAX_DPR = 2            // DPR 封顶 2：再高的物理密度看不见，像素/内存却翻倍
const MAX_DT = 0.05          // dt 上限 50ms：切标签页回来时不要瞬移一整屏

// 三层景深：近处 大/快/实，远处 小/慢/淡。
//   radius = CSS 像素半径；speed = 乘在 SPEED 上的倍率；alpha = 整层不透明度。
//   alpha 是浅色模式下最可能需要上调的旋钮（浅底上的淡雪花比深底上更难看见）。
const LAYERS = [
  { radius: 1.2, speed: 0.55, alpha: 0.30 }, // 远景
  { radius: 1.8, speed: 0.80, alpha: 0.50 }, // 中景
  { radius: 2.6, speed: 1.00, alpha: 0.75 }, // 近景
]
const NEAR = LAYERS[LAYERS.length - 1]

// 融化：落地后 停留 → 收缩成小雪花 → 最后快速淡出。见 frame() 里的三段。
//   每片收缩的目标半径取 min(MELT_RADIUS, 自己的半径) —— 有个 min 才不会出现
//   "小雪花越融越大"（远景最小的一片半径是 1.2 × 0.7 = 0.84，比 MELT_RADIUS 还小）。
//   小雪花本来就接近这个半径，收缩段几乎看不出，等于直接停一下再淡出；
//   大雪花才会明显先缩成一个点。正是想要的效果，不需要为大小写两条分支。
const MELT_REST = 0.6        // 落地后原样停留（让人看清"它停住了"）
const MELT_SHRINK = 0.9      // 收缩到 MELT_RADIUS
const MELT_FADE = 0.35       // 最后快速淡出归零
const MELT_RADIUS = 1.5      // "小雪花"的固定半径（0.8 嫌太小时调这里）
const MELT_TOTAL = MELT_REST + MELT_SHRINK + MELT_FADE

// 文档底部回收时，落点在文档顶端上方这个范围内随机散开，而不是全钉在一条线上。
// 必要性：快速滚动会让成百片**几乎同时**落到底部、同时被回收，钉在一条线上就结成
// 一堵"雪墙"推下来（实测过一次：930 片同时重生，文档最顶上挤了 1716 片）。
const RECYCLE_SPREAD = 250

// 柔和圆点的径向渐变节点。这就是"雪花长什么样"的旋钮：
// 中心段拉得越长越像实心圆点，收得越早越像雾团（太软会在浅色底上看不见）。
const GRADIENT = [[0, 1], [0.5, 0.9], [0.8, 0.3], [1, 0]]

// -----------------------------------------------------------------------------
// 状态（循环里不新建任何对象，也就没有 GC 抖动）
// -----------------------------------------------------------------------------
let canvas
let ctx
let sprite          // 预渲染的柔和圆点贴图
let spriteRgb = ''  // 贴图当前用的颜色，用来判断主题变化后要不要重建
let particles = []  // 每项 { x, y, r, vy, drift, alpha, melt }，都是普通数字
let W = 0
let H = 0
let docH = 0        // 文档高度（PAGE_ANCHORED 为 false 时它就是视口高）
let scrollY = 0     // 缓存的滚动量：由被动 scroll 监听更新，循环里不读 window.scrollY
let groundY = 0     // "地面"在文档坐标里的位置（= 屏幕底边），见 frame() 开头那段说明
let prevScrollY = 0 // 上一帧的滚动量，用来算 dScroll（"这次越界是不是滚动推的"）
let dpr = 1
let mouseNx = 0     // 鼠标归一化横坐标：-1 最左 … 0 正中 … +1 最右
let raf = 0
let last = 0
let running = false

const mqlReduce = window.matchMedia('(prefers-reduced-motion: reduce)')
const mqlDark = window.matchMedia('(prefers-color-scheme: dark)')

// -----------------------------------------------------------------------------
// 颜色
//
// custom.scss 给 .snow-canvas 的 color 写了 light-dark(...)。直接读自定义属性拿到的会是
// **未解析的 token 流**（"light-dark(rgb(…)…)" 这串字面量），canvas 不认、会静默当成黑色；
// 经 getComputedStyle(canvas).color 读才被解析成当前主题的 rgb()。
// 所以 canvas 兼作"取色探针"，不必多造元素。主题一变这里读到的就跟着变。
// -----------------------------------------------------------------------------
const readColor = () => {
  const m = getComputedStyle(canvas).color.match(/\d+(?:\.\d+)?/g)
  // 兜底给中性灰。绝不能把 light-dark(...) 字面量交给 canvas。
  return m ? m.slice(0, 3).join(', ') : '180, 190, 203'
}

// 预渲染一张"柔和圆点"贴图：径向渐变，中心实、边缘全透明。
// 用贴图而不是每帧 ctx.createRadialGradient —— 渐变对象每帧新建会产生垃圾
// （几百片 × 60fps 就是每秒上万个对象），而柔和边缘只需要算一次。
const makeSprite = (rgb) => {
  // 1.6 倍留白给渐变边缘，否则会被贴图边界切成硬边
  const size = Math.ceil(NEAR.radius * 2 * dpr * 1.6)
  const c = document.createElement('canvas')
  c.width = c.height = size
  const g = c.getContext('2d')
  const mid = size / 2
  const grad = g.createRadialGradient(mid, mid, 0, mid, mid, mid)
  for (const [at, a] of GRADIENT) grad.addColorStop(at, `rgba(${rgb}, ${a})`)
  g.fillStyle = grad
  g.fillRect(0, 0, size, size)
  return c
}

// -----------------------------------------------------------------------------
// 粒子池
// -----------------------------------------------------------------------------
const targetCount = () => Math.min(MAX_FLAKES, Math.round((W * docH) / AREA_PER_FLAKE))

const makeFlake = (yMin, yMax) => {
  const layer = LAYERS[(Math.random() * LAYERS.length) | 0]
  return {
    x: Math.random() * W,
    y: yMin + Math.random() * Math.max(0, yMax - yMin),
    r: layer.radius * (0.7 + Math.random() * 0.6), // 同层也留点大小差，避免整齐划一
    vy: SPEED * layer.speed * (0.85 + Math.random() * 0.3),
    drift: (Math.random() * 2 - 1) * BASE_DRIFT,
    alpha: layer.alpha,
    melt: -1,          // -1 = 正常下落；≥0 = 已融化了几秒
    meltY: 0,          // 融化时所在的文档位置；融化完就回到这里继续落
  }
}

// 融化结束后：**回到它融化的地方继续下落**（p.meltY）。
//
// ⚠️ "接了之后搬去哪儿"是这一整套里最容易做错的一步，因为它怎么选都会把密度搬歪：
//   - 全搬到地面下方 → 上半篇被抽空。实测：上滚一趟后屏幕内从 100% 一路掉到 **35%**，
//     而且停下后还在继续掉、要两分钟才回来（补回来要靠雪走完整个下半篇，约 133 秒）。
//   - 滚动推过去的那批改搬到屏幕顶端上方 → 反过来了：上篇过密、下篇抽空。实测停下后
//     冲到 **249%**，纵向剖面 5/8/73/114/294/487/404/…（偏差 214%），
//     **而且静止时滚到文档底部那里是 0.00× —— 底下一片雪都没有**。
//   - 原地不动（现在这个）→ 什么都不搬，密度自然不受影响。因为融化点是"雪花底边刚越过
//     屏幕底边"的那一刻，它的文档位置本来就在地面附近，回原地等价于"就地重新落下"。
//     融化期间它只是不参与下落（约占池子的一小截），融化完继续落。
//
// 唯一要处理的边角：这 MELT_TOTAL 秒里你可能往下滚，把它原来的位置滚进了视野 ——
// 那样直接在那儿冒出来会"凭空出现"，所以挪到屏幕底边之下。
const respawnFlake = (p) => {
  p.y = p.meltY
  if (PAGE_ANCHORED) {
    const sy = p.y - scrollY
    if (sy > -p.r && sy < H + p.r) p.y = scrollY + H + p.r
  }
}

// 只在数量变化时增删，**不重铺** —— 重铺会让所有雪花瞬移一下。
//
// ⚠️ 新增的片必须铺在 [yMin, yMax) 这一条区间里，不能全堆在一条线上。
//   这一条是给"文档长高了"用的：懒加载的图片会把页面越撑越高，新长出来的那一段
//   要按同样的密度补上。曾经图省事把补的片全放在屏幕底边那一条线上，后果是
//   开局长出约 800 片堆成一条"雪团"慢慢往下扩散，而它上方的首屏被抽干 ——
//   实测开局 25 秒内首屏的雪从 108 片掉到 0（每秒掉 4.7 片，正好等于融化速率），
//   要等两分半那团雪走到底部才补回来。按区间铺就没有这个过程。
//   另外文档很矮时（懒加载还没发生）最省事的判断就是让 [yMin,yMax) 覆盖整篇。
const syncCount = (yMin, yMax, avoidVisible) => {
  let lo = yMin
  let hi = yMax
  // 补片若正好压在屏幕上，就挪到屏幕底边之下，免得看到雪花凭空出现。
  // （只有"文档长高"这条路径会走到这里；首次铺场是故意要铺满屏幕的。）
  if (avoidVisible) {
    const top = PAGE_ANCHORED ? scrollY : 0
    if (hi > top - NEAR.radius && lo < top + H + NEAR.radius) {
      lo = top + H + NEAR.radius
      hi = Math.max(lo, yMax)
    }
  }
  const want = targetCount()
  while (particles.length < want) particles.push(makeFlake(lo, hi))
  if (particles.length > want) particles.length = want
}

// 文档高度会变（懒加载的图片、折叠面板）。用它重建"场"的尺寸。
const syncField = () => {
  const h = PAGE_ANCHORED ? Math.max(H, document.documentElement.scrollHeight) : H
  if (h === docH) return
  const prev = docH
  docH = h
  // 长高了：只给新长出来的那一条按同样密度补片（见 syncCount 的说明）
  // 变矮了：syncCount 会靠截断把多余的削掉
  syncCount(prev, h, h > prev)
}

// -----------------------------------------------------------------------------
// 渲染循环
// -----------------------------------------------------------------------------
const frame = (now) => {
  raf = requestAnimationFrame(frame)
  const dt = Math.min((now - last) / 1000, MAX_DT) // 夹住 dt：切回来不要瞬移
  last = now

  ctx.clearRect(0, 0, W, H)

  const top = PAGE_ANCHORED ? scrollY : 0 // 视野顶端在文档里的位置
  const dScroll = scrollY - prevScrollY    // 本帧的滚动量，用来判断越界是不是滚动推的
  prevScrollY = scrollY

  // ---- 地面 = 屏幕底边，永远是 ----
  //
  // 只要一片雪的**底边**越过屏幕底边往下走就融化 —— 不管这次越界是它自己下落造成的，
  // 还是你**向上滚**把页面推下去的。所以向上滚时能"全部接住"。
  //
  // 只接屏幕上那一层：已经落在屏幕下方（看不见）的雪不融化，它们继续往文档底部落、
  // 在底部回收 —— 否则屏幕下方那一段会被掏空，往下滚就没雪了。
  //
  // 「接住之后把它放回哪儿」决定了这件事会不会把密度搞歪，见 respawnFlake 的说明：
  // 自己下落的放地面下方，被滚动推过界的放屏幕顶端上方。两者分开处理，才能既全部
  // 接住、又不动上下两段的雪量。
  groundY = PAGE_ANCHORED ? Math.min(docH, scrollY + H) : H

  const gy = groundY - top // 融化线在屏幕上的位置（= H，除非已经滚到文档最底）
  const wind = mouseNx * MOUSE_WIND * SPEED
  const taper = 1 - Math.abs(mouseNx)

  for (let i = 0; i < particles.length; i++) {
    const p = particles[i]

    // ---- 融化中：钉在地面上，不参与下落，也不出现在别处 ----
    // （"融化期间不存在于任何其它位置"是消除破绽的关键：否则你一下滚，本体就会从
    //   屏幕下方升进视野，和还没淡完的残影叠在一起。）
    if (p.melt >= 0) {
      p.melt += dt
      if (p.melt >= MELT_TOTAL) {
        p.melt = -1
        respawnFlake(p) // 重生在看不见的地方
        continue
      }
      const t = p.melt
      const rEnd = MELT_RADIUS < p.r ? MELT_RADIUS : p.r // 见 MELT_RADIUS 处的说明
      let r, a
      if (t < MELT_REST) {                       // 1) 停留：原样不动
        r = p.r
        a = p.alpha
      } else if (t < MELT_REST + MELT_SHRINK) {  // 2) 收缩到小雪花（透明度不变）
        r = p.r + (rEnd - p.r) * ((t - MELT_REST) / MELT_SHRINK)
        a = p.alpha
      } else {                                   // 3) 最后快速淡出
        r = rEnd
        a = p.alpha * (1 - (t - MELT_REST - MELT_SHRINK) / MELT_FADE)
      }
      // 底边钉在地面上，所以圆心在 gy - r：缩小的时候是"往下沉进地里"，
      // 而不是浮在半空缩。
      ctx.globalAlpha = a
      ctx.drawImage(sprite, p.x - r, gy - r * 2, r * 2, r * 2)
      continue
    }

    // ---- 正常下落 ----
    p.x += (p.drift * taper + wind) * dt
    p.y += p.vy * dt

    const sy = p.y - top // 屏幕坐标

    // 落地判定：**底边越过屏幕底边往下走**。用屏幕坐标 + 本帧滚动量，于是
    // "自己下落越过的"和"向上滚把页面推下去的"都算 —— 也就是全部接住。
    //
    // prevSy = 扣掉本帧下落量、再加回本帧滚动量之后的屏幕坐标：
    //   扣下落量 → 判断"是不是下落推过去的"
    //   加滚动量 → 判断"是不是滚动推过去的"
    //   两者都留着，才是"不管什么原因，越过就接住"。
    //
    // ⚠️ 用底边（sy + r），不是顶边（sy - r）。用顶边等于"整片雪都掉出屏幕才算落地"，
    //    而重生点恰好紧贴屏幕底边下方 —— 刚重生就立刻满足"顶边越界"，无限循环
    //    融化→重生→融化，粒子永远卡在底边那一线上，回不到下面那段。实测后果：
    //    屏幕下方那段几乎没雪，往下滚露出一条空带，纵向密度也整个歪掉。
    //
    // 本来就位于屏幕下方的雪永远不会命中（prevSy 已经越界），它们继续往下落、
    // 到文档底部才回收 —— 这正是"滚下去还有雪"的来源。
    const prevSy = sy - p.vy * dt + dScroll
    if (sy + p.r > H && prevSy + p.r <= H) {
      p.meltY = p.y // 记住融化的位置，融化完回这儿继续落（见 respawnFlake）
      p.melt = 0
      continue
    }

    // 文档底部回收 → 回到顶端上方重来（这一路是看不见的，正好给上半篇供雪）
    if (p.y - p.r > docH) {
      p.y = -p.r - Math.random() * RECYCLE_SPREAD
      p.x = Math.random() * W
    }

    if (p.x < -p.r) p.x = W + p.r
    else if (p.x > W + p.r) p.x = -p.r

    if (sy > -p.r && sy < H + p.r) { // 屏幕外不画 —— 这是"铺满整篇文档"不花绘制成本的原因
      ctx.globalAlpha = p.alpha
      ctx.drawImage(sprite, p.x - p.r, sy - p.r, p.r * 2, p.r * 2)
    }
  }
  ctx.globalAlpha = 1
}

// -----------------------------------------------------------------------------
// 事件
// -----------------------------------------------------------------------------
const onMouse = (e) => {
  // 只认 mousemove 不认 pointermove：桌面端够用，且 CDP 的 Input.dispatchMouseEvent
  // 稳定产生 mouse 事件，验证脚本靠它驱动。
  mouseNx = Math.max(-1, Math.min(1, (e.clientX / W) * 2 - 1))
}

const onMouseLeave = () => { mouseNx = 0 } // 鼠标移出窗口 → 回到自然漂移

// 缓存滚动量。不写成"每帧读 window.scrollY"是为了不制造强制样式刷新：
// 本文件从不写 DOM 样式，于是布局永远是干净的，每帧读 scrollY 反而会把它弄脏。
const onScroll = () => { scrollY = window.scrollY || window.pageYOffset || 0 }

const onResize = () => {
  W = window.innerWidth
  H = window.innerHeight
  // DPR 也可能因为窗口被拖到另一块屏而变 → 跟着重建贴图
  const ndpr = Math.min(window.devicePixelRatio || 1, MAX_DPR)
  if (ndpr !== dpr) {
    dpr = ndpr
    sprite = makeSprite(spriteRgb)
  }
  canvas.width = Math.round(W * dpr)
  canvas.height = Math.round(H * dpr)
  // 显式写像素尺寸：让本文件不依赖 .snow-canvas 的 width/height 规则，单独也能跑
  canvas.style.width = `${W}px`
  canvas.style.height = `${H}px`
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0) // 之后一律按 CSS 像素作画，DPR 交给矩阵
  syncField()
}

const onVisibility = () => {
  // 切后台直接停 rAF（省电）；回来时重置 last，避免攒出一个大 dt
  if (document.visibilityState === 'hidden') {
    cancelAnimationFrame(raf)
    raf = 0
  } else if (running && !raf) {
    last = performance.now()
    raf = requestAnimationFrame(frame)
  }
}

// 主题切换有两条路径，都要盯：
//   1) 手动切 → <html data-theme-mode> 变（light|dark|auto），用 MutationObserver；
//   2) auto 模式下系统变 → 属性保持 'auto' 不动，只有 prefers-color-scheme 变，用 mql。
// 只写其中一个都会漏。两件事同一个结果：CSS 里 light-dark() 重新解析 → 重读颜色、
// 必要时重建贴图。MutationObserver 回调里调 getComputedStyle 会强制刷新样式，
// 所以读到的一定是新值。
const onThemeChange = () => {
  const rgb = readColor()
  if (rgb !== spriteRgb) {
    spriteRgb = rgb
    sprite = makeSprite(rgb)
  }
}

const themeObserver = new MutationObserver(onThemeChange)

// 文档高度变化（懒加载图片撑高页面）时补片
const fieldObserver = new ResizeObserver(syncField)

// -----------------------------------------------------------------------------
// 生命周期
// -----------------------------------------------------------------------------
const stop = () => {
  running = false
  cancelAnimationFrame(raf)
  raf = 0
}

const start = () => {
  if (running) return
  running = true
  last = performance.now()
  raf = requestAnimationFrame(frame)
}

// 系统在运行中切到"减少动效"就收摊，切回来再开一次
const onReduceChange = ({ matches }) => {
  if (matches) teardown()
  else initSnow()
}

const teardown = () => {
  stop()
  window.removeEventListener('mousemove', onMouse)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('load', onThemeChange)
  document.removeEventListener('mouseleave', onMouseLeave)
  document.removeEventListener('visibilitychange', onVisibility)
  mqlReduce.removeEventListener('change', onReduceChange)
  mqlDark.removeEventListener('change', onThemeChange)
  themeObserver.disconnect()
  fieldObserver.disconnect()
  canvas && canvas.remove()
  canvas = ctx = sprite = undefined
  particles = []
  window.fixitSnow = undefined
}

export const initSnow = () => {
  // 尊重 prefers-reduced-motion：与 custom.scss 第 4、5 节同一取舍 —— 直接不开
  if (mqlReduce.matches) return
  // 移动端不画。这里用指针能力判断而不是旧版的 UA 正则：旧正则漏掉 iPadOS（它发桌面
  // Safari 的 UA），按宽度判断又会在窄窗口的桌面上误伤。(pointer: coarse) 描述的是
  // "主指针是触摸"，正是本意，且不怕 resize。
  if (window.matchMedia('(pointer: coarse)').matches) return
  if (running) return

  canvas = document.createElement('canvas')
  canvas.className = 'snow-canvas'
  canvas.setAttribute('aria-hidden', 'true')
  document.body.appendChild(canvas) // 先入文档：getComputedStyle 才会返回解析后的 color
  ctx = canvas.getContext('2d')

  W = window.innerWidth
  H = window.innerHeight
  dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR)
  // 浏览器恢复滚动位置时，一上来就该是对的位置，否则整场雪会先滑一下
  onScroll()
  prevScrollY = scrollY // 免得第一帧算出一个巨大的 dScroll 把全场雪都判成"滚过去的"
  docH = PAGE_ANCHORED ? Math.max(H, document.documentElement.scrollHeight) : H
  groundY = PAGE_ANCHORED ? Math.min(docH, scrollY + H) : H // 一上来地面就贴着屏幕底边
  spriteRgb = readColor()
  sprite = makeSprite(spriteRgb)
  // 首次铺场：把整篇文档均匀铺满，屏幕里也是满的（avoidVisible = false）。
  // 此刻 document.scrollHeight 往往还很小（懒加载的图片没载入），没关系 ——
  // 页面随后长高时 syncField 会把新长出来的那一段按同样密度补上。
  syncCount(-NEAR.radius, docH, false)
  onResize() // 定下 bitmap 尺寸与变换矩阵

  window.addEventListener('mousemove', onMouse, { passive: true })
  window.addEventListener('resize', onResize, { passive: true })
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('load', onThemeChange) // CSS 万一晚于本脚本生效，兜一次
  document.addEventListener('mouseleave', onMouseLeave)
  document.addEventListener('visibilitychange', onVisibility)
  mqlReduce.addEventListener('change', onReduceChange)
  mqlDark.addEventListener('change', onThemeChange)
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme-mode'],
  })
  fieldObserver.observe(document.body)

  start()

  // 调试/验证把手（与主题自己的 window.fixit 同一风格）。CDP 脚本靠它读粒子位置来量
  // 速度、判断风向是否反号、看有多少片在融化 —— 事后复验的唯一无像素相关入口。
  // 不想要可以整段删掉（teardown 里的那行一起删），改用截图逐帧相关来验证。
  window.fixitSnow = {
    SPEED,
    MOUSE_WIND,
    PAGE_ANCHORED,
    LAYERS,
    MELT_TOTAL,
    particles: () => particles,
    debug: () => ({
      rgb: spriteRgb, count: particles.length, W, H, docH, scrollY, dpr, running,
      melting: particles.reduce((n, p) => n + (p.melt >= 0 ? 1 : 0), 0),
      groundY,
      // 融化线在屏幕上的位置。负 = 在屏幕上方；> H = 在屏幕下方（向上滚时就是这种）
      groundScreenY: groundY - (PAGE_ANCHORED ? scrollY : 0),
      // 把关键常量也报出来，好让验证脚本拿**实际生效的值**去算期望值。
      // （踩过：改完常量没重新构建就去测，脚本却用硬编码的期望值判定"通过"，
      //   结果测的是上一版产物。现在期望值一律从这里取。）
      AREA_PER_FLAKE, MAX_FLAKES, SPEED, MOUSE_WIND, MELT_RADIUS, MELT_TOTAL,
    }),
    start,
    stop,
    teardown,
  }
}
