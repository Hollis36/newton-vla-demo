-- Newton VLA Live Demo — Dock/Applications 启动器（可选）。
-- `make launcher` 会把本文件编译成「Newton VLA Demo.app」放在项目根目录，
-- 给你一个带图标、可拖进 Dock 的真·应用按钮。双击它 = 打开终端跑 launch.command。
-- .app 与 launch.command 同级，故用自身路径推出项目根，移动文件夹也不会失效。
on run
	set myPath to POSIX path of (path to me)
	set repoRoot to do shell script "dirname " & quoted form of myPath
	tell application "Terminal"
		activate
		do script "cd " & quoted form of repoRoot & " && ./launch.command"
	end tell
end run
