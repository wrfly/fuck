# fuck

命令报错之后敲 `fuck`，让 Claude 分析原因并给出修复命令，确认后直接在当前 shell 执行。

```
$ git psuh origin mian
git: 'psuh' is not a git command. See 'git --help'.
$ fuck
  拼写错误：psuh 应为 push，分支名 mian 应为 main。
➜ git push origin main
  [enter] run  [e] edit  [any other key] cancel
```

## 安装

```sh
pipx install git+https://github.com/wrfly/fuck   # 或 uv tool install / pip install --user
```

在 `~/.zshrc` 或 `~/.bashrc` 里加：

```sh
eval "$(command fuck --init zsh)"   # bash 用 --init bash
```

生成配置文件并填上 API key：

```sh
fuck --config          # 创建 ~/.config/fuck/config.toml（权限 600）并打印路径
$EDITOR "$(fuck --config)"
```

## 用法

- `fuck`：分析上一条命令
- `fuck 我想推到 dev 分支`：附带提示，告诉它你本来想干什么
- `fuck -y`：不确认直接执行（被标记为危险的命令仍然会询问）
- `fuck --dry-run`：只打印要发给模型的内容
- `fuck --config`：创建配置文件（已存在则不覆盖）并打印路径

## 工作原理

1. shell hook 记录上一条命令和退出码。
2. 获取报错输出：
   - 在 tmux 里：直接抓当前 pane 的屏幕内容，不重跑命令；
   - 不在 tmux 里：用 `$SHELL -ic` 重跑一遍（有超时），和 thefuck 一样。有副作用的命令请用 `--no-rerun`，或在配置里设 `rerun = false`。
3. 把命令、输出、退出码、系统、当前目录文件列表、最近历史发给 Claude，拿回结构化结果（解释 + 修复命令 + 是否危险）。
4. 确认后由 shell 函数 `eval` 执行，所以 `cd`、`export` 这类命令也能生效，并写入 shell 历史。

## 配置

配置文件在 `~/.config/fuck/config.toml`（设置了 `$XDG_CONFIG_HOME` 时用 `$XDG_CONFIG_HOME/fuck/config.toml`），除了 `api_key` 都可以省略。不读取环境变量（包括 `ANTHROPIC_API_KEY`、`ANTHROPIC_BASE_URL`），所有配置只看这个文件。

```toml
api_key = "sk-ant-..."                 # 必填
base_url = "https://api.anthropic.com" # API 地址或代理
model = "claude-opus-5-5"
effort = "low"                         # low / medium / high / xhigh / max，越高越慢越准
lang = "中文"                           # 解释用的语言，默认跟随 $LANG
rerun = true                           # 不在 tmux 时是否重跑命令抓输出
timeout = 10                           # 重跑的超时秒数
```
