#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 Chen Fangshuo
# SPDX-License-Identifier: MIT · 完整许可文本见仓库根目录 LICENSE
"""
双脉冲测试（DPT）示波器 CSV 自动分析脚本
==========================================

支持鼎阳（Siglent）示波器导出的“单通道一个 CSV”格式：
    前若干行是元数据（Record Length / Sample Interval / Vertical Units / Source ...），
    之后是 `Second,Value` 表头和数据。

默认按 CH1=VGS、CH2=ID、CH3=VDS 使用；三份 CSV 可以不同时基/点数，
脚本会自动对齐到同一条时间轴。

所有可调参数集中在下面的“0. 配置区”，改完直接运行即可。
命令行参数见 `python dpt_analyzer.py -h`。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
# 用 SciPy 的 trapezoid，兼容 NumPy 1.x / 2.x（NumPy 1.x 没有 np.trapezoid）。
from scipy.integrate import cumulative_trapezoid, trapezoid
from scipy.signal import bilinear, lfilter, lfilter_zi


# ==============================================================================
# 0. 配置区（所有可调参数都在这里）
# ==============================================================================

# ---------- 0.1 输入 / 输出 ----------
DEFAULT_DATA_DIR = "."                 # 无参数运行时扫描哪个目录
CSV_GLOB_C1 = "*_C1_*.csv"             # 自动扫描模式：C1 文件名的匹配规则
CH_VGS, CH_ID, CH_VDS = "C1", "C2", "C3"   # 通道角色 → 文件名里的通道标记

OUTPUT_DIR = "."                       # 图片/CSV 默认输出目录
OUTPUT_FIG_NAME = "dpt-switching-analysis.png"   # 与文章正文引用保持一致
DEFAULT_EXPORT_CSV = "dpt_processed.csv"
DEFAULT_EXPORT_METRICS = "dpt_metrics.csv"
PLOT_DPI = 200                         # 300 会很清晰但文件大；200 足够博客使用
PLOT_SHOW = True                       # 运行完是否弹窗；无头环境可加 --no-show
MARKDOWN_TABLE = True                  # 终端是否额外打印可粘贴的 Markdown 表

# ---------- 0.2 通道校准 ----------
# 示波器硬件里已经给电流通道加了 +27 ns 的 Deskew，CSV 导出的是校准后的波形。
# 这里再留一个软件微调：正值让电流波形提前（左移），负值让它延后（右移）。
DESKEW_ID_NS = 0.0
HARDWARE_DESKEW_NS = 27.0              # 只用于报告标题，提醒读者硬件已经校过

AUTO_ZERO_BASELINE = True              # 自动去掉探头零点/罗氏线圈零漂
INVERT_VGS = False                     # 探头接反时改成 True
INVERT_ID = False
INVERT_VDS = False

# ---------- 0.3 VGS 边沿识别 ----------
VGS_SMOOTH_NS = 10.0                   # 移动平均窗宽（ns）；2 ns 采样时约 5 个点
EDGE_HYST_FRAC = 0.10                  # 迟滞：门限上下各 10% 驱动幅度，防栅极振铃误触发
MIN_PULSE_NS = 200.0                   # 小于这个宽度的高电平视为振铃，丢弃
MIN_DEAD_NS = 100.0                    # 两个脉冲之间允许的最小低电平宽度
MIN_EDGE_SWING_V = 1.0                 # VGS 高低差小于此值就认为没有有效脉冲
ALLOW_TRUNCATED_SECOND_PULSE = True    # 记录在第二个脉冲中途结束时，允许 t_off2 = 记录终点

# ---------- 0.4 比例窗口 ----------
# 所有窗口都用“实测脉宽/死区的百分比”表示，不再写死 0.5us、4us 之类的偏移。
# 这样 1 us 窄脉冲和 50 us 宽脉冲都能用。
WIN_PRE_QUIET     = (0.20, 0.80)       # [记录起点, t_on1] 内取 20%~80%：Vbus、VGS/ID 零偏
WIN_PULSE1_MID    = (0.30, 0.70)       # 第一脉冲 30%~70%：VGS 高电平、VDS 导通压降
WIN_PULSE1_RAMP   = (0.20, 0.80)       # 第一脉冲 20%~80%：ID 线性拟合，估 L_load
WIN_PULSE1_END    = (0.97, 0.998)      # 关断前最后一段：取 I_off（避开下降沿）
WIN_DEAD_LATE     = (0.50, 0.85)       # 死区后段 50%~85%：VDS 续流平台、ID 零偏
WIN_PULSE2_EARLY  = (0.005, 0.02)      # 第二脉冲恢复后的短平台：I_load_on、Qrr 基线
WINDOW_MIN_SAMPLES = 20                # 比例窗口至少要有这么多点，否则自动向前扩展

# ---------- 0.5 分析窗口（示波器放大图的左右宽度） ----------
WINDOW_MODE = "auto"                   # "auto"：按实测开关时间自动定宽；"manual"：用下面两个值
WINDOW_PRE_NS = 60.0                   # manual 模式：边沿前窗口
WINDOW_POST_NS = 160.0                 # manual 模式：边沿后窗口
WINDOW_AUTO_PRE_FACTOR = 3.0           # auto：前窗 = 3 × 实测开关时间
WINDOW_AUTO_POST_FACTOR = 5.0          # auto：后窗 = 5 × 实测开关时间
WINDOW_AUTO_MIN_NS = 20.0              # auto 窗口下限
WINDOW_AUTO_MAX_FRAC = 0.30            # auto 窗口最多占相邻区间（脉宽/死区）的 30%

# ---------- 0.6 罗氏线圈数字补偿（默认关闭） ----------
# DIY 罗氏线圈的积分器不是理想积分器：电流阶跃后会出现“平台凸起”，
# 关断后会出现“低频下冲”。这里用一阶零极点滤波扣掉高通/交越失配分量：
#
#     H(s) = 1 - droop_gain * (s*tau) / (1 + s*tau)
#          = (1 + (1-droop_gain)*s*tau) / (1 + s*tau)
#
# 直流增益 = 1（不会把稳态电流整体放大），高频增益 = 1 - droop_gain。
# 在本文的实测数据上，tau=0.60 us、droop_gain=0.11 可以把开通后约 +2 A 的
# 平台凸起和关断后约 -2.7 A 的下冲压回 0 附近，同时不影响电流斜坡。
ENABLE_ROGOWSKI_COMP = False
ROGOWSKI_PRESET = "HQRocoil-Mini"
ROGOWSKI_PRESETS = {
    "HQRocoil-Mini": {"tau_us": 0.60, "droop_gain": 0.11},
    "ideal":         {"tau_us": 0.60, "droop_gain": 0.00},
}

# ---------- 0.7 JEDEC 开关时间阈值（10%~90%） ----------
TH_TIME = {
    # 开通：tdon/t_dv(on) 起点 = VGS 10%；tr/trv 终点 = 90%/10%
    "vgs_on_start": 0.10,
    "id_on_start":  0.10,
    "id_on_end":    0.90,
    "vds_on_start": 0.90,
    "vds_on_end":   0.10,
    # 关断：tdoff/t_dv(off) 起点 = VGS 90%；tf/tvf 终点 = 10%/90%
    "vgs_off_start": 0.90,
    "id_off_start":  0.90,
    "id_off_end":    0.10,
    "vds_off_start": 0.10,
    "vds_off_end":   0.90,
}

# ---------- 0.8 开关损耗积分阈值（JEDEC） ----------
TH_LOSS = {
    "eoff_start_ref": "VGS",           # 可选 "VGS" 或 "VDS"
    "eoff_start_pct": 0.90,
    "eoff_end_id":    0.02,
    "eon_start_ref":  "ID",            # 可选 "ID" 或 "VGS"
    "eon_start_pct":  0.10,
    "eon_end_vds":    0.02,
}

# ---------- 0.9 新增指标 ----------
L_LOAD_R2_MIN = 0.99                   # 线性拟合优度低于此值时给出警告
QRR_BAND_ABS_A = 0.30                  # Qrr 恢复结束判据：至少偏离基线 0.30 A
QRR_BAND_REL = 0.05                    # 或偏离 5% 的负载电流（取较大者，避免被慢漂尾拖住）
QRR_SETTLE_NS = 50.0                   # 回到基线并保持这么久，认为恢复结束
QRR_MAX_FRAC = 0.10                    # Qrr 最多看第二脉宽的 10%
QRR_MAX_US = 1.0                       # 且最多 1 us
IRM_MAX_FRAC = 0.05                    # IRM 搜索窗口最多占 tp2 的 5%
IRM_MAX_US = 1.0

# ---------- 0.10 报告文字 ----------
DEVICE_NAME = "100V 1.7mΩ TOLT SGT MOSFET"
TEST_TITLE = "Double Pulse Test (DPT) Switching Analysis"


# ==============================================================================
# 1. 数据结构与通用工具
# ==============================================================================

class DptError(Exception):
    """分析过程中可以直接展示给用户的错误。"""


@dataclass
class ChannelCsv:
    time: np.ndarray
    value: np.ndarray
    source: str
    unit: str
    meta: dict = field(default_factory=dict)


@dataclass
class DptData:
    t: np.ndarray
    vgs_raw: np.ndarray
    id_raw: np.ndarray
    vds_raw: np.ndarray
    dt: float
    fs: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class PulseTiming:
    t_on1: float
    t_off1: float
    t_on2: float
    t_off2: float
    tp1: float
    t_dead: float
    tp2: float
    truncated: bool = False


@dataclass
class Levels:
    vgs_low: float
    vgs_high: float
    vbus: float
    vds_on: float
    vds_off: float
    id_base_pre: float
    id_base_dead: float
    i_off: float
    i_load_on: float


@dataclass
class Config:
    smooth_ns: float = VGS_SMOOTH_NS
    edge_hyst: float = EDGE_HYST_FRAC
    min_pulse_ns: float = MIN_PULSE_NS
    min_dead_ns: float = MIN_DEAD_NS
    deskew_id_ns: float = DESKEW_ID_NS
    auto_zero: bool = AUTO_ZERO_BASELINE
    window_mode: str = WINDOW_MODE
    window_pre_ns: float = WINDOW_PRE_NS
    window_post_ns: float = WINDOW_POST_NS
    rogowski: bool = ENABLE_ROGOWSKI_COMP
    rogowski_preset: str = ROGOWSKI_PRESET
    rogowski_tau_us: float | None = None
    rogowski_gain: float | None = None
    plot: bool = True
    show: bool = PLOT_SHOW
    out_dir: Path = Path(OUTPUT_DIR)
    export_csv: Path | None = None
    export_metrics: Path | None = None
    verbose: bool = False


def _odd(n: int) -> int:
    """把移动平均点数变成奇数（保证窗口对称）。"""
    n = max(3, int(round(n)))
    return n if n % 2 == 1 else n + 1


def moving_average(y: np.ndarray, n: int) -> np.ndarray:
    """edge padding 的移动平均，避免首尾被零填充拉出假边沿。"""
    n = _odd(n)
    p = n // 2
    y_pad = np.pad(np.asarray(y, dtype=float), p, mode="edge")
    return np.convolve(y_pad, np.ones(n) / n, mode="valid")


def apply_deskew(t: np.ndarray, y: np.ndarray, skew_ns: float) -> np.ndarray:
    """把电流波形平移 skew_ns：正值左移（提前），负值右移（延后）。"""
    if abs(skew_ns) < 1e-9:
        return y.copy()
    return np.interp(t, t + skew_ns * 1e-9, y)


def find_crossing(
    t: np.ndarray,
    y: np.ndarray,
    level: float,
    direction: str = "rising",
    t_min: float | None = None,
    t_max: float | None = None,
) -> float | None:
    """亚采样线性内插找阈值交点；找不到返回 None（不再把 NaN 传下去）。"""
    mask = np.ones_like(t, dtype=bool)
    if t_min is not None:
        mask &= t >= t_min
    if t_max is not None:
        mask &= t <= t_max
    ts, ys = t[mask], y[mask]
    if len(ts) < 2:
        return None
    if direction == "rising":
        idx = np.where((ys[:-1] < level) & (ys[1:] >= level))[0]
    else:
        idx = np.where((ys[:-1] > level) & (ys[1:] <= level))[0]
    if len(idx) == 0:
        return None
    i = idx[0]
    denom = ys[i + 1] - ys[i]
    if abs(denom) < 1e-15:
        return float(ts[i])
    return float(ts[i] + (level - ys[i]) / denom * (ts[i + 1] - ts[i]))


def integrate_energy_uJ(
    t: np.ndarray,
    p: np.ndarray,
    t_start: float | None,
    t_end: float | None,
) -> tuple[float | None, np.ndarray | None]:
    """在 [t_start, t_end] 上对功率做高密度梯形积分，返回 (能量 uJ, 累计能量曲线)。"""
    if t_start is None or t_end is None:
        return None, None
    if not (np.isfinite(t_start) and np.isfinite(t_end)) or t_end <= t_start:
        return None, None
    t_start = max(float(t_start), float(t[0]))
    t_end = min(float(t_end), float(t[-1]))
    if t_end <= t_start:
        return None, None
    n = max(1000, int((t_end - t_start) / np.median(np.diff(t))) + 1)
    t_dense = np.linspace(t_start, t_end, n)
    p_dense = np.interp(t_dense, t, p)
    e_dense = cumulative_trapezoid(p_dense, t_dense, initial=0.0) * 1e6
    e_curve = np.zeros_like(t)
    m = (t >= t_start) & (t <= t_end)
    e_curve[m] = np.interp(t[m], t_dense, e_dense)
    e_curve[t > t_end] = e_dense[-1]
    return float(e_dense[-1]), e_curve


# ==============================================================================
# 2. CSV 解析与三通道对齐
# ==============================================================================

def parse_siglent_csv(path: Path) -> ChannelCsv:
    """解析鼎阳单通道 CSV：前 50 行找 Source / Second 表头。"""
    path = Path(path)
    if not path.exists():
        raise DptError(f"找不到文件：{path}")

    header_row = None
    source = path.stem
    meta: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for idx, line in enumerate(f):
            if idx >= 50:
                break
            parts = [p.strip() for p in line.strip().split(",")]
            if len(parts) >= 2:
                key = parts[0].lower()
                meta[parts[0]] = parts[1]
                if key == "source":
                    source = parts[1]
                elif key == "second":
                    header_row = idx
                    break
    if header_row is None:
        raise DptError(f"{path.name}：找不到 `Second,Value` 表头，可能不是鼎阳 CSV")

    df = pd.read_csv(path, skiprows=header_row, encoding="utf-8-sig")
    if df.shape[1] < 2:
        raise DptError(f"{path.name}：数据列不足（需要时间列 + 数值列）")
    t = df.iloc[:, 0].to_numpy(dtype=float)
    value = df.iloc[:, 1].to_numpy(dtype=float)

    # 少量 NaN 用线性插值补上；大量 NaN 说明导出有问题。
    bad = ~np.isfinite(value)
    if bad.any():
        if bad.mean() > 0.01 or bad[0] or bad[-1]:
            raise DptError(f"{path.name}：数值列有 {bad.sum()} 个无效点，无法可靠分析")
        good = np.arange(len(value))[~bad]
        value[bad] = np.interp(np.arange(len(value))[bad], good, value[~bad])

    unit = meta.get("Vertical Units", "") or meta.get("Vertical units", "")
    return ChannelCsv(time=t, value=value, source=source.upper(), unit=unit, meta=meta)


def _common_time_axis(channels: list[ChannelCsv], min_samples: int = 1000) -> tuple[np.ndarray, list[np.ndarray], list[str]]:
    """把三通道对齐到同一条均匀时间轴；必要时线性重采样。"""
    warnings: list[str] = []
    t0, t1 = channels[0].time, channels[0].time
    dt_ref = float(np.median(np.diff(t0)))
    same = True
    for ch in channels[1:]:
        if len(ch.time) != len(t0) or abs(np.median(np.diff(ch.time)) - dt_ref) > 1e-3 * abs(dt_ref):
            same = False
        if not np.allclose(ch.time, t0, rtol=0.0, atol=max(1e-12, abs(dt_ref) * 1e-3)):
            same = False

    if same:
        return t0, [ch.value for ch in channels], warnings

    start = max(float(ch.time[0]) for ch in channels)
    end = min(float(ch.time[-1]) for ch in channels)
    if end <= start:
        raise DptError("三份 CSV 的时间范围没有重叠，无法对齐")
    n = int((end - start) / abs(dt_ref)) + 1
    if n < min_samples:
        raise DptError(f"三份 CSV 的公共时间区间只有 {n} 点，少于 {min_samples} 点")
    t = np.linspace(start, end, n)
    vals = [np.interp(t, ch.time, ch.value) for ch in channels]
    warnings.append(
        f"三份 CSV 的时间轴/采样间隔不一致，已重采样到公共区间 "
        f"[{start*1e6:.3f}, {end*1e6:.3f}] us（{n} 点）"
    )
    return t, vals, warnings


def load_waveforms(paths: dict[str, Path], cfg: Config) -> DptData:
    """读取 C1/C2/C3，做极性、deskew、时间对齐和基本校验。"""
    channels = [parse_siglent_csv(paths[k]) for k in (CH_VGS, CH_ID, CH_VDS)]
    warnings: list[str] = []
    t, vals, more = _common_time_axis(channels)
    warnings.extend(more)
    vgs, i_d, vds = vals

    if INVERT_VGS:
        vgs = -vgs
    if INVERT_ID:
        i_d = -i_d
    if INVERT_VDS:
        vds = -vds
    if abs(cfg.deskew_id_ns) > 1e-9:
        i_d = apply_deskew(t, i_d, cfg.deskew_id_ns)
        warnings.append(f"ID 通道软件 deskew：{cfg.deskew_id_ns:+.1f} ns")

    dt = float(np.median(np.diff(t)))
    if dt <= 0:
        raise DptError("时间轴不是递增的，检查 CSV 第一列")
    if t.size < 100:
        raise DptError(f"采样点太少（{t.size} 点），至少需要 100 点")
    return DptData(t=t, vgs_raw=vgs, id_raw=i_d, vds_raw=vds, dt=dt, fs=1.0 / dt, warnings=warnings)


# ==============================================================================
# 3. Rogowski 数字补偿
# ==============================================================================

def _rogowski_params(cfg: Config) -> tuple[float, float]:
    preset = ROGOWSKI_PRESETS.get(cfg.rogowski_preset)
    if preset is None:
        raise DptError(f"未知的 Rogowski 预设：{cfg.rogowski_preset}；可选 {list(ROGOWSKI_PRESETS)}")
    tau_us = cfg.rogowski_tau_us if cfg.rogowski_tau_us is not None else preset["tau_us"]
    gain = cfg.rogowski_gain if cfg.rogowski_gain is not None else preset["droop_gain"]
    return float(tau_us), float(gain)


def compensate_rogowski(t: np.ndarray, i_raw: np.ndarray, cfg: Config) -> tuple[np.ndarray, list[str]]:
    """
    一阶零极点补偿：H(s) = 1 - g·sτ/(1+sτ)。
    用双线性变换离散，再用 lfilter 实现；返回补偿后的电流和提示信息。
    """
    warnings: list[str] = []
    if not cfg.rogowski:
        return i_raw.copy(), warnings
    tau_us, gain = _rogowski_params(cfg)
    if tau_us <= 0 or gain <= 0:
        warnings.append("Rogowski 补偿参数无效（tau/gain <= 0），已跳过")
        return i_raw.copy(), warnings

    tau = tau_us * 1e-6
    fs = 1.0 / float(np.median(np.diff(t)))
    # H(s) = ((1-g)·τ·s + 1) / (τ·s + 1)
    b, a = bilinear([(1.0 - gain) * tau, 1.0], [tau, 1.0], fs)
    zi = lfilter_zi(b, a) * i_raw[0]
    i_comp, _ = lfilter(b, a, i_raw, zi=zi)
    if not np.all(np.isfinite(i_comp)):
        raise DptError("Rogowski 补偿后出现 NaN/Inf，检查 tau/gain 或采样率")
    limit = 5.0 * max(float(np.max(np.abs(i_raw))), 1e-9)
    if np.max(np.abs(i_comp - i_raw)) > limit:
        warnings.append("Rogowski 补偿改动量异常大（>5×原始幅值），建议检查预设")
    warnings.append(
        f"Rogowski 补偿已开启：{cfg.rogowski_preset}（tau={tau_us:.2f} us, gain={gain:.2f}）"
    )
    return i_comp, warnings


# ==============================================================================
# 4. 双脉冲边沿识别
# ==============================================================================

def _interp_mid(t: np.ndarray, y: np.ndarray, i_left: int, i_right: int, level: float) -> float:
    """在相邻两点间线性插值出 50% 交点。"""
    denom = y[i_right] - y[i_left]
    if abs(denom) < 1e-15:
        return float(t[i_left])
    ratio = (level - y[i_left]) / denom
    return float(t[i_left] + ratio * (t[i_right] - t[i_left]))


def detect_pulses(t: np.ndarray, vgs: np.ndarray, cfg: Config) -> tuple[PulseTiming, list[str]]:
    """平滑 + 迟滞 + 最小脉宽配对，稳健找出双脉冲的 4 个边沿。"""
    warnings: list[str] = []
    n_smooth = _odd(round(cfg.smooth_ns * 1e-9 / float(np.median(np.diff(t)))))
    ys = moving_average(vgs, n_smooth)
    low = float(np.percentile(ys, 5))
    high = float(np.percentile(ys, 95))

    if high - low < MIN_EDGE_SWING_V:
        raise DptError(
            f"VGS 高低差只有 {high - low:.3f} V（< {MIN_EDGE_SWING_V} V），"
            "看不到有效驱动脉冲；检查通道映射/探头。"
        )

    mid = 0.5 * (low + high)
    span = high - low
    hi_thr = mid + cfg.edge_hyst * span
    lo_thr = mid - cfg.edge_hyst * span

    state = 1 if ys[0] >= mid else 0
    if state == 1:
        warnings.append("记录开始时 VGS 已经为高，第一脉冲可能不完整")

    edges: list[tuple[str, float]] = []
    for i in range(1, len(ys)):
        if state == 0 and ys[i] >= hi_thr:
            j = i - 1
            while j > 0 and ys[j] > mid:
                j -= 1
            edges.append(("R", _interp_mid(t, ys, j, j + 1, mid)))
            state = 1
        elif state == 1 and ys[i] <= lo_thr:
            j = i - 1
            while j > 0 and ys[j] < mid:
                j -= 1
            edges.append(("F", _interp_mid(t, ys, j, j + 1, mid)))
            state = 0

    # 配对：上升沿 + 下降沿 = 一个脉冲；太窄的当振铃丢掉。
    pulses: list[tuple[float, float, bool]] = []
    pending: float | None = None
    for kind, tc in edges:
        if kind == "R":
            if pending is not None:
                warnings.append("发现未配对的上升沿，保留最新一个")
            pending = tc
        else:
            if pending is None:
                warnings.append("发现无配对上升沿的下降沿，忽略")
                continue
            width = tc - pending
            if width >= cfg.min_pulse_ns * 1e-9:
                pulses.append((pending, tc, False))
            else:
                warnings.append(f"丢弃宽度 {width*1e9:.1f} ns 的疑似振铃")
            pending = None

    if pending is not None and ALLOW_TRUNCATED_SECOND_PULSE and pulses:
        pulses.append((pending, float(t[-1]), True))
        warnings.append("记录结束时 VGS 仍为高，第二脉冲按截断处理（t_off2 = 记录终点）")

    if len(pulses) < 2:
        widths = ", ".join(f"{(b-a)*1e9:.0f}ns" for a, b, _ in pulses) or "无"
        raise DptError(
            f"只找到 {len(pulses)} 个有效脉冲（宽度：{widths}），需要 2 个。"
            f"可尝试 --smooth-ns {max(2, cfg.smooth_ns/2):.0f}、"
            f"--min-pulse-ns {max(20, cfg.min_pulse_ns/4):.0f}，"
            "或手工指定 --t-on1-us 等四个时间。"
        )

    if len(pulses) > 2:
        warnings.append(f"找到 {len(pulses)} 个有效脉冲，只取前两个")
    p1, p2 = pulses[0], pulses[1]
    t_on1, t_off1, _ = p1
    t_on2, t_off2, truncated = p2
    tp1, t_dead, tp2 = t_off1 - t_on1, t_on2 - t_off1, t_off2 - t_on2

    if not (t_on1 < t_off1 < t_on2 < t_off2):
        raise DptError("识别到的脉冲顺序不对（要求 t_on1 < t_off1 < t_on2 < t_off2）")
    if tp1 < cfg.min_pulse_ns * 1e-9 or tp2 < cfg.min_pulse_ns * 1e-9:
        raise DptError(f"脉冲宽度过短（tp1={tp1*1e9:.0f} ns, tp2={tp2*1e9:.0f} ns）")
    if t_dead < cfg.min_dead_ns * 1e-9:
        raise DptError(
            f"两脉冲之间只有 {t_dead*1e9:.0f} ns 低电平（< {cfg.min_dead_ns:.0f} ns），"
            "可能是振铃被当成了第二个脉冲"
        )

    return PulseTiming(t_on1, t_off1, t_on2, t_off2, tp1, t_dead, tp2, truncated), warnings


def manual_timing(args, t: np.ndarray) -> PulseTiming | None:
    """四个 --t-*-us 都给齐时直接使用，跳过自动识别。"""
    vals = [args.t_on1_us, args.t_off1_us, args.t_on2_us, args.t_off2_us]
    if any(v is None for v in vals):
        return None
    t_on1, t_off1, t_on2, t_off2 = (float(v) * 1e-6 for v in vals)
    return PulseTiming(
        t_on1, t_off1, t_on2, t_off2,
        t_off1 - t_on1, t_on2 - t_off1, t_off2 - t_on2, False,
    )


# ==============================================================================
# 5. 比例窗口、电平与基线
# ==============================================================================

def _ratio_window(t0: float, t1: float, fracs: tuple[float, float]) -> tuple[float, float]:
    return t0 + fracs[0] * (t1 - t0), t0 + fracs[1] * (t1 - t0)


def _window_ok(t: np.ndarray, a: float, b: float, min_samples: int) -> bool:
    return b > a and int(np.count_nonzero((t >= a) & (t <= b))) >= min_samples


def _median_window(t: np.ndarray, y: np.ndarray, a: float, b: float) -> float | None:
    m = (t >= a) & (t <= b)
    if not m.any():
        return None
    return float(np.median(y[m]))


def _expand_backward(t: np.ndarray, a: float, b: float, min_samples: int) -> tuple[float, float]:
    """窗口点太少时向前扩展，保证至少 min_samples 个点。"""
    idx = np.where((t >= a) & (t <= b))[0]
    if len(idx) >= min_samples:
        return a, b
    start = max(0, idx[0] - (min_samples - len(idx))) if len(idx) else 0
    return float(t[start]), b


def compute_levels(data: DptData, timing: PulseTiming, cfg: Config) -> tuple[Levels, list[str]]:
    """用比例窗口提取稳态电平；所有窗口都随实测脉宽缩放。"""
    t, vgs, i_d, vds = data.t, data.vgs_raw, data.id_raw, data.vds_raw
    warnings: list[str] = []

    a, b = _ratio_window(float(t[0]), timing.t_on1, WIN_PRE_QUIET)
    a, b = _expand_backward(t, a, b, WINDOW_MIN_SAMPLES)
    vgs_low = _median_window(t, vgs, a, b)
    vbus = _median_window(t, vds, a, b)
    id_base_pre = _median_window(t, i_d, a, b)

    a, b = _ratio_window(timing.t_on1, timing.t_off1, WIN_PULSE1_MID)
    vgs_high = _median_window(t, vgs, a, b)
    vds_on = _median_window(t, vds, a, b)

    a, b = _ratio_window(timing.t_off1, timing.t_on2, WIN_DEAD_LATE)
    vds_off = _median_window(t, vds, a, b)
    id_base_dead = _median_window(t, i_d, a, b)

    a, b = _ratio_window(timing.t_on1, timing.t_off1, WIN_PULSE1_END)
    a, b = _expand_backward(t, a, b, WINDOW_MIN_SAMPLES)
    i_off = _median_window(t, i_d, a, b)

    a, b = _ratio_window(timing.t_on2, timing.t_off2, WIN_PULSE2_EARLY)
    a, b = _expand_backward(t, a, b, WINDOW_MIN_SAMPLES)
    i_load_on = _median_window(t, i_d, a, b)

    missing = [name for name, val in (
        ("VGS 低电平", vgs_low), ("VGS 高电平", vgs_high),
        ("Vbus", vbus), ("VDS 导通压降", vds_on), ("VDS 续流平台", vds_off),
        ("ID 第一脉冲零偏", id_base_pre), ("ID 死区零偏", id_base_dead),
        ("I_off", i_off), ("I_load_on", i_load_on),
    ) if val is None]
    if missing:
        raise DptError(f"以下电平的窗口内没有采样点：{', '.join(missing)}")

    if vgs_high - vgs_low < MIN_EDGE_SWING_V:
        raise DptError("VGS 高电平与低电平几乎相同，检查通道顺序/探头")
    if vds_off - vds_on < 1.0:
        raise DptError("VDS 关断平台与导通压降差太小，检查 CH3 是否接反")

    # I_off 用第一脉冲前段的零偏；I_load_on 用死区零偏。
    # 关闭 AUTO_ZERO_BASELINE 时，零偏强制为 0（保留 VDS 的导通压降归零，
    # 否则开关损耗积分会把 Rds(on) 的直流压降算进去）。
    vgs_zero = vgs_low if cfg.auto_zero else 0.0
    id_zero_pre = id_base_pre if cfg.auto_zero else 0.0
    id_zero_dead = id_base_dead if cfg.auto_zero else 0.0
    i_off_cal = i_off - id_zero_pre
    i_load_cal = i_load_on - id_zero_dead
    if i_off_cal <= 0:
        raise DptError(f"关断电流算出来是 {i_off_cal:.2f} A，检查 ID 极性（可设 INVERT_ID=True）")
    if i_load_cal <= 0:
        warnings.append(f"第二脉冲恢复后的电流只有 {i_load_cal:.2f} A，Qrr 基线可能不可靠")

    return Levels(
        vgs_low=vgs_zero, vgs_high=vgs_high, vbus=vbus, vds_on=vds_on, vds_off=vds_off,
        id_base_pre=id_zero_pre, id_base_dead=id_zero_dead,
        i_off=i_off_cal, i_load_on=i_load_cal,
    ), warnings


# ==============================================================================
# 6. 开关瞬态与损耗
# ==============================================================================

def _auto_window(pre: float, post: float, timing: PulseTiming, cfg: Config) -> tuple[float, float]:
    """auto：用实测开关时间定宽，并限制在相邻区间内。"""
    limit = min(timing.tp1, timing.t_dead, timing.tp2)
    pre_min = WINDOW_AUTO_MIN_NS * 1e-9
    pre_out = min(max(pre, pre_min), WINDOW_AUTO_MAX_FRAC * limit)
    post_out = min(max(post, max(2.0 * pre_out, 40e-9)), WINDOW_AUTO_MAX_FRAC * limit)
    return pre_out, post_out


def compute_transient(
    data: DptData,
    timing: PulseTiming,
    levels: Levels,
    pre: float,
    post: float,
) -> tuple[dict, dict]:
    """计算关断/开通两组交叉点、峰值、损耗和电流斜率。"""
    t, vgs, i_d, vds = data.t, data.vgs_raw, data.id_raw, data.vds_raw
    vgs_cal = vgs - levels.vgs_low
    vds_cal = vds - levels.vds_on
    id_off = i_d - levels.id_base_pre
    id_on = i_d - levels.id_base_dead
    vgs_amp = levels.vgs_high - levels.vgs_low
    vds_amp = levels.vds_off - levels.vds_on

    m_off = (t >= timing.t_off1 - pre) & (t <= timing.t_off1 + post)
    m_on = (t >= timing.t_on2 - pre) & (t <= timing.t_on2 + post)
    tw_off, vg_off, vd_off, idc_off = t[m_off], vgs_cal[m_off], vds_cal[m_off], id_off[m_off]
    tw_on, vg_on, vd_on, idc_on = t[m_on], vgs_cal[m_on], vds_cal[m_on], id_on[m_on]

    out: dict = {}
    ctx: dict = {
        "pre": pre, "post": post,
        "tw_off": tw_off, "vg_off": vg_off, "vd_off": vd_off, "id_off": idc_off,
        "tw_on": tw_on, "vg_on": vg_on, "vd_on": vd_on, "id_on": idc_on,
        "vgs_amp": vgs_amp, "vds_amp": vds_amp,
    }

    # ---------------- 第一脉冲关断 ----------------
    t_vgs_90 = find_crossing(tw_off, vg_off, TH_TIME["vgs_off_start"] * vgs_amp, "falling")
    t_id_90 = find_crossing(tw_off, idc_off, TH_TIME["id_off_start"] * levels.i_off, "falling", t_min=t_vgs_90)
    t_id_10 = find_crossing(tw_off, idc_off, TH_TIME["id_off_end"] * levels.i_off, "falling", t_min=t_id_90)
    t_vds_10 = find_crossing(tw_off, vd_off, TH_TIME["vds_off_start"] * vds_amp, "rising", t_min=t_vgs_90)
    t_vds_90 = find_crossing(tw_off, vd_off, TH_TIME["vds_off_end"] * vds_amp, "rising", t_min=t_vds_10)

    out.update({
        "t_vgs_90_off": t_vgs_90, "t_id_90_off": t_id_90, "t_id_10_off": t_id_10,
        "t_vds_10_off": t_vds_10, "t_vds_90_off": t_vds_90,
    })
    out["tdoff_ns"] = (t_id_90 - t_vgs_90) * 1e9 if t_id_90 is not None and t_vgs_90 is not None else None
    out["tf_ns"] = (t_id_10 - t_id_90) * 1e9 if t_id_10 is not None and t_id_90 is not None else None
    out["tdvoff_ns"] = (t_vds_10 - t_vgs_90) * 1e9 if t_vds_10 is not None and t_vgs_90 is not None else None
    out["tvf_ns"] = (t_vds_90 - t_vds_10) * 1e9 if t_vds_90 is not None and t_vds_10 is not None else None

    out["didt_off_A_ns"] = (
        (TH_TIME["id_off_start"] - TH_TIME["id_off_end"]) * levels.i_off / out["tf_ns"]
        if out["tf_ns"] and out["tf_ns"] > 0 else None
    )
    out["dvdt_off_V_ns"] = (
        (TH_TIME["vds_off_end"] - TH_TIME["vds_off_start"]) * vds_amp / out["tvf_ns"]
        if out["tvf_ns"] and out["tvf_ns"] > 0 else None
    )

    # Vpeak 用原始 VDS（绝对值），避免零点校准影响过冲读数。
    out["vpeak_V"] = float(np.max(vds[m_off]))
    out["vpeak_over_V"] = out["vpeak_V"] - levels.vbus
    out["t_vpeak"] = float(tw_off[int(np.argmax(vds[m_off]))])

    t_eoff_end = find_crossing(
        tw_off, idc_off, TH_LOSS["eoff_end_id"] * levels.i_off, "falling", t_min=t_id_90
    )
    t_eoff_vgs = find_crossing(
        tw_off, vg_off, TH_LOSS["eoff_start_pct"] * vgs_amp, "falling"
    ) if TH_LOSS["eoff_start_ref"].upper() == "VGS" else None
    t_eoff_vds = find_crossing(
        tw_off, vd_off, TH_LOSS["eoff_start_pct"] * vds_amp, "rising", t_min=t_vgs_90
    ) if TH_LOSS["eoff_start_ref"].upper() == "VDS" else None
    t_eoff_s = t_eoff_vgs if t_eoff_vgs is not None else t_eoff_vds
    p_off = vd_off * idc_off
    eoff, eoff_curve = integrate_energy_uJ(tw_off, p_off, t_eoff_s, t_eoff_end)
    eoff_vgs, _ = integrate_energy_uJ(
        tw_off, p_off,
        find_crossing(tw_off, vg_off, TH_TIME["vgs_off_start"] * vgs_amp, "falling"),
        t_eoff_end,
    )
    eoff_vds, _ = integrate_energy_uJ(
        tw_off, p_off,
        find_crossing(tw_off, vd_off, TH_TIME["vds_off_start"] * vds_amp, "rising", t_min=t_vgs_90),
        t_eoff_end,
    )
    out.update({
        "eoff_uJ": eoff, "eoff_vgs_uJ": eoff_vgs, "eoff_vds_uJ": eoff_vds,
        "t_eoff_s": t_eoff_s, "t_eoff_end": t_eoff_end,
    })
    ctx["eoff_curve"] = eoff_curve

    # ---------------- 第二脉冲开通 ----------------
    i_load = levels.i_off          # 物理负载电流：第一脉冲关断时的电流
    t_vgs_10 = find_crossing(tw_on, vg_on, TH_TIME["vgs_on_start"] * vgs_amp, "rising")
    t_id_10 = find_crossing(tw_on, idc_on, TH_TIME["id_on_start"] * i_load, "rising", t_min=t_vgs_10)
    t_id_90 = find_crossing(tw_on, idc_on, TH_TIME["id_on_end"] * i_load, "rising", t_min=t_id_10)
    t_vds_90 = find_crossing(tw_on, vd_on, TH_TIME["vds_on_start"] * vds_amp, "falling", t_min=t_vgs_10)
    t_vds_10 = find_crossing(tw_on, vd_on, TH_TIME["vds_on_end"] * vds_amp, "falling", t_min=t_vds_90)

    out.update({
        "t_vgs_10_on": t_vgs_10, "t_id_10_on": t_id_10, "t_id_90_on": t_id_90,
        "t_vds_90_on": t_vds_90, "t_vds_10_on": t_vds_10,
    })
    out["tdon_ns"] = (t_id_10 - t_vgs_10) * 1e9 if t_id_10 is not None and t_vgs_10 is not None else None
    out["tr_ns"] = (t_id_90 - t_id_10) * 1e9 if t_id_90 is not None and t_id_10 is not None else None
    out["tdvon_ns"] = (t_vds_90 - t_vgs_10) * 1e9 if t_vds_90 is not None and t_vgs_10 is not None else None
    out["trv_ns"] = (t_vds_10 - t_vds_90) * 1e9 if t_vds_10 is not None and t_vds_90 is not None else None

    out["didt_on_A_ns"] = (
        (TH_TIME["id_on_end"] - TH_TIME["id_on_start"]) * i_load / out["tr_ns"]
        if out["tr_ns"] and out["tr_ns"] > 0 else None
    )
    out["dvdt_on_V_ns"] = (
        (TH_TIME["vds_on_start"] - TH_TIME["vds_on_end"]) * vds_amp / out["trv_ns"]
        if out["trv_ns"] and out["trv_ns"] > 0 else None
    )

    # Ipeak 只在第二开通后的短窗口里找，避免把后面电感电流的线性上升当成 IRM。
    irm_end = timing.t_on2 + min(IRM_MAX_FRAC * timing.tp2, IRM_MAX_US * 1e-6)
    m_ipk = (t >= timing.t_on2) & (t <= irm_end)
    if int(m_ipk.sum()) < 2:
        m_ipk = m_on
    out["ipeak_A"] = float(np.max(i_d[m_ipk]))
    out["irm_A"] = out["ipeak_A"] - levels.id_base_pre - levels.i_off
    out["irm_plat_A"] = out["ipeak_A"] - (levels.i_load_on + levels.id_base_dead)
    out["t_ipeak"] = float(t[m_ipk][int(np.argmax(i_d[m_ipk]))])
    ctx["irm_end"] = irm_end

    t_eon_end = find_crossing(
        tw_on, vd_on, TH_LOSS["eon_end_vds"] * vds_amp, "falling", t_min=t_vds_90
    )
    # 注意：这里直接用已经求出的 t_id_10，不能再次搜索“10% 上升交点”，否则会返回 None。
    if TH_LOSS["eon_start_ref"].upper() == "ID":
        t_eon_s = t_id_10
    else:
        t_eon_s = find_crossing(tw_on, vg_on, TH_LOSS["eon_start_pct"] * vgs_amp, "rising")
    p_on = vd_on * idc_on
    eon, eon_curve = integrate_energy_uJ(tw_on, p_on, t_eon_s, t_eon_end)
    eon_id, _ = integrate_energy_uJ(tw_on, p_on, t_id_10, t_eon_end)
    eon_vgs, _ = integrate_energy_uJ(
        tw_on, p_on,
        find_crossing(tw_on, vg_on, TH_TIME["vgs_on_start"] * vgs_amp, "rising"),
        t_eon_end,
    )
    out.update({
        "eon_uJ": eon, "eon_id_uJ": eon_id, "eon_vgs_uJ": eon_vgs,
        "t_eon_s": t_eon_s, "t_eon_end": t_eon_end,
    })
    ctx["eon_curve"] = eon_curve

    out["etotal_uJ"] = (
        out["eon_uJ"] + out["eoff_uJ"]
        if out["eon_uJ"] is not None and out["eoff_uJ"] is not None else None
    )
    return out, ctx


def estimate_auto_window(data: DptData, timing: PulseTiming, levels: Levels, cfg: Config) -> tuple[float, float, list[str]]:
    """两遍测量：先用粗窗口估开关时间，再按 3×/5× 开关时间定最终窗口。"""
    warnings: list[str] = []
    if cfg.window_mode == "manual":
        return cfg.window_pre_ns * 1e-9, cfg.window_post_ns * 1e-9, warnings

    coarse = max(20e-9, 0.05 * min(timing.tp1, timing.t_dead, timing.tp2))
    rough, _ = compute_transient(data, timing, levels, coarse, 2.0 * coarse)
    candidates = [
        abs(rough.get(k)) for k in ("tr_ns", "tf_ns", "trv_ns", "tvf_ns")
        if rough.get(k) is not None and np.isfinite(rough[k])
    ]
    t_sw = max(candidates) * 1e-9 if candidates else 0.02 * min(timing.tp1, timing.tp2)
    pre, post = _auto_window(
        max(WINDOW_AUTO_MIN_NS * 1e-9, WINDOW_AUTO_PRE_FACTOR * t_sw),
        max(WINDOW_AUTO_MIN_NS * 1e-9, WINDOW_AUTO_POST_FACTOR * t_sw),
        timing, cfg,
    )
    return pre, post, warnings


# ==============================================================================
# 7. 新增指标：L_load / L_loop / Qrr
# ==============================================================================

def fit_ramp(t: np.ndarray, y: np.ndarray, a: float, b: float) -> tuple[float, float, float] | None:
    """在 [a,b] 内对 y(t) 做一次线性拟合，返回 (斜率 A/s, 截距 A, R²)。"""
    m = (t >= a) & (t <= b)
    if int(m.sum()) < 10:
        return None
    ts, ys = t[m], y[m]
    slope, intercept = np.polyfit(ts, ys, 1)
    pred = slope * ts + intercept
    ss_res = float(np.sum((ys - pred) ** 2))
    ss_tot = float(np.sum((ys - np.mean(ys)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-15 else 0.0
    return float(slope), float(intercept), r2


def estimate_l_load(t: np.ndarray, id_off: np.ndarray, timing: PulseTiming, levels: Levels) -> tuple[float | None, float | None]:
    """L_load = V_L / (dI/dt)；V_L 用 Vbus - VDS_on，拟合窗口取第一脉冲 20%~80%。"""
    a, b = _ratio_window(timing.t_on1, timing.t_off1, WIN_PULSE1_RAMP)
    fit = fit_ramp(t, id_off, a, b)
    if fit is None:
        return None, None
    slope, _intercept, r2 = fit
    if slope <= 0:
        return None, r2
    v_l = levels.vbus - levels.vds_on
    return float(v_l / slope), r2


def estimate_qrr(
    t: np.ndarray,
    id_on: np.ndarray,
    timing: PulseTiming,
    levels: Levels,
    cfg: Config,
) -> tuple[float | None, float | None, float | None, bool]:
    """
    Qrr = ∫ max(ID - I_plateau, 0) dt，从第二开通到恢复结束。
    返回 (Qrr nC, 恢复结束时刻, 峰值时刻, 是否被窗口截断)。
    """
    base = levels.i_load_on
    band = max(QRR_BAND_ABS_A, QRR_BAND_REL * abs(base))
    t_end_limit = timing.t_on2 + min(QRR_MAX_FRAC * timing.tp2, QRR_MAX_US * 1e-6)
    m = (t >= timing.t_on2) & (t <= t_end_limit)
    if int(m.sum()) < 10:
        return None, None, None, True
    tt, yy = t[m], id_on[m]
    dev = yy - base
    ipk_rel = int(np.argmax(dev))
    t_peak = float(tt[ipk_rel])
    if dev[ipk_rel] <= band:
        return 0.0, t_peak, t_peak, False

    bad = np.abs(dev) > band
    after = np.where(bad & (tt > t_peak))[0]
    if len(after) == 0:
        t_rr_end = t_peak + QRR_SETTLE_NS * 1e-9
        truncated = False
    else:
        t_rr_end = float(tt[after[-1]] + QRR_SETTLE_NS * 1e-9)
        truncated = bool(tt[after[-1]] >= t_end_limit - 2 * np.median(np.diff(t)))
    t_rr_end = min(t_rr_end, float(tt[-1]))

    m_int = (t >= timing.t_on2) & (t <= t_rr_end)
    if int(m_int.sum()) < 2:
        return None, t_rr_end, t_peak, truncated
    q_c = float(trapezoid(np.maximum(id_on[m_int] - base, 0.0), t[m_int]))
    return q_c * 1e9, t_rr_end, t_peak, truncated


# ==============================================================================
# 8. 汇总计算
# ==============================================================================

def analyze(data: DptData, timing: PulseTiming, cfg: Config) -> tuple[dict, dict, Levels, list[str]]:
    warnings = list(data.warnings)
    levels, w = compute_levels(data, timing, cfg)
    warnings.extend(w)

    pre, post, w = estimate_auto_window(data, timing, levels, cfg)
    warnings.extend(w)
    metrics, ctx = compute_transient(data, timing, levels, pre, post)

    id_off = data.id_raw - levels.id_base_pre
    id_on = data.id_raw - levels.id_base_dead
    l_load, r2 = estimate_l_load(data.t, id_off, timing, levels)
    if l_load is not None and r2 is not None and r2 < L_LOAD_R2_MIN:
        warnings.append(f"L_load 拟合 R²={r2:.4f} < {L_LOAD_R2_MIN}，结果仅供参考")

    didt = metrics.get("didt_off_A_ns")
    overshoot = metrics.get("vpeak_over_V")
    l_loop = (overshoot / didt) if (didt and didt > 0 and overshoot is not None) else None
    if overshoot is not None and overshoot <= 0:
        warnings.append("没有测到 VDS 过冲（Vpeak <= Vbus），L_loop 记为 0")
        l_loop = 0.0

    qrr, t_rr_end, t_qpeak, qrr_trunc = estimate_qrr(data.t, id_on, timing, levels, cfg)
    if qrr_trunc:
        warnings.append("Qrr 恢复过程在搜索窗口末端仍未结束，Qrr 只作下限参考")

    # 自动窗口如果刚好切到峰值，扩大一次 post 后重算。
    if metrics.get("t_vpeak") is not None and abs(metrics["t_vpeak"] - (timing.t_off1 + post)) < 3 * data.dt:
        warnings.append("Vpeak 落在窗口边界，已自动扩大 post 窗口")
        metrics, ctx = compute_transient(data, timing, levels, pre, post * 1.5)
        overshoot = metrics.get("vpeak_over_V")
        didt = metrics.get("didt_off_A_ns")
        l_loop = (overshoot / didt) if (didt and didt > 0 and overshoot is not None) else None
    if metrics.get("t_ipeak") is not None and ctx.get("irm_end") is not None:
        if ctx["irm_end"] - metrics["t_ipeak"] < 3 * data.dt:
            warnings.append(
                "IRM 峰值落在搜索窗口边界，可能未完整捕获；可调大 IRM_MAX_FRAC / IRM_MAX_US"
            )

    metrics.update({
        "vbus_V": levels.vbus,
        "vgs_high_V": levels.vgs_high - levels.vgs_low,
        "vgs_low_V": levels.vgs_low,
        "vds_on_V": levels.vds_on,
        "vds_off_V": levels.vds_off,
        "i_off_A": levels.i_off,
        "i_load_on_A": levels.i_load_on,
        "l_load_uH": None if l_load is None else l_load * 1e6,
        "l_load_r2": r2,
        # V / (A/ns) = nH，所以这里不再乘 1e9。
        "l_loop_nH": l_loop,
        "qrr_nC": qrr,
        "t_rr_end": t_rr_end,
        "qrr_truncated": qrr_trunc,
        "pre_ns": ctx["pre"] * 1e9,
        "post_ns": ctx["post"] * 1e9,
    })
    return metrics, ctx, levels, warnings


# ==============================================================================
# 9. 报告与 Markdown 表
# ==============================================================================

def _v(m: dict, key: str, nd: int = 2) -> str:
    x = m.get(key)
    if x is None or not np.isfinite(x):
        return "N/A"
    return f"{x:.{nd}f}"


TABLE_ROWS = [
    # (中文名, 符号, 字典 key, 单位, 小数位)
    ("母线电压", "V_bus", "vbus_V", "V", 2),
    ("VGS 高电平", "V_GS,H", "vgs_high_V", "V", 2),
    ("第一脉冲关断电流", "I_off", "i_off_A", "A", 2),
    ("第一关断电压尖峰", "V_peak", "vpeak_V", "V", 2),
    ("电压过冲", "V_ov", "vpeak_over_V", "V", 2),
    ("第二开通电流峰值", "I_peak", "ipeak_A", "A", 2),
    ("反向恢复峰值电流", "I_RM", "irm_A", "A", 2),
    ("相对恢复平台的 IRM", "I_RM,plat", "irm_plat_A", "A", 2),
    ("负载电感", "L_load", "l_load_uH", "µH", 2),
    ("换流回路寄生电感", "L_loop", "l_loop_nH", "nH", 1),
    ("反向恢复电荷", "Q_rr", "qrr_nC", "nC", 0),
    ("关断 dI/dt (90%-10%)", "dI/dt_off", "didt_off_A_ns", "A/ns", 3),
    ("关断 dV/dt (10%-90%)", "dV/dt_off", "dvdt_off_V_ns", "V/ns", 3),
    ("开通 dI/dt (10%-90%)", "dI/dt_on", "didt_on_A_ns", "A/ns", 3),
    ("开通 dV/dt (90%-10%)", "dV/dt_on", "dvdt_on_V_ns", "V/ns", 3),
    ("tdon(VGS-ID)", "t_d(on)", "tdon_ns", "ns", 2),
    ("tr(ID)", "t_r", "tr_ns", "ns", 2),
    ("tdoff(VGS-ID)", "t_d(off)", "tdoff_ns", "ns", 2),
    ("tf(ID)", "t_f", "tf_ns", "ns", 2),
    ("tdvon(VGS-VDS)", "t_dv(on)", "tdvon_ns", "ns", 2),
    ("trv(VDS)", "t_rv", "trv_ns", "ns", 2),
    ("tdvoff(VGS-VDS)", "t_dv(off)", "tdvoff_ns", "ns", 2),
    ("tvf(VDS)", "t_vf", "tvf_ns", "ns", 2),
    ("关断损耗", "E_off", "eoff_uJ", "µJ", 3),
    ("开通损耗", "E_on", "eon_uJ", "µJ", 3),
    ("单次总损耗", "E_total", "etotal_uJ", "µJ", 3),
]


def print_report(m: dict, timing: PulseTiming, data: DptData, cfg: Config, paths: dict[str, Path], warnings: list[str]) -> None:
    print("\n" + "=" * 78)
    print(f"  {TEST_TITLE}")
    print(f"  {DEVICE_NAME}")
    print("=" * 78)
    print(f"  输入: C1={paths[CH_VGS].name}  C2={paths[CH_ID].name}  C3={paths[CH_VDS].name}")
    print(f"  采样: {len(data.t)} 点, dt={data.dt*1e9:.3f} ns, fs={data.fs/1e6:.1f} MSa/s")
    print(f"  脉冲: tp1={timing.tp1*1e6:.3f} us, 死区={timing.t_dead*1e6:.3f} us, tp2={timing.tp2*1e6:.3f} us"
          + ("  [第二脉冲截断]" if timing.truncated else ""))
    print(f"  窗口: {cfg.window_mode} (pre={m.get('pre_ns', 0):.1f} ns, post={m.get('post_ns', 0):.1f} ns)")
    print(f"  Deskew: 硬件 +{HARDWARE_DESKEW_NS:.0f} ns (已写入 CSV) + 软件 {cfg.deskew_id_ns:+.1f} ns")
    print("-" * 78)
    print(f"  Vbus={_v(m,'vbus_V')} V | VGS_high={_v(m,'vgs_high_V')} V | "
          f"VDS_on={_v(m,'vds_on_V')} V | VDS_off={_v(m,'vds_off_V')} V")
    print(f"  I_off={_v(m,'i_off_A')} A | I_load(on)={_v(m,'i_load_on_A')} A | "
          f"Vpeak={_v(m,'vpeak_V')} V (过冲 {_v(m,'vpeak_over_V')} V) | Ipeak={_v(m,'ipeak_A')} A")
    print(f"  IRM={_v(m,'irm_A')} A (相对恢复平台 {_v(m,'irm_plat_A')} A) | "
          f"Qrr={_v(m,'qrr_nC',0)} nC")
    print(f"  dI/dt(off)={_v(m,'didt_off_A_ns',3)} A/ns | dV/dt(off)={_v(m,'dvdt_off_V_ns',3)} V/ns | "
          f"dI/dt(on)={_v(m,'didt_on_A_ns',3)} A/ns | dV/dt(on)={_v(m,'dvdt_on_V_ns',3)} V/ns")
    print(f"  L_load={_v(m,'l_load_uH')} uH (R²={_v(m,'l_load_r2',4)}) | "
          f"L_loop={_v(m,'l_loop_nH',1)} nH")
    print("-" * 78)
    print(f"  tdon={_v(m,'tdon_ns')} ns | tr={_v(m,'tr_ns')} ns | "
          f"tdoff={_v(m,'tdoff_ns')} ns | tf={_v(m,'tf_ns')} ns")
    print(f"  tdvon={_v(m,'tdvon_ns')} ns | trv={_v(m,'trv_ns')} ns | "
          f"tdvoff={_v(m,'tdvoff_ns')} ns | tvf={_v(m,'tvf_ns')} ns")
    print(f"  Eoff={_v(m,'eoff_uJ',3)} uJ | Eon={_v(m,'eon_uJ',3)} uJ | "
          f"Etotal={_v(m,'etotal_uJ',3)} uJ")
    if warnings:
        print("-" * 78)
        print("  提示/警告:")
        for w in dict.fromkeys(warnings):
            print(f"    - {w}")
    print("=" * 78 + "\n")


def print_markdown(m: dict) -> None:
    if not MARKDOWN_TABLE:
        return
    print("--- 可直接粘贴到博客的 Markdown 表格 ---\n")
    print("| 参数 | 符号 | 数值 | 单位 |")
    print("|:---|:---|---:|:---|")
    for label, sym, key, unit, nd in TABLE_ROWS:
        print(f"| {label} | {sym} | {_v(m, key, nd)} | {unit} |")
    print(
        "\n> 口径：L_load 由第一脉冲 20%~80% 区间的 ID 线性拟合得到，"
        "V_L = Vbus − VDS_on；L_loop = (Vpeak − Vbus) / (dI/dt, 90%–10%)；"
        "Qrr 为第二开通后 ID 高出恢复平台的部分对时间的积分。\n"
    )


# ==============================================================================
# 10. CSV 导出
# ==============================================================================

def export_processed_csv(
    path: Path,
    data: DptData,
    timing: PulseTiming,
    levels: Levels,
    m: dict,
) -> None:
    """导出校准后的完整时域波形 + 两个开关窗口内的累计开关能量。"""
    t = data.t
    vgs = data.vgs_raw - levels.vgs_low
    vds = data.vds_raw - levels.vds_on
    id_off = data.id_raw - levels.id_base_pre
    id_on = data.id_raw - levels.id_base_dead

    # 死区里下管电流为 0，所以第二脉冲开始前用 pre 零偏，之后用死区零偏。
    i_d = np.where(t < timing.t_on2, id_off, id_on)
    p = vds * i_d

    # 累计开关能量：只在 Eoff/Eon 积分窗口里累加，其余时间保持不变。
    e_sw = np.zeros_like(t)
    e_acc = 0.0
    for key_s, key_e in (("t_eoff_s", "t_eoff_end"), ("t_eon_s", "t_eon_end")):
        t0, t1 = m.get(key_s), m.get(key_e)
        if t0 is None or t1 is None or t1 <= t0:
            continue
        seg = (t >= t0) & (t <= t1)
        if int(seg.sum()) >= 2:
            e_seg = cumulative_trapezoid(p[seg], t[seg], initial=0.0) * 1e6
            e_sw[seg] = e_acc + e_seg
            e_acc += float(e_seg[-1])
        e_sw[t > t1] = e_acc

    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.column_stack([t, vgs, i_d, vds, p, e_sw])
    np.savetxt(
        path, arr, delimiter=",", fmt="%.9e",
        header="Time_s,VGS_V,ID_A,VDS_V,P_W,E_sw_uJ",
        comments="",
    )
    print(f"已导出处理后的波形：{path}")


def export_metrics_csv(path: Path, m: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        f.write("Metric,Value,Unit\n")
        for label, sym, key, unit, nd in TABLE_ROWS:
            val = _v(m, key, nd)
            f.write(f"{label} ({sym}),{val},{unit}\n")
    print(f"已导出指标汇总：{path}")


# ==============================================================================
# 11. 绘图
# ==============================================================================

def plot_analysis(
    data: DptData,
    timing: PulseTiming,
    levels: Levels,
    m: dict,
    ctx: dict,
    cfg: Config,
) -> Path:
    import matplotlib
    if not cfg.show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(
        3, 2, figsize=(15, 9.5), sharex="col",
        gridspec_kw={"height_ratios": [1.0, 1.45, 1.25]},
    )
    fig.suptitle(
        f"{DEVICE_NAME} — {TEST_TITLE}\n"
        f"Vbus={_v(m,'vbus_V')} V | I_off={_v(m,'i_off_A')} A | Vpeak={_v(m,'vpeak_V')} V | "
        f"Ipeak={_v(m,'ipeak_A')} A | L_load={_v(m,'l_load_uH')} µH | "
        f"L_loop={_v(m,'l_loop_nH',1)} nH | Qrr={_v(m,'qrr_nC',0)} nC",
        fontsize=12.5, fontweight="bold", y=0.98,
    )

    # ---- 左栏：第一脉冲关断 ----
    t_off_ns = (ctx["tw_off"] - timing.t_off1) * 1e9
    ax0, ax1, ax2 = axes[0, 0], axes[1, 0], axes[2, 0]
    ax0.plot(t_off_ns, ctx["vg_off"], color="#D99B00", lw=2.0, label="$V_{GS}$")
    ax0.axhline(TH_TIME["vgs_off_start"] * ctx["vgs_amp"], color="#D99B00", ls=":", alpha=0.7, label="90% $V_{GS}$")
    if m.get("t_vgs_90_off") is not None:
        ax0.axvline((m["t_vgs_90_off"] - timing.t_off1) * 1e9, color="#D99B00", ls="--", alpha=0.6)
    ax0.set_title(
        f"First Pulse Turn-Off\n"
        f"$t_{{d(off)}}$={_v(m,'tdoff_ns')} ns, $t_f$={_v(m,'tf_ns')} ns | "
        f"$t_{{dv(off)}}$={_v(m,'tdvoff_ns')} ns, $t_{{vf}}$={_v(m,'tvf_ns')} ns",
        fontsize=10.5, fontweight="bold",
    )
    ax0.set_ylabel("$V_{GS}$ (V)", color="#B37700", fontweight="bold")
    ax0.grid(True, ls="--", alpha=0.35)
    ax0.legend(loc="upper right", fontsize=8.5)

    ax1_id = ax1.twinx()
    l_vds = ax1.plot(t_off_ns, ctx["vd_off"], color="#0088CC", lw=2.0, label="$V_{DS}$ (V)")
    l_id = ax1_id.plot(t_off_ns, ctx["id_off"], color="#D81B60", lw=2.0, label="$I_D$ (A)")
    if m.get("t_vpeak") is not None:
        xv = (m["t_vpeak"] - timing.t_off1) * 1e9
        yv = m["vpeak_V"] - levels.vds_on
        ax1.plot(xv, yv, "o", color="#0088CC")
        ax1.annotate(
            f"$V_{{peak}}$={_v(m,'vpeak_V')} V\n($dV/dt$={_v(m,'dvdt_off_V_ns',2)} V/ns)",
            xy=(xv, yv), xytext=(xv + 12, yv - 4),
            arrowprops=dict(arrowstyle="->", color="#0088CC", lw=1.2),
            fontsize=8.5, fontweight="bold", color="#005580",
        )
    if m.get("t_id_10_off") is not None:
        ax1_id.annotate(
            f"$dI/dt$=-{_v(m,'didt_off_A_ns',2)} A/ns",
            xy=((m["t_id_10_off"] - timing.t_off1) * 1e9, 0.45 * levels.i_off),
            xytext=((m["t_id_10_off"] - timing.t_off1) * 1e9 - 45, 0.45 * levels.i_off),
            arrowprops=dict(arrowstyle="->", color="#D81B60", lw=1.2),
            fontsize=8.5, fontweight="bold", color="#AD1457",
        )
    if m.get("t_eoff_s") is not None:
        ax1.axvline((m["t_eoff_s"] - timing.t_off1) * 1e9, color="#444444", ls="--", lw=1.1)
    if m.get("t_eoff_end") is not None:
        ax1.axvline((m["t_eoff_end"] - timing.t_off1) * 1e9, color="#444444", ls="--", lw=1.1)
    ax1.set_ylabel("$V_{DS}$ (V)", color="#0088CC", fontweight="bold")
    ax1_id.set_ylabel("$I_D$ (A)", color="#D81B60", fontweight="bold")
    ax1.grid(True, ls="--", alpha=0.35)
    ax1.legend(l_vds + l_id, [x.get_label() for x in l_vds + l_id], loc="center right", fontsize=8.5)

    ax2_e = ax2.twinx()
    p_off_kw = ctx["vd_off"] * ctx["id_off"] * 1e-3
    ax2.plot(t_off_ns, p_off_kw, color="#6A1B9A", lw=1.6, label="$P_{sw}(t)$ (kW)")
    if m.get("t_eoff_s") is not None and m.get("t_eoff_end") is not None:
        mask = (ctx["tw_off"] >= m["t_eoff_s"]) & (ctx["tw_off"] <= m["t_eoff_end"])
        ax2.fill_between(t_off_ns[mask], 0, p_off_kw[mask], color="#6A1B9A", alpha=0.22, label="JEDEC $E_{off}$ area")
    if ctx.get("eoff_curve") is not None:
        ax2_e.plot(t_off_ns, ctx["eoff_curve"], color="#2E7D32", lw=2.2, ls="-.",
                   label=f"$E_{{off}}$ = {_v(m,'eoff_uJ',2)} µJ")
    ax2.set_xlabel("Time relative to $V_{GS}$ 50% turn-off edge (ns)", fontweight="bold")
    ax2.set_ylabel("Power (kW)", color="#6A1B9A", fontweight="bold")
    ax2_e.set_ylabel("Energy (µJ)", color="#2E7D32", fontweight="bold")
    ax2.grid(True, ls="--", alpha=0.35)
    ax2_e.legend(loc="upper left", fontsize=8.5)

    # ---- 右栏：第二脉冲开通 ----
    t_on_ns = (ctx["tw_on"] - timing.t_on2) * 1e9
    bx0, bx1, bx2 = axes[0, 1], axes[1, 1], axes[2, 1]
    bx0.plot(t_on_ns, ctx["vg_on"], color="#D99B00", lw=2.0, label="$V_{GS}$")
    bx0.axhline(TH_TIME["vgs_on_start"] * ctx["vgs_amp"], color="#D99B00", ls=":", alpha=0.7, label="10% $V_{GS}$")
    if m.get("t_vgs_10_on") is not None:
        bx0.axvline((m["t_vgs_10_on"] - timing.t_on2) * 1e9, color="#D99B00", ls="--", alpha=0.6)
    bx0.set_title(
        f"Second Pulse Turn-On\n"
        f"$t_{{d(on)}}$={_v(m,'tdon_ns')} ns, $t_r$={_v(m,'tr_ns')} ns | "
        f"$t_{{dv(on)}}$={_v(m,'tdvon_ns')} ns, $t_{{rv}}$={_v(m,'trv_ns')} ns",
        fontsize=10.5, fontweight="bold",
    )
    bx0.set_ylabel("$V_{GS}$ (V)", color="#B37700", fontweight="bold")
    bx0.grid(True, ls="--", alpha=0.35)
    bx0.legend(loc="lower right", fontsize=8.5)

    bx1_id = bx1.twinx()
    l_vds_on = bx1.plot(t_on_ns, ctx["vd_on"], color="#0088CC", lw=2.0, label="$V_{DS}$ (V)")
    l_id_on = bx1_id.plot(t_on_ns, ctx["id_on"], color="#D81B60", lw=2.0, label="$I_D$ (A)")
    bx1_id.axhline(levels.i_off, color="#D81B60", ls=":", alpha=0.55, label=f"$I_{{off}}$={levels.i_off:.1f} A")
    if m.get("t_ipeak") is not None:
        xp = (m["t_ipeak"] - timing.t_on2) * 1e9
        yp = m["ipeak_A"] - levels.id_base_dead
        bx1_id.plot(xp, yp, "o", color="#D81B60")
        bx1_id.annotate(
            f"$I_{{peak}}$={_v(m,'ipeak_A')} A\n$I_{{RM}}$={_v(m,'irm_A')} A",
            xy=(xp, yp), xytext=(xp + 12, yp - 4),
            arrowprops=dict(arrowstyle="->", color="#D81B60", lw=1.2),
            fontsize=8.5, fontweight="bold", color="#AD1457",
        )
    if m.get("t_vds_10_on") is not None:
        bx1.annotate(
            f"$dV/dt$=-{_v(m,'dvdt_on_V_ns',2)} V/ns",
            xy=((m["t_vds_10_on"] - timing.t_on2) * 1e9, 0.35 * ctx["vds_amp"]),
            xytext=((m["t_vds_10_on"] - timing.t_on2) * 1e9 + 15, 0.45 * ctx["vds_amp"]),
            arrowprops=dict(arrowstyle="->", color="#0088CC", lw=1.2),
            fontsize=8.5, fontweight="bold", color="#005580",
        )
    if m.get("t_eon_s") is not None:
        bx1.axvline((m["t_eon_s"] - timing.t_on2) * 1e9, color="#444444", ls="--", lw=1.1)
    if m.get("t_eon_end") is not None:
        bx1.axvline((m["t_eon_end"] - timing.t_on2) * 1e9, color="#444444", ls="--", lw=1.1)
    bx1.set_ylabel("$V_{DS}$ (V)", color="#0088CC", fontweight="bold")
    bx1_id.set_ylabel("$I_D$ (A)", color="#D81B60", fontweight="bold")
    bx1.grid(True, ls="--", alpha=0.35)
    bx1.legend(l_vds_on + l_id_on, [x.get_label() for x in l_vds_on + l_id_on], loc="center right", fontsize=8.5)

    bx2_e = bx2.twinx()
    p_on_kw = ctx["vd_on"] * ctx["id_on"] * 1e-3
    bx2.plot(t_on_ns, p_on_kw, color="#6A1B9A", lw=1.6, label="$P_{sw}(t)$ (kW)")
    if m.get("t_eon_s") is not None and m.get("t_eon_end") is not None:
        mask = (ctx["tw_on"] >= m["t_eon_s"]) & (ctx["tw_on"] <= m["t_eon_end"])
        bx2.fill_between(t_on_ns[mask], 0, p_on_kw[mask], color="#6A1B9A", alpha=0.22, label="JEDEC $E_{on}$ area")
    if ctx.get("eon_curve") is not None:
        bx2_e.plot(t_on_ns, ctx["eon_curve"], color="#2E7D32", lw=2.2, ls="-.",
                   label=f"$E_{{on}}$ = {_v(m,'eon_uJ',2)} µJ")
    bx2.set_xlabel("Time relative to $V_{GS}$ 50% turn-on edge (ns)", fontweight="bold")
    bx2.set_ylabel("Power (kW)", color="#6A1B9A", fontweight="bold")
    bx2_e.set_ylabel("Energy (µJ)", color="#2E7D32", fontweight="bold")
    bx2.grid(True, ls="--", alpha=0.35)
    bx2_e.legend(loc="upper left", fontsize=8.5)

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    out = cfg.out_dir / OUTPUT_FIG_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=PLOT_DPI)
    if cfg.show:
        plt.show()
    plt.close(fig)
    print(f"已生成分析图：{out}")
    return out


# ==============================================================================
# 12. 命令行参数与主流程
# ==============================================================================

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="双脉冲测试（DPT）CSV 自动分析：开关时间、损耗、L_load、L_loop、Qrr",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python dpt_analyzer.py\n"
            "  python dpt_analyzer.py -c1 a_C1.csv -c2 a_C2.csv -c3 a_C3.csv\n"
            "  python dpt_analyzer.py --export-csv --export-metrics\n"
            "  python dpt_analyzer.py --rogowski HQRocoil-Mini\n"
            "  python dpt_analyzer.py --window manual --pre-ns 80 --post-ns 200 --no-show\n"
        ),
    )

    g_in = p.add_argument_group("输入文件")
    g_in.add_argument("-c1", "--c1", type=Path,
                      help="CH1 / VGS 的 CSV；省略时自动扫描 *_C1_*.csv 并推导 C2/C3")
    g_in.add_argument("-c2", "--c2", type=Path,
                      help="CH2 / ID 的 CSV（省略时由 C1 文件名推导）")
    g_in.add_argument("-c3", "--c3", type=Path,
                      help="CH3 / VDS 的 CSV（省略时由 C1 文件名推导）")
    g_in.add_argument("--data-dir", type=Path, default=Path(DEFAULT_DATA_DIR),
                      help=f"自动扫描目录（默认 {DEFAULT_DATA_DIR}）")

    g_edge = p.add_argument_group("分析窗口与边沿识别")
    g_edge.add_argument("--window", choices=("auto", "manual"), default=None,
                        help="窗口模式：auto 按实测开关时间自动定宽；manual 用 --pre-ns/--post-ns（默认 auto）")
    g_edge.add_argument("--pre-ns", type=float, default=None,
                        help="manual 模式的前窗，单位 ns（默认 60）")
    g_edge.add_argument("--post-ns", type=float, default=None,
                        help="manual 模式的后窗，单位 ns（默认 160）")
    g_edge.add_argument("--smooth-ns", type=float, default=None,
                        help="VGS 移动平均窗宽，单位 ns（默认 10）")
    g_edge.add_argument("--min-pulse-ns", type=float, default=None,
                        help="最小有效脉宽，单位 ns（默认 200）")
    g_edge.add_argument("--edge-hyst", type=float, default=None,
                        help="边沿迟滞比例，0~0.5（默认 0.10）")
    g_edge.add_argument("--deskew-id-ns", type=float, default=None,
                        help="ID 软件 deskew，单位 ns（默认 0）")
    g_edge.add_argument("--no-auto-zero", action="store_true",
                        help="关闭自动零偏校准（默认开启）")

    g_rog = p.add_argument_group("罗氏线圈补偿")
    g_rog.add_argument("--rogowski", nargs="?", const="__default__",
                       help="开启罗氏线圈补偿，可选预设名（不带值时用 HQRocoil-Mini）")
    g_rog.add_argument("--no-rogowski", action="store_true",
                       help="强制关闭罗氏线圈补偿（覆盖顶部配置）")
    g_rog.add_argument("--rogowski-tau-us", type=float,
                       help="临时覆盖预设里的时间常数，单位 us")
    g_rog.add_argument("--rogowski-gain", type=float,
                       help="临时覆盖预设里的高通失配增益")

    g_out = p.add_argument_group("输出")
    g_out.add_argument("--out-dir", type=Path, default=Path(OUTPUT_DIR),
                       help=f"图片和导出 CSV 的输出目录（默认 {OUTPUT_DIR}）")
    g_out.add_argument("--export-csv", nargs="?", const="__default__",
                       help=f"导出处理后的时域 CSV；不带路径时写 {DEFAULT_EXPORT_CSV}")
    g_out.add_argument("--export-metrics", nargs="?", const="__default__",
                       help=f"导出指标汇总 CSV；不带路径时写 {DEFAULT_EXPORT_METRICS}")
    g_out.add_argument("--no-plot", action="store_true", help="不生成分析图")
    g_out.add_argument("--no-show", action="store_true",
                       help="生成分析图但不弹窗（无头/服务器环境）")

    g_rep = p.add_argument_group("手工覆盖与报告")
    g_rep.add_argument("--t-on1-us", type=float,
                       help="手工指定第一脉冲开通时刻，单位 us；四个时刻给齐时跳过自动识别")
    g_rep.add_argument("--t-off1-us", type=float,
                       help="手工指定第一脉冲关断时刻，单位 us")
    g_rep.add_argument("--t-on2-us", type=float,
                       help="手工指定第二脉冲开通时刻，单位 us")
    g_rep.add_argument("--t-off2-us", type=float,
                       help="手工指定第二脉冲关断时刻，单位 us")
    g_rep.add_argument("--title", default=TEST_TITLE, help="报告和分析图标题")
    g_rep.add_argument("--device", default=DEVICE_NAME, help="被测器件描述，写进报告标题")
    g_rep.add_argument("--verbose", action="store_true", help="打印输入路径、点数等调试信息")
    return p


def build_config(args) -> Config:
    cfg = Config()
    if args.smooth_ns is not None:
        cfg.smooth_ns = args.smooth_ns
    if args.min_pulse_ns is not None:
        cfg.min_pulse_ns = args.min_pulse_ns
    if args.edge_hyst is not None:
        cfg.edge_hyst = args.edge_hyst
    if args.deskew_id_ns is not None:
        cfg.deskew_id_ns = args.deskew_id_ns
    if args.window is not None:
        cfg.window_mode = args.window
    if args.pre_ns is not None:
        cfg.window_pre_ns = args.pre_ns
    if args.post_ns is not None:
        cfg.window_post_ns = args.post_ns
    if args.no_auto_zero:
        cfg.auto_zero = False
    cfg.plot = not args.no_plot
    cfg.show = PLOT_SHOW and not args.no_show
    cfg.out_dir = args.out_dir
    cfg.verbose = args.verbose

    if args.no_rogowski:
        cfg.rogowski = False
    elif args.rogowski is not None:
        cfg.rogowski = True
        if args.rogowski != "__default__":
            cfg.rogowski_preset = args.rogowski
    cfg.rogowski_tau_us = args.rogowski_tau_us
    cfg.rogowski_gain = args.rogowski_gain

    if args.export_csv is not None:
        name = DEFAULT_EXPORT_CSV if args.export_csv == "__default__" else args.export_csv
        cfg.export_csv = cfg.out_dir / name
    if args.export_metrics is not None:
        name = DEFAULT_EXPORT_METRICS if args.export_metrics == "__default__" else args.export_metrics
        cfg.export_metrics = cfg.out_dir / name
    return cfg


def resolve_input_paths(args, cfg: Config) -> dict[str, Path]:
    """解析 -c1/-c2/-c3；缺省时自动扫描 *_C1_*.csv 并推导 C2/C3。"""
    data_dir = Path(args.data_dir)
    c1, c2, c3 = args.c1, args.c2, args.c3

    if c1 is None:
        candidates = sorted(data_dir.glob(CSV_GLOB_C1), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            raise DptError(
                f"在 {data_dir.resolve()} 下找不到 {CSV_GLOB_C1}。"
                "请用 -c1/-c2/-c3 指定，或把三份 CSV 放在当前目录。"
            )
        c1 = candidates[0]
        if len(candidates) > 1:
            print(f"[提示] 找到 {len(candidates)} 个 C1 文件，使用最新的 {c1.name}")

    def derive(base: Path, from_tag: str, to_tag: str) -> Path | None:
        name = base.name
        for a, b in ((f"_{from_tag}_", f"_{to_tag}_"), (f"{from_tag}-", f"{to_tag}-")):
            if a in name:
                cand = base.with_name(name.replace(a, b))
                if cand.exists():
                    return cand
        hits = sorted(base.parent.glob(f"*_{to_tag}_*.csv"))
        return hits[0] if hits else None

    if c2 is None:
        c2 = derive(c1, "C1", "C2")
    if c3 is None:
        c3 = derive(c1, "C1", "C3")
    missing = [name for name, p in (("C2", c2), ("C3", c3)) if p is None or not Path(p).exists()]
    if missing:
        raise DptError(f"无法推导/找到 {', '.join(missing)} 的 CSV，请显式传 -c2 / -c3")
    return {CH_VGS: Path(c1), CH_ID: Path(c2), CH_VDS: Path(c3)}


def main(argv: list[str] | None = None) -> int:
    global TEST_TITLE, DEVICE_NAME
    # Windows 控制台默认是 GBK，直接打印 µ/² 等字符会报 UnicodeEncodeError。
    # 统一改成 UTF-8；重定向到文件或管道时也能正常工作。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = build_arg_parser()
    args = parser.parse_args(argv)
    cfg = build_config(args)
    TEST_TITLE = args.title
    DEVICE_NAME = args.device

    try:
        paths = resolve_input_paths(args, cfg)
        data = load_waveforms(paths, cfg)
        if cfg.verbose:
            print("输入文件：")
            for k, v in paths.items():
                print(f"  {k}: {v.resolve()}")
            print(f"  点数={len(data.t)}, dt={data.dt*1e9:.3f} ns")

        timing = manual_timing(args, data.t)
        if timing is None:
            timing, w = detect_pulses(data.t, data.vgs_raw, cfg)
            data.warnings.extend(w)
        else:
            print("[提示] 使用命令行手工指定的四个脉冲时刻，跳过自动边沿识别")

        i_comp, w = compensate_rogowski(data.t, data.id_raw, cfg)
        data.warnings.extend(w)
        if cfg.rogowski:
            data.id_raw = i_comp

        metrics, ctx, levels, warnings = analyze(data, timing, cfg)
        print_report(metrics, timing, data, cfg, paths, warnings)
        print_markdown(metrics)

        if cfg.export_csv is not None:
            export_processed_csv(cfg.export_csv, data, timing, levels, metrics)
        if cfg.export_metrics is not None:
            export_metrics_csv(cfg.export_metrics, metrics)
        if cfg.plot:
            plot_analysis(data, timing, levels, metrics, ctx, cfg)
        return 0
    except DptError as exc:
        print(f"\n[错误] {exc}\n", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
