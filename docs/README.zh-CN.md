# Newton VLA Live Demo — 中文说明

> 英文主文档见 [`../README.md`](../README.md)。本文件覆盖架构、VLA 后端选择、
> 评测与可复现性,以及开发工作流。

一个在 **MacBook 上无需 GPU、无需云端**就能运行的 3 分钟具身 AI(Embodied AI)
课堂演示:NVIDIA Newton 物理引擎 + pygame 2D 界面 + Claude 作为视觉-语言-动作
(VLA)大脑。

---

## 三种交互模式

| 模式 | 说明 |
|---|---|
| **接球(BALL CATCH)** | 经典 MPC 弹道拦截,无 AI,实测 62–82% 接球率 |
| **对话控制(TALK TO ARM)** | 自然语言 → JSON 动作 → 机械臂程序(VLA,中英双语) |
| **手势(GESTURES)** | 挥手 / 指向 / 鞠躬 / 跳舞 |

## 混合 VLA 流水线(延迟解耦)

Claude 解析一句话需 2–10 秒,远超 60 fps 帧预算。解决办法:

1. **~1 ms 关键词预检**立即让机械臂开始动作(前台:廉价 + 确定性);
2. **Claude 在后台线程**(~9.4 s)refine,返回后作为"智能复核者"对齐结果;
3. **generation 计数器**防止过期慢线程覆盖更新指令。

---

## VLA 后端与模型选择

语言层(`demo_live/vla.py`)把**四个可互换后端**统一到同一动作 schema,并共享
同一个即时关键词兜底,因此演示永远不会在台上卡住:

| 后端 | 选择方式 | 说明 |
|---|---|---|
| `cli` | 默认 | `claude --print` 子进程。无需 API key、无需 Python 依赖。 |
| `api` | `--vla-backend api` + `ANTHROPIC_API_KEY`(`uv sync --extra api`) | Anthropic Python SDK,**强制工具调用(forced tool-use)**→ 保证结构化输出合法(无需正则解析),系统提示标记为可缓存。单次 HTTP 往返,相较启动 Node CLI 延迟更低。 |
| `keyword` | `--vla-backend keyword` | 纯离线确定性解析器。 |
| `learned` | `--vla-backend learned` | 可插拔的**学习型意图策略**(`policy.py`):内置确定性 mock + 可在 CPU 运行的零样本适配器;可自带 checkpoint。 |

```bash
# 选择模型(别名或完整 id)和/或后端
uv run python -m demo_live --industrial --vla-model haiku
uv run python -m demo_live --industrial --vla-backend api --vla-model opus

# 也可用环境变量(评测脚本同样识别)
NEWTON_VLA_BACKEND=api NEWTON_VLA_MODEL=sonnet uv run python -m demo_live
```

模型别名解析到当前 Claude 家族:`sonnet` → Sonnet 4.6,`haiku` → Haiku 4.5,
`opus` → Opus 4.8,也可直接传完整 model id。默认保持 `sonnet`——台上演示更看重速度。

### 学习型策略接口(`policy.py`)

`learned` 后端通过一个最小接口接入真正的学习型模型:

* `MockLearnedPolicy` —— 确定性参考实现(默认),无额外依赖即可完整测试整条接入路径;
* `TransformersZeroShotPolicy` —— 真正可在 MacBook CPU 上运行的零样本文本分类适配器,
  懒加载 `transformers`,缺失依赖时抛出 `PolicyUnavailable` 并给出安装提示;
* 若要接入真实的感知-动作 VLA(如 **SmolVLA**),只需实现同样的 `parse()` 契约,
  后端接线无需改动。

用 `vla.set_learned_policy(...)` 注入自定义策略。

---

## 可复现评测

`demo_live/eval.py` 用一个**中英双语黄金集**(覆盖每个动作)给任意后端打分,
低于阈值时返回非零退出码,因此可直接作为 CI 回归门禁:

```bash
uv run python -m demo_live.eval                 # 关键词解析器 → 100%
uv run python -m demo_live.eval --backend api --model haiku
uv run python -m demo_live.eval --json          # 机器可读输出
```

关键词后端必须在黄金集上保持 100%——任何让已排练命令掉队的改动都会让 CI 变红。

---

## 开发与质量门禁

```bash
make test        # 完整单元 + 集成测试
make eval        # VLA 黄金集准确率(关键词后端)
make lint        # ruff 检查
make typecheck   # mypy(纯 VLA / policy / eval 模块)
make fix         # ruff 自动修复 + 格式化
```

CI(`.github/workflows/tests.yml`)在 Python 3.10–3.13 矩阵上运行无 Newton 依赖的
测试 + 覆盖率门禁 + 评测门禁,并单独运行 `mypy` 与 `ruff` 任务。

| 门禁 | 命令 |
|---|---|
| 单元测试 | `python -m unittest`(矩阵 + 覆盖率 ≥ 85%) |
| 评测回归 | `python -m demo_live.eval` |
| 类型检查 | `mypy`(范围见 `pyproject.toml` 的 `[tool.mypy]`) |
| 代码风格 | `ruff check demo_live/` |

---

## 设计取舍(摘选)

* **球用 Python 解析积分**(非 XPBD):某些 Newton 版本会在首步把 `body_qd` 清零,
  因此球每帧按 `z(t) = z₀ + v_z·t − ½ g·t²` 解析驱动。
* **方块 Python 侧存储**:带质量的运动学瞬移会让 XPBD 失稳,`mass=0` 大跳变会出 NaN。
* **机械臂从 `body_q` 渲染**而非自定义 FK:保证精灵与物理一致。

更多见英文 README 的 *Design notes* 与 `docs/report.pdf`。

---

MIT 许可证。Built on a MacBook. No cloud. No GPU.
