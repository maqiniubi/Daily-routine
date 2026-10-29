# 班级作息助手 · ClassBell

Windows 桌面班级作息时间管理工具。顶部半透明玻璃悬浮条 + 24 小时进度条 + 到点提醒 + 每周作息周期 + 课程表 +
**目标日期倒计时（悬浮条 / 桌面贴纸）+ 定时关机**，纯 Python 标准库（tkinter + ctypes）实现，
打包后为单文件 exe，目标机器**无需安装 Python 或任何依赖**。

- 作者：**永恒**
- 界面风格：Apple 风格深色界面（窗口 → 区块 → 卡片三层明度、统一 14dp 圆角、4pt 基线间距、
  字阶角色化、白色主操作 + 系统蓝选中态、缓动动效）；顶部悬浮条为**半透明玻璃质地**
  （整窗 86% 不透明度 + 真圆角区域裁剪 + 边缘高光，壁纸从条面与四角透出）
- 当前版本：`1.6.1`（修复主题切换两处缺陷：浅色切回深色时部分元素不还原；换色卡顿）
  v1.6.0 新增界面 / 悬浮条 UI 自定义：配色预设 + 锚点色微调 + 透明度，实时预览、即时生效
- 打包产物：`dist/ClassBell.exe`（约 13 MB，单文件，双击即用）
- 运行环境：Windows 7 SP1 及以上（x86 / x64 均可运行 32 位 exe）
- 关闭方式：**只能右键系统托盘图标 →「退出程序」**，界面上没有任何退出入口

---

## 一、运行方式

| 场景 | 操作 |
| --- | --- |
| 直接使用 | 双击 `dist/ClassBell.exe` |
| 从源码运行 | `python main.py`（需带 tkinter 的官方 Python 3.9+） |
| 重新打包 | 双击 `build.bat`，或执行下方命令 |

```bat
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ClassBell ^
    --icon assets\icon.ico --add-data "assets;assets" ^
    --workpath build --distpath dist --specpath build main.py
```

> `--add-data` 必须保留：托盘图标与赞赏二维码都在 `assets/` 里，运行期通过 `sys._MEIPASS` 定位。

**使用要点**

- 启动后屏幕最顶部出现悬浮条，全宽、置顶，覆盖在任何窗口之上（含全屏窗口）。
- 单击悬浮条右侧 `设置`，或双击悬浮条任意空白处，打开设置中心。
- **退出程序只有一条路**：右下角系统托盘图标 → 右键 → `退出程序（唯一关闭途径）` → 确认后退出。
  退出时静默保存数据，并用 watchdog 兜底：0.8 秒内仍未结束则强制终止进程。
- 托盘图标左键单击 = 打开设置中心；悬停可看到「当前状态 + 时间」。
- **关闭设置中心不会退出程序**：悬浮条继续按置顶规则常驻运行。需要开机自启时在「设置 → 开机自动启动」勾选。
- 托盘图标可能被 Win11 折叠进「隐藏的图标」溢出区，可在系统设置里把它拖到任务栏常显。

---

## 二、模块划分

```
ClassBell/
├─ main.py                  入口：单实例互斥、DPI 感知、全局异常兜底、启动主循环
├─ app/
│  ├─ config.py             应用常量、数据目录定位（便携模式 / %APPDATA%）、打包资源定位
│  ├─ theme.py              设计令牌：分层色板 + 玻璃叠色 glass() + 4pt 间距 P() + 圆角 R() + 字阶 T() + 缓动
│  ├─ win32util.py          Win32 能力：置顶下发、工具窗口、圆角区域裁剪、整窗 alpha、单实例、开机自启、DPI
│  ├─ models.py             数据模型与校验：Period / Schedule / Countdown / AppData / 默认数据
│  ├─ store.py              JSON 持久化：原子写入、.bak 备份、导入导出
│  ├─ scheduler.py          时间轴解析、当天状态、提醒引擎（去重/跨天重置）
│  ├─ power.py              定时关机：星期/时刻校验 + 排程状态机（只调 shutdown.exe，测试可注入假 runner）
│  ├─ palette.py            外观数据层：预设方案、颜色校验/清洗、透明度夹取、恢复出厂
│  ├─ tray.py               系统托盘：Shell_NotifyIconW 注册 + 原生右键菜单（ctypes 实现）
│  ├─ controller.py         控制器：串起数据、悬浮条、提醒、托盘、桌面贴纸、设置中心
│  └─ ui/
│     ├─ widgets.py         基础部件：RoundedBox / Button / TabBar / Switch / Badge(✦永恒) / 圆角几何 / 缓动
│     ├─ common.py          ttk 深色样式、滚动容器、表单对话框、确认框、深色下拉选择器
│     ├─ topbar.py          玻璃悬浮条：半透明 + 圆角裁剪 + 高光/内阴影 + 三段式状态 + 进度/时段条 + 置顶守护
│     ├─ timeaxis.py        非线性时间轴：压缩凌晨/大空档，把宽度让给活跃时段（TimeAxis）
│     ├─ appearance_tab.py  外观自定义页：配色预设、锚点色微调、透明度、实时预览画布
│     ├─ toast.py           非模态提醒气泡：堆叠、置顶、N 秒自动消失
│     ├─ countdown_tab.py   倒计时页：增删改查、悬浮条/桌面开关、底部统计
│     ├─ desktop_countdown.py 桌面倒计时贴纸：无边框半透明、可拖动、被最小化后自动恢复
│     ├─ sponsor.py         赞赏面板：微信 / 支付宝收款码
│     └─ main_window.py     设置中心：作息表 CRUD / 每周周期 / 课程表 / 倒计时 / 全局设置 / 外观
├─ assets/                  icon.ico(10 帧)、icon.png、sponsor_wechat.png、sponsor_alipay.png
├─ tests/                   自动化测试（test_core / test_axis / test_ui / test_crud / test_quit）
├─ tools/                   开发期工具：图标生成、玻璃对照实验、截图、exe 冒烟、托盘压测（不参与打包）
├─ build.bat                一键打包脚本
└─ dist/ClassBell.exe       打包产物
```

