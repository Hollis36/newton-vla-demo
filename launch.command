#!/usr/bin/env bash
# Newton VLA Live Demo — double-clickable launcher.
#
# Finder 里双击本文件即可启动（这就是「本地按钮」）。它弹出一个中文菜单让你挑
# 演示模式，跑的就是 Makefile 里那条 `uv run … python -m demo_live …` —— 没有
# 任何新依赖、不打包、不冻结二进制。演示中按 Esc 关闭画面即回到菜单换模式。
#
# 也可在终端直接 `./launch.command` 运行。环境变量 NEWTON 可覆盖 ../newton 路径，
# DRY_RUN=1 只打印将要执行的命令而不真正启动（自测用）。
set -uo pipefail

# 把工作目录切到「本脚本所在目录」= 项目根。Finder 双击时 CWD 是 $HOME，必须
# 自己解析，否则既找不到项目、也找不到旁边的 ../newton 克隆。
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(pwd)"
NEWTON="${NEWTON:-../newton}"

# 现场防呆：演示中误触 Ctrl-C 只打断当前 demo 子进程，不要杀掉本启动器 ——
# 控制权应回到菜单（正常退出请用 Esc 或菜单里的 q）。
trap ':' INT

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
dim()  { printf '\033[2m%s\033[0m\n'  "$1"; }
red()  { printf '\033[1;31m%s\033[0m\n' "$1"; }
grn()  { printf '\033[1;32m%s\033[0m\n' "$1"; }

# ---- 依赖自检：uv 必须在；缺 ../newton 克隆时当场询问是否克隆 ----
preflight() {
  if ! command -v uv >/dev/null 2>&1; then
    red "未找到 uv。请先安装："
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "装好后重新双击本启动器。"
    printf "按回车关闭…"; read -r _; exit 1
  fi
  if [ ! -f "$NEWTON/pyproject.toml" ]; then
    red "未找到 Newton 源码克隆：$NEWTON"
    echo "需要把它克隆到项目同级目录（$ROOT 的旁边）。"
    printf "现在克隆 newton-physics/newton？[y/N] "
    read -r ans
    case "$ans" in
      y|Y) git clone https://github.com/newton-physics/newton "$NEWTON" \
             || { red "克隆失败。"; printf "按回车关闭…"; read -r _; exit 1; } ;;
      *)   echo "没有 Newton 无法运行，退出。"; printf "按回车关闭…"; read -r _; exit 1 ;;
    esac
  fi
}

# ---- 启动某个模式：$1=中文标签，其余=传给 demo_live 的参数 ----
run() {
  local label="$1"; shift
  echo
  grn ">> 启动：$label"
  dim "   演示中按 Esc（或关闭窗口）即返回本菜单"
  local cmd=(uv run --extra demo --with "newton[sim] @ $NEWTON" python -m demo_live "$@")
  if [ "${DRY_RUN:-0}" = "1" ]; then
    printf 'DRY_RUN: %s\n' "${cmd[*]}"
    return 0
  fi
  "${cmd[@]}" || red "演示以错误退出（详见上方输出）"
  printf "\n按回车返回菜单…"; read -r _
}

menu() {
  clear
  bold "Newton VLA Live Demo"
  dim  "一台 MacBook 上的实时课堂级具身智能 —— 选择演示模式"
  echo
  echo "  1) 课堂演示          单臂 VLA：接球 + 打字/语音指令     ← 最简单"
  echo "  2) 工业双臂          双臂工作站"
  echo "  3) 双臂协作 ★        接力搭塔（旗舰·舞台安全）          ← 答辩推荐"
  echo "  4) 真实方块          工业 + 真实刚体（会真的倒/碰）"
  echo "  5) 物理实验          偏移塔失稳讲解（真实 XPBD 判倒）"
  echo "  6) 自动彩排          3 分钟脚本化全流程（免手动）"
  echo
  echo "  q) 退出"
  echo
  printf "请输入序号并回车: "
}

preflight
while true; do
  menu
  # 交互式终端里误按 Ctrl-D 只刷新菜单（用 q 退出）；非交互/管道输入到末尾则退出。
  read -r choice || { [ -t 0 ] && { echo; continue; } || break; }
  case "$choice" in
    1) run "课堂演示"        --fullscreen ;;
    2) run "工业双臂"        --fullscreen --industrial ;;
    3) run "双臂协作（旗舰）" --fullscreen --industrial --collab ;;
    4) run "真实方块"        --fullscreen --industrial --real-blocks ;;
    5) run "物理实验"        --fullscreen --experiment ;;
    6) run "自动彩排"        --fullscreen --industrial --scripted rehearsal ;;
    q|Q) echo "再见。"; break ;;
    "")  : ;;  # 直接回车 = 刷新菜单
    *)   red "无效选项：$choice"; sleep 1 ;;
  esac
done
