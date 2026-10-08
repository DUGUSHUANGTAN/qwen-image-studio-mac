# Qwen Image Studio — Mac 版

本地 Qwen-Image-2.1 生图与多图编辑工具，Mac 原生应用。包豪斯玻璃风格界面，支持中英文、浅色/深色、多会话、参考图、渲染队列、图库、透明背景与 ComfyUI 实时进度。

渲染全部通过本地 [ComfyUI](https://github.com/comfyanonymous/ComfyUI) 完成，因此可以使用 diffusers 管线加载不了的量化权重。

> 本项目基于 [janishar/qwen-image-2.1-studio](https://github.com/janishar/qwen-image-2.1-studio)（MIT）二开，保留了上游的许可与署名。改动集中在 macOS 发行版：原生 Swift 外壳、一键打包、参数质量保护和 MPS 兼容修复。详见[与上游的差异](#与上游的差异)。

## 安装

从 [Releases](https://github.com/DUGUSHUANGTAN/qwen-image-studio-mac/releases) 下载 `Qwen Image Studio.zip`，解压后把 `Qwen Image Studio.app` 拖进「应用程序」。

首次启动会在 `~/Qwen Image Studio/server-env/` 准备一个仅供界面服务使用的 Python 环境，需要联网下载 Pillow 与 websocket-client。**这个环境不是渲染环境** —— 渲染由你自己安装的 ComfyUI 承担。

## 配置

打开应用，点「⚙ 路径」，填写 ComfyUI：

- **安装目录**（如 `~/ComfyUI-Installs/ComfyUI`）—— Studio 会自动以无头模式拉起它，用完随应用退出。
- **运行中的 HTTP 地址**（如 `http://127.0.0.1:8188`）—— 直接复用，Studio 不会关闭它。

ComfyUI 需要能访问 Qwen-Image-2.1 的主模型、文本编码器与 VAE；编辑还需编辑模型。应用会读取 `/object_info` 自动挑选匹配的文件名。

## 使用

输入提示词点「生成」即文生图。**添加参考图会自动切到编辑模式**，可用 `@` 引用具体图片（转成 `<image1>`、`<image2>`）。成片区和图库里的图片支持右键删除、复用参数、作为新参考图。

## 图像编辑：默认参数与画质保护

这是本二改版投入最多的部分，请务必读完再调参。

**为什么强制 CPU VAE。** 在 Apple Silicon（MPS）上用 GPU 跑 VAE 编码参考图，会**静默**产出「浮雕 + 均匀噪点」的损坏画面——不报错，只是结果错。已定位到 VAE 编解码环节：不经过生成模型、仅做 encode→decode 的往返测试，在默认编辑尺寸 1376×768 下 PSNR 仅 9.2 dB，同参数改用 CPU VAE 恢复到约 44.0 dB。因此：

- Mac 自动启动 ComfyUI 时追加 `--cpu-vae`，**只有 VAE 跑 CPU，扩散模型仍用 GPU**。
- 复用已有服务时会检查其真实设备与启动参数；若目标在 MPS 上且未带 `--cpu-vae`，应用拒绝提交编辑任务，并在报错里告诉你如何修正。

这也是为什么应用会检查**你手动启动的** ComfyUI：如果绕过了应用直接开 ComfyUI，VAE 又跑在 GPU 上，画质就会坏掉，而没有任何报错。

**为什么默认 40 步。** 官方模型卡用 40 步，ComfyUI 模板用 25 步。25–39 步适合快速预览；应用会阻止低于 25 步的编辑，防止误套其他蒸馏模型的少步配方。

**为什么编辑画布限制在约 1 MP。** 官方编辑配方把参考图缩放到约 1 MP，画布也应保持在同一量级。文生图的 4 MP 画布是参考图条件分辨率的四倍，这正是「中心清晰、四周发糊」的成因。编辑模式下选比例时会按约 1 MP 像素预算换算，而不是套用文生图的 4 MP 尺寸表。自定义宽高时软件阻止超过 150 万像素——**这是本软件的质量保护策略，不是 Qwen 模型的能力上限**，建议先在 1 MP 完成编辑再放大。

> 以上阈值都是 Studio 的策略，不是模型的硬性限制。相关代码集中在 [`validate_edit_settings`](app/web/server.py) 与 [`ComfyBackend._safe_for_edit`](app/web/server.py)，改前请读注释。完整排查过程和实测数据见 **[docs/QUALITY-NOTES.md](docs/QUALITY-NOTES.md)**。

### 官方依据

- [Qwen-Image-2.1 模型卡（编辑示例为 40 步）](https://huggingface.co/Qwen/Qwen-Image-2.1)
- [ComfyUI 官方编辑模板](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_qwen_image_2_1_image_edit.json)
- [ComfyUI Qwen 2.1 编码节点（参考图缩放与首图画布）](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_qwen.py)
- [ComfyUI Qwen 2.1 模型实现（分段因果注意力）](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy/ldm/qwen_image21/model.py)

### 诊断范围与免责

MPS VAE 编码故障已在 ComfyUI 0.37.4 / PyTorch 2.13.0 / Apple M5 Pro 上复现。上游同类报告见 [ComfyUI #16433](https://github.com/Comfy-Org/ComfyUI/issues/16433)——这是用户复现报告，不是官方参数规范。

**本软件无法保证每条提示词都能得到预期编辑结果。** 换人、改姿势、保留指定内容这类指令尤其需要人工验收成图。CFG 固定为 1，负向提示词不提供额外引导；采样器、调度器与 denoise 不随自定义参数改变。

### 双图换人提示词示例

换人容易失败，原因是没交代清楚每张图的职责。有效的写法是明确分工：

> 以 `<image1>` 为编辑底图，保留它的画面布局、背景、人物姿势和服装。将其中人物的身份和面部特征替换为 `<image2>` 中的人物。`<image2>` 仅提供人物身份参考，不采用它的姿势、服装、背景和构图。输出编辑后的 `<image1>`。

实测对照：同一参考图与种子，简短写「把第一张的人换成第二张的人」会复现第二张的场景；明确角色分工后，才能保留第一张布局并替换上方人像。即便如此，人物相似度仍需逐张检查。

## 开发

```bash
bash app/run_dev.sh          # 开发服务 → http://127.0.0.1:8731
bash app/run_dev.sh stop     # 停止
QWEN_COMFYUI=~/ComfyUI bash app/run_dev.sh
```

前端无构建步骤，改完 `app/web/static/` 刷新浏览器即可。

自检与测试（无需 GPU、无需 ComfyUI）：

```bash
app/.venv/bin/python app/verify_params.py     # 校验每个参数确实落进了节点图
app/.venv/bin/python -m unittest discover -s tests -v
```

打包 `.app`（需 macOS + Swift 编译器 + Pillow）：

```bash
bash build/build_app.sh
```

产出 `dist/Qwen Image Studio.app` 与同名 zip。

## 项目结构

```
app/web/server.py          后端全部逻辑（纯标准库 + Pillow，单文件）
app/web/static/            前端三件套，无构建步骤
app/verify_params.py       参数落图自检脚本
app/run_dev.sh             开发启动脚本
build/                     Swift 外壳、图标、bootstrap、打包脚本
tests/                     回归测试
docs/QUALITY-NOTES.md      画质排查记录与实测数据
app/project/               上游 diffusers 管线（本发行版未引用，仅作溯源参考）
```

## 与上游的差异

上游是面向全平台的 HelmStudio + CLI 项目。本二改版重写为 macOS 专用发行版：

| | 上游 | 本项目 |
|---|---|---|
| 交付形态 | `uv sync` + CLI + helmstudio | 原生 `.app`，双击即用 |
| 渲染后端 | diffusers / PyTorch 管线 | 仅 ComfyUI（支持量化权重）|
| 依赖 | torch、transformers、diffusers… | Pillow、websocket-client |
| 编辑默认步数 | 25 | 40（对齐官方模型卡）|
| 编辑画布 | 4 MP 比例表 | 约 1 MP 像素预算 |
| MPS 支持 | 无专门处理 | 强制 CPU VAE，含静默损坏防护 |

另外补充了中英文界面、浅色/深色主题、会话管理、图库右键菜单、渲染队列可视化和渲染质量自检。

## 数据存放

会话、设置、参考图与成片都在 `~/Qwen Image Studio/`：`Input/` 是参考图、`Output/` 是成片、`store.json` 是索引。日志在同目录的 `logs/` 与 `bootstrap.log`。

`Input/` 和 `Output/` 就是存储本体——在 Finder 里删掉文件，下次启动应用会同步移除对应条目。

## 致谢与许可

- 上游：[janishar/qwen-image-2.1-studio](https://github.com/janishar/qwen-image-2.1-studio) — MIT License, © 2026 Janishar Ali
- Qwen-Image-2.1 模型：Alibaba
- ComfyUI：Comfy Org，GPL-3.0（本项目不包含 ComfyUI 代码，仅通过 HTTP 接口调用；使用者需自行安装并遵守其许可）

本项目 MIT 许可，见 [LICENSE](LICENSE)。