**分层原则**：`models → store → scheduler` 为纯数据层，不依赖 tkinter；`ui/*` 只负责渲染与交互；
`controller` 是唯一把数据变化广播给界面的地方（`topbar.refresh()` / `tab.refresh()` / `sync_desktop_countdown()`）。

---

## 三、数据 JSON 结构

默认路径：`%APPDATA%\ClassBell\config.json`（若 exe 同级存在 `portable.txt`，则改为 `.\data\config.json`）。

```jsonc
{
  "version": 1,
  "settings": {
    "reminders_enabled": true,     // 是否弹出到点提醒
    "reminder_seconds": 5,         // 气泡停留秒数（默认 5）
    "remind_period_end": true,     // 课程结束是否提醒「到下课时间了！」
    "show_24h_bar": true,          // 显示 24 小时进度条
    "show_slot_bar": true,         // 显示今日时段条
    "font_scale": 1.0,             // 悬浮条文字缩放 0.8 ~ 1.4
    "autostart": false,            // 开机自启（同时写入注册表 Run 项）
    "topmost_guard_ms": 1000,      // 置顶守护周期（毫秒，500 ~ 5000）
    "show_desktop_countdown": false, // 桌面贴纸总开关
    "desktop_pos": [1520, 200],    // 桌面贴纸位置（拖动后自动写回）
    "shutdown_enabled": false,     // 定时关机开关（默认关闭，必须显式打开）
    "shutdown_time": "22:30",      // 关机时刻（24 小时制，非法值自动退回 22:30）
    "shutdown_days": [0, 1, 2, 3, 4], // 生效星期：0=周一 … 6=周日
    "shutdown_notice_min": 1,      // 提前几分钟提醒并排程（1 ~ 30）
    "ui_theme": {                  // 设置中心界面配色（锚点色，缺失键自动补默认）
      "bg": "#0b0b0d", "card": "#1b1b20", "fg": "#f5f5f7",
      "line": "#2c2c33", "accent": "#0a84ff"
    },
    "bar_theme": {                 // 顶部悬浮条配色（bg/fg/line/accent 四锚点）
      "bg": "#0a0a0e", "fg": "#f5f5f7", "line": "#2c2c33", "accent": "#0a84ff"
    },
    "ui_alpha": 1.0,               // 设置中心不透明度（0.75 ~ 1.00）
    "bar_alpha": 0.86              // 悬浮条不透明度（0.55 ~ 1.00）
  },
  "schedules": [                   // 作息表集合：可有多张（基础作息 / 特殊作息）
    {
      "id": "base",
      "name": "基础作息",
      "periods": [                 // 时段列表，渲染时按 start 自动排序
        { "id": "p1a2b3c4d", "name": "第一节", "start": "08:00", "end": "08:45",
          "kind": "class" }        // kind: class（上课）/ break（课间）/ other（其它）
      ]
    }
  ],
  "week": {                        // 每周周期：星期 → 作息表 id
    "mon": "base", "tue": "base", "wed": "special_wed",
    "thu": "base", "fri": "base", "sat": "base", "sun": "base"
  },
  "courses": {                     // 课程表：星期 → { 时段 id: 课程名 }
    "mon": { "p1a2b3c4d": "数学" }
  },
  "countdowns": [                  // 目标日期倒计时
    {
      "id": "c1a2b3c4d",
      "name": "期末考试",
      "target": "2026-12-30",      // 也接受 "2026/12/30"、"2026-12-30 09:00"
      "show_in_bar": true,         // 显示在顶部悬浮条
      "show_desktop": true,        // 显示在桌面贴纸
      "pos": [80, 96]              // 预留：单个倒计时的位置
    }
  ]
}
```

设计要点：

1. **作息表与星期解耦**：「基础作息」「周三半天」各是一张表，`week` 决定每天用哪张，改一处即可全局生效。
2. **课程按 `period.id` 绑定**，而非行号：时段改名、调时间、调顺序都不会错位；删除时段时自动清理孤立课程。
3. **时长为 `HH:MM` 字符串**，便于手改 JSON；载入时统一校验（24 小时制、结束必须晚于开始）。
4. **倒计时按自然日计算**（`date` 相减），与具体时刻无关；`target` 非法或为空时视为「未设置日期」，不会崩。
5. 导入/导出用的就是这份结构，导出文件可直接手工编辑后再导回。

---

## 四、关键实现方案

### 0. 界面设计体系（v1.2.0 Apple 风格 → v1.3.0 玻璃拟态 → v1.4.0 可调留白）

设计令牌集中在 `theme.py`，UI 一律只用令牌，不写字面量：

| 维度 | 做法 |
| --- | --- |
| 视觉层级 | 三层明度：`window #0b0b0d` → `surface #131317` → `card #1b1b20` → 悬停 `#232329`。层级靠**明度差 + 圆角 + 留白**建立，不靠描边 |
| 间距 | 4pt 基线，`P(n) = S(n*4)`；卡片内部 12/16/20 三档，页面外边距 20/24 |
| 字体 | 优先 `Segoe UI Variable Text / Display`，回退 `Microsoft YaHei UI`；字阶 `display 28 / title 20 / headline 15 / body 13 / subhead 12 / caption 11`，用 `T(role)` 取 |
| 圆角 | 统一 14dp（弹窗 16dp、按钮 8dp、胶囊取半高），`R(px)` 过 DPI 缩放；Canvas `create_polygon(rounded_points(...))` 自绘 |
| 语义色 | 主操作 = 白色填充（深色下最「重」的按钮），选中/焦点 = 系统蓝 `#0a84ff`，危险 = `#ff453a`，成功 = `#30d158` |
| 动效 | 全部走 `after` 单链 + `ease_out` 缓动：按钮悬停 120ms、分段胶囊滑动 200ms、开关 180ms、气泡滑入 240ms / 淡出 160ms |

**自绘部件**（`app/ui/widgets.py`）：`RoundedBox`（圆角卡片，内容放 `.body`）、`Button`（primary/secondary/ghost/danger 四种）、
`TabBar`（胶囊分段导航，替换掉难深色化的 `ttk.Notebook`）、`Switch`（iOS 开关，替换 `Checkbutton`）。

两个必须记住的坑：

1. **圆角会被内容盖掉**：`RoundedBox` 的内容窗口必须内缩**至少一个圆角半径**，否则承载内容的 `Frame` 是直角的，
   会正好压在圆角上，卡片看起来还是方盒子。内部统一用 `self._pad = max(pad, R(radius))`。
2. **`tkinter.Misc._w` 是控件路径名**：任何部件都**不能**用 `self._w / self._h` 存尺寸，
   `super().__init__()` 会把它们覆盖成字符串，之后参与算术就是 `TypeError: unsupported operand type(s) for -: 'str' and 'float'`。

> 同类细节：多个动画可能叠在一起（连点开关、连续切页），所以每个带动画的部件都持有 `self._gen` 代数号，
> 新动画一起步旧 tick 立刻失效，避免两条动画互相覆盖把位置写花。

### 1. 顶部悬浮条（半透明玻璃 · 圆角 · 自适应高度 · 始终置顶）

整条是一块**浮在壁纸上的玻璃板**：左右各留 12dp、顶部留 8dp，四角 18dp 真圆角，壁纸从条面与四角透出。

- `root.overrideredirect(True)` 去掉标题栏与边框，`geometry(f"{屏宽-2×边距}x{内容高}+{边距}+{8dp}")`。
- **半透明**：`attributes("-alpha", 0.86)`（可在设置里用「玻璃通透度」在 0.60 ~ 1.00 间调）。
- **真圆角**：`SetWindowRgn(hwnd, CreateRoundRectRgn(...))` 做窗口区域裁剪。这是关键——
  `-alpha` 走 `SetLayeredWindowAttributes(LWA_ALPHA)`、`-transparentcolor` 走 `LWA_COLORKEY`，
  两者在 Win32 层**互斥**；只有窗口 region 的几何裁剪能和 layered 叠加，所以「半透明 + 圆角」只能这么组合。
- **玻璃感**：顶部 1px 渐变高光（中间亮两端淡，模拟光从上方打在玻璃边上）、底部 1px 内阴影、
  条内所有控件都叠一层**预混半透明白**（`theme.glass(base, amount)`）——Canvas 没有 RGBA，
  所有「白 8% / 12%」都先按 alpha 混成实色再画到半透明窗口上，两层透明叠出来的观感与真透明一致。
- **DWM acrylic 不用**：`SetWindowCompositionAttribute(ACCENT_ENABLE_ACRYLICBLURBEHIND)` 在
  layered 窗口上只会把窗口染黑、并不产生模糊（`tools/probe_glass.py` 做过 A/B/C 三组对照），
  与其引入一个不可控的分支，不如老实做 alpha + 光学暗示。
- **「✦ 永恒」标识**：右上角紧邻时钟的玻璃胶囊徽标（`widgets.Badge`，四角星 + 名称，悬停微亮、点击打开「关于」）；
  设置中心顶栏、设置页「关于」区、桌面贴纸、托盘提示里也各挂了一处。
- **高度自适应**：内容全部用 `pack` 自然布局，构建完成后取 `shell.winfo_reqheight()` 作为窗口高度；
  开关「24 小时进度条 / 今日时段条」或调整字号时重建布局并重新测量。
- **课程名称显示区**：正中那块「正在上课 · 数学 / 剩余 42:15」的区域高度可调（设置 → 课程名称区域高度，
  28~96dp，默认 56dp）。做法是给它一个固定高度并 `pack_propagate(False)`，再让两行文字在内部垂直居中；
  下限取「内容实际需要的高度 + 2px」，所以把文字缩放拉到 1.4 倍也不会裁掉半行。
- **置顶守护**：`-topmost` + `SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE)` 双保险，按
  `topmost_guard_ms`（默认 1 秒）循环下发，可覆盖被其它置顶窗口、全屏窗口抢 Z 序的情况；
  `WS_EX_TOOLWINDOW` 让悬浮条不出现在任务栏与 Alt+Tab，`SWP_NOACTIVATE` 保证不抢输入焦点。

### 2. 24 小时进度条（唯一进度位置 · 开机自动校准）

- 每 1000 ms 触发一次 `_tick()`，**每次都重新读取 `datetime.now()`**，不做累加计时，因此不存在漂移，
  开机/休眠唤醒/改系统时间后自然对齐，无需手动校准。
- 进度 = `(时*3600 + 分*60 + 秒) / 86400`，画布上只有**一个**白色进度端点（竖线 + 游标），
  左侧填充已过时段，下方标注整点刻度，端点上浮显示百分比。百分比永远是**时间比例**，
  与横坐标是否被压缩无关（1.4.3 起横坐标是非线性的，见下节）。

#### 今日时段条与时间轴对齐（v1.4.2）

时段条和 24 小时进度条**共用同一条时间轴**（`app/ui/timeaxis.py` 的 `TimeAxis` 实例来自同一个
`_time_axis()`，两条画布连坐标系都取自它），所以 09:50 的色块正好压在上面 09:50 刻度的下方。

- 时段条内画整点网格（6 点倍数更亮）：有课块的地方被盖住，只在空档里露出，
  视觉上把上下两条缝成一条轴；当前时刻的蓝色游标在两条上横坐标一致。
- **按字宽决定写不写**：`_fit_slot_text()` 用 `tkfont.measure` 量真实宽度，整名 → 逐字省略 → 留白。
  旧实现是「块宽 > 46dp 才写字」的固定像素阈值（150% 缩放下 = 69px），30 分钟的窄节永远轮不到写字，
  于是出现「最右边一个白块、里面空的」那种观感（实测 21:50-22:20 只有 57px，正好被刷掉）。
- 相邻块之间留 1px 缝，窄块也能看出边界；游标先画、文字后画，避免蓝线横穿正在上的那节课的名称。
- 画布宽度统一走 `_canvas_w()`：首帧还没布局时按「条宽 - 左右内边距」估算，
  不再退回整条宽度（那会把最右的块画出画布外，看起来像被切掉）。

#### 时间轴压缩：空白折叠、活跃时段展开（v1.4.3）

等距的 24 小时轴上，凌晨 0–6 点这类「没有作息数据」的空白要白占掉整条宽度的 1/4，
真正有课的 09:50–22:20 被挤在后半段。实测 1920 屏、150% 缩放下，一节 45 分钟只剩 57px，
课程名写不下、30 分钟的晚自习更会糊成一个空白的白块。

现在轴上只有两处允许「不等比例」，阈值全部集中在 `app/ui/timeaxis.py` 头部：

| 规则 | 阈值 | 效果（1920 屏） |
| --- | --- | --- |
| **活跃窗口** | 首个时段前 `PAD` = 10 分钟 ~ 末个时段后 10 分钟 | 窗口内 **1:1**，不缩放 |
| **窗口外空白** | 各压成整宽的 `EDGE_RATIO` = 4.5%，夹在 `EDGE_MIN` 22dp ~ `EDGE_MAX` 90dp | 6 小时凌晨 ≈ 75px（等距时 456px） |
| **窗口内大空档** | 前 `GAP_KEEP` = 45 分钟保留原比例，超出部分 × `GAP_RATE` = 0.35 | 4 小时午休 → 113 分钟的长度 |
| **短空档** | ≤ 45 分钟不动 | 课间仍按真实比例，相邻两节不会粘在一起 |
| **全天无时段** | — | 退化为等距，不替用户假设哪里活跃 |

几条不能破的约束：

- **时长即长度**：同一活跃窗口内，两节 45 分钟的课块等宽（测试断言 ≤2px），45 : 30 分钟 = 1.5。
  压缩只作用于「没有数据的地方」，有数据的地方一律真实比例。
- **顺序与端点**：映射单调不减，`to_x(00:00)` 精确贴左端、`to_x(24:00)` 精确贴右端。
- **压缩可见**：压缩区铺 45° 淡斜纹、进度条上再加一个 `//` 记号，明确「这段被折叠过」，
  不会被误读成时间错位（斜纹刻意不用实心暗底——同高度的暗块会冒充成一节课）。
- **刻度自适应**：整点标签按像素间距降采样（挤不下就跳过），0 点与 24 点尽量保留；
  不再固定画 00/06/12/18/24 五个点，压缩后 06:00 未必还在 1/4 处。
- **无缓存**：一次构建只有几十次浮点运算，用 `id(slots)` 做缓存键会踩对象 id 复用的坑。

### 3. 到点提醒（非模态 · 自动消失）

- `ReminderEngine` 每个 tick 扫描当天时间轴：
  - 时段开始 → 有课程则「到上数学课时间了！」，否则「到早读时间了！」；
  - `kind=class` 的时段结束 → 「到下课时间了！」。
- 触发条件为 `0 ≤ now - 节点 ≤ 5 秒`：既容忍定时器抖动，又保证**中途启动不会补报**几十条历史提醒；
  每个节点用 `(日期, 时段id, 阶段)` 去重，跨天自动清空。
- 气泡是独立的 `Toplevel`：`overrideredirect + topmost + WS_EX_NOACTIVATE`，不夺焦点、不进任务栏，
  右侧堆叠排布，默认 5 秒后自动销毁（时长可配），点击可立即关闭。

### 4. 每周周期 + 课程表自动切换

- `day_key(date)` 把 `date.weekday()` 映射为 `mon..sun`，再用 `week` 取当天作息表、用 `courses` 取当天课程，
  合成 `Slot` 时间轴供悬浮条与提醒共用 —— 跨零点或切换日期时下一次 tick 即自动切换，无需重启。

#### 小屏 / 高 DPI 下的滚动

- 「每周周期」「设置」两页由 `ScrollFrame`（自绘滚动容器）承载：内容放得下时滚动条自动隐藏，
  放不下时右侧出现 8px 深灰细条，支持**鼠标滚轮**、**拖动滑块**、**点击轨道跳转**。
- 窗口高度按屏幕可用高度自适应（`min(650dp, 屏高 - 悬浮条 - 70dp)`），最小高度同样随屏幕收缩，
  因此 1366×768、150% 缩放等场景下不会再出现「周日被裁掉」的情况。
- 切到「每周周期」页时，若内容超高会自动把**今天**那一行滚进视野。

#### 作息表增删改：一次改动 = 一次全量重建（v1.4.1）

左栏列表与右侧时段表是同一份数据的两个视图，**任何写入都必须同时重建两者**。改动走 `SchedulesTab._commit()`：

```python
def _commit(self, tip=""):
    self.ctl.save_data()                    # 落盘
    self.refresh()                          # 左栏列表 + 右侧表格（同一次重建）
    self.ctl.main_window_refresh_week()     # 周周期页的作息表名 / 摘要
    self.ctl.main_window_refresh_course()   # 课程表页按当天作息表列时段
    self.ctl.topbar.refresh()               # 悬浮条
```

两条硬约束：

1. **选中态按 id 对齐，绝不按行号。** 删除后行号会整体前移，用行号记选中会指到别人身上；
   `_reload_list()` 重建时按 `_current_id` 反查行号，`_on_pick()` 先判越界再取数据。
2. **重建列表期间屏蔽 `<<ListboxSelect>>`。** 重填会反复触发选中事件，不屏蔽就会边填边回调，
   出现「填到一半又被重填」的抖动（`_reloading` 标志位）。

新建对话框合并为一级：`名称` + `复制自`（默认=当前作息表，「空白」= 从零开始），
不再先弹「名称」再弹「模板」两级弹窗——第二级被忽略时用户会以为没建成功。

### 5. 倒计时（融合 CountDay 的核心能力）

参考 [CountDay](https://github.com/maqiniubi/CountDay) 的目标日计数需求，用 tkinter 重写、零新增依赖：

- **数据模型** `Countdown`：`target` 兼容 `YYYY-MM-DD` / `YYYY/MM/DD` / `YYYY-MM-DD HH:MM` 三种写法，
  统一取 `date` 做差，`days_left()` 返回自然日差额。
- **三套文案**：`phrase()` → 「还剩 11 天 / 就是今天 / 已过 3 天」（列表与弹窗）；
  `short()` → 「期末考试 11天」（悬浮条紧凑形式）。
- **悬浮条**：左侧日期后追加 `· 运动会 11天 · 期末考试 63天`，最多两个（`bar_countdowns(limit=2)`），
  按「未过期的、剩余天数最少」排序，过期项排到末尾。
- **倒计时页**：表格按目标日期升序（未填日期的沉底），列含名称/目标日期/剩余/悬浮条/桌面；
  双击或右键菜单可编辑、切换两处显示、删除；底部实时统计；没有数据时显示空态引导。
- **桌面贴纸** `desktop_countdown.py`：无边框 `Toplevel` + `-alpha 0.88`，大号数字 + 小号「天」底部对齐，
  宽度按 `winfo_reqwidth` 自适应；可拖动，松手即写回 `settings["desktop_pos"]`；
  双击进设置中心；右键可「隐藏桌面倒计时」；每 3 秒刷新一次（编辑后立刻同步，不必重开贴纸）。

### 6. 托盘图标与「唯一关闭途径」

- `app/tray.py` 直接调 `Shell_NotifyIconW` 注册图标，用 `RegisterClassW` + `CreateWindowExW(HWND_MESSAGE)`
  建一个纯消息窗口接回调；**所有 Win32 函数都显式声明 `restype/argtypes`**，否则 64 位下句柄会被截断成 `c_int`。
- 右键菜单用原生 `TrackPopupMenu`（`SetForegroundWindow` + `PostMessage(WM_NULL)` 的经典规避手法，
  否则点菜单外区域菜单不会消失）：打开设置中心 / 重新校准并置顶 / 显示·隐藏桌面倒计时 / 赞赏支持 / 退出程序。

#### 1.2.0 修掉的崩溃：点托盘菜单任意一项，进程直接消失

**现象**：只有 `--onefile --windowed` 打包出来的 exe 会崩，点菜单里任何一项都崩，
事件查看器里是 `0xC0000409`（`STATUS_STACK_BUFFER_OVERRUN`）、故障模块 `ucrtbase.dll`、WER 事件名 **BEX**。
源码运行、`pythonw`、`--onedir --windowed`、`--onefile --console` 都不复现。

**根因**：旧实现把「弹菜单」直接放在 Win32 的 `WNDPROC` 回调里跑，菜单返回后又在这个回调栈里执行
`root.after(0, callback)`。此时 Tk 正在派发 Windows 消息，`after` 等于在 Tcl 解释器的中间状态里重入，
`--onefile` 的 bootloader 让 CRT 的栈检查更严格，于是触发 `__fastfail`（`/GS` 栈保护失败）。
这类失败**不经过 SEH**，所以 `SetUnhandledExceptionFilter`、`faulthandler`、`sys.excepthook`、
stderr 重定向统统抓不到 —— 进程只是静默消失。

**修复**：窗口过程退化成「只记事件、立刻返回」——

```python
def _wndproc(self, hwnd, msg, wparam, lparam) -> int:
    if msg == WM_TRAYICON:
        event = lparam & 0xFFFF
        if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
            self._pending.append("open")       # 只入队
            return 0
        if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
            self._pending.append("menu")
            return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
```

菜单与回调全部交给 Tk 侧的 `after(40ms)` 轮询（`poll()`）在主循环里执行，并用 `_busy` 标志防重入；
`TrackPopupMenu` 之后补 `DestroyMenu`，避免每右键一次泄漏一个 `HMENU`。
复验方式：`python tools\stress_tray.py dist\ClassBell.exe 10` —— 连点 10 轮菜单全部存活。

> 顺带修掉两个同源问题：`TopBar._popup_menu` 里把 `recalibrate` 写成了 `_recalibrate`（`AttributeError`），
> 以及 `SettingsTab` 调用 `topbar._recalibrate()` 的同类笔误。

- 退出前先 `destroy()` 托盘图标，避免任务栏留下「幽灵图标」；再用 `root.quit()` + 0.8 秒
  `os._exit(0)` watchdog 兜底，保证「点了退出一定退得掉」。
- 界面侧已移除全部退出入口：悬浮条 ✕ 删除、悬浮条右键菜单不再有「退出程序」、设置中心 `×` 只做隐藏。

### 6.5 鼠标穿透（v1.4.0）

需求是「除了设置中心和赞赏面板，其它界面一律让鼠标穿过去」，实现只有一个要点：

```python
style = GetWindowLongW(hwnd, GWL_EXSTYLE)
SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER)
```

- `WS_EX_TRANSPARENT` 让窗口在**命中测试**阶段被跳过，`WindowFromPoint` 直接返回它下面的窗口。
  再补一个 `WS_EX_LAYERED`：分层窗口 + TRANSPARENT 是 Windows 上最经典也最稳的组合
  （悬浮条 / 气泡 / 贴纸本来就是 layered，加这个只是幂等）。
- **改完 exstyle 必须走一次 `SetWindowPos(SWP_FRAMECHANGED)`**，否则命中区域要等下一次移动/缩放才刷新。
- 作用范围：悬浮条、提醒气泡、桌面贴纸。设置中心（以及它弹出的表单、确认框）与赞赏面板**不设**这个位，
  否则连「关掉穿透」都点不到。
- 入口：设置 → 系统与交互 →「鼠标穿透」开关；托盘菜单也有「切换鼠标穿透」，
  因为穿透之后界面上点不动，托盘是唯一随时可达的入口。
- 实测（`tools/probe_clickthrough.py`）：关穿透时命中窗口的根祖先是悬浮条自己，
  开穿透时命中变成了底下的其它程序 —— 这条判据比读 exstyle 位更能说明问题。

副作用（设计取舍，不是缺陷）：开启后悬浮条的双击/右键菜单、贴纸拖动都不再生效，
要移动贴纸或调整参数，先从托盘进设置把穿透关掉。

### 6.6 定时关机（v1.5.0）

教室 / 宿舍最常见的诉求是「晚上到点自动关电脑」。实现刻意做得很薄：

- **只调用系统 `shutdown.exe`**，不自建定时器、不碰需要管理员权限的 API：
  - 排程 `shutdown /s /t <剩余秒数>`，撤销 `shutdown /a`（没有排程时只会返回 1116，无副作用）；
  - `subprocess` 一律带 `CREATE_NO_WINDOW`，否则 `--windowed` 打包后会闪一个黑框。
- 由悬浮条每秒的 tick 驱动 `ShutdownScheduler.tick()`；状态只有一个字段 `armed_at`（已排程的目标时刻），
  它是「是否已排程」的唯一真相。
- **排程条件（全部满足）**：开关打开 → 至少选中一个星期 → 今天是选中星期 →
  距目标时刻 ≤ `shutdown_notice_min`（默认 1 分钟）→ 且距目标时刻 ≥ `MIN_LEAD_SECONDS`（15 秒）。
  只剩十几秒就**放弃今天**，比突然黑屏礼貌得多。
- **到点不补关**：软件若是目标时刻之后才启动（或休眠唤醒），当天直接跳过，等下一次。
- 改时间 / 关开关 / 跨天 → 先 `/a` 撤旧排程，再按新配置重排。
- 提醒气泡带「取消关机」按钮：这类气泡会**单独关掉鼠标穿透**（普通提醒气泡仍然穿透），
  否则按钮点不到。点按钮 → `shutdown /a` → 气泡收起。托盘右键也有「取消定时关机」。
- **退出程序的第一件事是撤销排程**，否则会出现「软件关了、电脑还是关了」这种最难解释的现象。

安全默认值：开关默认**关闭**、星期默认只勾周一到周五、不提供「立即关机」按钮；
真实调用集中在 `power.run_shutdown()` 一处，测试全部注入假 runner
（`tests/test_power.py` 51 项，`test_ui` 里 3 项端到端断言也只打假命令，跑测试永远不会关机）。

### 6.7 界面与悬浮条 UI 自定义（v1.6.0）

设置中心新增「外观」页签，界面与悬浮条**各自独立**配色 + 透明度，改动即时生效。

- **锚点色模型**：用户只调 5 个界面色（背景/卡片/文字/边框/强调）和 4 个悬浮条色，
  其余全部派生色（surface、hover、fill、三级文字、网格线、内阴影……）由 `theme.apply_palette()`
  按锚点推导——所以「把卡片色设得比背景还暗」这类组合**根本产生不了**，不会把界面搞崩。
  深色与浅色主题用不同推导系数（浅色下百分比 ×1.7，否则白卡叠黑字看不出层次）。
- **6 套预设**：深色（默认）/ 浅色 / 午夜蓝 / 松林绿 / 暖砂 / 纯黑，成对切换，
  不会出现「界面浅色、悬浮条深色」的违和组合；改完任意色后不再匹配预设，按钮高亮自动取消。
- **实时预览**：右栏画布画的是**当前 theme 令牌**（壁纸 + 悬浮条 + 设置中心小样），
  不是另抄一份配色——预览不能比真界面更好看。预览按 1dp = 1 逻辑像素绘制后整组平移居中，
  等比拉伸会让圆角和字号一起放大，看着像「放大的截图」而不是「缩略图」。
- **即时生效链路**：任何一次取色 / 回车 / 调透明度 → 写 settings → `save_data()` 落盘
  → `apply_appearance()`（`palette.apply` 重算 theme 令牌 → 悬浮条就地换色 → 设置中心就地重着色）
  → 控件回填。设置中心**不销毁窗口**（正在被点击的控件不会凭空消失），
  悬浮条也**不整条重建**（见下节）。
- **输入容错**：色块点开系统取色器；hex 输入框接受 `#rgb` / `#rrggbb` / 无 `#` 写法，
  只在回车 / 失焦时校验，非法输入退回原值（边打字边纠正会一直跳字，与关机时间同一个坑）。
  手改 JSON 写了非法颜色 / 越界透明度，`models.py` 统一清洗回落，不会让界面画不出来。
- **恢复默认**：`palette.restore_defaults()` 只改四个外观字段，作息表 / 课程 / 倒计时数据不动。
- 不透明度区间：界面 0.75~1.00、悬浮条 0.55~1.00（悬浮条要透出壁纸，下限更低）。

#### 换肤映射：按「角色」翻译，而不是按「颜色」查表（v1.6.1）

就地换色的关键在 `theme.remap(color, kind, family)`：它不查「旧色 → 新色」的字典，
而是先确定这个旧色**扮演什么角色**，再取该角色在当前配色里的值。

- **为什么不能按颜色查表**：白色在浅色主题里同时是「卡片底色」（`CARD=#ffffff`）和
  「按钮上的白字」（`ON_ACCENT=#ffffff`）。一刀切按颜色映射，必然有一半恢复不对——
  症状正是「切回深色后白卡片还留在深色界面上」。旧实现把 `#ffffff/#000000` 整类排除，
  浅色卡片因此根本进不了映射表。
- **角色分家族**：`bg` 家族（背景 / 卡片 / 填充 / 描边 / 轨道）与 `fg` 家族（主 / 次 / 三级文字、
  强调色、强调色上的前景色）分开查；`family` 再区分界面色板与悬浮条色板。
  控件的 `bg` 只可能在 bg 家族里找角色，`fg` 只可能在 fg 家族里找——
  歧义从根上消失。
- **换肤账本**：每次 `apply_palette()` 记一份当前配色（保留最近 8 份）。
  `remap` 由新到旧在账本里找这个旧色的角色，再取该角色**当前**的值。
  连续切换多次也能把任意一轮的旧色还原回去（不是只支持「一轮往返」）。
- **字面量颜色不动**：壁纸渐变、开关小圆点这类不属于任何令牌的颜色，
  账本里查不到角色就原样返回——它们本来就不该跟着主题变。

验收方式：`tools/shot_restore.py` 做「深色 → 浅色 → 深色」往返，
设置中心**逐像素对比**（差异 0.000%），悬浮条比对画布图元的实际着色（167 个图元全部还原）。

#### 换肤还原的三个隐藏坑（v1.6.1）

前两个坑修完残留扫描是 0 了，但还剩一块颜色怎么都换不掉。逐层挖下去发现三处：

1. **换色只遍历子控件，不换「自己」**：`_restyle_tree(widget)` 从头到尾只处理
   `widget` 的**子**控件，唯独漏掉 `widget` 自己。而六个页签的容器
   （`SchedulesTab` / `WeekTab` / …）底色正是直接设在自己身上的——
   于是页签容器永远停在上一轮配色，浅色界面里留着一块深色底。
   现在拆出 `_restyle_one()` 先换自身再递归。
2. **补色逻辑提前 return**：切到欠账的页签时补色，可它先判断「这一页没欠账吗」，
   没欠账就直接 return——把兜底的容器底色修正一起跳过了。
   现在没欠账也单独修一次容器自身（代价：一个控件）。
3. **首帧初始化会抢用户的页签**：`after(80, select(0))` 是为了让胶囊高亮定位到第一页，
   但它是**无条件**执行的，用户在这 80 毫秒内点开的别的页签会被弹回第一页
   （连带让「切到作息表页补色」这条路径根本走不到）。
   现在只在用户没切过时才定位。

前两条保证了「所有元素完整还原」，第三条保证换色流程本身不被 UI 时序打断。

#### 换肤性能：一次切换从 480 ms 降到 155 ms（v1.6.1）

Tk 是立即模式渲染，换配色等于「几百个控件各改一次颜色 + 全窗口重绘」。
逐项定位后做了五件事：

| 措施 | 效果 |
| --- | --- |
| 悬浮条**就地换色**（`TopBar.restyle()`）替代整条销毁重建 | 142 ms → **7.6 ms** |
| 设置中心**只重着色当前可见页签**，其余切过去时再补 | 42 ms → **16 ms** |
| ttk 样式**按需刷新**：表格样式（Treeview）切到表格页再刷 | 省 **24 ms** |
| 时段条**文字宽度缓存**（`tkfont.measure` 一次近 1 ms，中文还要字形整形） | 18 ms → **2.4 ms** |
| 滚动容器**合并滚动区重算**（`after_idle` 去抖） | 省 **几十次**重算 |

另外两个容易踩的坑：

- `style.theme_use("clam")` 会把整个 ttk 主题重新套一遍，逼所有 ttk 控件重新派生并重排；
  换配色时只改颜色，这一步只在第一次做。
- `ttk` 的 Treeview 颜色只由**样式**驱动，控件自己的 `bg` 改不动它——
  表格样式必须刷，但只在表格页可见时刷。

**连续操作**（拖动透明度滑块）走「即时反馈 + 重活延后」：
只换 theme 令牌 + 重绘预览（十几毫秒），悬浮条换色 / 设置中心重着色 / ttk 样式刷新
合并成停手后的最后一次执行（`_schedule_apply` 的 160 ms 去抖）。

### 7. 赞赏面板

- 「❤ 赞赏支持」按钮放在设置中心顶部标题栏右侧（白底黑字，最显眼位置），托盘菜单里也有一项。
- 二维码为两张 320×320 PNG，`tk.PhotoImage`（Tk 原生只认 PNG/GIF）+ `subsample` 缩到约 216dp，
  高 DPI 下不模糊；图片放在 `assets/`，打包时用 `--add-data` 带进 `_MEIPASS`。
- 窗口顺序有讲究：`center()` → `transient` → `deiconify()` → `-topmost` → `lift()` → `set_dark_titlebar()`。
  `DwmSetWindowAttribute` 必须在窗口已 map 之后调用，否则标题栏仍是浅色。

### 8. 打包与兼容性

- 只用标准库：`tkinter`、`json`、`dataclasses`、`ctypes`、`winreg`，无第三方运行时依赖。
- `--onefile --windowed`：单文件、无控制台窗口；tkinter 与 tcl/tk 由 PyInstaller 自动收集。
- 数据写在 `%APPDATA%`，不依赖 exe 所在目录的写权限（放 Program Files 也能运行）。
- `main.py` 覆盖 `report_callback_exception`，异常写入 `%APPDATA%\ClassBell\error.log` 并弹框提示，避免静默退出。

---

## 五、测试

```bat
python tests\test_core.py    :: 55 项：模型校验 / 存取 / 周期调度 / 提醒触发 / 倒计时计算与排序 / 进度
python tests\test_axis.py    :: 28 项：时间轴压缩规则（端点/单调/窗口内 1:1/凌晨压缩/大空档折算/短空档保留/无数据等距/刻度降采样）
python tests\test_power.py   :: 51 项：定时关机（时间与星期校验、排程条件、太晚放弃、改配置先撤销、跨天重排、配置清洗）
python tests\test_ui.py      :: 55 项：悬浮条高度、状态文案、周切换、课程显示、滚动到底、倒计时页、桌面贴纸、气泡、压缩轴对齐、定时关机设置
python tests\test_crud.py    :: 27 项：作息表新建/复制/改名/删除后左栏与表格同步、删除后逐行点击不抛异常、时段增删
python tests\test_quit.py    :: 12 项：托盘唯一退出项、退出执行、确认框不被悬浮条遮挡（各起子进程实测）
python tests\test_appearance.py :: 110 项：外观自定义（颜色校验/预设匹配/透明度夹取/theme 令牌推导/配置清洗 +
                                     真实窗口：选预设→落盘→即时生效→手填 hex→非法退回→恢复默认不动数据）
                                     + 换肤回归：角色映射还原、浅→深与基准逐控件一致、页签容器自身底色跟随、
                                     悬浮条 167 个图元完全还原、切换耗时上限
```

> 跑测试前无需准备：每套测试都会把 `APPDATA` 指到临时目录，不会碰真实配置，更不会真的关机。

开发期工具（不参与打包）：

```bat
python tools\capture.py        :: 截全部界面到 shots\（悬浮条垫网格壁纸 / 五分页 / 气泡 / 贴纸 / 赞赏）
python tools\make_icon.py      :: 从作者原图生成多尺寸 assets\icon.ico（10 帧）+ icon.png
python tools\stress_tray.py    :: 托盘菜单连点 N 轮，确认不再崩（默认 8 轮）
python tools\check_sticker.py  :: 发 Win+D 后验证贴纸能自动恢复、位置不丢
python tools\check_exe.py      :: 启动 dist\ClassBell.exe 做进程级冒烟（悬浮条、首启配置）
python tools\probe_clickthrough.py :: 实测鼠标穿透：WindowFromPoint 是否跨过悬浮条落在下层窗口
python tools\probe_glass.py    :: 玻璃效果 A/B/C 对照（证明 Tk 上 DWM acrylic 不产生真模糊）
python tools\smoke_test.py     :: 源码级冒烟：起悬浮条 → 开设置 → 弹气泡 → 截图 → 退出
python tools\shot_crud.py      :: 作息表页验收截图：新建对话框 + 新建后左栏是否出现并选中新表
python tools\shot_axis.py      :: 把「24 小时条 + 时段条」画到普通窗口截图（带真实配置，验证刻度对齐）
python tools\shot_appearance.py :: 外观页验收截图：python tools\shot_appearance.py dark|light|midnight|bar
python tools\shot_restore.py   :: 换肤还原验收：深色→浅色→深色 往返，设置中心逐像素对比 + 悬浮条图元着色对比
python tools\diag_theme.py     :: 换肤诊断：残留色扫描 + 逐阶段耗时（定位卡顿热点用）
python tools\diag_tabbg.py     :: 页签容器底色专项诊断：打印每一步换色后各页签容器自己的 bg 取值
```

---

## 六、已知限制

1. 悬浮条占据桌面顶部约 120 逻辑像素（「课程名称区域高度」调到 96dp 时可到约 180），
   会覆盖最大化窗口的标题栏区域（这是「始终最顶层」的必然代价）。
   如需更矮，可在设置中关闭「今日时段条」、降低文字缩放，或把课程名称区域高度调小。
2. **鼠标穿透是「整窗让位」**：开启后悬浮条的双击/右键菜单、贴纸拖动都不再生效，
   要恢复交互请在托盘图标右键 →「切换鼠标穿透」，或进设置中心关掉。
3. **玻璃只有「半透明」，没有「实时模糊」**：tkinter 拿不到逐像素 alpha 的窗口，DWM 的 acrylic/Mica
   对 Tk 的 layered 窗口不生效（实测见 `tools/probe_glass.py`），所以条面透出的是**清晰**的壁纸而非磨砂。
   若壁纸纹理很花，读起来会略吵，把「玻璃通透度」调高（如 0.95）即可。
4. 单个时段的结束时间必须晚于开始时间，**跨零点的时段（如 22:00–01:00）不支持**，请拆成两条。
5. 提醒为纯文字气泡，未做声音提示；如需要可在 `controller._on_remind` 中调用 `winsound`。
6. **时间轴是非线性的**（v1.4.3 起）：凌晨与深夜空白被折叠，所以「横向距离」只在活跃时段内
   等于「真实时长」。看精确时间请读刻度标签，不要用尺子量块宽；被折叠的区段铺了斜纹、
   进度条上有 `//` 记号。若某天全天都没有时段，轴会退回等距。
7. **桌面贴纸是普通置底窗口，不是壁纸层**：Win11 的 WorkerW 结构与旧版不同，`SetParent` 挂到壁纸层
   在多台机器上会失败（`GetParent` 返回 0），因此改用「被最小化后 3 秒内自动恢复」的方案。
   按 `Win+D` 显示桌面时贴纸会出现；打开新的最大化窗口时它会正常被盖住。
8. 托盘图标可能被 Win11 收进溢出区（折叠面板），需在系统设置中手动设为常显；程序侧无法强制。
9. **定时关机会真的关机**：到点后未保存的文档由系统强制结束进程，救不回来。所以默认关闭、
   星期默认只勾工作日、提前 1 分钟弹带「取消关机」按钮的气泡。
10. 排程一旦下发就存在系统里：若绕开托盘「退出程序」直接强杀进程（任务管理器结束 ClassBell.exe），
    排程不会被撤销，到点仍会关机 —— 此时在命令行执行 `shutdown /a` 取消。
11. 若机器被组策略 / 还原卡禁用 `shutdown.exe`，排程会静默失败（设置页不会显示「已排程」），
    这种环境下定时关机用不了，属系统限制。
12. 32 位 exe 在 64 位 Windows 上可正常运行；若需 64 位版本，用 64 位 Python 重新执行 `build.bat` 即可。
13. 换配色时**只重着色当前可见的页签**，看不见的页签切过去时才补色；
    若在外观页改色后立刻切到别的页，可能看到极短暂的一帧旧配色（毫秒级）。
14. 自定义配色只要偏离任一预设（哪怕只差一个色），预设按钮就全部不高亮——这是「当前不等于任何预设」的
    正确提示，不是 bug；想回到成套方案点一下对应预设即可。

---

## 七、图标

应用图标由作者提供的原图（人像）生成，`tools/make_icon.py` 会：

1. 按固定框 `(230,135,710,615)` 做正方形裁切（框住头部，脸占画面约 60%）；
2. 提饱和 1.08 / 对比 1.06，再缩放到 512 作为母版；
3. 逐尺寸缩放，`≤48px` 追加一次 `UnsharpMask`（否则 16px 会糊成灰块）；
4. 手写 ICO 容器：10 帧（16/20/24/32/40/48/64/96/128/256），小尺寸用 32bpp DIB、
   256px 用 PNG 压缩——Pillow 自带的 ICO 写入器无法逐尺寸定制质量，只能自己拼。

图标出现在：exe 资源（`--icon`）、任务栏/标题栏（`root.iconbitmap(default=…)`）、
系统托盘（`LoadImageW` 读 `assets/icon.ico`，Windows 自选合适帧）。
